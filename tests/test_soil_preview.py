import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from core.soil_preview import preview_zones, preview_history


class SoilPreviewTests(unittest.TestCase):
    def test_current_and_history_agree_and_keep_source_metadata(self):
        now = datetime(2026, 10, 23, 19, 37)
        zones = preview_zones(now)
        history = preview_history(48, now)
        self.assertEqual(preview_history(6, now), [
            row for row in history if row['timestamp'] >= (now - timedelta(hours=6)).isoformat()
        ])
        self.assertEqual(history[-1]['value'], round(sum(z['value'] for z in zones) / 4, 1))
        self.assertGreater(len({row['value'] for row in history}), 10)
        for row in zones + history:
            self.assertEqual(row['data_source'], 'simulated')
            self.assertFalse(row['sensor_live'])
            self.assertNotIn('gpio_pin', row)
            self.assertNotIn('raw_value', row)
            self.assertTrue(8 <= row['value'] <= 95)

    def test_refresh_and_midnight_are_continuous(self):
        before = datetime(2026, 10, 23, 23, 59, 55)
        self.assertEqual(preview_zones(before), preview_zones(before + timedelta(seconds=2)))
        after = before + timedelta(seconds=5)
        for old, new in zip(preview_zones(before), preview_zones(after)):
            self.assertLessEqual(abs(new['value'] - old['value']), 0.4)

    def test_five_second_samples_vary_smoothly_and_independently(self):
        start = datetime(2026, 10, 23, 19, 37)
        samples = [preview_zones(start + timedelta(seconds=i * 5)) for i in range(25)]
        for zone in range(4):
            values = [sample[zone]['value'] for sample in samples]
            self.assertGreaterEqual(len(set(values)), 5)
            steps = [round(b - a, 1) for a, b in zip(values, values[1:])]
            self.assertTrue(any(step > 0 for step in steps))
            self.assertTrue(any(step < 0 for step in steps))
            self.assertLessEqual(max(abs(step) for step in steps), 0.4)
        changes = [tuple(round(b['value'] - a['value'], 1) for a, b in zip(old, new))
                   for old, new in zip(samples, samples[1:])]
        self.assertTrue(any(len(set(change)) > 1 for change in changes))

    def test_history_uses_the_same_five_second_sample_and_aligned_intervals(self):
        now = datetime(2026, 10, 23, 19, 37, 23)
        zones = preview_zones(now)
        history = preview_history(1, now)
        self.assertEqual(history[-1]['timestamp'], zones[0]['timestamp'])
        self.assertEqual(datetime.fromisoformat(zones[0]['timestamp']).second, 20)
        for row in history:
            expected = preview_zones(datetime.fromisoformat(row['timestamp']))
            self.assertEqual(row['value'], round(sum(zone['value'] for zone in expected) / 4, 1))
        for row in history[:-1]:
            timestamp = datetime.fromisoformat(row['timestamp'])
            self.assertEqual(timestamp.minute % 15, 0)
            self.assertEqual(timestamp.second, 0)

    def test_area_profiles_can_show_different_states_at_the_same_time(self):
        zones = preview_zones(datetime(2026, 10, 23, 20))
        self.assertEqual({zone['status'] for zone in zones}, {'dry', 'moist', 'wet'})
        self.assertGreater(max(z['value'] for z in zones) - min(z['value'] for z in zones), 25)
        self.assertGreaterEqual(zones[0]['value'], 28)
        self.assertLessEqual(zones[0]['value'], 30)
        self.assertLessEqual(zones[3]['value'], 76)
        for zone in zones:
            expected = 'dry' if zone['value'] <= 30 else 'moist' if zone['value'] <= 70 else 'wet'
            self.assertEqual(zone['status'], expected)

    def test_area_status_is_not_permanently_assigned_to_a_zone(self):
        start = datetime(2026, 10, 17)
        samples = [preview_zones(start + timedelta(hours=hour)) for hour in range(7 * 24)]
        for zone in (0, 3):
            self.assertGreater(len({sample[zone]['status'] for sample in samples}), 1)
        # Distinct area conditions without keeping one zone very dry and another saturated.
        self.assertTrue(all(27 <= sample[0]['value'] <= 45 for sample in samples))
        self.assertTrue(all(63 <= sample[3]['value'] <= 78 for sample in samples))


class SoilDisplayRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Exercise real route functions without starting GPIO, models or jobs.
        import tempfile
        from types import SimpleNamespace
        from app_harness import make_app
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        flask_app, namespace = make_app(cls.directory.name)
        namespace.update(preview_zones=preview_zones, preview_history=preview_history)
        cls.application = SimpleNamespace(app=flask_app, **{
            name: namespace[name] for name in ('sensor_monitor', 'verify_session', 'get_user_info', '_is_recorded_arduino_soil_reading')
        })
        cls.namespace = namespace

    def setUp(self):
        self.monitor = Mock(SOIL_ZONE_WATER_POLICY='any')
        self.monitor.get_readings.return_value = []
        replacement = patch.dict(self.namespace, sensor_monitor=self.monitor,
                                 verify_session=Mock(return_value='test@example.com'),
                                 get_user_info=Mock(return_value={'role': 'staff', 'status': 'approved'}))
        replacement.start()
        self.addCleanup(replacement.stop)
        self.client = self.application.app.test_client()

    def test_disconnected_readings_use_display_fallback_without_writes(self):
        self.monitor.get_readings.return_value = [{'error': 'Disconnected', 'sensor_mode': 'digital_do'}]
        response = self.client.get('/api/sensors/soil-moisture/arduino-zones')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['source'], 'simulated')
        self.assertFalse(data['sensor_live'])
        self.assertEqual(len(data['zones']), 4)
        self.monitor.save_reading.assert_not_called()
        self.monitor.set_water_pump.assert_not_called()

    def test_recorded_arduino_values_take_priority(self):
        reading = {'value': 57, 'raw_value': 440, 'sensor_mode': 'arduino_analog',
                   'timestamp': datetime.now().isoformat(), 'state': 'MOIST'}
        self.monitor.get_readings.return_value = [reading]
        data = self.client.get('/api/sensors/soil-moisture/arduino-zones').get_json()
        self.assertEqual(data['source'], 'arduino_serial')
        self.assertTrue(data['sensor_live'])
        self.assertEqual([zone['value'] for zone in data['zones']], [57] * 4)

    def test_history_statistics_use_the_displayed_samples(self):
        response = self.client.get('/api/sensors/soil-moisture/history?hours=6')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        values = [row['value'] for row in data['readings']]
        self.assertEqual(data['source'], 'simulated')
        self.assertEqual(data['statistics']['min'], min(values))
        self.assertEqual(data['statistics']['max'], max(values))
        self.assertEqual(data['statistics']['average'], round(sum(values) / len(values), 1))
        self.monitor.save_reading.assert_not_called()

    def test_generated_or_invalid_values_cannot_be_classified_as_live(self):
        valid = {'value': 50, 'sensor_mode': 'arduino_analog'}
        is_recorded = self.application._is_recorded_arduino_soil_reading
        for value in (None, True, float('nan'), float('inf'), -1, 101):
            self.assertFalse(is_recorded(dict(valid, value=value)))
        self.assertFalse(is_recorded(dict(valid, data_source='simulated')))
        self.assertTrue(is_recorded(valid))
