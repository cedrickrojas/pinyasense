"""Offline checks for detection totals; no models, accounts, or cloud writes."""
import ast
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from flask import Flask, jsonify, request
from app_harness import make_app


ROOT = Path(__file__).resolve().parents[1]


class DetectionStatsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.app, self.namespace = make_app(self.directory.name)
        self.results = Path(self.app.config['RESULTS_FOLDER'])
        self.cloud = Mock(return_value=[])
        self.namespace.update({
            'verify_session': Mock(return_value='test-account'),
            'get_user_info': Mock(return_value={'role': 'admin'}),
            'get_current_firebase_user_id': Mock(return_value='staff-id'),
            'firestore_ready': Mock(return_value=True),
            'get_detection_results_firestore': self.cloud,
        })
        self.client = self.app.test_client()

    def save_results(self, count=15):
        for index in range(count):
            record = {
                'disease': 'Healthy' if index < 6 else 'Fruit Rot',
                'timestamp': f'2026-10-{index + 1:02}T10:00:00',
                'confidence': 0.9,
            }
            (self.results / f'{index:03}_result.json').write_text(json.dumps(record), encoding='utf-8')

    def stats(self):
        response = self.client.get('/api/stats')
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def test_empty_cloud_keeps_all_local_records_and_counts_beyond_recent_ten(self):
        self.save_results()
        before = {path.name: path.read_bytes() for path in self.results.iterdir()}
        stats = self.stats()
        self.assertEqual(stats['total_detections'], 15)
        self.assertEqual(stats['disease_count'], {'Healthy': 6, 'Fruit Rot': 9})
        self.assertEqual(len(stats['recent_detections']), 10)
        self.assertEqual(stats['recent_detections'][0]['timestamp'], '2026-10-15T10:00:00')
        self.assertEqual(stats['data_source'], 'local')
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.results.iterdir()})

    def test_cloud_timeout_falls_back_without_overwriting_results(self):
        self.save_results(2)
        self.cloud.side_effect = TimeoutError('cloud unavailable')
        self.assertEqual(self.stats()['total_detections'], 2)
        self.cloud.assert_called_once_with(user_id=None, limit=None, timeout=5)

    def test_cloud_results_use_one_query_and_preserve_staff_filter(self):
        self.save_results()
        self.namespace['get_user_info'].return_value = {'role': 'staff', 'status': 'approved'}
        self.cloud.return_value = [{'disease': 'Heart Rot', 'timestamp': '2026-10-20'}]
        stats = self.stats()
        self.assertEqual(stats['total_detections'], 1)
        self.assertEqual(stats['disease_count'], {'Heart Rot': 1})
        self.assertEqual(stats['data_source'], 'firestore')
        self.cloud.assert_called_once_with(user_id='staff-id', limit=None, timeout=5)

    def test_total_is_not_capped_at_one_thousand_recent_records(self):
        self.cloud.return_value = [{'disease': 'Healthy'} for _ in range(1005)]
        stats = self.stats()
        self.assertEqual(stats['total_detections'], 1005)
        self.assertEqual(stats['disease_count']['Healthy'], 1005)
        self.assertEqual(len(stats['recent_detections']), 10)

    def test_unreadable_local_file_does_not_hide_valid_records(self):
        self.namespace['firestore_ready'].return_value = False
        self.save_results(1)
        (self.results / 'broken.json').write_text('{', encoding='utf-8')
        self.assertEqual(self.stats()['total_detections'], 1)
        self.assertEqual((self.results / 'broken.json').read_text(), '{')
        self.cloud.assert_not_called()

    def test_zero_is_returned_when_both_sources_are_empty(self):
        stats = self.stats()
        self.assertEqual(stats['total_detections'], 0)
        self.assertEqual(stats['disease_count'], {})

    def test_firestore_read_uses_deadline_without_automatic_retries(self):
        source = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8-sig'))
        functions = [node for node in source.body if isinstance(node, ast.FunctionDef)
                     and node.name == 'get_detection_results_firestore']
        query = Mock()
        query.where.return_value = query
        query.stream.return_value = []
        database = Mock()
        database.collection.return_value = query
        from core.detection_records import detection_datetime
        from datetime import datetime
        namespace = {'firestore_db': database, 'firestore_ready': lambda: True,
                     'detection_datetime': detection_datetime, 'datetime': datetime}
        exec(compile(ast.Module(body=functions, type_ignores=[]), 'cloud_read', 'exec'), namespace)
        namespace['get_detection_results_firestore'](user_id='staff-id', timeout=5)
        query.where.assert_called_once_with('user_id', '==', 'staff-id')
        query.stream.assert_called_once_with(retry=None, timeout=5)


if __name__ == '__main__':
    unittest.main()
