import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.detection_records import detection_datetime
from core.disease_detector import PineappleDiseaseDetector
from core.time_series_forecaster import PineappleGrowthForecaster


class DetectionLogicTests(unittest.TestCase):
    def test_legacy_and_timezone_timestamps_are_parseable(self):
        for value in ('20261023_120001', '20261023_120001_123456',
                      '2026-10-23T12:00:01Z', datetime.now(timezone.utc)):
            self.assertIsNotNone(detection_datetime(value))
        self.assertIsNone(detection_datetime('invalid'))

    def test_model_labels_are_not_replaced_by_unrelated_disease_names(self):
        with patch.object(PineappleDiseaseDetector, 'load_model'), \
             patch.object(PineappleDiseaseDetector, 'load_metadata'), \
             patch.object(PineappleDiseaseDetector, 'load_scene_model'):
            detector = PineappleDiseaseDetector()
        for raw, expected in [('RootRot', 'Root Rot'), ('MealybugWilt', 'Mealybug Wilt'),
                              ('FruitFasciation', 'Fruit Fasciation Disorder'),
                              ('Heart_Rot_Disease', 'Heart Rot')]:
            result = SimpleNamespace(names={0: raw}, boxes=[SimpleNamespace(cls=[0], conf=[0.9])])
            detector.model = Mock()
            detector.model.predict.return_value = [result]
            disease, confidence, _ = detector.yolov8_detection('plant.jpg')
            self.assertEqual(disease, expected)
            self.assertAlmostEqual(confidence, 0.9)

    def test_yolo_checkpoint_does_not_require_yolov8_in_filename(self):
        detector = PineappleDiseaseDetector.__new__(PineappleDiseaseDetector)
        detector.model_path = '/test/models/best.pt'
        checkpoint = Mock()
        loader = Mock(return_value=checkpoint)
        with patch.dict(sys.modules, {'ultralytics': SimpleNamespace(YOLO=loader)}):
            detector.load_model()
        self.assertIs(detector.model, checkpoint)
        self.assertEqual(detector.model_type, 'yolov8')

    def test_forecast_uses_calibrated_arduino_percentage_and_rejects_bad_binary_values(self):
        forecaster = PineappleGrowthForecaster()
        self.assertEqual(forecaster._soil_row_to_percent({
            'sensor_mode': 'arduino_analog', 'value': 57, 'raw_value': 440}), 57)
        for raw in (True, 2, float('nan'), float('inf')):
            self.assertIsNone(forecaster._soil_row_to_percent({'sensor_mode': 'digital_do', 'raw_value': raw}))


if __name__ == '__main__':
    unittest.main()
