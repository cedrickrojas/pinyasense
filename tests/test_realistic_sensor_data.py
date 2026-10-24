from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock
import json
import unittest
import tempfile
from pathlib import Path
from scripts.maintenance.realistic_sensor_data import generate_samples, prepare_updates, apply_updates


def fake_db(previous):
    existing = Mock(id='soil_history_20260917_zone1')
    existing.get.return_value = SimpleNamespace(exists=True, to_dict=lambda: previous, update_time='version')
    missing = Mock()
    missing.get.return_value = SimpleNamespace(exists=False)
    db = Mock(project='pinyasense')
    db.collection.return_value.document.side_effect = lambda key: existing if key.startswith('soil_history') else missing
    return db, existing


class RealisticSensorDataTests(unittest.TestCase):
    def test_overlapping_runs_produce_identical_samples_and_adc_conversion(self):
        full = list(generate_samples(date(2026, 9, 17), date(2026, 10, 11)))
        overlap = list(generate_samples(date(2026, 10, 1), date(2026, 10, 11)))
        assert overlap == [row for row in full if row[0] >= date(2026, 10, 1)]
        assert len(full) == 100
        for day, zone, data in full:
            assert data['zone'] == zone
            assert abs(data['value'] - (1023 - data['raw_value']) * 100 / 1023) <= 0.051
            expected = 'dry' if data['value'] <= 30 else 'moist' if data['value'] <= 70 else 'wet'
            assert data['status'] == expected
            assert data['state'] == expected.upper()
            assert 'data_source' not in data
        by_day = {}
        for day, zone, data in full:
            by_day.setdefault(day, []).append(data)
        assert all(len({row['timestamp'] for row in rows}) == 1 for rows in by_day.values())
        assert all(len({row['value'] for row in rows}) > 1 for rows in by_day.values())
        assert len({rows[0]['timestamp'][11:] for rows in by_day.values()}) > 20


    def test_calibration_and_date_validation(self):
        with self.assertRaises(ValueError):
            list(generate_samples(date(2026, 10, 2), date(2026, 10, 1)))
        with self.assertRaises(ValueError):
            list(generate_samples(date(2026, 10, 1), date(2026, 10, 1), adc_wet=1023))
        rows = list(generate_samples(date(2026, 10, 1), date(2026, 10, 1), adc_dry=850, adc_wet=320))
        for _, _, data in rows:
            assert 320 <= data['raw_value'] <= 850
            assert abs(data['value'] - (850 - data['raw_value']) * 100 / 530) <= 0.051




    def test_existing_ownership_and_source_metadata_are_preserved(self):
        previous = {'sensor_type': 'soil_moisture_zone1', 'user_id': 'owner',
                    'data': {'sensor_mode': 'arduino_analog', 'zone': 1, 'data_source': 'existing', 'extra': 17}}
        db, reference = fake_db(previous)
        sample = next(generate_samples(date(2026, 9, 17), date(2026, 9, 17)))
        updates, backups = prepare_updates(db, [sample])
        assert len(updates) == len(backups) == 1
        assert 'user_id' not in updates[0][1]
        assert 'data.data_source' not in updates[0][1]
        assert 'data.extra' not in updates[0][1]
        assert backups[0]['fields']['user_id'] == {'stringValue': 'owner'}
        assert updates[0][2] == 'version'
        db.batch.assert_not_called()


    def test_hardware_record_collision_aborts_before_writing(self):
        db, reference = fake_db({'sensor_type': 'soil_moisture_zone1', 'data': {'sensor_mode': 'digital_do'}})
        sample = next(generate_samples(date(2026, 9, 17), date(2026, 9, 17)))
        with self.assertRaisesRegex(ValueError, 'unexpected record'):
            prepare_updates(db, [sample])
        db.batch.assert_not_called()


    def test_legacy_daily_analog_shape_is_corrected_but_binary_is_rejected(self):
        day = date(2026, 9, 28)
        sample = next(generate_samples(day, day))
        previous = {'sensor_type': 'soil_moisture_zone1', 'data': {
            'sensor_mode': 'digital_do', 'unit': '%', 'raw_value': 698, 'zone': 1}}
        reference = Mock(id='daily_soil_moisture_20260928_zone1')
        reference.get.return_value = SimpleNamespace(exists=True, to_dict=lambda: previous, update_time='version')
        missing = Mock()
        missing.get.return_value = SimpleNamespace(exists=False)
        db = Mock()
        db.collection.return_value.document.side_effect = lambda key: reference if key.startswith('daily_') else missing
        updates, backups = prepare_updates(db, [sample])
        assert updates[0][1]['data.sensor_mode'] == 'arduino_analog'
        previous['data']['raw_value'] = 1
        with self.assertRaisesRegex(ValueError, 'unexpected record'):
            prepare_updates(db, [sample])

    def test_backup_is_written_before_atomic_commit(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.check_backup_before_commit(Path(temporary))

    def check_backup_before_commit(self, tmp_path):
        from datetime import datetime, timezone
        db = Mock(project='pinyasense')
        reference = Mock(id='soil_history_20260917_zone1')
        data = next(generate_samples(date(2026, 9, 17), date(2026, 9, 17)))[2]
        reference.get.return_value.to_dict.return_value = {'timestamp': data['timestamp'], 'data': data}
        fields = {f'data.{key}': value for key, value in data.items()}
        fields['timestamp'] = data['timestamp']
        version = datetime(2026, 10, 11, tzinfo=timezone.utc)
        backups = [{'document_id': reference.id, 'exists': True, 'fields': {}}]
        def check_backup(**kwargs):
            files = list(tmp_path.glob('*.json'))
            assert len(files) == 1
            assert json.loads(files[0].read_text())['documents'] == backups
        db.batch.return_value.commit.side_effect = check_backup
        apply_updates(db, [(reference, fields, version, data)], backups, tmp_path)
        assert db.batch.return_value.update.call_args.kwargs['option']._last_update_time == version
        db.batch.return_value.commit.assert_called_once_with(timeout=30, retry=None)


if __name__ == '__main__':
    unittest.main()
