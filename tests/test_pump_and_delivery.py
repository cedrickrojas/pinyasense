import ast
import io
import tempfile
import json
import threading
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Optional
from unittest.mock import Mock, patch

from core import email_service
from core.json_storage import write_json_atomic


class PumpAndDeliveryTests(unittest.TestCase):
    def hardware_status(self, gpio=False, gpiozero=False, device=None):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'core/sensor_monitor.py').read_text(encoding='utf-8-sig'))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'SensorMonitor')
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'get_water_pump_hardware_status')
        namespace = {'Dict': Dict, 'os': SimpleNamespace(name='nt'),
                     'GPIO_AVAILABLE': gpio, 'GPIOZERO_AVAILABLE': gpiozero, 'Device': device}
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'pump_hardware', 'exec'), namespace)
        return namespace['get_water_pump_hardware_status'](None)

    def test_windows_without_gpio_reports_where_to_control_the_real_pump(self):
        status = self.hardware_status()
        self.assertFalse(status['hardware_available'])
        self.assertIn('PUMP_REMOTE_URL', status['hardware_message'])

    def test_installed_gpiozero_requires_a_working_pin_factory(self):
        device = Mock()
        device.ensure_pin_factory.side_effect = PermissionError('gpiochip access denied')
        status = self.hardware_status(gpiozero=True, device=device)
        self.assertFalse(status['hardware_available'])
        self.assertIn('gpiochip access denied', status['hardware_message'])

    def test_working_gpio_backend_is_available_without_claiming_a_relay(self):
        device = Mock()
        self.assertTrue(self.hardware_status(gpiozero=True, device=device)['hardware_available'])
        device.ensure_pin_factory.assert_called_once_with()
        self.assertTrue(self.hardware_status(gpio=True)['hardware_available'])

    def test_mock_factory_cannot_report_physical_pump_access(self):
        factory = type('MockFactory', (), {'__module__': 'gpiozero.pins.mock'})()
        device = SimpleNamespace(ensure_pin_factory=Mock(), pin_factory=factory)
        self.assertFalse(self.hardware_status(gpiozero=True, device=device)['hardware_available'])

    def pump(self):
        # Load just the timed-run method; importing SensorMonitor initializes GPIO.
        path = Path(__file__).resolve().parents[1] / 'core/sensor_monitor.py'
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'SensorMonitor')
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'run_water_pump_for_seconds')
        namespace = {'Optional': Optional, 'Dict': Dict, 'datetime': datetime,
                     'time': SimpleNamespace(sleep=Mock())}
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'pump_method', 'exec'), namespace)
        pump = SimpleNamespace(WATER_PUMP_DEFAULT_DURATION=5, WATER_PUMP_MAX_DURATION=300, WATER_PUMP_PIN=27,
                               WATER_PUMP_BREAKER_PIN=None, water_pump_rearm_required=False,
                               _pump_run_lock=threading.Lock(),
                               water_pump_on=Mock(return_value={'status': 'on'}),
                               water_pump_off=Mock(return_value={'status': 'off'}))
        return pump, namespace

    def test_pump_stops_on_interruption_and_releases_the_run_lock(self):
        pump, ns = self.pump()
        ns['time'].sleep.side_effect = RuntimeError('interrupted')
        with self.assertRaises(RuntimeError):
            ns['run_water_pump_for_seconds'](pump, 2)
        pump.water_pump_off.assert_called_once()
        self.assertFalse(pump._pump_run_lock.locked())

    def test_overlapping_runs_do_not_start_the_pump_twice(self):
        pump, ns = self.pump()
        pump._pump_run_lock.acquire()
        result = ns['run_water_pump_for_seconds'](pump, 2)
        self.assertIn('error', result)
        pump.water_pump_on.assert_not_called()

    def test_stop_failure_is_not_reported_as_a_completed_watering(self):
        pump, ns = self.pump()
        pump.water_pump_off.return_value = {'error': 'Cannot stop device'}
        result = ns['run_water_pump_for_seconds'](pump, 2)
        self.assertEqual(result['status'], 'error')
        self.assertIn('error', result)

    def test_unconfigured_email_is_not_reported_as_sent_and_does_not_log_reset_codes(self):
        configuration = {'server': None, 'username': None, 'password': None}
        with patch.object(email_service, 'get_email_config', return_value=configuration), \
             patch.object(email_service.smtplib, 'SMTP') as smtp, redirect_stdout(io.StringIO()) as output:
            self.assertFalse(email_service.send_reset_code_email('test@example.com', 'PRIVATECODE'))
            self.assertFalse(email_service.send_welcome_email('test@example.com', 'Test'))
            self.assertFalse(email_service.send_report_email('test@example.com', 'Subject', 'Body'))
        smtp.assert_not_called()
        self.assertNotIn('PRIVATECODE', output.getvalue())

    def test_new_sensor_reading_does_not_discard_older_samples_after_one_thousand(self):
        path = Path(__file__).resolve().parents[1] / 'core/sensor_monitor.py'
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'SensorMonitor')
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'save_reading')
        import os
        namespace = {'Dict': Dict, 'datetime': datetime, 'os': os, 'json': json,
                     'write_json_atomic': write_json_atomic}
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'sensor_append', 'exec'), namespace)
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / f"soil_moisture_{datetime.now().strftime('%Y%m%d')}.json"
            original = [{'value': index} for index in range(1200)]
            write_json_atomic(filename, original)
            monitor = SimpleNamespace(data_folder=directory, _reading_lock=threading.RLock())
            namespace['save_reading'](monitor, 'soil_moisture', {'value': 45})
            rows = json.loads(filename.read_text())
            self.assertEqual(rows[:-1], original)
            self.assertEqual(len(rows), 1201)


if __name__ == '__main__':
    unittest.main()
