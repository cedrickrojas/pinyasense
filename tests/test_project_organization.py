"""Offline migration checks: no app import, model loading, or external calls."""

import ast
import importlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask, send_from_directory


ROOT = Path(__file__).resolve().parents[1]


class OrganizationTests(unittest.TestCase):
    def test_pwa_routes_serve_the_relocated_files_without_importing_app(self):
        source = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8-sig'))
        functions = [node for node in source.body if isinstance(node, ast.FunctionDef)
                     and node.name in {'manifest', 'service_worker'}]
        self.assertEqual(len(functions), 2)
        app = Flask('organization_asset_test', root_path=str(ROOT))
        namespace = {'app': app, 'send_from_directory': send_from_directory}
        exec(compile(ast.Module(body=functions, type_ignores=[]), 'asset_routes', 'exec'), namespace)
        with app.test_client() as client:
            with client.get('/manifest.webmanifest') as manifest:
                self.assertEqual(manifest.status_code, 200)
                self.assertIn('application/manifest+json', manifest.content_type)
                for icon in manifest.get_json(force=True)['icons']:
                    with client.get(icon['src']) as icon_response:
                        self.assertEqual(icon_response.status_code, 200)
            with client.get('/sw.js') as worker:
                self.assertEqual(worker.status_code, 200)
                self.assertIn(b'/manifest.webmanifest', worker.data)
            self.assertFalse((ROOT / 'static/js/sw.js').exists())
            self.assertFalse((ROOT / 'static/js/manifest.webmanifest').exists())

    def test_moved_helpers_keep_application_storage_roots(self):
        for name in ('scripts.maintenance.realistic_sensor_data',
                     'scripts.maintenance.normalize_sensor_ids',
                     'scripts.reporting.export_detection_reports',
                     'scripts.reporting.send_detection_reports'):
            module = importlib.import_module(name)
            self.assertEqual(module.ROOT, ROOT, name)
        reset = importlib.import_module('scripts.maintenance.reset_sensor_data')
        self.assertEqual(reset.ROOT_DIR, ROOT)
        sample = importlib.import_module('scripts.reporting.build_sample_detection_reports')
        self.assertEqual(sample.mail.ROOT, ROOT)
        self.assertEqual(sample.mail.FOLDER.parent, ROOT / 'results')

    def test_quickstart_subprocesses_find_grouped_tools_from_another_directory(self):
        quickstart = importlib.import_module('scripts.training.yolov8_quickstart')
        cases = (
            (lambda: quickstart.setup_dataset('input-data'), 'scripts/training/prepare_yolov8_dataset.py'),
            (lambda: quickstart.train_model('input-data/data.yaml'), 'scripts/training/train_yolov8.py'),
            (lambda: quickstart.test_model('weights.pt', 'image.jpg'), 'scripts/diagnostics/test_yolov8_inference.py'),
        )
        original = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                for operation, target in cases:
                    with patch.object(quickstart.subprocess, 'run', return_value=SimpleNamespace(
                            returncode=0, stdout='')) as run, redirect_stdout(io.StringIO()):
                        self.assertTrue(operation())
                    command = run.call_args.args[0]
                    self.assertEqual(command[0], sys.executable)
                    self.assertEqual(Path(command[1]), ROOT / target)
                    self.assertTrue(Path(command[1]).is_file())
            finally:
                os.chdir(original)

    def test_diagnostic_file_checks_use_the_application_root(self):
        diagnostic = importlib.import_module('scripts.diagnostics.setup_diagnostics')
        original = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                with redirect_stdout(io.StringIO()):
                    self.assertTrue(diagnostic.check_yolov8_tools())
                    self.assertTrue(diagnostic.check_app_structure())
            finally:
                os.chdir(original)

    def test_grouped_module_help_is_available_without_running_operations(self):
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
        for module in ('scripts.maintenance.realistic_sensor_data',
                       'scripts.maintenance.normalize_sensor_ids',
                       'scripts.reporting.export_detection_reports',
                       'scripts.reporting.build_sample_detection_reports'):
            result = subprocess.run([sys.executable, '-B', '-m', module, '--help'],
                                    cwd=ROOT, env=environment, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, module)
            self.assertIn(b'usage:', result.stdout.lower())

    def test_deployment_payload_contains_imported_core_modules_and_pwa_assets(self):
        deploy = (ROOT / 'deploy_to_pi.ps1').read_text(encoding='utf-8-sig')
        payload = set()
        for line in deploy.splitlines():
            if not line.strip().startswith('scp '):
                continue
            for token in line.strip().split()[1:]:
                if token.startswith('"${PiHost}:'):
                    break
                token = token.replace('\\', '/')
                payload.update(p.relative_to(ROOT).as_posix() for p in ROOT.glob(token) if p.is_file())
        required = {'static/sw.js', 'static/manifest.webmanifest', 'static/icons/pinya-icon.svg',
                    'scripts/arduino_serial_bridge.py', 'core/__init__.py'}
        tree = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith('core.'):
                required.add(node.module.replace('.', '/') + '.py')
        required.add('core/notification_service.py')
        self.assertTrue(required.issubset(payload), 'Runtime dependency missing from deployment payload')


if __name__ == '__main__':
    unittest.main()
