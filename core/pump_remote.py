"""Authenticated pump requests between the web host and the GPIO host."""
import hmac
import json
import os
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, quote
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

from flask import Blueprint, current_app, jsonify, request


ROUTES = {
    ('GET', 'status'): 'water_pump_status',
    ('POST', 'on'): 'water_pump_on',
    ('POST', 'off'): 'water_pump_off',
    ('POST', 'run'): 'water_pump_run',
    ('GET', 'auto'): 'water_pump_auto',
    ('POST', 'auto'): 'water_pump_auto',
    ('GET', 'schedules'): 'water_pump_schedules',
    ('POST', 'schedules'): 'water_pump_schedules',
    ('DELETE', 'schedules'): 'delete_water_pump_schedule',
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class RemotePumpClient:
    def __init__(self, url, token):
        parsed = urlsplit(url)
        if (parsed.scheme not in {'http', 'https'} or not parsed.hostname or
                parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError('PUMP_REMOTE_URL must be an HTTP(S) app URL.')
        if len(token) < 32:
            raise ValueError('PUMP_BRIDGE_TOKEN must contain at least 32 characters.')
        self.url = url.rstrip('/')
        self.token = token
        # LAN traffic must not inherit an unrelated system HTTP proxy.
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def call(self, method, action, payload=None, schedule_id=None):
        if (method, action) not in ROUTES or ((method == 'DELETE') != bool(schedule_id)):
            return {'error': 'Unknown pump operation.'}, 404
        suffix = f'/{quote(schedule_id, safe="")}' if schedule_id else ''
        url = f'{self.url}/api/internal/pump/{action}{suffix}'
        body = json.dumps(payload or {}).encode('utf-8') if method == 'POST' else None
        req = Request(url, data=body, method=method, headers={
            'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'})
        timeout = 10
        if action == 'run':
            duration = (payload or {}).get('duration_seconds', 5)
            try:
                timeout = max(10, min(310, int(duration or 5) + 10))
            except (TypeError, ValueError):
                return {'error': 'Invalid pump duration.'}, 400
        try:
            with self.opener.open(req, timeout=timeout) as response:
                data = json.load(response)
                if not isinstance(data, dict):
                    raise ValueError('Invalid controller response')
                return data, response.status
        except HTTPError as error:
            try:
                data = json.load(error)
            except (ValueError, OSError):
                data = {'error': 'Pump controller rejected the request.'}
            return data, error.code
        except (URLError, OSError, ValueError):
            return {'error': 'Cannot reach the pump controller. Check that the Pi is online and connected to the network.'}, 502


def proxy_pump_request():
    """Called only after the Windows web app has verified staff access."""
    url = os.getenv('PUMP_REMOTE_URL', '').strip()
    if not url or not request.path.startswith('/api/water-pump/'):
        return None
    parts = request.path.removeprefix('/api/water-pump/').split('/')
    if len(parts) > 2 or (len(parts) == 2 and parts[0] != 'schedules'):
        return jsonify({'error': 'Unknown pump operation.'}), 404
    try:
        client = RemotePumpClient(url, os.getenv('PUMP_BRIDGE_TOKEN', ''))
    except ValueError:
        return jsonify({'error': 'Remote pump connection is not configured correctly.'}), 503
    payload = request.get_json(silent=True) if request.method == 'POST' else None
    if parts[0] == 'run' and 'duration_seconds' in request.args:
        payload = dict(payload or {})
        payload.setdefault('duration_seconds', request.args['duration_seconds'])
    data, status = client.call(request.method, parts[0], payload,
                               schedule_id=parts[1] if len(parts) == 2 else None)
    return jsonify(data), status


def create_pump_bridge(monitor=None):
    """Expose only fixed pump operations, authenticated by a server-held token."""
    if monitor is not None:
        if not hasattr(monitor, '_pump_run_lock'):
            monitor._pump_run_lock = Lock()
        if not hasattr(monitor, 'WATER_PUMP_MAX_DURATION'):
            monitor.WATER_PUMP_MAX_DURATION = max(1, int(os.getenv('WATER_PUMP_MAX_DURATION_SECONDS', '300')))
    blueprint = Blueprint('pump_bridge', __name__)

    @blueprint.route('/api/internal/pump/<action>', methods=['GET', 'POST'])
    @blueprint.route('/api/internal/pump/schedules/<schedule_id>', methods=['DELETE'], defaults={'action': 'schedules'})
    def dispatch(action, schedule_id=None):
        expected = os.getenv('PUMP_BRIDGE_TOKEN', '')
        if len(expected) < 32 or os.getenv('PUMP_REMOTE_URL', '').strip():
            return jsonify({'error': 'Pump bridge is not enabled on this host.'}), 404
        supplied = request.headers.get('Authorization', '')
        if not hmac.compare_digest(supplied.encode(), f'Bearer {expected}'.encode()):
            return jsonify({'error': 'Unauthorized pump controller request.'}), 401
        endpoint = ROUTES.get((request.method, action))
        view = current_app.view_functions.get(endpoint) if endpoint else None
        if view is None:
            return jsonify({'error': 'Unknown pump operation.'}), 404
        # The token authenticates this device request in place of a browser session.
        # Only the fixed, explicitly listed pump views can be invoked here.
        view = getattr(view, '__wrapped__', view)
        response = current_app.make_response(view(schedule_id) if schedule_id else view())
        if action == 'status' and response.status_code == 200:
            monitor = view.__globals__.get('sensor_monitor')
            if monitor is not None:
                hardware = monitor.get_water_pump_hardware_status()
                data = response.get_json()
                data.update(hardware)
                if not hardware['hardware_available']:
                    data.update(status='unavailable', logical_on=None)
                response = jsonify(data)
        response.headers['Cache-Control'] = 'no-store'
        return response

    return blueprint
