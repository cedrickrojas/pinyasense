"""Load real Flask route functions without models, GPIO, jobs, or cloud startup."""
import ast
import csv
import json
import math
import os
import tempfile
import hmac
from datetime import datetime, timedelta
from functools import wraps
from io import BytesIO, StringIO
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import Mock
from uuid import uuid4

import cv2
import numpy as np
from flask import Flask, jsonify, make_response, redirect, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

from core.detection_records import detection_datetime, load_local_results, save_local_result
from core.json_storage import write_json_atomic
from core.pump_remote import proxy_pump_request


ROOT = Path(__file__).resolve().parents[1]


def make_app(folder):
    app = Flask('offline_application_test', root_path=str(ROOT))
    app.config.update(TESTING=True, MAX_CONTENT_LENGTH=200 * 1024 * 1024,
                      UPLOAD_FOLDER=str(Path(folder) / 'uploads'),
                      RESULTS_FOLDER=str(Path(folder) / 'results'))
    for name in ('UPLOAD_FOLDER', 'RESULTS_FOLDER'):
        Path(app.config[name]).mkdir(parents=True, exist_ok=True)
    namespace = dict(globals(), app=app, PROJECT_ROOT=str(folder), scheduler=None,
                     WATER_PUMP_SCHEDULES_FILE=str(Path(folder) / 'schedules.json'),
                     AUTO_PUMP_SETTINGS_FILE=str(Path(folder) / 'auto.json'),
                     ALLOWED_IMAGE_EXTENSIONS={'jpg', 'jpeg', 'png'},
                     ALLOWED_VIDEO_EXTENSIONS={'mp4', 'mov', 'avi', 'mkv', 'webm'},
                     ALLOWED_EXTENSIONS={'jpg', 'jpeg', 'png', 'mp4', 'mov', 'avi', 'mkv', 'webm'},
                     _AUTO_PUMP_STATE={'consecutive_dry': 0},
                     sensor_monitor=Mock(WATER_PUMP_DEFAULT_DURATION=5, WATER_PUMP_MAX_DURATION=300), detector=Mock(),
                     firestore_ready=Mock(return_value=False), firestore_db=Mock(),
                     verify_session=Mock(side_effect=lambda token: 'owner@example.com' if token == 'approved' else None),
                     get_user_info=Mock(return_value={'role': 'staff', 'status': 'approved'}))
    tree = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8-sig'))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    exec(compile(ast.Module(body=functions, type_ignores=[]), 'app_routes', 'exec'), namespace)
    namespace['firestore_ready'] = Mock(return_value=False)
    return app, namespace
