import io
import json
import os
import tempfile
import unittest
from functools import wraps
from unittest.mock import Mock, patch
from urllib.error import URLError

from flask import Flask, jsonify
from app_harness import make_app
from core.pump_remote import RemotePumpClient, create_pump_bridge

TOKEN = 'test-token-' * 5


class PumpRemoteTests(unittest.TestCase):
    def test_bridge_requires_secret_and_only_dispatches_listed_pump_views(self):
        app = Flask(__name__)
        called = Mock()

        def guarded(view):
            @wraps(view)
            def auth():
                return jsonify(error='Browser login required'), 401
            return auth

        @app.post('/api/water-pump/off', endpoint='water_pump_off')
        @guarded
        def off():
            called()
            return jsonify(status='off')

        app.register_blueprint(create_pump_bridge())
        client = app.test_client()
        with patch.dict(os.environ, {'PUMP_BRIDGE_TOKEN': TOKEN, 'PUMP_REMOTE_URL': ''}):
            self.assertEqual(client.post('/api/internal/pump/off').status_code, 401)
            self.assertEqual(client.post('/api/water-pump/off').status_code, 401)
            called.assert_not_called()
            response = client.post('/api/internal/pump/off', headers={'Authorization': f'Bearer {TOKEN}'})
            self.assertEqual(response.get_json(), {'status': 'off'})
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            called.assert_called_once()
            self.assertEqual(client.post('/api/internal/pump/delete-account', headers={
                'Authorization': f'Bearer {TOKEN}'}).status_code, 404)
        with patch.dict(os.environ, {'PUMP_BRIDGE_TOKEN': '', 'PUMP_REMOTE_URL': ''}):
            self.assertEqual(client.post('/api/internal/pump/off').status_code, 404)

    def test_bridge_cannot_forward_a_request_back_into_another_bridge(self):
        app = Flask(__name__)
        app.register_blueprint(create_pump_bridge())
        with patch.dict(os.environ, {'PUMP_BRIDGE_TOKEN': TOKEN, 'PUMP_REMOTE_URL': 'http://pi.local'}):
            response = app.test_client().post('/api/internal/pump/on', headers={'Authorization': f'Bearer {TOKEN}'})
        self.assertEqual(response.status_code, 404)

    def test_remote_calls_keep_token_out_of_url_and_forward_json_and_status(self):
        client = RemotePumpClient('http://pi.local:5001', TOKEN)
        response = io.BytesIO(b'{"status":"completed"}')
        response.status = 201
        client.opener = Mock()
        client.opener.open.return_value = response
        data, status = client.call('POST', 'run', {'duration_seconds': 2})
        self.assertEqual((data['status'], status), ('completed', 201))
        req = client.opener.open.call_args.args[0]
        self.assertEqual(json.loads(req.data), {'duration_seconds': 2})
        self.assertNotIn(TOKEN, req.full_url)
        self.assertEqual(req.get_header('Authorization'), f'Bearer {TOKEN}')
        self.assertGreater(client.opener.open.call_args.kwargs['timeout'], 2)

    def test_connection_failure_never_retries_a_pump_command(self):
        client = RemotePumpClient('http://pi.local', TOKEN)
        client.opener = Mock()
        client.opener.open.side_effect = URLError('offline')
        data, status = client.call('POST', 'on')
        self.assertEqual(status, 502)
        self.assertIn('error', data)
        client.opener.open.assert_called_once()

    def test_remote_control_still_requires_approved_local_staff_login(self):
        with tempfile.TemporaryDirectory() as directory:
            app, ns = make_app(directory)
            proxy = Mock(return_value=(json.dumps({'status': 'off'}), 200))
            ns['proxy_pump_request'] = proxy
            with patch.dict(os.environ, {'PUMP_REMOTE_URL': 'http://pi.local'}):
                client = app.test_client()
                self.assertEqual(client.post('/api/water-pump/on').status_code, 401)
                proxy.assert_not_called()
                client.set_cookie('session_token', 'approved')
                self.assertEqual(client.get('/api/water-pump/status').status_code, 200)
                proxy.assert_called_once()
                ns['sensor_monitor'].water_pump_on.assert_not_called()

    def test_on_without_json_still_sends_an_empty_object(self):
        client = RemotePumpClient('http://pi.local', TOKEN)
        response = io.BytesIO(b'{"status":"on"}')
        response.status = 200
        client.opener = Mock()
        client.opener.open.return_value = response
        client.call('POST', 'on')
        self.assertEqual(json.loads(client.opener.open.call_args.args[0].data), {})


if __name__ == '__main__':
    unittest.main()
