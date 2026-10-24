import csv
import io
import json
import tempfile
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from app_harness import make_app


class ApplicationRegressionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.app, self.ns = make_app(self.folder.name)
        self.client = self.app.test_client()

    def sign_in(self, role='staff'):
        self.client.set_cookie('session_token', 'approved')
        self.ns['get_user_info'].return_value = {'role': role, 'status': 'approved'}

    def test_control_and_record_endpoints_reject_anonymous_requests(self):
        for method, path in [
            ('POST', '/api/detect'), ('POST', '/api/detect-batch'), ('POST', '/api/detect-video'),
            ('GET', '/api/stats'), ('GET', '/api/history'), ('GET', '/api/training-results'),
            ('GET', '/api/forecast/growth-harvest'),
            ('POST', '/api/water-pump/on'), ('POST', '/api/water-pump/off'),
            ('POST', '/api/water-pump/run'), ('GET', '/api/water-pump/status'),
            ('GET', '/api/water-pump/auto'), ('POST', '/api/water-pump/auto'),
            ('GET', '/api/water-pump/schedules'), ('POST', '/api/water-pump/schedules'),
            ('DELETE', '/api/water-pump/schedules/example'), ('GET', '/api/sensors/all'),
            ('GET', '/api/sensors/soil-moisture/history'), ('POST', '/api/admin/trigger-weekly-report'),
        ]:
            with self.subTest(path=path, method=method):
                self.assertEqual(self.client.open(path, method=method).status_code, 401)
        self.ns['sensor_monitor'].run_water_pump_for_seconds.assert_not_called()

    def test_disabled_staff_cannot_reuse_a_session(self):
        self.sign_in()
        self.ns['get_user_info'].return_value = {'role': 'staff', 'status': 'inactive'}
        self.assertEqual(self.client.post('/api/water-pump/run').status_code, 403)

    def test_invalid_json_and_field_types_are_client_errors(self):
        for data in ([], None, {'email': 17}, {'password': None}):
            response = self.client.post('/api/login', data=json.dumps(data), content_type='application/json')
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post('/api/login', data='{', content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post('/api/login', data='text').status_code, 400)
        self.assertEqual(self.client.get('/api/stats?limit=-1').status_code, 400)

    def test_string_false_cannot_enable_automatic_watering(self):
        self.sign_in()
        response = self.client.post('/api/water-pump/auto', json={'enabled': 'false'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Path(self.ns['AUTO_PUMP_SETTINGS_FILE']).exists())

    def test_pump_duration_is_validated_before_hardware_access(self):
        self.sign_in()
        for duration in (-1, 0, 301, 'invalid'):
            self.assertEqual(self.client.post('/api/water-pump/run', json={'duration_seconds': duration}).status_code, 400)
        self.ns['sensor_monitor'].run_water_pump_for_seconds.assert_not_called()

    def test_missing_gpio_is_unavailable_instead_of_falsely_reported_off(self):
        self.sign_in()
        monitor = self.ns['sensor_monitor']
        monitor.get_water_pump_hardware_status.return_value = {
            'hardware_available': False, 'backend': None, 'hardware_message': 'Open the Raspberry Pi app.'}
        monitor.water_pump_device = None
        monitor.water_pump_state = True
        monitor.WATER_PUMP_PIN = 27
        monitor.WATER_PUMP_ACTIVE_LOW = False
        monitor.WATER_PUMP_BREAKER_PIN = None
        monitor.WATER_PUMP_BREAKER_REQUIRED = False
        monitor.water_pump_rearm_required = False
        monitor.is_water_pump_breaker_on.return_value = False
        with patch.dict(os.environ, {'PUMP_REMOTE_URL': ''}):
            response = self.client.get('/api/water-pump/status')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['status'], 'unavailable')
        self.assertIsNone(data['logical_on'])
        monitor.set_water_pump.assert_not_called()

    def test_detection_survives_cloud_failure_with_complete_unique_records(self):
        self.sign_in()
        self.ns['detector'].detect.side_effect = lambda path: {'disease': 'Healthy', 'confidence': 0.9}
        self.ns['firestore_ready'].return_value = True
        self.ns['save_detection_result_firestore'] = Mock(side_effect=TimeoutError())
        self.ns['get_detection_results_firestore'] = Mock(return_value=[])
        responses = [self.client.post('/api/detect', data={'image': (io.BytesIO(b'image'), 'plant.jpg')})
                     for _ in range(2)]
        self.assertTrue(all(response.status_code == 200 for response in responses))
        results = list(Path(self.app.config['RESULTS_FOLDER']).glob('*_result.json'))
        self.assertEqual(len(results), 2)
        for path in results:
            record = json.loads(path.read_text())
            self.assertIn('media_path', record)
            self.assertEqual(record['user_id'], 'owner@example_com')
            self.assertFalse(record['cloud_saved'])
            with self.client.get('/uploads/' + record['image_path']) as media:
                self.assertEqual(media.status_code, 200)
        self.assertEqual(self.client.get('/api/stats').get_json()['total_detections'], 2)

    def test_batch_ignores_rejections_and_persists_successful_results(self):
        self.sign_in()
        self.ns['detector'].detect.side_effect = [
            {'not_pineapple': True, 'error': 'Not a pineapple'}, {'disease': 'Healthy', 'confidence': 0.8}]
        response = self.client.post('/api/detect-batch', data={
            'files': [(io.BytesIO(b'a'), 'a.jpg'), (io.BytesIO(b'b'), 'b.jpg')]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['batch_count'], 1)
        self.assertEqual(response.get_json()['error_count'], 1)
        self.assertEqual(len(list(Path(self.app.config['RESULTS_FOLDER']).glob('*.json'))), 1)

    def test_failed_detection_is_not_saved_or_counted(self):
        self.sign_in()
        self.ns['detector'].detect.return_value = {'error': 'Unreadable image'}
        response = self.client.post('/api/detect', data={'image': (io.BytesIO(b'bad'), 'bad.jpg')})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(list(Path(self.app.config['RESULTS_FOLDER']).glob('*.json')), [])

    def test_staff_cannot_see_another_users_local_results_or_media(self):
        self.sign_in()
        record = {'record_id': 'other', 'disease': 'Healthy', 'image_path': 'private.jpg',
                  'timestamp': datetime.now().isoformat(), 'user_id': 'someone_else'}
        self.ns['save_local_result'](self.app.config['RESULTS_FOLDER'], record)
        (Path(self.app.config['UPLOAD_FOLDER']) / 'private.jpg').write_bytes(b'image')
        self.assertEqual(self.client.get('/api/stats').get_json()['total_detections'], 0)
        self.assertEqual(self.client.get('/api/history').get_json()['results'], [])
        self.assertEqual(self.client.get('/uploads/private.jpg').status_code, 404)

    def test_sensor_csv_reads_sensor_records_and_preserves_zero(self):
        self.ns['get_sensor_data_firestore'] = Mock(return_value=[{
            'sensor_type': 'soil_moisture', 'timestamp': '2026-10-23T10:00:00',
            'data': {'value': 0, 'unit': '%'}}])
        text = self.ns['generate_csv_report'](user_id='owner', filters={'scope': 'sensors'})
        rows = list(csv.reader(io.StringIO(text)))
        self.assertEqual(rows[1][2:5], ['soil_moisture', '0', '%'])
        self.ns['get_sensor_data_firestore'].assert_called_once()

    def test_healthy_detections_do_not_raise_disease_spread_risk(self):
        healthy = [{'disease': 'Healthy', 'timestamp': datetime.now().isoformat()} for _ in range(10)]
        result = self.ns['calculate_disease_spread_risk'](healthy)
        self.assertEqual(result['risk_level'], 'low')
        self.assertEqual(result['recent_detection_count'], 0)

    def test_missing_weather_readings_are_not_internal_server_errors(self):
        self.sign_in()
        self.ns['sensor_monitor'].get_readings.return_value = []
        response = self.client.get('/api/weather-recommendations')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()['available'])

    def test_weather_accepts_nested_live_sensor_values(self):
        self.sign_in()
        self.ns['sensor_monitor'].get_readings.return_value = [{
            'sensor_live': True, 'temperature': {'value': 26}, 'humidity': {'value': 75}}]
        response = self.client.get('/api/weather-recommendations')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['current_temperature'], 26)

    def test_history_page_no_longer_uses_a_missing_template(self):
        self.sign_in()
        self.assertEqual(self.client.get('/training-results').status_code, 200)

    def test_video_sampling_is_bounded_handles_zero_fps_and_releases_resources(self):
        capture = Mock()
        capture.isOpened.return_value = True
        capture.get.side_effect = lambda prop: 19 if prop == self.ns['cv2'].CAP_PROP_FRAME_COUNT else 0
        capture.read.return_value = True, np.zeros((2, 2, 3), dtype=np.uint8)
        self.ns['detector'].detect.return_value = {'disease': 'Healthy', 'confidence': 0.8}
        with patch.object(self.ns['cv2'], 'VideoCapture', return_value=capture):
            result = self.ns['process_video_for_detection']('test.mp4', max_frames=10)
        self.assertEqual(result['frame_count'], 10)
        self.assertTrue(all(row['frame_timestamp'] is None for row in result['frame_results']))
        capture.release.assert_called_once()

    def test_daily_schedule_does_not_inherit_weekly_day_filter(self):
        self.ns['scheduler'] = Mock()
        self.ns['_register_water_pump_schedule']({
            'id': 'test', 'enabled': True, 'schedule_type': 'daily',
            'time': '06:00', 'days_of_week': ['mon']})
        self.assertNotIn('day_of_week', self.ns['scheduler'].add_job.call_args.kwargs)

    def test_sensor_get_is_read_only_and_remote_posts_require_a_token(self):
        with patch.dict(os.environ, {'SENSOR_INGEST_TOKEN': ''}):
            self.assertEqual(self.client.get('/save_sensor').status_code, 200)
            self.ns['sensor_monitor'].save_reading.assert_not_called()
            response = self.client.post('/save_sensor', json={'zones': []},
                                        environ_overrides={'REMOTE_ADDR': '192.0.2.1'})
            self.assertEqual(response.status_code, 403)

    def test_sensor_state_is_derived_from_moisture_and_duplicate_zones_are_ignored(self):
        with patch.dict(os.environ, {'SENSOR_INGEST_TOKEN': ''}):
            response = self.client.post('/save_sensor', json={'zones': [
                {'zone': 1, 'moisture': 20, 'raw': 700, 'status': 'WET'},
                {'zone': 1, 'moisture': 90, 'raw': 200, 'status': 'WET'}]})
        # Local save is successful, with the existing 503 cloud-unavailable signal.
        self.assertEqual(response.status_code, 503)
        self.assertEqual(len(response.get_json()['zones']), 1)
        self.assertEqual(response.get_json()['zones'][0]['state'], 'DRY')

    def test_date_filter_excludes_invalid_timestamps_and_next_days_midnight(self):
        filters = self.ns['_normalize_report_filters'](end_date='2026-10-23')
        rows = [{'timestamp': 'bad'}, {'timestamp': '2026-10-24T00:00:00'},
                {'timestamp': '20261023_235959'}]
        selected = self.ns['_filter_detection_results'](rows, filters)
        self.assertEqual(selected, [rows[-1]])

    def test_notification_cannot_be_changed_by_a_different_owner(self):
        self.ns['firestore_ready'].return_value = True
        reference = self.ns['firestore_db'].collection.return_value.document.return_value
        reference.get.return_value.exists = True
        reference.get.return_value.to_dict.return_value = {'user_id': 'other'}
        self.assertFalse(self.ns['mark_notification_read_firestore']('notification', user_id='owner'))
        reference.update.assert_not_called()

    def test_scheduled_reports_do_not_invent_a_recipient_or_claim_failed_delivery(self):
        self.ns['send_report_email'] = Mock(return_value=False)
        with patch.dict(os.environ, {'REPORT_RECIPIENTS': ''}):
            self.assertFalse(self.ns['send_scheduled_reports']())
        self.ns['send_report_email'].assert_not_called()
        self.ns['generate_csv_report'] = Mock(return_value='CSV')
        self.ns['REPORTLAB_AVAILABLE'] = False
        self.assertFalse(self.ns['send_scheduled_reports'](recipients='test@example.com'))


if __name__ == '__main__':
    unittest.main()
