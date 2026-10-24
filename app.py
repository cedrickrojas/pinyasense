from flask import Flask, render_template, request, jsonify, make_response, send_from_directory, redirect
from flask_cors import CORS
import os
from werkzeug.utils import secure_filename
import cv2
import numpy as np
import math
import tempfile
import hmac
from datetime import datetime, timedelta
from uuid import uuid4
from typing import Dict, List
from dotenv import load_dotenv

load_dotenv()

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    SCHEDULER_AVAILABLE = True
except Exception:
    SCHEDULER_AVAILABLE = False
    BackgroundScheduler = None

from core.email_service import send_report_email
import json
from core.disease_detector import PineappleDiseaseDetector
from core.sensor_monitor import sensor_monitor
from core.time_series_forecaster import growth_forecaster
from core.soil_preview import preview_zones, preview_history
from core.detection_records import detection_datetime, load_local_results, save_local_result
from core.json_storage import write_json_atomic
from core.pump_remote import create_pump_bridge, proxy_pump_request
from core.plant_monitoring import (
    PlantMonitoringStore,
    ProblemRecommender,
    MonitoringStoreUnavailable,
    STORE_UNAVAILABLE_MESSAGE,
    ValidationError as MonitoringValidationError,
    monitoring_options,
    validate_problem_status,
    validate_problem_submission,
    validate_status_submission,
)
from core.auth import register_user, create_super_admin, verify_login, verify_session, get_user_info, invalidate_session, update_user_fullname, generate_reset_code, verify_reset_code, reset_password, list_staff_accounts, update_staff_account_status, load_users
from core.email_service import send_reset_code_email, send_welcome_email
from functools import wraps
import firebase_admin
from firebase_admin import credentials, firestore
import csv
from io import StringIO, BytesIO
try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
CORS(app)
app.register_blueprint(create_pump_bridge(sensor_monitor))


@app.before_request
def validate_api_request():
    """Reject malformed request bodies before broad route error handlers run."""
    if request.content_length and request.content_length > app.config['MAX_CONTENT_LENGTH']:
        return jsonify({'error': 'Upload exceeds the 200 MB limit.'}), 413
    if request.path.startswith('/api/'):
        for key, maximum in (('limit', 1000), ('hours', 168), ('days', 3650)):
            if key in request.args:
                try:
                    value = int(request.args[key])
                    if not 1 <= value <= maximum:
                        raise ValueError()
                except ValueError:
                    return jsonify({'error': f'{key} must be an integer between 1 and {maximum}.'}), 400
    if request.path.startswith('/api/') and request.method in {'POST', 'PUT', 'PATCH'}:
        if request.is_json:
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return jsonify({'error': 'Expected a JSON object.'}), 400
            for key in ('fullname', 'email', 'password', 'confirmPassword', 'phone', 'code',
                        'new_password', 'confirm_password', 'title', 'content', 'type', 'status', 'message'):
                if key in data and not isinstance(data[key], str):
                    return jsonify({'error': f'{key} must be text.'}), 400
        json_paths = {'/api/signup', '/api/login', '/api/forgot-password', '/api/reset-password',
                      '/api/profile', '/api/admin/super-admins', '/api/reports', '/api/notifications'}
        if request.path in json_paths and not request.is_json:
            return jsonify({'error': 'Expected an application/json request.'}), 400

# Configuration
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(PROJECT_ROOT, 'uploads')
RESULTS_FOLDER = os.path.join(PROJECT_ROOT, 'results')
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv', 'webm'}
ALLOWED_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS | ALLOWED_VIDEO_EXTENSIONS
MAX_FILE_SIZE = 200 * 1024 * 1024  # 200MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['RESULTS_FOLDER'] = RESULTS_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE
scheduler = None

# Create necessary directories
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)
os.makedirs(os.path.join(PROJECT_ROOT, 'static', 'images'), exist_ok=True)

# Initialize disease detector
MODEL_PATH = os.getenv('PINEAPPLE_MODEL_PATH') or os.getenv('MODEL_PATH')
detector = PineappleDiseaseDetector(model_path=MODEL_PATH)


# Official Firestore setup using service account
FIREBASE_SERVICE_ACCOUNT_KEY = os.getenv('FIREBASE_SERVICE_ACCOUNT_KEY')
FIREBASE_KEY_CANDIDATES = [
    FIREBASE_SERVICE_ACCOUNT_KEY,
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'serviceAccountKey.json'),
    'serviceAccountKey.json',
]
firestore_db = None

try:
    firestore_error = None
    for firestore_key_path in FIREBASE_KEY_CANDIDATES:
        if not firestore_key_path or not os.path.exists(firestore_key_path):
            continue

        try:
            firestore_cred = credentials.Certificate(firestore_key_path)
            if not firebase_admin._apps:
                firebase_admin.initialize_app(firestore_cred)
            firestore_db = firestore.client()
            os.environ['FIREBASE_SERVICE_ACCOUNT_KEY'] = firestore_key_path
            print(f"✅ Firestore initialized successfully from {firestore_key_path}")
            break
        except Exception as candidate_error:
            firestore_error = candidate_error

    if firestore_db is None:
        if firestore_error:
            raise firestore_error
        print("⚠️  Firestore service account not found in any expected path")
except Exception as e:
    print(f"⚠️  Firestore initialization failed: {e}")


def firestore_ready() -> bool:
    """Return True when Firestore is available."""
    return firestore_db is not None


def sync_user_firestore(email, deleted=False):
    """Mirror account metadata to Firestore without storing password data."""
    if not firestore_ready() or not email:
        return False

    document_id = (
        email.strip().lower()
        .replace('.', '_').replace('#', '_').replace('$', '_')
        .replace('[', '_').replace(']', '_').replace('/', '_')
    )
    reference = firestore_db.collection('users').document(document_id)
    if deleted:
        reference.delete()
        return True

    user = load_users().get(email.strip().lower())
    if not user:
        return False
    reference.set({
        'email': user.get('email', email).lower(),
        'fullname': user.get('fullname', 'User'),
        'phone': user.get('phone', ''),
        'role': user.get('role', 'staff'),
        'status': user.get('status', 'pending'),
        'created_at': user.get('created_at'),
        'last_login': user.get('last_login'),
        'updated_at': datetime.now().isoformat(),
    }, merge=True)
    return True


def _collection_query(collection_name, user_id=None):
    """Build a Firestore query for a top-level collection."""
    query = firestore_db.collection(collection_name)
    if user_id:
        query = query.where('user_id', '==', user_id)
    return query


def save_detection_result_firestore(result, user_id=None):
    if not firestore_ready():
        return False

    timestamp = result.get('timestamp', datetime.now().isoformat())
    data = {
        'disease': result.get('disease'),
        'confidence': result.get('confidence'),
        'severity': result.get('severity'),
        'timestamp': timestamp,
        'media_type': result.get('media_type'),
        'media_path': result.get('media_path'),
        'farm': result.get('farm'),
        'user_id': user_id,
        'record_id': result.get('record_id'),
        'image_path': result.get('image_path'),
        'method': result.get('method'),
    }
    firestore_db.collection('disease_results').document(result.get('record_id') or str(timestamp)).set(data, retry=None, timeout=8)
    return True


def get_detection_results_firestore(user_id=None, limit=50, timeout=8):
    if not firestore_ready():
        return []

    query = firestore_db.collection('disease_results')
    if user_id is not None:
        # Filtering by user_id and ordering by timestamp together requires a
        # composite index. Avoid that by sorting client-side instead.
        query = query.where('user_id', '==', user_id)
    else:
        query = query.order_by('timestamp', direction=firestore.Query.DESCENDING)
        if limit is not None:
            query = query.limit(limit)

    stream_options = {'retry': None, 'timeout': timeout} if timeout is not None else {}
    docs = query.stream(**stream_options)
    results = []
    for doc in docs:
        item = doc.to_dict() or {}
        item['id'] = doc.id
        results.append(item)

    if user_id is not None:
        results.sort(key=lambda r: detection_datetime(r.get('timestamp')) or datetime.min, reverse=True)
        results = results[:limit]

    return results


def _parse_report_date(value):
    return detection_datetime(value)


def _normalize_report_filters(start_date=None, end_date=None, farm=None, sensor_type=None, media_type=None):
    return {
        'start_date': _parse_report_date(start_date),
        'end_date': _parse_report_date(end_date),
        'farm': farm.strip() if isinstance(farm, str) and farm.strip() else None,
        'sensor_type': sensor_type.strip() if isinstance(sensor_type, str) and sensor_type.strip() else None,
        'media_type': media_type.strip().lower() if isinstance(media_type, str) and media_type.strip() else None,
    }


def _build_report_filters_from_request():
    return _normalize_report_filters(
        start_date=request.args.get('start_date') or request.form.get('start_date'),
        end_date=request.args.get('end_date') or request.form.get('end_date'),
        farm=request.args.get('farm') or request.form.get('farm'),
        sensor_type=request.args.get('sensor_type') or request.form.get('sensor_type'),
        media_type=request.args.get('media_type') or request.form.get('media_type'),
    )


def _filter_detection_results(results, filters):
    filtered = []
    for result in results:
        timestamp = _parse_report_date(result.get('timestamp'))
        if not timestamp and (filters.get('start_date') or filters.get('end_date')):
            continue
        if filters.get('start_date') and timestamp and timestamp < filters['start_date']:
            continue
        if filters.get('end_date') and timestamp and timestamp >= filters['end_date'] + timedelta(days=1):
            continue

        if filters.get('farm'):
            farm_value = str(result.get('farm') or result.get('farm_id') or result.get('location') or '').strip().lower()
            if farm_value != filters['farm'].lower():
                continue

        if filters.get('media_type'):
            media_value = str(result.get('media_type') or '').strip().lower()
            if media_value != filters['media_type']:
                continue

        filtered.append(result)
    return filtered


def _filter_sensor_results(results, filters):
    filtered = []
    for result in results:
        timestamp = _parse_report_date(result.get('timestamp'))
        if not timestamp and (filters.get('start_date') or filters.get('end_date')):
            continue
        if filters.get('start_date') and timestamp and timestamp < filters['start_date']:
            continue
        if filters.get('end_date') and timestamp and timestamp >= filters['end_date'] + timedelta(days=1):
            continue

        if filters.get('sensor_type'):
            sensor_value = str(result.get('sensor_type') or '').strip().lower()
            if sensor_value != filters['sensor_type'].lower():
                continue

        filtered.append(result)
    return filtered




def save_sensor_data_firestore(sensor_type, data, user_id=None):
    if not firestore_ready():
        return False

    payload = {
        'sensor_type': sensor_type,
        'user_id': user_id,
        'timestamp': data.get('timestamp', datetime.now().isoformat()),
        'data': data,
    }
    firestore_db.collection('sensor_data').add(payload, retry=None, timeout=8)
    return True


def get_sensor_data_firestore(sensor_type, user_id=None, limit=100, timeout=None):
    if not firestore_ready():
        return []

    # Filtering by sensor_type/user_id and ordering by timestamp together
    # requires a composite index. Avoid that by sorting client-side instead.
    query = firestore_db.collection('sensor_data').where('sensor_type', '==', sensor_type)
    if user_id:
        query = query.where('user_id', '==', user_id)

    readings = []
    stream_options = {'retry': None, 'timeout': timeout} if timeout is not None else {}
    for doc in query.stream(**stream_options):
        item = doc.to_dict() or {}
        item['id'] = doc.id
        readings.append(item)

    readings.sort(key=lambda r: r.get('timestamp', ''), reverse=True)
    return readings[:limit]


def _load_forecast_sensor_rows(history_days=90):
    """Load the current user's real digital DO readings from Firestore."""
    if not firestore_ready():
        return [], 'Firestore is unavailable, so actual sensor readings could not be loaded.'

    current_email = verify_session(request.cookies.get('session_token'))
    allowed_users = {None, get_current_firebase_user_id(), current_email}
    sensor_types = [
        'soil_moisture',
        'soil_moisture_zone1',
        'soil_moisture_zone2',
        'soil_moisture_zone3',
        'soil_moisture_zone4',
        'temp_humidity',
        'temperature_humidity',
    ]
    rows = []
    reading_limit = max(500, min(10000, int(history_days) * 4 * 24))
    try:
        for sensor_type in sensor_types:
            readings = get_sensor_data_firestore(sensor_type, limit=reading_limit, timeout=8)
            for record in readings:
                if record.get('user_id') not in allowed_users:
                    continue

                reading = dict(record)
                nested_data = record.get('data')
                if isinstance(nested_data, dict):
                    reading.update(nested_data)
                reading['sensor_type'] = record.get('sensor_type') or sensor_type
                reading['user_id'] = record.get('user_id')
                if str(reading.get('data_source', '')).strip().lower() == 'simulated_daily':
                    continue
                rows.append(reading)
    except Exception as error:
        print(f'⚠️  Unable to load forecast sensor history from Firestore: {error}')
        return [], 'Firestore sensor history could not be loaded.'

    return rows, None


def save_report_firestore(report, user_id=None):
    if not firestore_ready():
        return False

    report_id = report.get('id') or uuid4().hex
    data = {
        'id': report_id,
        'title': report.get('title', ''),
        'type': report.get('type', 'general'),
        'content': report.get('content', ''),
        'status': report.get('status', 'open'),
        'created_by': report.get('created_by'),
        'user_id': user_id,
        'created_at': report.get('created_at', datetime.now().isoformat()),
        'updated_at': datetime.now().isoformat(),
    }
    firestore_db.collection('reports').document(report_id).set(data, retry=None, timeout=8)
    return True


def _list_user_documents(collection, user_id=None, limit=50):
    """Avoid a compound-index requirement while preserving per-user isolation."""
    if not firestore_ready():
        return []
    query = firestore_db.collection(collection)
    if user_id is not None:
        query = query.where('user_id', '==', user_id)
    else:
        query = query.order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit)
    rows = []
    for document in query.stream(retry=None, timeout=8):
        row = document.to_dict() or {}
        row['id'] = document.id
        rows.append(row)
    rows.sort(key=lambda row: detection_datetime(row.get('created_at')) or datetime.min, reverse=True)
    return rows[:limit]


def get_reports_firestore(user_id=None, limit=50):
    return _list_user_documents('reports', user_id, limit)


def save_notification_firestore(notification, user_id=None):
    if not firestore_ready():
        return False

    notification_id = notification.get('id') or uuid4().hex
    data = {
        'id': notification_id,
        'title': notification.get('title', ''),
        'message': notification.get('message', ''),
        'type': notification.get('type', 'info'),
        'read': bool(notification.get('read', False)),
        'user_id': user_id,
        'created_at': notification.get('created_at', datetime.now().isoformat()),
    }
    firestore_db.collection('notifications').document(notification_id).set(data, retry=None, timeout=8)
    return True


def get_notifications_firestore(user_id=None, limit=50):
    return _list_user_documents('notifications', user_id, limit)


def mark_notification_read_firestore(notification_id, user_id=None):
    if not firestore_ready() or not notification_id or '/' in notification_id:
        return False
    reference = firestore_db.collection('notifications').document(notification_id)
    snapshot = reference.get(retry=None, timeout=8)
    if not snapshot.exists or (snapshot.to_dict() or {}).get('user_id') != user_id:
        return False
    reference.update({'read': True}, retry=None, timeout=8)
    return True


def to_firebase_user_id(email):
    """Sanitize user identifiers for Firebase Realtime Database keys."""
    if not email:
        return None
    return (
        email.strip().lower()
        .replace('.', '_')
        .replace('#', '_')
        .replace('$', '_')
        .replace('[', '_')
        .replace(']', '_')
        .replace('/', '_')
    )


def get_current_firebase_user_id():
    """Return Firebase-safe user id from current session cookie, if available."""
    session_token = request.cookies.get('session_token')
    email = verify_session(session_token)
    return to_firebase_user_id(email)


def _detection_user_id():
    """Admins review the farm's records; staff see only their own uploads."""
    user = getattr(request, 'current_user', None)
    if user and user.get('role') in {'admin', 'super_admin'}:
        return None
    return get_current_firebase_user_id()


def _read_detection_results(user_id=None, limit=1000):
    local = load_local_results(app.config['RESULTS_FOLDER'], user_id=user_id)
    cloud = []
    if firestore_ready():
        try:
            cloud = get_detection_results_firestore(user_id=user_id, limit=limit, timeout=5)
        except Exception as error:
            app.logger.warning('Cloud detection read failed (%s); using local records.', type(error).__name__)
    source = 'firestore' if cloud else 'local'
    if cloud:
        known = {row.get('record_id') or row.get('id') for row in cloud}
        pending = [row for row in local if row.get('cloud_saved') is False
                   and row.get('record_id') not in known]
        rows = cloud + pending
        if pending:
            source = 'mixed'
    else:
        rows = local
    rows.sort(key=lambda row: detection_datetime(row.get('timestamp')) or datetime.min, reverse=True)
    return rows[:limit], source


def _persist_detection_result(result):
    """Preserve successful analysis locally before attempting the cloud write."""
    result['record_id'] = datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_' + uuid4().hex[:8]
    result['timestamp'] = (detection_datetime(result.get('timestamp')) or datetime.now()).isoformat()
    result['user_id'] = get_current_firebase_user_id()
    result['cloud_saved'] = False
    save_local_result(app.config['RESULTS_FOLDER'], result)
    if firestore_ready():
        try:
            result['cloud_saved'] = bool(save_detection_result_firestore(result, user_id=result['user_id']))
        except Exception as error:
            app.logger.warning('Detection saved locally; cloud write failed (%s).', type(error).__name__)
        if result['cloud_saved']:
            save_local_result(app.config['RESULTS_FOLDER'], result)
    return result


@app.route("/save_sensor", methods=["GET", "POST"])
def save_sensor():
    if request.method == "POST":
        ingest_token = os.getenv('SENSOR_INGEST_TOKEN', '')
        supplied_token = request.headers.get('X-Sensor-Token', '')
        if ingest_token:
            if not hmac.compare_digest(ingest_token, supplied_token):
                return jsonify({'error': 'Invalid sensor ingest token'}), 401
        elif request.remote_addr not in {'127.0.0.1', '::1'} or request.headers.get('X-Forwarded-For'):
            return jsonify({'error': 'Remote sensor ingestion requires SENSOR_INGEST_TOKEN'}), 403
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("zones"), list):
            return jsonify({"message": "Expected JSON with a zones list"}), 400

        timestamp = detection_datetime(payload.get('timestamp', datetime.now().isoformat()))
        if timestamp is None or timestamp > datetime.now() + timedelta(minutes=10):
            return jsonify({'error': 'Invalid sensor timestamp'}), 400
        timestamp = timestamp.isoformat()
        saved_zones = []
        firebase_saved_zones = 0
        firebase_error = None
        for zone in payload["zones"]:
            if not isinstance(zone, dict):
                continue
            try:
                zone_number = int(zone["zone"])
                raw_value = int(zone["raw"])
                moisture = int(zone["moisture"])
            except (KeyError, TypeError, ValueError):
                continue

            if not 1 <= zone_number <= 4 or not 0 <= moisture <= 100:
                continue
            if any(item['zone'] == zone_number for item in saved_zones):
                continue
            status = 'dry' if moisture <= 30 else 'moist' if moisture <= 70 else 'wet'

            reading = {
                "value": moisture,
                "unit": "%",
                "status": status,
                "state": status.upper(),
                "raw_value": raw_value,
                "sensor_mode": "arduino_analog",
                "zone": zone_number,
                "timestamp": timestamp,
            }
            sensor_monitor.save_reading(f"soil_moisture_zone{zone_number}", reading)
            if firestore_ready():
                try:
                    if save_sensor_data_firestore(
                        f"soil_moisture_zone{zone_number}",
                        reading,
                        user_id=None,
                    ):
                        firebase_saved_zones += 1
                    else:
                        firebase_error = "Firestore is not available"
                except Exception as error:
                    print(f"⚠️ Unable to save soil moisture data to Firestore: {error}")
                    firebase_error = "Firestore write failed; check the app logs"
            else:
                firebase_error = "Firestore is not initialized"
            saved_zones.append(reading)

        if not saved_zones:
            return jsonify({"message": "No valid sensor zones received"}), 400

        response = {
            "message": "Arduino sensor data saved locally",
            "zones": saved_zones,
            "firebase_saved": firebase_error is None,
            "firebase_saved_zones": firebase_saved_zones,
        }
        if firebase_error:
            response["firebase_error"] = firebase_error
            return jsonify(response), 503

        response["message"] = "Arduino sensor data saved locally and to Firestore"
        return jsonify(response), 201

    return jsonify({'message': 'Send actual Arduino readings with POST; GET does not write sensor data.'}), 200

def allowed_file(filename):
    """Check if uploaded file has allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_video_file(filename):
    """Check if uploaded file is a supported video type"""
    if '.' not in filename:
        return False
    return filename.rsplit('.', 1)[1].lower() in ALLOWED_VIDEO_EXTENSIONS

def login_required(f):
    """Use the same account and approval checks on every protected API."""
    return staff_access_required(f)


def admin_required(f):
    """Decorator to require admin privileges."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        session_token = request.cookies.get('session_token')
        email = verify_session(session_token)
        if not email:
            return jsonify({'error': 'Unauthorized. Please log in.'}), 401

        user = get_user_info(email)
        if not user:
            return jsonify({'error': 'Unauthorized. Please log in.'}), 401

        if user.get('role') not in {'admin', 'super_admin'}:
            return jsonify({'error': 'Admin access required.'}), 403

        request.user_email = email
        request.current_user = user
        return f(*args, **kwargs)
    return decorated_function


def staff_access_required(f):
    """Decorator to require approved staff or admin access."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        session_token = request.cookies.get('session_token')
        email = verify_session(session_token)
        if not email:
            return jsonify({'error': 'Unauthorized. Please log in.'}), 401

        user = get_user_info(email)
        if not user:
            return jsonify({'error': 'Unauthorized. Please log in.'}), 401

        role = user.get('role')
        status = user.get('status', 'pending')
        if role in {'admin', 'super_admin'}:
            request.user_email = email
            request.current_user = user
            return f(*args, **kwargs)

        if role != 'staff' or status != 'approved':
            return jsonify({'error': 'Your account is not authorized to access PinyaSense.'}), 403

        request.user_email = email
        request.current_user = user
        return f(*args, **kwargs)
    return decorated_function


@app.before_request
def forward_remote_pump():
    if os.getenv('PUMP_REMOTE_URL', '').strip() and request.path.startswith('/api/water-pump/'):
        return staff_access_required(proxy_pump_request)()
    return None


def require_staff_page_access():
    """Check page access for staff/admin pages without building a full decorator."""
    session_token = request.cookies.get('session_token')
    email = verify_session(session_token)
    if not email:
        return render_template('login.html')

    user = get_user_info(email)
    if not user:
        return render_template('login.html')

    if user.get('role') == 'staff':
        status = user.get('status', 'pending')
        if status == 'pending':
            return render_template('login.html')
        if status in {'rejected', 'inactive'}:
            return render_template('login.html')
        if status != 'approved':
            return render_template('login.html')

    return None


def require_admin_page_access():
    """Check page access for admin-only pages."""
    session_token = request.cookies.get('session_token')
    email = verify_session(session_token)
    if not email:
        return render_template('login.html')

    user = get_user_info(email)
    if not user or user.get('role') not in {'admin', 'super_admin'}:
        return render_template('login.html')
    return None


def require_super_admin_page_access():
    """Check page access for the separate Super Admin dashboard."""
    session_token = request.cookies.get('session_token')
    email = verify_session(session_token)
    user = get_user_info(email) if email else None
    if not user or user.get('role') != 'super_admin':
        return render_template('login.html', message='Super Admin access required.')
    return None


def extract_video_frame(video_path, output_folder, base_name):
    """Extract representative frame from video for disease detection"""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError("Unable to open uploaded video file")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    target_frame = max(0, total_frames // 2)
    if total_frames > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)

    success, frame = cap.read()
    if not success or frame is None:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        success, frame = cap.read()

    cap.release()

    if not success or frame is None:
        raise ValueError("Unable to extract a frame from the uploaded video")

    frame_filename = f"{base_name}_frame.jpg"
    frame_path = os.path.join(output_folder, frame_filename)
    cv2.imwrite(frame_path, frame)
    return frame_filename, frame_path

# ============================================
# MULTILINGUAL SUPPORT
# ============================================
TRANSLATIONS = {
    'en': {
        'page_title': 'Pineapple Disease Detection System',
        'title': 'Pineapple Disease Detection System',
        'brand': 'PiñaSense',
        'agriculture_section': 'Agriculture',
        'home': 'Home',
        'sensors': 'Sensors',
        'soil_moisture': 'Soil Moisture',
        'fertilization': 'Fertilization',
        'forecast': 'Forecast',
        'diseases': 'Diseases',
        'about': 'About',
        'analytics': 'Analytics',
        'system': 'System',
        'upload_analyze': 'Upload & Analyze',
        'hero_subtitle': 'Upload pineapple photos or drone videos for disease detection',
        'open_camera': 'Open Camera',
        'open_camera_desc': 'Use your device camera to capture',
        'upload_photo': 'Upload Photo',
        'upload_photo_desc': 'Choose a photo from your device',
        'batch_upload': 'Batch Upload',
        'batch_upload_desc': 'Upload multiple photos at once',
        'upload_video': 'Upload Video',
        'upload_video_desc': 'Analyze video frames',
        'total_detections_label': 'Total Detections',
        'healthy_label': 'Healthy',
        'diseased_label': 'Diseased',
        'current_soil_moisture': 'Current Soil Moisture',
        'loading_sensor_data': 'Loading sensor data...',
        'choose_file': 'Choose File',
        'detect_disease': 'Detect Disease',
        'cancel': 'Cancel',
        'click_or_drag': 'Click or drag a photo/video here',
        'accepted_formats': 'Accepted: PNG, JPG, JPEG, MP4, MOV, AVI, MKV, WEBM (Max 200MB)',
        'weather_recommendation': 'Weather Recommendation',
        'disease_spread_risk': 'Disease Spread Risk',
        'detection_result': 'Detection Result',
        'severity': 'Severity',
        'action_required': 'Action Required',
        'immediate_action': 'Immediate Action',
        'treatments': 'Treatments',
        'recommendations': 'Recommendations',
        'fertilization_recommendations': 'Fertilization Recommendations',
        'quick_farming_tips': 'Quick Farming Tips',
        'growth_monitoring_guide': 'Growth Monitoring Guide',
        'quick_resources': 'Quick Resources',
        'monitor_soil_moisture': 'Monitor Soil Moisture',
        'monitor_soil_moisture_desc': 'Check sensor data regularly to maintain optimal soil moisture levels (40-60%). Prevent waterlogging and drought stress.',
        'sunlight_exposure': 'Sunlight Exposure',
        'sunlight_exposure_desc': 'Ensure 6-8 hours of direct sunlight daily for optimal growth and fruit development.',
        'ideal_temperature': 'Ideal Temperature',
        'ideal_temperature_desc': 'Maintain temperature between 20-30°C for best results. Protect from frost and extreme heat.',
        'soil_requirements': 'Soil Requirements',
        'soil_requirements_desc': 'Use well-draining soil with pH 4.5-6.5. Add organic matter to improve fertility.',
        'pest_control': 'Pest Control',
        'pest_control_desc': 'Inspect plants weekly for mealybugs and scale insects. Use organic pesticides when needed.',
        'harvest_time': 'Harvest Time',
        'harvest_time_desc': 'Harvest when fruit turns golden-yellow and emits sweet aroma (18-22 months after planting).',
        'monitor_sensors': 'Monitor Sensors',
        'monitor_sensors_desc': 'Check real-time soil and environmental data',
        'fertilization_guide': 'Fertilization Guide',
        'fertilization_guide_desc': 'Get fertilization recommendations',
        'growth_forecast': 'Growth Forecast',
        'growth_forecast_desc': 'Predict growth stage and harvest schedule',
        'disease_database': 'Disease Database',
        'disease_database_desc': 'Learn about pineapple diseases',
        'about_system': 'About System',
        'about_system_desc': 'System information and help',
        'footer_copyright': '© 2026 AgriPinya - Pineapple Disease Detection System',
        'footer_tagline': 'Helping pineapple farmers achieve healthier harvests',
        'analyze': 'Analyze',
        'upload': 'Upload',
        'results': 'Results',
        'disease': 'Disease',
        'confidence': 'Confidence',
        'severity': 'Severity',
        'high': 'High',
        'medium': 'Medium',
        'low': 'Low',
        'treatment': 'Treatment',
        'recommendations': 'Recommendations',
        'history': 'History',
        'alerts': 'Alerts',
        'trends': 'Trends',
        'export': 'Export',
        'weather_alert': 'Weather Alert',
        'optimal_spray': 'Optimal spray conditions',
        'high_risk': 'High risk conditions',
        'disease_spread': 'Disease Spread Risk',
        'at_risk': 'At Risk',
        'no_risk': 'No Risk',
    },
    'tl': {
        'page_title': 'Sistema ng Pag-detect ng Sakit ng Pinya',
        'title': 'Sistema ng Pag-detect ng Sakit ng Pinya',
        'brand': 'PiñaSense',
        'agriculture_section': 'Agrikultura',
        'home': 'Home',
        'sensors': 'Sensors',
        'soil_moisture': 'Halumigmig ng Lupa',
        'fertilization': 'Pataba',
        'forecast': 'Hula',
        'diseases': 'Mga Sakit',
        'about': 'Tungkol',
        'analytics': 'Analitika',
        'system': 'Sistema',
        'water_pump': 'Water Pump',
        'water_pump_desc': 'Manual na kontrol ng patubig',
        'water_pump_title': 'Water Pump',
        'water_pump_subtitle': 'I-on o i-off ang irrigation pump',
        'pump_status': 'Kalagayan ng Pump',
        'pump_on': 'Buhay',
        'pump_off': 'Patay',
        'run_pump': 'Paandarin 2s',
        'upload_analyze': 'Mag-upload at Suriin',
        'hero_subtitle': 'Mag-upload ng mga larawan ng pinya o drone video para sa disease detection',
        'open_camera': 'Buksan ang Kamera',
        'open_camera_desc': 'Gamitin ang kamera ng device para kumuha',
        'upload_photo': 'Mag-upload ng Larawan',
        'upload_photo_desc': 'Pumili ng larawan mula sa device',
        'batch_upload': 'Maramihang Upload',
        'batch_upload_desc': 'Mag-upload ng maraming larawan sabay-sabay',
        'upload_video': 'Mag-upload ng Video',
        'upload_video_desc': 'Suriin ang mga frame ng video',
        'total_detections_label': 'Kabuuang Pagsusuri',
        'healthy_label': 'Malusog',
        'diseased_label': 'May Sakit',
        'current_soil_moisture': 'Kasalukuyang Halumigmig ng Lupa',
        'loading_sensor_data': 'Naglo-load ng sensor data...',
        'choose_file': 'Pumili ng File',
        'detect_disease': 'Tukuyin ang Sakit',
        'cancel': 'Kanselahin',
        'click_or_drag': 'I-click o i-drag ang larawan/video dito',
        'accepted_formats': 'Tinatanggap: PNG, JPG, JPEG, MP4, MOV, AVI, MKV, WEBM (Max 200MB)',
        'weather_recommendation': 'Rekomendasyon sa Panahon',
        'disease_spread_risk': 'Panganib ng Pagkalat ng Sakit',
        'detection_result': 'Resulta ng Pagsusuri',
        'severity': 'Kalubhaan',
        'action_required': 'Kinakailangang Gawin',
        'immediate_action': 'Agad na Gagawin',
        'treatments': 'Paggamot',
        'recommendations': 'Mga Rekomendasyon',
        'fertilization_recommendations': 'Mga Rekomendasyon sa Pataba',
        'quick_farming_tips': 'Mabilis na Tips sa Pagsasaka',
        'growth_monitoring_guide': 'Gabay sa Pagmamanman ng Paglago',
        'quick_resources': 'Mabilis na Resources',
        'monitor_soil_moisture': 'Bantayan ang Halumigmig ng Lupa',
        'monitor_soil_moisture_desc': 'Suriin ang sensor data nang regular upang mapanatili ang tamang halumigmig ng lupa (40-60%). Iwasan ang sobrang tubig at tagtuyot.',
        'sunlight_exposure': 'Sikát ng Araw',
        'sunlight_exposure_desc': 'Siguraduhin ang 6-8 oras na direktang sikat ng araw araw-araw para sa maayos na paglaki at pagbuo ng bunga.',
        'ideal_temperature': 'Tamáng Temperatura',
        'ideal_temperature_desc': 'Panatilihin ang temperatura sa pagitan ng 20-30°C para sa pinakamahusay na resulta. Protektahan laban sa lamig at sobrang init.',
        'soil_requirements': 'Kailangan sa Lupa',
        'soil_requirements_desc': 'Gumamit ng well-draining soil na may pH 4.5-6.5. Magdagdag ng organikong bagay para sa mas magandang fertility.',
        'pest_control': 'Pagkontrol sa Peste',
        'pest_control_desc': 'Suriin ang halaman linggo-linggo para sa mealybugs at scale insects. Gumamit ng organic pesticide kung kailangan.',
        'harvest_time': 'Panahon ng Ani',
        'harvest_time_desc': 'Anihin kapag ang prutas ay ginto-dilaw na at may matamis na amoy (18-22 buwan matapos itanim).',
        'monitor_sensors': 'Bantayan ang Mga Sensor',
        'monitor_sensors_desc': 'Suriin ang real-time na datos ng lupa at kapaligiran',
        'fertilization_guide': 'Gabay sa Pataba',
        'fertilization_guide_desc': 'Kumuha ng mga rekomendasyon sa pataba',
        'growth_forecast': 'Hula sa Paglago',
        'growth_forecast_desc': 'Tantiya sa yugto ng paglago at iskedyul ng ani',
        'disease_database': 'Database ng Sakit',
        'disease_database_desc': 'Matuto tungkol sa mga sakit ng pinya',
        'about_system': 'Tungkol sa Sistema',
        'about_system_desc': 'Impormasyon at tulong tungkol sa sistema',
        'footer_copyright': '© 2026 AgriPinya - Sistema ng Pag-detect ng Sakit ng Pinya',
        'footer_tagline': 'Tinutulungan ang mga magsasaka ng pinya na magkaroon ng mas malusog na ani',
        'analyze': 'Suriin',
        'upload': 'I-upload',
        'results': 'Mga Resulta',
        'disease': 'Sakit',
        'confidence': 'Kumpiyansa',
        'severity': 'Kalubhaan',
        'high': 'Mataas',
        'medium': 'Katamtaman',
        'low': 'Mababa',
        'treatment': 'Paggamot',
        'recommendations': 'Mga Rekomendasyon',
        'history': 'Kasaysayan',
        'alerts': 'Mga Alerto',
        'trends': 'Mga Uso',
        'export': 'I-export',
        'weather_alert': 'Alerto sa Panahon',
        'optimal_spray': 'Pinakamahusay na oras ng pagspray',
        'high_risk': 'Mataas na panganib na kondisyon',
        'disease_spread': 'Panganib ng Pagkalat ng Sakit',
        'at_risk': 'May Panganib',
        'no_risk': 'Walang Panganib',
        # Additional UI keys added during i18n wiring
        'refresh': 'I-refresh',
        'back_to_dashboard': 'Bumalik sa Dashboard',
        'refresh_all': 'I-refresh Lahat',
        'sensor_monitoring_title': 'Pagsubaybay ng Sensor',
        'sensor_monitoring_subtitle': 'Real-time na pagmamanman ng mga sensor sa sakahan ng pinya',
        'temp_humidity_title': 'Pagsubaybay ng Temperatura at Halumigmig',
        'temp_humidity_subtitle': 'Real-time na pagmamanman ng temperatura at halumigmig',
        'diseases_title': 'Mga Sakit ng Pinya',
        'diseases_subtitle': 'Komprehensibong gabay sa mga sakit ng pinya, sintomas, at paggamot',
        'soil_moisture_title': 'Pagsubaybay ng Halumigmig ng Lupa',
        'soil_moisture_subtitle': 'Real-time na pagmamanman ng halumigmig ng lupa',
        'forecast_title': 'Hula sa Paglago',
        'forecast_subtitle': 'Time-series na hula para sa paglago at iskedyul ng ani',
        'about_title': 'Tungkol sa PiñaSense',
        'about_lead': 'Abansadong sistema na pinatatakbo ng AI para sa pag-detect ng sakit ng pinya para sa mga modernong magsasaka',
        # Auth / onboarding
        'welcome_back': 'Maligayang Pagbabalik',
        'login_subtitle': 'Mag-login sa iyong AgriPinya account',
        'remember_me': 'Tandaan ako',
        'forgot_password': 'Nakalimutan ang Password?',
        'log_in': 'Mag-log in',
        'dont_have_account': 'Wala pang account?',
        'sign_up': 'Mag-sign up nang libre',
        'create_account': 'Gumawa ng Account',
        'signup_subtitle': 'Sumali sa AgriPinya at simulan ang pagmamanman ng iyong mga pananim',
        'create_account_btn': 'Gumawa ng Account',
        'already_have_account': 'Mayroon nang account?',
        'log_in_here': 'Mag-log in dito',
    },
    'es': {
        'page_title': 'Sistema de Detección de Enfermedades de la Piña',
        'title': 'Sistema de Detección de Enfermedades de la Piña',
        'brand': 'PiñaSense',
        'agriculture_section': 'Agricultura',
        'home': 'Inicio',
        'sensors': 'Sensores',
        'soil_moisture': 'Humedad del Suelo',
        'fertilization': 'Fertilización',
        'forecast': 'Pronóstico',
        'diseases': 'Enfermedades',
        'about': 'Acerca de',
        'analytics': 'Analítica',
        'system': 'Sistema',
        'upload_analyze': 'Subir y Analizar',
        'hero_subtitle': 'Sube fotos de piña o videos de drones para la detección de enfermedades',
        'open_camera': 'Abrir Cámara',
        'open_camera_desc': 'Usa la cámara de tu dispositivo para capturar',
        'upload_photo': 'Subir Foto',
        'upload_photo_desc': 'Elige una foto de tu dispositivo',
        'batch_upload': 'Carga por Lotes',
        'batch_upload_desc': 'Sube varias fotos a la vez',
        'upload_video': 'Subir Video',
        'upload_video_desc': 'Analizar fotogramas del video',
        'total_detections_label': 'Detecciones Totales',
        'healthy_label': 'Sano',
        'diseased_label': 'Enfermo',
        'current_soil_moisture': 'Humedad Actual del Suelo',
        'loading_sensor_data': 'Cargando datos del sensor...',
        'choose_file': 'Elegir Archivo',
        'detect_disease': 'Detectar Enfermedad',
        'cancel': 'Cancelar',
        'click_or_drag': 'Haz clic o arrastra una foto/video aquí',
        'accepted_formats': 'Aceptado: PNG, JPG, JPEG, MP4, MOV, AVI, MKV, WEBM (Máx 200MB)',
        'weather_recommendation': 'Recomendación del Clima',
        'disease_spread_risk': 'Riesgo de Propagación',
        'detection_result': 'Resultado de Detección',
        'severity': 'Gravedad',
        'action_required': 'Acción Requerida',
        'immediate_action': 'Acción Inmediata',
        'treatments': 'Tratamientos',
        'recommendations': 'Recomendaciones',
        'fertilization_recommendations': 'Recomendaciones de Fertilización',
        'quick_farming_tips': 'Consejos Rápidos de Cultivo',
        'growth_monitoring_guide': 'Guía de Monitoreo del Crecimiento',
        'quick_resources': 'Recursos Rápidos',
        'monitor_soil_moisture': 'Monitorear la Humedad del Suelo',
        'monitor_soil_moisture_desc': 'Verifica los datos del sensor regularmente para mantener niveles óptimos de humedad del suelo (40-60%). Evita el encharcamiento y la sequía.',
        'sunlight_exposure': 'Exposición Solar',
        'sunlight_exposure_desc': 'Asegura 6-8 horas de luz solar directa diaria para un crecimiento y desarrollo óptimos.',
        'ideal_temperature': 'Temperatura Ideal',
        'ideal_temperature_desc': 'Mantén la temperatura entre 20-30°C para mejores resultados. Protege de heladas y calor extremo.',
        'soil_requirements': 'Requisitos del Suelo',
        'soil_requirements_desc': 'Usa suelo con buen drenaje y pH 4.5-6.5. Añade materia orgánica para mejorar la fertilidad.',
        'pest_control': 'Control de Plagas',
        'pest_control_desc': 'Inspecciona las plantas semanalmente para detectar cochinillas e insectos escama. Usa pesticidas orgánicos cuando sea necesario.',
        'harvest_time': 'Tiempo de Cosecha',
        'harvest_time_desc': 'Cosecha cuando la fruta se torne amarillo dorado y emita aroma dulce (18-22 meses después de plantar).',
        'monitor_sensors': 'Monitorear Sensores',
        'monitor_sensors_desc': 'Revisa los datos en tiempo real del suelo y del entorno',
        'fertilization_guide': 'Guía de Fertilización',
        'fertilization_guide_desc': 'Obtén recomendaciones de fertilización',
        'growth_forecast': 'Pronóstico de Crecimiento',
        'growth_forecast_desc': 'Predice la etapa de crecimiento y el calendario de cosecha',
        'disease_database': 'Base de Datos de Enfermedades',
        'disease_database_desc': 'Aprende sobre las enfermedades de la piña',
        'about_system': 'Acerca del Sistema',
        'about_system_desc': 'Información y ayuda del sistema',
        'footer_copyright': '© 2026 AgriPinya - Sistema de Detección de Enfermedades de la Piña',
        'footer_tagline': 'Ayudando a los agricultores de piña a lograr cosechas más saludables',
        'analyze': 'Analizar',
        'upload': 'Cargar',
        'results': 'Resultados',
        'disease': 'Enfermedad',
        'confidence': 'Confianza',
        'severity': 'Gravedad',
        'high': 'Alto',
        'medium': 'Medio',
        'low': 'Bajo',
        'treatment': 'Tratamiento',
        'recommendations': 'Recomendaciones',
        'history': 'Historial',
        'alerts': 'Alertas',
        'trends': 'Tendencias',
        'export': 'Exportar',
        'weather_alert': 'Alerta meteorológica',
        'optimal_spray': 'Condiciones óptimas de pulverización',
        'high_risk': 'Condiciones de alto riesgo',
        'disease_spread': 'Riesgo de propagación de enfermedades',
        'at_risk': 'En Riesgo',
        'no_risk': 'Sin Riesgo',
        # Additional UI keys added during i18n wiring
        'refresh': 'Actualizar',
        'back_to_dashboard': 'Volver al Panel',
        'refresh_all': 'Actualizar Todo',
        'sensor_monitoring_title': 'Monitoreo de Sensores',
        'sensor_monitoring_subtitle': 'Monitoreo en tiempo real de los sensores en la granja de piñas',
        'temp_humidity_title': 'Monitoreo de Temperatura y Humedad',
        'temp_humidity_subtitle': 'Monitoreo en tiempo real de temperatura y humedad',
        'diseases_title': 'Enfermedades de la Piña',
        'diseases_subtitle': 'Guía completa de enfermedades de la piña, síntomas y tratamientos',
        'soil_moisture_title': 'Monitoreo de Humedad del Suelo',
        'soil_moisture_subtitle': 'Monitoreo en tiempo real de la humedad del suelo',
        'forecast_title': 'Pronóstico de Crecimiento',
        'forecast_subtitle': 'Predicción de series temporales para crecimiento y calendario de cosecha',
        'about_title': 'Acerca de PiñaSense',
        'about_lead': 'Sistema avanzado impulsado por IA para la detección de enfermedades de la piña para agricultores modernos',
        # Auth / onboarding
        'welcome_back': 'Bienvenido de nuevo',
        'login_subtitle': 'Inicia sesión en tu cuenta AgriPinya',
        'remember_me': 'Recuérdame',
        'forgot_password': '¿Olvidaste la contraseña?',
        'log_in': 'Iniciar sesión',
        'dont_have_account': '¿No tienes una cuenta?',
        'sign_up': 'Regístrate gratis',
        'create_account': 'Crear cuenta',
        'signup_subtitle': 'Únete a AgriPinya y comienza a monitorear tus cultivos',
        'create_account_btn': 'Crear cuenta',
        'already_have_account': '¿Ya tienes cuenta?',
        'log_in_here': 'Inicia sesión aquí',
    }
}

def get_translation(key, language='en'):
    """Get translated text"""
    return TRANSLATIONS.get(language, TRANSLATIONS['en']).get(key, key)

# ============================================
# BATCH & VIDEO PROCESSING
# ============================================
def process_video_for_detection(video_path, max_frames=10):
    """Sample at most max_frames, ignoring rejected or failed detections."""
    cap = cv2.VideoCapture(video_path)
    results = []
    try:
        if not cap.isOpened():
            return None
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        if total_frames <= 0:
            return None
        sample_count = max(1, min(int(max_frames), total_frames))
        indices = sorted(set(int(i) for i in np.linspace(0, total_frames - 1, sample_count)))
        with tempfile.TemporaryDirectory(prefix='pinyasense-frames-') as folder:
            for frame_index in indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                success, frame = cap.read()
                if not success or frame is None:
                    continue
                path = os.path.join(folder, f'frame_{frame_index}.jpg')
                if not cv2.imwrite(path, frame):
                    continue
                result = detector.detect(path)
                if result.get('error') or result.get('not_pineapple') or not result.get('disease'):
                    continue
                result['frame_number'] = frame_index
                result['frame_timestamp'] = frame_index / fps if fps > 0 else None
                results.append(result)
    finally:
        cap.release()
    if not results:
        return None
    counts = {}
    for result in results:
        disease = result['disease']
        counts[disease] = counts.get(disease, 0) + 1
    final_disease = max(counts, key=counts.get)
    matching = [r for r in results if r['disease'] == final_disease]
    return {
        'final_disease': final_disease,
        'avg_confidence': float(np.mean([r.get('confidence', 0) for r in matching])),
        'frame_count': len(results), 'disease_distribution': counts,
        'frame_results': results,
    }

# ============================================
# HISTORICAL TREND ANALYSIS
# ============================================
def analyze_detection_trends(user_id=None, days=30):
    """Analyze detection trends over time"""
    results, _ = _read_detection_results(user_id=user_id, limit=1000)
    
    if not results:
        return {
            'daily_trends': {},
            'disease_timeline': {},
            'total_detections': 0,
            'unique_diseases': 0,
            'period_days': days,
            'message': 'No trend data available yet'
        }
    
    # Filter by date
    cutoff_date = datetime.now() - timedelta(days=days)
    recent_results = [
        r for r in results 
        if (detection_datetime(r.get('timestamp')) or datetime.min) > cutoff_date
    ]
    
    if not recent_results:
        return {
            'daily_trends': {},
            'disease_timeline': {},
            'total_detections': 0,
            'unique_diseases': 0,
            'period_days': days,
            'message': 'No trend data available in the selected period'
        }
    
    # Organize by date
    trends = {}
    disease_timeline = {}
    
    for result in recent_results:
        date = detection_datetime(result.get('timestamp')).date().isoformat()
        disease = result.get('disease', 'Unknown')
        
        if date not in trends:
            trends[date] = {'count': 0, 'diseases': {}}
        trends[date]['count'] += 1
        trends[date]['diseases'][disease] = trends[date]['diseases'].get(disease, 0) + 1
        
        if disease not in disease_timeline:
            disease_timeline[disease] = []
        disease_timeline[disease].append(date)
    
    return {
        'daily_trends': trends,
        'disease_timeline': disease_timeline,
        'total_detections': len(recent_results),
        'unique_diseases': len(disease_timeline),
        'period_days': days
    }

# ============================================
# DATA EXPORT (CSV & PDF)
# ============================================
def generate_csv_report(user_id=None, limit=1000, filters=None):
    """Generate CSV report of detection history"""
    filters = filters or {'scope': 'detections'}
    scope = filters.get('scope', 'detections')
    if scope == 'detections':
        results, _ = _read_detection_results(user_id=user_id, limit=limit)
        results = _filter_detection_results(results, filters)
    else:
        results = get_sensor_data_firestore(filters.get('sensor_type') or 'soil_moisture', user_id=user_id, limit=limit, timeout=8)
        results = _filter_sensor_results(results, filters)
    
    output = StringIO()
    writer = csv.writer(output)
    
    # Header
    if scope == 'detections':
        writer.writerow(['Date', 'Time', 'Disease', 'Confidence', 'Severity', 'Method', 'Media Type', 'Farm'])
    else:
        writer.writerow(['Date', 'Time', 'Sensor Type', 'Value', 'Unit', 'Farm'])
    
    if not results:
        if scope == 'detections':
            writer.writerow(['No data available', '', '', '', '', '', '', ''])
        else:
            writer.writerow(['No data available', '', '', '', '', ''])
        return output.getvalue()
    
    # Data rows
    for result in results:
        parsed = detection_datetime(result.get('timestamp'))
        timestamp = parsed.isoformat().split('T') if parsed else []
        date = timestamp[0] if timestamp else 'Unknown'
        time = timestamp[1][:8] if len(timestamp) > 1 else 'Unknown'
        
        if scope == 'detections':
            writer.writerow([
                date,
                time,
                result.get('disease', 'Unknown'),
                f"{result.get('confidence', 0):.2%}",
                result.get('severity', 'Unknown'),
                result.get('method', 'unknown'),
                result.get('media_type', 'image'),
                result.get('farm', 'Unknown')
            ])
        else:
            sensor_data = result.get('data', {}) if isinstance(result.get('data'), dict) else {}
            writer.writerow([
                date,
                time,
                result.get('sensor_type', 'Unknown'),
                sensor_data.get('value', sensor_data.get('humidity', sensor_data.get('temperature', result.get('value', 'Unknown')))),
                sensor_data.get('unit') or result.get('unit', ''),
                result.get('farm', 'Unknown')
            ])
    
    return output.getvalue()


# ============================================
# SCHEDULED REPORTS
# ============================================
def send_scheduled_reports(filters=None, recipients=None):
    """Generate CSV/PDF reports and email to configured recipients."""
    try:
        recipients_value = recipients if recipients is not None else os.getenv('REPORT_RECIPIENTS', '')
        if not recipients_value:
            app.logger.info('Scheduled report skipped: REPORT_RECIPIENTS is not configured.')
            return False

        if isinstance(recipients_value, str):
            recipients = [r.strip() for r in recipients_value.split(',') if r.strip()]
        else:
            recipients = [r.strip() for r in recipients_value if r.strip()]

        filters = filters or _normalize_report_filters(
            start_date=os.getenv('REPORT_START_DATE'),
            end_date=os.getenv('REPORT_END_DATE'),
            farm=os.getenv('REPORT_FARM'),
            sensor_type=os.getenv('REPORT_SENSOR_TYPE'),
            media_type=os.getenv('REPORT_MEDIA_TYPE'),
        )
        filters.setdefault('scope', os.getenv('REPORT_SCOPE', 'detections'))

        print(f'Starting scheduled report generation for: {recipients}')

        # Generate CSV
        csv_content = generate_csv_report(limit=1000, filters=filters)

        # Generate PDF if available
        pdf_content = None
        if REPORTLAB_AVAILABLE:
            pdf_content = generate_pdf_report(limit=200, filters=filters)

        # Send to each recipient
        deliveries = []
        for r in recipients:
            subject = f'AgriPinya - Scheduled Detection Report ({datetime.utcnow().date().isoformat()})'
            body = 'Attached are the scheduled detection reports (CSV and PDF if available).'
            attachments = {'detections_report.csv': csv_content}
            if pdf_content:
                attachments['detections_report.pdf'] = pdf_content

            deliveries.append(send_report_email(r, subject, body, attachments=attachments))

        return bool(deliveries) and all(deliveries)
    except Exception as e:
        print('Error in scheduled report job:', str(e))
        return False


WATER_PUMP_SCHEDULES_FILE = os.path.join(PROJECT_ROOT, 'data', 'water_pump_schedules.json')


def _water_pump_schedule_job_id(schedule_id: str) -> str:
    return f'water_pump_schedule_{schedule_id}'


def _water_pump_schedule_path() -> str:
    os.makedirs(os.path.dirname(WATER_PUMP_SCHEDULES_FILE), exist_ok=True)
    return WATER_PUMP_SCHEDULES_FILE


def _load_water_pump_schedules() -> List[Dict]:
    path = _water_pump_schedule_path()
    if not os.path.exists(path):
        return []

    try:
        with open(path, 'r') as f:
            data = json.load(f)
    except Exception:
        return []

    if not isinstance(data, list):
        return []

    schedules = []
    for item in data:
        if isinstance(item, dict) and item.get('id'):
            schedules.append(item)
    return schedules


def _save_water_pump_schedules(schedules: List[Dict]) -> None:
    path = _water_pump_schedule_path()
    write_json_atomic(path, schedules)


def _normalize_days_of_week(days) -> List[str]:
    if not days:
        return []

    if isinstance(days, str):
        days = [item.strip() for item in days.split(',')]
    if not isinstance(days, (list, tuple, set)):
        return []

    canonical = {
        'mon': 'mon', 'monday': 'mon',
        'tue': 'tue', 'tues': 'tue', 'tuesday': 'tue',
        'wed': 'wed', 'wednesday': 'wed',
        'thu': 'thu', 'thur': 'thu', 'thurs': 'thu', 'thursday': 'thu',
        'fri': 'fri', 'friday': 'fri',
        'sat': 'sat', 'saturday': 'sat',
        'sun': 'sun', 'sunday': 'sun',
    }

    normalized = []
    for item in days:
        key = str(item).strip().lower()
        value = canonical.get(key)
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def _parse_schedule_time(time_value: str) -> Dict[str, int]:
    try:
        parsed = datetime.strptime(time_value, '%H:%M')
    except ValueError:
        raise ValueError('time must use HH:MM format')

    return {'hour': parsed.hour, 'minute': parsed.minute}


def _serialize_water_pump_schedule(schedule: Dict) -> Dict:
    serialized = dict(schedule)
    serialized['days_of_week'] = _normalize_days_of_week(serialized.get('days_of_week', []))
    serialized['enabled'] = bool(serialized.get('enabled', True))
    serialized['duration_seconds'] = int(serialized.get('duration_seconds', sensor_monitor.WATER_PUMP_DEFAULT_DURATION))
    serialized['next_run_at'] = None

    job_id = _water_pump_schedule_job_id(serialized['id'])
    if scheduler is not None:
        try:
            job = scheduler.get_job(job_id)
            if job and job.next_run_time:
                serialized['next_run_at'] = job.next_run_time.isoformat()
        except Exception:
            pass

    return serialized


def _register_water_pump_schedule(schedule: Dict) -> bool:
    if scheduler is None:
        return False

    if not schedule.get('enabled', True):
        try:
            scheduler.remove_job(_water_pump_schedule_job_id(schedule['id']))
        except Exception:
            pass
        return False

    schedule_time = _parse_schedule_time(str(schedule.get('time', '06:00')))
    trigger_kwargs = {
        'trigger': 'cron',
        'hour': schedule_time['hour'],
        'minute': schedule_time['minute'],
    }

    days_of_week = _normalize_days_of_week(schedule.get('days_of_week', [])) if schedule.get('schedule_type') == 'weekly' else []
    if days_of_week:
        trigger_kwargs['day_of_week'] = ','.join(days_of_week)

    scheduler.add_job(
        _run_water_pump_schedule,
        id=_water_pump_schedule_job_id(schedule['id']),
        args=[schedule['id']],
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        **trigger_kwargs,
    )
    return True


def _sync_water_pump_schedules_to_scheduler() -> None:
    if scheduler is None:
        return

    for schedule in _load_water_pump_schedules():
        try:
            _register_water_pump_schedule(schedule)
        except Exception as e:
            print(f"⚠️  Failed to register water pump schedule {schedule.get('id')}: {e}")


def _run_water_pump_schedule(schedule_id: str) -> bool:
    schedules = _load_water_pump_schedules()
    schedule = next((item for item in schedules if item.get('id') == schedule_id), None)
    if not schedule or not schedule.get('enabled', True):
        return False

    # Automatic (moisture-based) watering takes over irrigation decisions when it's
    # on, so fixed-time schedules skip themselves to avoid double-watering the field.
    if _auto_pump_enabled():
        schedule['last_run_at'] = datetime.now().isoformat()
        schedule['last_run_status'] = 'skipped_auto_mode'
        schedule['updated_at'] = datetime.now().isoformat()
        updated_schedules = [schedule if item.get('id') == schedule_id else item for item in schedules]
        _save_water_pump_schedules(updated_schedules)
        print(f"Water pump schedule {schedule_id} skipped: automatic watering is ON")
        return False

    duration_seconds = int(schedule.get('duration_seconds', sensor_monitor.WATER_PUMP_DEFAULT_DURATION))
    result = sensor_monitor.run_water_pump_for_seconds(duration_seconds)
    schedule['last_run_at'] = datetime.now().isoformat()
    schedule['last_run_status'] = 'error' if result.get('error') else 'completed'
    schedule['updated_at'] = datetime.now().isoformat()

    updated_schedules = []
    for item in schedules:
        if item.get('id') == schedule_id:
            updated_schedules.append(schedule)
        else:
            updated_schedules.append(item)
    _save_water_pump_schedules(updated_schedules)

    return not bool(result.get('error'))


AUTO_PUMP_SETTINGS_FILE = os.path.join(PROJECT_ROOT, 'data', 'auto_pump_settings.json')


def _auto_pump_settings_path() -> str:
    os.makedirs(os.path.dirname(AUTO_PUMP_SETTINGS_FILE), exist_ok=True)
    return AUTO_PUMP_SETTINGS_FILE


def _load_auto_pump_settings() -> Dict:
    path = _auto_pump_settings_path()
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    # First run / unreadable file: seed from the env var default so existing
    # deployments that set AUTO_PUMP_ENABLED keep working, then persist it.
    default_enabled = os.getenv('AUTO_PUMP_ENABLED', '0').strip().lower() in ('1', 'true', 'yes', 'on')
    settings = {'enabled': default_enabled}
    _save_auto_pump_settings(settings)
    return settings


def _save_auto_pump_settings(settings: Dict) -> None:
    path = _auto_pump_settings_path()
    write_json_atomic(path, settings)


def _auto_pump_enabled() -> bool:
    return bool(_load_auto_pump_settings().get('enabled', False))


_AUTO_PUMP_STATE = {
    'consecutive_dry': 0,
    'last_run_ts': None,
    'last_seen_status': None,
    'last_seen_ts': None,
}


def auto_irrigation_tick() -> bool:
    """Auto-trigger irrigation when soil stays dry (guarded by env flags)."""
    if not _auto_pump_enabled():
        return False

    # Avoid running twice under Flask debug reloader (parent + child).
    # In production WERKZEUG_RUN_MAIN is usually unset.
    run_main = os.environ.get('WERKZEUG_RUN_MAIN')
    if run_main not in (None, 'true'):
        return False

    interval_seconds = int(os.getenv('AUTO_PUMP_INTERVAL_SECONDS', '60'))
    cooldown_seconds = int(os.getenv('AUTO_PUMP_COOLDOWN_SECONDS', '600'))
    duration_seconds = int(os.getenv('AUTO_PUMP_DURATION_SECONDS', os.getenv('WATER_PUMP_DEFAULT_DURATION', '5')))
    dry_confirmations = int(os.getenv('AUTO_PUMP_DRY_CONFIRMATIONS', '2'))

    now = datetime.now()

    try:
        # Read all configured soil sensors (one per zone) and decide watering based
        # on SOIL_ZONE_WATER_POLICY (default: 'any' zone dry triggers irrigation).
        reading = sensor_monitor.read_soil_moisture_all()
        _AUTO_PUMP_STATE['last_seen_ts'] = now.isoformat()

        summary = reading.get('summary') if isinstance(reading, dict) else None
        if not summary or summary.get('valid_zones', 0) == 0:
            _AUTO_PUMP_STATE['last_seen_status'] = 'error'
            _AUTO_PUMP_STATE['consecutive_dry'] = 0
            return False

        should_water = bool(summary.get('watering_recommended'))
        status = 'dry' if should_water else 'wet'
        _AUTO_PUMP_STATE['last_seen_status'] = status

        if should_water:
            _AUTO_PUMP_STATE['consecutive_dry'] += 1
        else:
            _AUTO_PUMP_STATE['consecutive_dry'] = 0

        # Cooldown check
        last_run = _AUTO_PUMP_STATE.get('last_run_ts')
        if last_run:
            try:
                last_run_dt = datetime.fromisoformat(last_run)
                if (now - last_run_dt).total_seconds() < cooldown_seconds:
                    return False
            except Exception:
                # If parsing fails, reset last run
                _AUTO_PUMP_STATE['last_run_ts'] = None

        if _AUTO_PUMP_STATE['consecutive_dry'] < dry_confirmations:
            return False

        # Trigger pump
        print(
            f"💧 AUTO_PUMP: soil is DRY for {_AUTO_PUMP_STATE['consecutive_dry']} checks; "
            f"running pump for {duration_seconds}s (interval={interval_seconds}s, cooldown={cooldown_seconds}s)"
        )
        result = sensor_monitor.run_water_pump_for_seconds(duration_seconds)
        if isinstance(result, dict) and not result.get('error'):
            _AUTO_PUMP_STATE['last_run_ts'] = now.isoformat()
            _AUTO_PUMP_STATE['consecutive_dry'] = 0
            return True

        print(f"⚠️  AUTO_PUMP: pump run failed: {result}")
        return False
    except Exception as e:
        print(f"⚠️  AUTO_PUMP: tick failed: {e}")
        _AUTO_PUMP_STATE['consecutive_dry'] = 0
        return False


# Start scheduler if APScheduler available
if SCHEDULER_AVAILABLE:
    try:
        scheduler = BackgroundScheduler()
        # Schedule every 7 days
        scheduler.add_job(send_scheduled_reports, 'interval', days=7, id='weekly_reports', replace_existing=True)

        # Auto irrigation: always scheduled, but auto_irrigation_tick() itself checks
        # _auto_pump_enabled() (persisted in data/auto_pump_settings.json) and no-ops
        # when disabled. This lets the Water Pump page toggle it on/off at runtime
        # without needing a server restart.
        pump_interval_seconds = int(os.getenv('AUTO_PUMP_INTERVAL_SECONDS', '60'))
        scheduler.add_job(
            auto_irrigation_tick,
            'interval',
            seconds=pump_interval_seconds,
            id='auto_irrigation',
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        print(f"Scheduler: auto irrigation check every {pump_interval_seconds}s (currently {'ON' if _auto_pump_enabled() else 'OFF'})")

        _sync_water_pump_schedules_to_scheduler()
        scheduler.start()
    except Exception as e:
        print('Failed to start scheduler:', str(e))
else:
    print('APScheduler not available. Weekly scheduled reports are disabled. You can still trigger via /api/admin/trigger-weekly-report')


@app.route('/api/admin/trigger-weekly-report', methods=['POST'])
@admin_required
def trigger_weekly_report():
    """Manual trigger for the weekly report (admin use)."""
    try:
        filters = _build_report_filters_from_request()
        filters['scope'] = request.args.get('scope', request.form.get('scope', 'detections'))
        recipient_override = request.args.get('recipients') or request.form.get('recipients')
        success = send_scheduled_reports(filters=filters, recipients=recipient_override)
        if success:
            return jsonify({'status': 'ok', 'message': 'Weekly report sent or queued'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Failed to send weekly report'}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

def generate_pdf_report(user_id=None, limit=100, filters=None):
    """Generate PDF report with graphs and statistics"""
    if not REPORTLAB_AVAILABLE:
        return None

    filters = filters or {'scope': 'detections'}
    scope = filters.get('scope', 'detections')

    if scope == 'detections':
        results, _ = _read_detection_results(user_id=user_id, limit=limit)
        results = _filter_detection_results(results, filters)
        trends = analyze_detection_trends(user_id=user_id, days=30)
    else:
        results = get_sensor_data_firestore(filters.get('sensor_type') or 'soil_moisture', user_id=user_id, limit=limit)
        results = _filter_sensor_results(results, filters)
        trends = None

    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                           rightMargin=0.5*inch, leftMargin=0.5*inch,
                           topMargin=0.75*inch, bottomMargin=0.75*inch)

    elements = []
    styles = getSampleStyleSheet()

    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1e40af'),
        spaceAfter=30,
        alignment=1
    )
    elements.append(Paragraph('AgriPinya Detection Report' if scope == 'detections' else 'AgriPinya Sensor Report', title_style))
    elements.append(Spacer(1, 0.3*inch))

    if filters:
        filter_lines = []
        if filters.get('start_date'):
            filter_lines.append(f"Start date: {filters['start_date'].strftime('%Y-%m-%d')}")
        if filters.get('end_date'):
            filter_lines.append(f"End date: {filters['end_date'].strftime('%Y-%m-%d')}")
        if filters.get('farm'):
            filter_lines.append(f"Farm: {filters['farm']}")
        if filters.get('sensor_type'):
            filter_lines.append(f"Sensor: {filters['sensor_type']}")
        if filters.get('media_type'):
            filter_lines.append(f"Media: {filters['media_type']}")
        if filter_lines:
            elements.append(Paragraph('Applied Filters', styles['Heading2']))
            for line in filter_lines:
                elements.append(Paragraph(line, styles['BodyText']))
            elements.append(Spacer(1, 0.2*inch))

    # Summary statistics
    total_detections = len(results)
    disease_counts = {}
    avg_confidence = 0

    if scope == 'detections':
        for result in results:
            disease = result.get('disease', 'Unknown')
            disease_counts[disease] = disease_counts.get(disease, 0) + 1
            avg_confidence += result.get('confidence', 0)

        avg_confidence /= total_detections if total_detections > 0 else 1

        if total_detections == 0:
            elements.append(Paragraph('No detection data is available yet.', styles['BodyText']))
            elements.append(Spacer(1, 0.2*inch))
        elif trends and trends.get('message'):
            elements.append(Paragraph(trends['message'], styles['BodyText']))
            elements.append(Spacer(1, 0.2*inch))

        summary_data = [
            ['Metric', 'Value'],
            ['Total Detections', str(total_detections)],
            ['Average Confidence', f'{avg_confidence:.1%}'],
            ['Unique Diseases Detected', str(len(disease_counts))],
            ['Report Date', datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
        ]
    else:
        # Sensor report summary
        summary_data = [
            ['Metric', 'Value'],
            ['Total Readings', str(total_detections)],
            ['Sensor Type', str(filters.get('sensor_type') or 'All')],
            ['Report Date', datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
        ]

    summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))

    elements.append(summary_table)
    elements.append(Spacer(1, 0.3*inch))

    if scope == 'detections':
        # Disease distribution
        elements.append(Paragraph('Disease Distribution', styles['Heading2']))
        disease_data = [['Disease', 'Count', 'Percentage']]

        if disease_counts:
            for disease, count in sorted(disease_counts.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / total_detections * 100) if total_detections > 0 else 0
                disease_data.append([disease, str(count), f'{percentage:.1f}%'])
        else:
            disease_data.append(['No data available', '0', '0.0%'])

        disease_table = Table(disease_data, colWidths=[2.5*inch, 1*inch, 1.5*inch])
        disease_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3b82f6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey])
        ]))

        elements.append(disease_table)
        elements.append(Spacer(1, 0.2*inch))
    else:
        elements.append(Paragraph('Sensor Readings', styles['Heading2']))
        sensor_data = [['Date', 'Time', 'Sensor Type', 'Value', 'Unit', 'Farm']]
        for result in results[:20]:
            timestamp = str(result.get('timestamp', '')).split('T')
            date = timestamp[0] if timestamp else 'Unknown'
            time = timestamp[1][:8] if len(timestamp) > 1 else 'Unknown'
            payload = result.get('data', {}) if isinstance(result.get('data'), dict) else {}
            sensor_data.append([
                date,
                time,
                result.get('sensor_type', 'Unknown'),
                payload.get('humidity') or payload.get('temperature') or result.get('value', 'Unknown'),
                payload.get('unit') or result.get('unit', ''),
                result.get('farm', 'Unknown')
            ])

        sensor_table = Table(sensor_data, colWidths=[1.1*inch, 0.9*inch, 1.4*inch, 1*inch, 0.8*inch, 1.1*inch])
        sensor_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3b82f6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey])
        ]))
        elements.append(sensor_table)
        elements.append(Spacer(1, 0.2*inch))

    doc.build(elements)
    buffer.seek(0)
    return buffer

# ============================================
# WEATHER-BASED RECOMMENDATIONS
# ============================================
def get_weather_recommendations(temp, humidity):
    """Get recommendations based on current weather conditions"""
    recommendations = {
        'spray_conditions': 'unfavorable',
        'risk_level': 'moderate',
        'actions': [],
        'warnings': []
    }
    
    # Optimal conditions: 20-30°C, 60-85% humidity
    if 20 <= temp <= 30 and 60 <= humidity <= 85:
        recommendations['spray_conditions'] = 'optimal'
        recommendations['risk_level'] = 'low'
        recommendations['actions'].append('Good conditions for preventive fungicide spray')
    elif temp > 30 or humidity > 85:
        recommendations['risk_level'] = 'high'
        recommendations['warnings'].append('High temperature and humidity - disease risk ELEVATED')
        recommendations['actions'].append('Increase field inspection frequency')
        recommendations['actions'].append('Consider emergency fungicide application')
    elif temp < 15 or humidity < 50:
        recommendations['risk_level'] = 'low'
        recommendations['warnings'].append('Dry conditions - most fungi dormant')
        recommendations['actions'].append('Focus on pest monitoring')
    
    return recommendations

# ============================================
# DISEASE SPREAD RISK MAP
# ============================================
def calculate_disease_spread_risk(detection_history, field_coordinates=None):
    """Calculate disease spread risk based on recent detections"""
    if not detection_history:
        return {'risk_level': 'low', 'days_to_spread': None}
    
    # Get most recent detections
    recent = detection_history[:10]  # Last 10
    
    # Count disease occurrences in last 7 days
    cutoff = datetime.now() - timedelta(days=7)
    recent_diseases = [
        d for d in recent 
        if ((detection_datetime(d.get('timestamp')) or datetime.min) > cutoff
            and d.get('disease') not in {'Healthy', 'Unknown', 'Not Pineapple', None})
    ]
    
    disease_count = len(recent_diseases)
    disease_frequency = disease_count / 7  # Detections per day
    
    # Risk calculation
    if disease_frequency > 1:
        risk_level = 'critical'
        days_to_spread = 1
    elif disease_frequency > 0.5:
        risk_level = 'high'
        days_to_spread = 3
    elif disease_frequency > 0.2:
        risk_level = 'medium'
        days_to_spread = 7
    else:
        risk_level = 'low'
        days_to_spread = 14
    
    return {
        'risk_level': risk_level,
        'detections_per_day': disease_frequency,
        'days_to_likely_spread': days_to_spread,
        'recent_detection_count': disease_count
    }

@app.route('/')
def landing():
    """Render landing page"""
    return render_template('landing.html')

@app.route('/dashboard')
def index():
    """Render main dashboard - requires authentication and approval."""
    session_token = request.cookies.get('session_token')
    email = verify_session(session_token)
    if not email:
        return render_template('login.html')

    user = get_user_info(email)
    if not user:
        return render_template('login.html')

    if user.get('role') == 'super_admin':
        return redirect('/super-admin/dashboard')

    if user.get('role') == 'staff':
        status = user.get('status', 'pending')
        if status == 'pending':
            return render_template('login.html', message='Your account is still waiting for Admin approval.')
        if status in {'rejected', 'inactive'}:
            return render_template('login.html', message='Your account is not authorized to access PinyaSense.')
        if status != 'approved':
            return render_template('login.html', message='Your account is not authorized to access PinyaSense.')

    return render_template('index.html')

@app.route('/about')
def about():
    """Render about page"""
    blocked = require_staff_page_access()
    if blocked is not None:
        return blocked
    return render_template('about.html')

@app.route('/diseases')
def diseases():
    """Render diseases page"""
    blocked = require_staff_page_access()
    if blocked is not None:
        return blocked
    return render_template('diseases.html')

@app.route('/admin')
@app.route('/admin/staff-requests')
def admin_staff_requests_page():
    """Render staff approval dashboard for admin users."""
    blocked = require_admin_page_access()
    if blocked is not None:
        return blocked
    session_email = verify_session(request.cookies.get('session_token'))
    current_user = get_user_info(session_email) if session_email else None
    dashboard_url = '/super-admin/dashboard' if current_user and current_user.get('role') == 'super_admin' else '/dashboard'
    return render_template('admin_staff.html', dashboard_url=dashboard_url)


@app.route('/super-admin')
@app.route('/super-admin/dashboard')
def super_admin_dashboard_page():
    """Render the separate Super Admin dashboard."""
    blocked = require_super_admin_page_access()
    if blocked is not None:
        return blocked
    return render_template('super_admin_dashboard.html')


@app.route('/admin/notifications')
@app.route('/admin/activity-logs')
@app.route('/admin/alerts')
@app.route('/admin/analytics')
@app.route('/admin/reports')
@app.route('/admin/settings')
def super_admin_section_page():
    """Render protected Super Admin management sections."""
    blocked = require_super_admin_page_access()
    if blocked is not None:
        return blocked
    return render_template('super_admin_section.html', active_page=request.path.rsplit('/', 1)[-1])

@app.route('/login')
def login():
    """Render login page"""
    return render_template('login.html')

@app.route('/signup')
def signup():
    """Render signup page"""
    return render_template('signup.html')


@app.route('/terms')
def terms_of_service():
    """Show terms publicly so visitors can read them before registering."""
    return render_template('legal.html', policy='terms')


@app.route('/privacy')
def privacy_policy():
    """Show the privacy notice before account information is submitted."""
    return render_template('legal.html', policy='privacy')


@app.route('/manifest.webmanifest')
def manifest():
    """Serve PWA manifest from static directory."""
    return send_from_directory('static', 'manifest.webmanifest', mimetype='application/manifest+json')


@app.route('/sw.js')
def service_worker():
    """Serve service worker from root for full-site scope."""
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')

@app.route('/training-results')
def training_results():
    """Show saved detections rather than referencing a missing template."""
    blocked = require_staff_page_access()
    if blocked is not None:
        return blocked
    return render_template('training_results.html')

@app.route('/api/signup', methods=['POST'])
def api_signup():
    """API endpoint for user registration. All new staff accounts start pending."""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400

        fullname = data.get('fullname', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        confirm_password = data.get('confirmPassword', '')
        phone = data.get('phone', '').strip()

        if not fullname:
            return jsonify({'success': False, 'message': 'Full name is required'}), 400
        if not email:
            return jsonify({'success': False, 'message': 'Email is required'}), 400
        if '@' not in email:
            return jsonify({'success': False, 'message': 'Invalid email format'}), 400
        if not password:
            return jsonify({'success': False, 'message': 'Password is required'}), 400
        if len(password) < 8:
            return jsonify({'success': False, 'message': 'Password must be at least 8 characters'}), 400
        if password != confirm_password:
            return jsonify({'success': False, 'message': 'Passwords do not match'}), 400

        result = register_user(fullname, email, password, phone)

        if result['success']:
            try:
                sync_user_firestore(email)
            except Exception as firestore_error:
                print(f'⚠️ Unable to sync new user to Firestore: {firestore_error}')
            try:
                send_welcome_email(email, fullname)
            except Exception:
                pass
            return jsonify(result), 201
        return jsonify(result), 400

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/login', methods=['POST'])
def api_login():
    """API endpoint for user login"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
        
        email = data.get('email', '').strip()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'success': False, 'message': 'Email and password are required'}), 400
        
        # Verify login
        result = verify_login(email, password)
        
        if result['success']:
            response = make_response(jsonify(result), 200)
            response.set_cookie('session_token', result['session_token'], 
                              max_age=30*24*60*60, httponly=True, samesite='Lax')
            return response
        else:
            return jsonify(result), 401
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/super-admins', methods=['POST'])
@admin_required
def api_create_super_admin():
    """Create a separate approved Super Admin account from an admin session."""
    data = request.get_json(silent=True) or {}
    fullname = str(data.get('fullname') or '').strip()
    email = str(data.get('email') or '').strip()
    password = data.get('password') or ''
    confirm_password = data.get('confirmPassword') or ''
    phone = str(data.get('phone') or '').strip()

    if len(password) < 8:
        return jsonify({'success': False, 'message': 'Password must be at least 8 characters'}), 400
    if password != confirm_password:
        return jsonify({'success': False, 'message': 'Passwords do not match'}), 400
    if '@' not in email:
        return jsonify({'success': False, 'message': 'Valid email is required'}), 400

    result = create_super_admin(fullname, email, password, phone)
    if result.get('success'):
        try:
            sync_user_firestore(email)
        except Exception as firestore_error:
            print(f'⚠️ Unable to sync Super Admin to Firestore: {firestore_error}')
    return jsonify(result), 201 if result.get('success') else 400

@app.route('/api/logout', methods=['POST'])
def api_logout():
    """API endpoint for user logout"""
    try:
        session_token = request.cookies.get('session_token')
        
        if session_token:
            invalidate_session(session_token)
        
        response = make_response(jsonify({'success': True, 'message': 'Logged out successfully'}), 200)
        response.set_cookie('session_token', '', max_age=0)
        return response
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/verify-session', methods=['GET'])
def api_verify_session():
    """API endpoint to verify if user is logged in and authorized."""
    try:
        session_token = request.cookies.get('session_token')
        email = verify_session(session_token)

        if not email:
            return jsonify({'authenticated': False}), 200

        user_info = get_user_info(email)
        if not user_info:
            return jsonify({'authenticated': False}), 200

        if user_info.get('role') == 'staff':
            status = user_info.get('status', 'pending')
            if status == 'pending':
                return jsonify({'authenticated': False, 'message': 'Your account is still waiting for Admin approval.'}), 200
            if status in {'rejected', 'inactive'}:
                return jsonify({'authenticated': False, 'message': 'Your account is not authorized to access PinyaSense.'}), 200

        return jsonify({'authenticated': True, 'user': user_info}), 200

    except Exception as e:
        return jsonify({'authenticated': False, 'message': str(e)}), 500

@app.route('/api/admin/staff-requests', methods=['GET'])
@admin_required
def admin_staff_requests():
    """Return pending and relevant staff accounts for admin review."""
    staff_by_email = {account['email']: account for account in list_staff_accounts()}

    if firestore_ready():
        try:
            for document in firestore_db.collection('users').stream():
                account = document.to_dict() or {}
                email = str(account.get('email') or '').strip().lower()
                if not email or account.get('role', 'staff') != 'staff' or email in staff_by_email:
                    continue
                created_at = account.get('created_at')
                staff_by_email[email] = {
                    'email': email,
                    'fullname': account.get('fullname') or 'User',
                    'phone': account.get('phone', ''),
                    'role': 'staff',
                    'status': account.get('status', 'pending'),
                    'created_at': created_at.isoformat() if hasattr(created_at, 'isoformat') else created_at,
                    'last_login': account.get('last_login'),
                }
        except Exception as firestore_error:
            print(f'⚠️ Unable to load Firestore staff accounts: {firestore_error}')

    staff = sorted(staff_by_email.values(), key=lambda account: account.get('created_at') or '')
    return jsonify({'success': True, 'staff': staff}), 200


@app.route('/api/admin/staff-requests/<email>', methods=['PATCH'])
@admin_required
def admin_update_staff_status(email):
    """Approve, reject, or deactivate a staff account."""
    data = request.get_json(silent=True) or {}
    status = (data.get('status') or '').strip().lower()
    if not status:
        return jsonify({'success': False, 'message': 'Status is required'}), 400
    result = update_staff_account_status(email, status)
    if not result.get('success') and firestore_ready():
        document_id = (
            email.strip().lower()
            .replace('.', '_').replace('#', '_').replace('$', '_')
            .replace('[', '_').replace(']', '_').replace('/', '_')
        )
        reference = firestore_db.collection('users').document(document_id)
        snapshot = reference.get()
        if snapshot.exists:
            reference.update({'status': status, 'updated_at': datetime.now().isoformat()})
            result = {'success': True, 'message': 'Staff status updated in Firestore.'}
    if result.get('success'):
        try:
            sync_user_firestore(email, deleted=result.get('user', {}).get('status') == 'deleted')
        except Exception as firestore_error:
            print(f'⚠️ Unable to sync staff status to Firestore: {firestore_error}')
    return jsonify(result), 200 if result.get('success') else 400


@app.route('/api/profile', methods=['PUT'])
@login_required
def api_update_profile():
    """API endpoint to update user profile"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400

        fullname = data.get('fullname', '').strip()
        if not fullname:
            return jsonify({'success': False, 'message': 'Full name is required'}), 400

        result = update_user_fullname(request.user_email, fullname)

        if result.get('success'):
            return jsonify(result), 200

        return jsonify(result), 400

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/forgot-password', methods=['POST'])
def api_forgot_password():
    """API endpoint for password reset request"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
        
        email = data.get('email', '').strip()
        
        if not email:
            return jsonify({'success': False, 'message': 'Email is required'}), 400
        
        # Generate reset code
        result = generate_reset_code(email)
        
        if result['success']:
            # Send email with reset code
            email_sent = send_reset_code_email(email, result['reset_code'])

            if not email_sent:
                return jsonify({
                    'success': False,
                    'message': 'Unable to send reset email. Please verify Gmail SMTP settings and try again.'
                }), 500
            
            return jsonify({
                'success': True,
                'message': 'Password reset code has been sent to your email. Check your inbox or spam folder.'
            }), 200
        
        return jsonify(result), 400
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/reset-password', methods=['POST'])
def api_reset_password():
    """API endpoint for password reset"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
        
        email = data.get('email', '').strip()
        code = data.get('code', '').strip()
        new_password = data.get('new_password', '')
        confirm_password = data.get('confirm_password', '')
        
        # Validate inputs
        if not email or not code or not new_password:
            return jsonify({'success': False, 'message': 'Email, code, and password are required'}), 400
        
        if new_password != confirm_password:
            return jsonify({'success': False, 'message': 'Passwords do not match'}), 400
        
        if len(new_password) < 8:
            return jsonify({'success': False, 'message': 'Password must be at least 8 characters'}), 400
        
        # Reset password
        result = reset_password(email, code, new_password)
        
        return jsonify(result), 200 if result['success'] else 400
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/training-results', methods=['GET'])
@staff_access_required
def api_training_results():
    """Compatibility endpoint for the saved detection records page."""
    results, source = _read_detection_results(user_id=_detection_user_id(), limit=1000)
    return jsonify({'success': True, 'total_results': len(results),
                    'results': results, 'data_source': source}), 200

@app.route('/api/detect', methods=['POST'])
@staff_access_required
def detect_disease():
    """API endpoint for disease detection"""
    try:
        # Check if file is in request
        if 'image' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['image']
        
        # Check if file is selected
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Check if file is allowed
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Allowed: PNG, JPG, JPEG, MP4, MOV, AVI, MKV, WEBM'}), 400
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_' + uuid4().hex[:8]
        unique_filename = f"{timestamp}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)

        is_video = is_video_file(filename)
        detection_filepath = filepath
        detection_media_type = 'video' if is_video else 'image'
        preview_image_filename = unique_filename
        farm = request.form.get('farm') or request.args.get('farm') or request.headers.get('X-Farm')

        if is_video:
            frame_filename, frame_path = extract_video_frame(
                filepath,
                app.config['UPLOAD_FOLDER'],
                f"{timestamp}_{os.path.splitext(filename)[0]}"
            )
            detection_filepath = frame_path
            preview_image_filename = frame_filename
        
        # Detect disease
        result = detector.detect(detection_filepath)

        if result.get('not_pineapple'):
            result['image_path'] = preview_image_filename
            result['media_type'] = detection_media_type
            result['media_path'] = unique_filename
            result['timestamp'] = timestamp
            if farm:
                result['farm'] = farm
            return jsonify(result), 422
        if result.get('error'):
            return jsonify(result), 400
        
        # Add media metadata to result
        result['image_path'] = preview_image_filename
        result['media_type'] = detection_media_type
        result['media_path'] = unique_filename
        result['timestamp'] = datetime.now().isoformat()
        if farm:
            result['farm'] = farm

        _persist_detection_result(result)
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/history', methods=['GET'])
@staff_access_required
def get_history():
    """Read history with the same scope and offline fallback as the dashboard."""
    results, source = _read_detection_results(user_id=_detection_user_id(), limit=50)
    return jsonify({'results': results, 'data_source': source}), 200


@app.route('/uploads/<path:filename>')
@staff_access_required
def uploaded_media(filename):
    """Serve saved media only to its owner or a farm administrator."""
    if filename != os.path.basename(filename) or '\\' in filename:
        return jsonify({'error': 'Media not found'}), 404
    owner = _detection_user_id()
    if owner is not None:
        records = load_local_results(app.config['RESULTS_FOLDER'], user_id=owner)
        permitted = any(filename == os.path.basename(str(row.get(key) or '').replace('\\', '/'))
                        for row in records for key in ('image_path', 'media_path'))
        if not permitted:
            return jsonify({'error': 'Media not found'}), 404
    response = send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    response.headers['Cache-Control'] = 'private, no-store'
    return response

# Disease library shown on the Diseases page; its symptoms also drive the
# Forecast page's problem-to-disease matching.
DISEASE_LIBRARY = [
    {
        'name': 'Heart Rot',
        'scientific_name': 'Phytophthora spp.',
        'symptoms': [
            'Dark spot formation at the fruit core',
            'Foul odor inside the pineapple',
            'Wilting flowers or fruit tissue'
        ],
        'treatment': [
            'Apply fungicide such as metalaxyl',
            'Avoid excessive water around the plant',
            'Remove infected plants immediately'
        ],
        'prevention': [
            'Plant in well-drained areas',
            'Use certified planting materials',
            'Perform regular field inspections'
        ]
    },
    {
        'name': 'Fruit Rot',
        'scientific_name': 'Thielaviopsis paradoxa',
        'symptoms': [
            'Black discoloration on fruit skin',
            'Soft spots on the fruit',
            'Rapid decay after harvest'
        ],
        'treatment': [
            'Use benomyl or thiabendazole',
            'Sanitize wounds on fruit surfaces',
            'Keep harvested fruit dry'
        ],
        'prevention': [
            'Handle fruit carefully during harvest',
            'Prevent cuts and bruises on fruit',
            'Apply post-harvest fungicide treatment'
        ]
    },
    {
        'name': 'Yellow Spot',
        'scientific_name': 'Curvularia spp.',
        'symptoms': [
            'Yellow spots on leaves',
            'Wilting of affected leaves',
            'Reduced fruit quality'
        ],
        'treatment': [
            'Spray copper-based fungicide',
            'Remove infected leaves',
            'Use biological control agents'
        ],
        'prevention': [
            'Keep the field clean',
            'Avoid excessive humidity',
            'Maintain regular fertilization for healthy plants'
        ]
    },
    {
        'name': 'Pink Disease',
        'scientific_name': 'Pantoea citrea',
        'symptoms': [
            'Pink coloration inside the fruit',
            'Soft tissue in affected areas',
            'Water-soaked appearance'
        ],
        'treatment': [
            'No direct cure after infection',
            'Remove infected fruits',
            'Disinfect tools and equipment'
        ],
        'prevention': [
            'Handle fruit properly',
            'Use clean tools during harvest',
            'Control insect pests'
        ]
    },
    {
        'name': 'Healthy',
        'scientific_name': 'N/A',
        'symptoms': [
            'Healthy green leaf color',
            'No spots or discoloration',
            'Normal plant and fruit development'
        ],
        'treatment': [
            'Continue regular maintenance practices'
        ],
        'prevention': [
            'Perform regular fertilization',
            'Provide proper watering levels',
            'Monitor pests and diseases consistently'
        ]
    }
]


@app.route('/api/diseases', methods=['GET'])
def get_diseases():
    """Get list of pineapple diseases information"""
    return jsonify({'diseases': DISEASE_LIBRARY}), 200

@app.route('/api/stats', methods=['GET'])
@staff_access_required
def get_stats():
    """Count the same accessible records used by history and exports."""
    results, source = _read_detection_results(user_id=_detection_user_id(), limit=None)
    counts = {}
    for result in results:
        disease = result.get('disease') or 'Unknown'
        counts[disease] = counts.get(disease, 0) + 1
    return jsonify({
        'total_detections': len(results), 'disease_count': counts,
        'recent_detections': results[:10], 'data_source': source,
    }), 200

# ============================================
# SENSOR MONITORING ROUTES
# ============================================

@app.route('/sensors')
def sensors_dashboard():
    """Render sensor dashboard page"""
    blocked = require_staff_page_access()
    if blocked is not None:
        return blocked
    return render_template('sensors.html')

@app.route('/sensors/soil-moisture')
def soil_moisture_page():
    """Render soil moisture monitoring page"""
    blocked = require_staff_page_access()
    if blocked is not None:
        return blocked
    return render_template('soil_moisture.html')

@app.route('/sensors/water-pump')
def water_pump_page():
    """Render water pump control page"""
    blocked = require_staff_page_access()
    if blocked is not None:
        return blocked
    return render_template('water_pump.html', pump_max_seconds=sensor_monitor.WATER_PUMP_MAX_DURATION)

# Sensor API Endpoints

@app.route('/api/sensors/soil-moisture', methods=['GET'])
@staff_access_required
def get_soil_moisture():
    """Get current soil moisture reading"""
    try:
        reading = sensor_monitor.read_soil_moisture()
        # Save reading only if valid
        if 'error' not in reading:
            sensor_monitor.save_reading('soil_moisture', reading)
            try:
                sensor_monitor.check_and_notify_all_users()
            except Exception:
                pass
            if firestore_ready():
                save_sensor_data_firestore(
                    'soil_moisture',
                    reading,
                    user_id=get_current_firebase_user_id()
                )
        return jsonify(reading), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/sensors/soil-moisture/zones', methods=['GET'])
@staff_access_required
def get_soil_moisture_zones():
    """Get current readings from all configured soil moisture sensors (one per zone)."""
    try:
        result = sensor_monitor.read_soil_moisture_all()
        for zone_reading in result.get('zones', []):
            if 'error' not in zone_reading:
                zone = zone_reading.get('zone')
                sensor_type = f'soil_moisture_zone{zone}' if zone else 'soil_moisture'
                sensor_monitor.save_reading(sensor_type, zone_reading)
                if firestore_ready():
                    save_sensor_data_firestore(
                        sensor_type,
                        zone_reading,
                        user_id=get_current_firebase_user_id()
                    )
        try:
            sensor_monitor.check_and_notify_all_users()
        except Exception:
            pass
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def _is_recorded_arduino_soil_reading(reading):
    value = reading.get('value')
    return (
        not reading.get('error')
        and reading.get('sensor_mode') == 'arduino_analog'
        and not str(reading.get('data_source', '')).lower().startswith('simulated')
        and isinstance(value, (int, float)) and not isinstance(value, bool)
        and 0 <= value <= 100
    )


@app.route('/api/sensors/soil-moisture/arduino-zones', methods=['GET'])
@staff_access_required
def get_arduino_soil_moisture_zones():
    """Prefer recorded Arduino readings; use a read-only display fallback if absent."""
    try:
        now = datetime.now()
        live_zones = []
        for zone_number in range(1, 5):
            readings = sensor_monitor.get_readings(
                f'soil_moisture_zone{zone_number}',
                hours=24,
            )
            for candidate in reversed(readings):
                if not _is_recorded_arduino_soil_reading(candidate):
                    continue
                try:
                    reading_time = datetime.fromisoformat(str(candidate['timestamp']).replace('Z', '+00:00'))
                    if reading_time.tzinfo is not None:
                        reading_time = reading_time.astimezone().replace(tzinfo=None)
                    age_seconds = (now - reading_time).total_seconds()
                except (KeyError, TypeError, ValueError):
                    continue
                if 0 <= age_seconds <= 180:
                    reading = dict(candidate)
                    reading['zone'] = zone_number
                    live_zones.append(reading)
                    break

        if live_zones:
            zones = live_zones
            source = 'arduino_serial'
        else:
            zones = []
            source = 'recent_history'
            for zone_number in range(1, 5):
                readings = sensor_monitor.get_readings(
                    f'soil_moisture_zone{zone_number}',
                    hours=72,
                )
                valid_readings = [reading for reading in readings if _is_recorded_arduino_soil_reading(reading)]
                if valid_readings:
                    reading = dict(valid_readings[-1])
                    reading['zone'] = zone_number
                    zones.append(reading)

        if not zones:
            zones = preview_zones(now)
            source = 'simulated'

        dry_zones = [zone for zone in zones if zone.get('state') == 'DRY']
        return jsonify({
            'zones': zones,
            'source': source,
            'sensor_live': source == 'arduino_serial',
            'summary': {
                'total_zones': 4,
                'valid_zones': len(zones),
                'dry_zones': len(dry_zones),
                'wet_zones': sum(zone.get('state') == 'WET' for zone in zones),
                'moist_zones': sum(zone.get('state') == 'MOIST' for zone in zones),
                'policy': sensor_monitor.SOIL_ZONE_WATER_POLICY,
                'watering_recommended': bool(dry_zones),
            },
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/water-pump/on', methods=['POST'])
@staff_access_required
def water_pump_on():
    """Turn the water pump on."""
    try:
        return jsonify(sensor_monitor.water_pump_on()), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/water-pump/off', methods=['POST'])
@staff_access_required
def water_pump_off():
    """Turn the water pump off."""
    try:
        return jsonify(sensor_monitor.water_pump_off()), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/water-pump/run', methods=['POST'])
@staff_access_required
def water_pump_run():
    """Run the water pump for a short duration."""
    try:
        payload = request.get_json(silent=True) or {}
        duration_seconds = payload.get('duration_seconds', request.args.get('duration_seconds'))
        duration_seconds = int(duration_seconds) if duration_seconds not in (None, '') else None
        if duration_seconds is not None and not 1 <= duration_seconds <= sensor_monitor.WATER_PUMP_MAX_DURATION:
            raise ValueError(f'duration_seconds must be between 1 and {sensor_monitor.WATER_PUMP_MAX_DURATION}')
        return jsonify(sensor_monitor.run_water_pump_for_seconds(duration_seconds)), 200
    except (ValueError, TypeError) as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/water-pump/status', methods=['GET'])
@staff_access_required
def water_pump_status():
    """Get best-effort water pump status."""
    try:
        hardware = sensor_monitor.get_water_pump_hardware_status()
        device = getattr(sensor_monitor, 'water_pump_device', None)
        logical_on = bool(getattr(sensor_monitor, 'water_pump_state', False))
        try:
            if device is not None and hasattr(device, 'value'):
                logical_on = bool(device.value)
        except Exception:
            pass

        return jsonify({
            **hardware,
            'status': ('on' if logical_on else 'off') if hardware['hardware_available'] else 'unavailable',
            'logical_on': logical_on if hardware['hardware_available'] else None,
            'gpio_pin': getattr(sensor_monitor, 'WATER_PUMP_PIN', None),
            'active_low': getattr(sensor_monitor, 'WATER_PUMP_ACTIVE_LOW', None),
            'breaker_pin': getattr(sensor_monitor, 'WATER_PUMP_BREAKER_PIN', None),
            'breaker_required': getattr(sensor_monitor, 'WATER_PUMP_BREAKER_REQUIRED', None),
            'breaker_on': sensor_monitor.is_water_pump_breaker_on(),
            'rearm_required': getattr(sensor_monitor, 'water_pump_rearm_required', None),
            'auto_pump_enabled': _auto_pump_enabled(),
            'timestamp': datetime.now().isoformat(),
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/water-pump/auto', methods=['GET', 'POST'])
@staff_access_required
def water_pump_auto():
    """Get or toggle automatic (moisture-based) watering."""
    try:
        if request.method == 'GET':
            settings = _load_auto_pump_settings()
            return jsonify({
                'enabled': bool(settings.get('enabled', False)),
                'interval_seconds': int(os.getenv('AUTO_PUMP_INTERVAL_SECONDS', '60')),
                'cooldown_seconds': int(os.getenv('AUTO_PUMP_COOLDOWN_SECONDS', '600')),
                'duration_seconds': int(os.getenv('AUTO_PUMP_DURATION_SECONDS', os.getenv('WATER_PUMP_DEFAULT_DURATION', '5'))),
                'dry_confirmations': int(os.getenv('AUTO_PUMP_DRY_CONFIRMATIONS', '2')),
                'consecutive_dry': _AUTO_PUMP_STATE.get('consecutive_dry', 0),
                'last_run_at': _AUTO_PUMP_STATE.get('last_run_ts'),
                'last_seen_status': _AUTO_PUMP_STATE.get('last_seen_status'),
                'last_seen_at': _AUTO_PUMP_STATE.get('last_seen_ts'),
                'scheduler_available': scheduler is not None,
            }), 200

        payload = request.get_json(silent=True) or {}
        if 'enabled' not in payload:
            raise ValueError('enabled (true/false) is required')

        enabled = payload.get('enabled')
        if not isinstance(enabled, bool):
            raise ValueError('enabled must be true or false, not a string or number')
        settings = _load_auto_pump_settings()
        settings['enabled'] = enabled
        settings['updated_at'] = datetime.now().isoformat()
        _save_auto_pump_settings(settings)

        if not enabled:
            _AUTO_PUMP_STATE['consecutive_dry'] = 0

        return jsonify({
            'message': f"Automatic watering turned {'ON' if enabled else 'OFF'}",
            'enabled': enabled,
        }), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/water-pump/schedules', methods=['GET', 'POST'])
@staff_access_required
def water_pump_schedules():
    """List or create scheduled watering jobs."""
    try:
        if request.method == 'GET':
            schedules = [_serialize_water_pump_schedule(item) for item in _load_water_pump_schedules()]
            return jsonify({
                'schedules': schedules,
                'scheduler_available': scheduler is not None,
            }), 200

        payload = request.get_json(silent=True) or {}
        name = str(payload.get('name') or 'Scheduled watering').strip()
        schedule_type = str(payload.get('schedule_type') or 'daily').strip().lower()
        time_value = str(payload.get('time') or '06:00').strip()
        duration_value = payload.get('duration_seconds')
        duration_seconds = int(duration_value) if duration_value not in (None, '') else sensor_monitor.WATER_PUMP_DEFAULT_DURATION
        enabled = payload.get('enabled', True)
        if not isinstance(enabled, bool):
            raise ValueError('enabled must be true or false')
        days_of_week = _normalize_days_of_week(payload.get('days_of_week', []))

        if schedule_type not in ('daily', 'weekly'):
            raise ValueError('schedule_type must be daily or weekly')

        if schedule_type == 'weekly' and not days_of_week:
            raise ValueError('Select at least one day for weekly schedules')

        if not 1 <= duration_seconds <= sensor_monitor.WATER_PUMP_MAX_DURATION:
            raise ValueError(f'duration_seconds must be between 1 and {sensor_monitor.WATER_PUMP_MAX_DURATION}')

        _parse_schedule_time(time_value)

        schedule = {
            'id': uuid4().hex[:12],
            'name': name,
            'schedule_type': schedule_type,
            'time': time_value,
            'days_of_week': days_of_week,
            'duration_seconds': duration_seconds,
            'enabled': enabled,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'last_run_at': None,
            'last_run_status': None,
        }

        schedules = _load_water_pump_schedules()
        schedules.append(schedule)
        _save_water_pump_schedules(schedules)

        if enabled:
            _register_water_pump_schedule(schedule)

        return jsonify({
            'message': 'Watering schedule created',
            'schedule': _serialize_water_pump_schedule(schedule),
        }), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/water-pump/schedules/<schedule_id>', methods=['DELETE'])
@staff_access_required
def delete_water_pump_schedule(schedule_id):
    """Delete a scheduled watering job."""
    try:
        schedules = _load_water_pump_schedules()
        remaining = [item for item in schedules if item.get('id') != schedule_id]

        if len(remaining) == len(schedules):
            return jsonify({'error': 'Schedule not found'}), 404

        _save_water_pump_schedules(remaining)

        if scheduler is not None:
            try:
                scheduler.remove_job(_water_pump_schedule_job_id(schedule_id))
            except Exception:
                pass

        return jsonify({'message': 'Watering schedule deleted'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/sensors/soil-moisture/diagnose', methods=['GET'])
@staff_access_required
def diagnose_soil_moisture():
    """Diagnose soil moisture sensor connectivity"""
    try:
        diagnosis = sensor_monitor.diagnose_soil_moisture_sensor()
        return jsonify(diagnosis), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/sensors/soil-moisture/diagnose/all', methods=['GET'])
@staff_access_required
def diagnose_soil_moisture_all():
    """Diagnose connectivity for every configured soil moisture sensor (all zones)"""
    try:
        diagnosis = sensor_monitor.diagnose_all_soil_moisture_sensors()
        return jsonify(diagnosis), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/sensors/soil-moisture/history', methods=['GET'])
@staff_access_required
def get_soil_moisture_history():
    """Get averaged Arduino soil moisture history."""
    try:
        hours = max(1, min(168, int(request.args.get('hours', 24))))
        readings_by_timestamp = {}
        for zone_number in range(1, 5):
            zone_readings = sensor_monitor.get_readings(
                f'soil_moisture_zone{zone_number}',
                hours,
            )
            for reading in zone_readings:
                if not _is_recorded_arduino_soil_reading(reading):
                    continue
                timestamp = reading.get('timestamp')
                value = reading.get('value')
                if timestamp is None or not isinstance(value, (int, float)):
                    continue
                readings_by_timestamp.setdefault(timestamp, []).append(reading)

        readings = []
        for timestamp, zone_readings in sorted(readings_by_timestamp.items()):
            values = [float(reading['value']) for reading in zone_readings]
            raw_values = [float(reading.get('raw_value', 0)) for reading in zone_readings]
            average = round(sum(values) / len(values))
            status = 'dry' if average <= 30 else 'moist' if average <= 70 else 'wet'
            readings.append({
                'timestamp': timestamp,
                'value': average,
                'unit': '%',
                'status': status,
                'state': status.upper(),
                'raw_value': round(sum(raw_values) / len(raw_values)),
                'sensor_mode': 'arduino_analog',
                'zone_count': len(zone_readings),
                'alert': status != 'moist',
            })

        source = 'recorded_history'
        if not readings:
            readings = preview_history(hours)
            source = 'simulated'

        values = [reading['value'] for reading in readings]
        stats = {
            'count': len(values),
            'average': round(sum(values) / len(values), 1) if values else 0,
            'min': min(values) if values else 0,
            'max': max(values) if values else 0,
            'alerts': sum(1 for reading in readings if reading['alert']),
            'sensor_mode': readings[-1]['sensor_mode'] if readings else 'arduino_analog',
        }
        return jsonify({
            'readings': readings,
            'statistics': stats,
            'source': source,
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/sensors/all', methods=['GET'])
@staff_access_required
def get_all_sensors():
    """Get all sensor readings at once"""
    try:
        soil = sensor_monitor.read_soil_moisture()

        # Save readings
        sensor_monitor.save_reading('soil_moisture', soil)
        try:
            sensor_monitor.check_and_notify_all_users()
        except Exception:
            pass

        if firestore_ready() and 'error' not in soil:
            save_sensor_data_firestore('soil_moisture', soil, user_id=get_current_firebase_user_id())

        return jsonify({
            'soil_moisture': soil,
            'timestamp': datetime.now().isoformat()
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# FERTILIZATION ROUTES
# ============================================

@app.route('/fertilization')
def fertilization_page():
    """Fertilization recommendations are disabled."""
    return jsonify({'error': 'Fertilization recommendations are disabled'}), 404

@app.route('/api/fertilization/recommendations', methods=['GET'])
def get_fertilization_recommendations():
    """Fertilization recommendations are disabled."""
    return jsonify({'error': 'Fertilization recommendations are disabled'}), 404


# ============================================
# REPORTS & NOTIFICATIONS ROUTES
# ============================================

@app.route('/api/reports', methods=['POST'])
@login_required
def create_report():
    """Create a new report entry"""
    try:
        if not firestore_ready():
            return jsonify({'success': False, 'message': 'Firebase is not enabled'}), 503

        data = request.get_json() or {}
        title = data.get('title', '').strip()
        content = data.get('content', '').strip()
        report_type = data.get('type', 'general').strip() or 'general'
        status = data.get('status', 'open').strip() or 'open'

        if not title:
            return jsonify({'success': False, 'message': 'Report title is required'}), 400
        if not content:
            return jsonify({'success': False, 'message': 'Report content is required'}), 400

        user_id = to_firebase_user_id(request.user_email)
        report = {
            'title': title,
            'type': report_type,
            'content': content,
            'status': status,
            'created_by': request.user_email,
            'created_at': datetime.now().isoformat(),
        }

        saved = save_report_firestore(report, user_id=user_id)
        if not saved:
            return jsonify({'success': False, 'message': 'Failed to save report'}), 500

        return jsonify({'success': True, 'message': 'Report created successfully'}), 201
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/reports', methods=['GET'])
@login_required
def list_reports():
    """Get reports for current user"""
    try:
        if not firestore_ready():
            return jsonify({'success': True, 'reports': []}), 200

        limit = int(request.args.get('limit', 50))
        user_id = to_firebase_user_id(request.user_email)
        reports = get_reports_firestore(user_id=user_id, limit=limit)
        return jsonify({'success': True, 'reports': reports}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/notifications', methods=['POST'])
@login_required
def create_notification():
    """Create a notification for current user"""
    try:
        if not firestore_ready():
            return jsonify({'success': False, 'message': 'Firebase is not enabled'}), 503

        data = request.get_json() or {}
        title = data.get('title', '').strip()
        message = data.get('message', '').strip()
        notification_type = data.get('type', 'info').strip() or 'info'

        if not title:
            return jsonify({'success': False, 'message': 'Notification title is required'}), 400
        if not message:
            return jsonify({'success': False, 'message': 'Notification message is required'}), 400

        user_id = to_firebase_user_id(request.user_email)
        notification = {
            'title': title,
            'message': message,
            'type': notification_type,
            'read': False,
            'created_at': datetime.now().isoformat(),
        }

        saved = save_notification_firestore(notification, user_id=user_id)
        if not saved:
            return jsonify({'success': False, 'message': 'Failed to save notification'}), 500

        return jsonify({'success': True, 'message': 'Notification created successfully'}), 201
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/notifications', methods=['GET'])
@login_required
def list_notifications():
    """Get notifications for current user"""
    try:
        if not firestore_ready():
            return jsonify({'success': True, 'notifications': []}), 200

        limit = int(request.args.get('limit', 50))
        user_id = to_firebase_user_id(request.user_email)
        notifications = get_notifications_firestore(user_id=user_id, limit=limit)
        return jsonify({'success': True, 'notifications': notifications}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/notifications/<notification_id>/read', methods=['PUT'])
@login_required
def mark_notification_read(notification_id):
    """Mark a notification as read"""
    try:
        if not firestore_ready():
            return jsonify({'success': False, 'message': 'Firebase is not enabled'}), 503

        updated = mark_notification_read_firestore(notification_id, user_id=to_firebase_user_id(request.user_email))
        if not updated:
            return jsonify({'success': False, 'message': 'Notification not found'}), 404

        return jsonify({'success': True, 'message': 'Notification marked as read'}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================
# GROWTH FORECASTING ROUTES
# ============================================

@app.route('/forecast')
def forecast_page():
    """Render growth and harvest forecast page"""
    blocked = require_staff_page_access()
    if blocked is not None:
        return blocked
    return render_template('forecast.html', monitoring=monitoring_options())

# Plant monitoring records (plots, status logs, problem reports, growth
# predictions) live in Firestore next to the app's other collections.
monitoring_store = PlantMonitoringStore(firestore_db)
problem_recommender = ProblemRecommender(
    detector=detector,
    disease_library=DISEASE_LIBRARY,
    growth_forecaster=growth_forecaster,
)
PROBLEM_IMAGE_FOLDER = 'problem_images'
MAX_PROBLEM_IMAGE_BYTES = 10 * 1024 * 1024


def _forecast_kwargs(source, plant=None):
    """Read growth-forecast settings from query args or a request body; saved plot settings fill gaps."""
    plant = plant or {}

    def text(name):
        return str(source.get(name) or '').strip()

    def optional_int(name):
        return int(text(name)) if text(name) else None

    def optional_float(name):
        return float(text(name)) if text(name) else None

    return {
        'planting_date': text('planting_date') or plant.get('planting_date'),
        'horizon_days': int(text('horizon_days') or 30),
        'history_days': int(text('history_days') or 90),
        'profile': (text('profile') or plant.get('farm_profile') or 'standard').lower(),
        'cycle_days': optional_int('cycle_days') if text('cycle_days') else plant.get('cycle_days'),
        'stage_vegetative_end': optional_int('stage_vegetative_end'),
        'stage_pre_flowering_end': optional_int('stage_pre_flowering_end'),
        'stage_fruit_development_end': optional_int('stage_fruit_development_end'),
        'stage_ripening_end': optional_int('stage_ripening_end'),
        'actual_height_cm': optional_float('actual_height_cm'),
        'actual_canopy_cm': optional_float('actual_canopy_cm'),
    }


def _monitoring_owner():
    return get_current_firebase_user_id() or 'anonymous'


def _monitoring_error(message, status=400, errors=None):
    payload = {'success': False, 'message': message, 'error': message}
    if errors:
        payload['errors'] = errors
    return jsonify(payload), status


def _load_plant_history(plant_code, owner_id):
    """Return (plant, status logs, warning) for a plot; a Firestore failure becomes a warning."""
    plant_code = (plant_code or '').strip()
    if not plant_code:
        return None, [], None
    try:
        plant = monitoring_store.get_plant(owner_id, plant_code)
        logs = monitoring_store.list_status_logs(plant['id']) if plant else []
        return plant, logs, None
    except MonitoringStoreUnavailable as e:
        return None, [], str(e)
    except Exception as e:
        print(f"⚠️  Could not load status records for {plant_code}: {e}")
        return None, [], 'Saved status records could not be loaded, so this forecast does not include them.'


def _compute_growth_outlook(plant, status_logs, source):
    """Harvest forecast plus monthly size predictions, both calibrated with the plot's status logs."""
    forecast_kwargs = _forecast_kwargs(source, plant)
    sensor_rows, sensor_warning = _load_forecast_sensor_rows(forecast_kwargs['history_days'])
    forecast = growth_forecaster.forecast_growth_and_harvest(
        **forecast_kwargs, status_logs=status_logs, sensor_rows=sensor_rows
    )
    if sensor_warning:
        forecast['warnings'].append(sensor_warning)
    predictions = growth_forecaster.predict_monthly_growth(forecast, status_logs)
    return forecast, predictions


def _latest_soil_sensor_reading():
    try:
        readings = sensor_monitor.get_readings('soil_moisture', hours=24)
    except Exception:
        return None
    valid = [r for r in readings if 'error' not in r and r.get('state')]
    return valid[-1] if valid else None


def _problem_image_folder():
    return os.path.abspath(os.path.join(app.config['UPLOAD_FOLDER'], PROBLEM_IMAGE_FOLDER))


def _save_problem_image(file_storage):
    """Validate and store an optional problem photo. Returns (relative path, error message)."""
    if not file_storage or not file_storage.filename:
        return None, None

    filename = secure_filename(file_storage.filename)
    extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        return None, 'Image must be a PNG or JPG file.'

    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size == 0:
        return None, 'The selected image is empty.'
    if size > MAX_PROBLEM_IMAGE_BYTES:
        return None, 'Image must be 10 MB or smaller.'

    folder = _problem_image_folder()
    os.makedirs(folder, exist_ok=True)
    stored_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}_{filename}"
    path = os.path.join(folder, stored_name)
    file_storage.save(path)
    if cv2.imread(path) is None:
        os.remove(path)
        return None, 'The uploaded file is not a readable image.'
    return f'{PROBLEM_IMAGE_FOLDER}/{stored_name}', None


def _discard_problem_image(relative_path):
    if not relative_path:
        return
    try:
        os.remove(os.path.join(_problem_image_folder(), os.path.basename(relative_path)))
    except OSError:
        pass


@app.route('/api/forecast/growth-harvest', methods=['GET'])
@staff_access_required
def get_growth_harvest_forecast():
    """Forecast pineapple growth stage and optimal harvest date."""
    try:
        plant, status_logs, monitoring_warning = _load_plant_history(
            request.args.get('plant_code'), _monitoring_owner()
        )
        forecast_kwargs = _forecast_kwargs(request.args, plant)
        sensor_rows, sensor_warning = _load_forecast_sensor_rows(forecast_kwargs['history_days'])
        forecast = growth_forecaster.forecast_growth_and_harvest(
            **forecast_kwargs, status_logs=status_logs, sensor_rows=sensor_rows
        )
        if sensor_warning:
            forecast['warnings'].append(sensor_warning)
        if plant:
            forecast['plant'] = plant
        if monitoring_warning:
            forecast['warnings'].append(monitoring_warning)
        return jsonify(forecast), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/forecast/plants', methods=['GET'])
@login_required
def list_monitored_plants():
    """List the user's plots and whether Firebase is connected."""
    payload = {
        'success': True,
        'plants': [],
        'storage':{'provider': 'firebase', 'connected': monitoring_store.available},
    }
    try:
        payload['plants'] = monitoring_store.list_plants(_monitoring_owner())
    except MonitoringStoreUnavailable as e:
        payload['storage']['message'] = str(e)
    except Exception as e:
        print(f"⚠️  Could not load plots: {e}")
        payload['storage']['message'] = 'Saved plots could not be loaded from Firebase. Please try again.'
    return jsonify(payload), 200


@app.route('/api/forecast/status', methods=['GET'])
@login_required
def get_plant_status():
    """Latest status (current condition) and full status history for a plot."""
    plant_code = (request.args.get('plant_code') or '').strip()
    if not plant_code:
        return _monitoring_error('Plant/Plot ID is required.', 400, {'plant_code': 'Plant/Plot ID is required.'})
    try:
        plant = monitoring_store.get_plant(_monitoring_owner(), plant_code)
        logs = monitoring_store.list_status_logs(plant['id']) if plant else []
    except MonitoringStoreUnavailable as e:
        return _monitoring_error(str(e), 503)
    except Exception as e:
        print(f"❌ Could not load status records: {e}")
        return _monitoring_error('Status records could not be loaded from Firebase. Please try again.', 500)

    history = list(reversed(logs))
    limit = max(1, min(500, request.args.get('limit', default=200, type=int)))
    return jsonify({
        'success': True,
        'plant': plant,
        'latest': history[0] if history else None,
        'history': history[:limit],
        'total': len(history),
    }), 200


@app.route('/api/forecast/status', methods=['POST'])
@login_required
def save_plant_status():
    """Save a new status record (earlier records are kept), then recalculate the forecast."""
    data = request.get_json(silent=True) or {}
    try:
        plant_fields, status_fields = validate_status_submission(data)
    except MonitoringValidationError as e:
        return _monitoring_error(str(e), 400, e.errors)

    try:
        plant, plant_created = monitoring_store.upsert_plant(_monitoring_owner(), plant_fields)
        record = monitoring_store.add_status_log(plant, status_fields)
        logs = monitoring_store.list_status_logs(plant['id'])
    except MonitoringStoreUnavailable as e:
        return _monitoring_error(str(e), 503)
    except Exception as e:
        print(f"❌ Could not save status record: {e}")
        return _monitoring_error('The status record could not be saved to Firebase. Please try again.', 500)

    response = {
        'success': True,
        'message': 'Current pineapple status saved successfully.',
        'record': record,
        'latest': logs[-1] if logs else record,
        'plant': plant,
        'plant_created': plant_created,
        'total': len(logs),
    }
    # Recalculate the harvest forecast and monthly predictions with the new record.
    try:
        forecast, predictions = _compute_growth_outlook(plant, logs, data)
        monitoring_store.save_prediction_snapshot(plant, predictions['prediction_date'], predictions['months'])
        response['forecast_summary'] = forecast['summary']
        response['predictions_saved'] = len(predictions['months'])
    except Exception as e:
        print(f"⚠️  Forecast recalculation failed after saving status: {e}")
        response['recalculation_warning'] = f'Status saved, but the forecast could not be recalculated: {e}'
    return jsonify(response), 201


@app.route('/api/forecast/problems', methods=['POST'])
@login_required
def log_plant_problem():
    """Save a plant problem report together with a generated recommendation."""
    data = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    try:
        plant_fields, problem_fields = validate_problem_submission(data)
    except MonitoringValidationError as e:
        return _monitoring_error(str(e), 400, e.errors)

    if not monitoring_store.available:
        return _monitoring_error(STORE_UNAVAILABLE_MESSAGE, 503)

    image_path, image_error = _save_problem_image(request.files.get('image'))
    if image_error:
        return _monitoring_error(image_error, 400, {'image': image_error})

    try:
        plant, _ = monitoring_store.upsert_plant(_monitoring_owner(), plant_fields)
        logs = monitoring_store.list_status_logs(plant['id'])
        recommendation = problem_recommender.recommend(
            problem_fields,
            latest_status=logs[-1] if logs else None,
            image_path=os.path.join(_problem_image_folder(), os.path.basename(image_path)) if image_path else None,
            sensor_reading=_latest_soil_sensor_reading(),
            planting_date=plant.get('planting_date'),
        )
        record = monitoring_store.add_problem_log(plant, problem_fields, image_path, recommendation)
    except MonitoringStoreUnavailable as e:
        _discard_problem_image(image_path)
        return _monitoring_error(str(e), 503)
    except Exception as e:
        print(f"❌ Could not log plant problem: {e}")
        _discard_problem_image(image_path)
        return _monitoring_error('The problem report could not be saved. Please try again.', 500)

    return jsonify({
        'success': True,
        'message': 'Plant problem logged successfully. Recommendation generated successfully.',
        'record': record,
    }), 201


@app.route('/api/forecast/problems', methods=['GET'])
@login_required
def list_plant_problems():
    """Problem & recommendation history (all plots, or one plot with ?plant_code=)."""
    owner = _monitoring_owner()
    plant_code = (request.args.get('plant_code') or '').strip()
    limit = max(1, min(500, request.args.get('limit', default=200, type=int)))
    try:
        plant_id = None
        if plant_code:
            plant = monitoring_store.get_plant(owner, plant_code)
            if plant is None:
                return jsonify({'success': True, 'problems': [], 'total': 0}), 200
            plant_id = plant['id']
        problems = monitoring_store.list_problem_logs(owner, plant_id=plant_id, limit=limit)
    except MonitoringStoreUnavailable as e:
        return _monitoring_error(str(e), 503)
    except Exception as e:
        print(f"❌ Could not load problem history: {e}")
        return _monitoring_error('Problem history could not be loaded from Firebase. Please try again.', 500)
    return jsonify({'success': True, 'problems': problems, 'total': len(problems)}), 200


@app.route('/api/forecast/problems/<problem_id>', methods=['GET'])
@login_required
def get_plant_problem(problem_id):
    try:
        problem = monitoring_store.get_problem_log(_monitoring_owner(), problem_id)
    except MonitoringStoreUnavailable as e:
        return _monitoring_error(str(e), 503)
    except Exception as e:
        print(f"❌ Could not load problem {problem_id}: {e}")
        return _monitoring_error('The problem record could not be loaded. Please try again.', 500)
    if problem is None:
        return _monitoring_error('Problem record not found.', 404)
    return jsonify({'success': True, 'record': problem}), 200


@app.route('/api/forecast/problems/<problem_id>', methods=['PATCH'])
@login_required
def update_plant_problem_status(problem_id):
    data = request.get_json(silent=True) or {}
    try:
        status = validate_problem_status(data)
    except MonitoringValidationError as e:
        return _monitoring_error(str(e), 400, e.errors)
    try:
        problem = monitoring_store.update_problem_status(_monitoring_owner(), problem_id, status)
    except MonitoringStoreUnavailable as e:
        return _monitoring_error(str(e), 503)
    except Exception as e:
        print(f"❌ Could not update problem {problem_id}: {e}")
        return _monitoring_error('The problem status could not be updated. Please try again.', 500)
    if problem is None:
        return _monitoring_error('Problem record not found.', 404)
    return jsonify({'success': True, 'message': f'Problem status updated to {status}.', 'record': problem}), 200


@app.route('/api/forecast/problems/<problem_id>/image', methods=['GET'])
@login_required
def get_plant_problem_image(problem_id):
    try:
        problem = monitoring_store.get_problem_log(_monitoring_owner(), problem_id)
    except MonitoringStoreUnavailable as e:
        return _monitoring_error(str(e), 503)
    if not problem or not problem.get('image_path'):
        return _monitoring_error('Image not found.', 404)
    filename = os.path.basename(problem['image_path'])
    if not os.path.exists(os.path.join(_problem_image_folder(), filename)):
        return _monitoring_error('Image file is missing on the server.', 404)
    return send_from_directory(_problem_image_folder(), filename)


@app.route('/api/forecast/growth-predictions', methods=['GET'])
@login_required
def get_growth_predictions():
    """Monthly plant height / fruit size predictions, calibrated with the plot's status records.

    Pass persist=1 to store the result as today's prediction snapshot.
    """
    plant, status_logs, warning = _load_plant_history(request.args.get('plant_code'), _monitoring_owner())
    try:
        forecast, predictions = _compute_growth_outlook(plant, status_logs, request.args)
    except ValueError as e:
        return _monitoring_error(str(e), 400)
    except Exception as e:
        print(f"❌ Could not generate growth predictions: {e}")
        return _monitoring_error(f'Predictions could not be generated: {e}', 500)

    saved = 0
    if plant and request.args.get('persist') == '1':
        try:
            saved = monitoring_store.save_prediction_snapshot(
                plant, predictions['prediction_date'], predictions['months']
            )
        except Exception as e:
            print(f"⚠️  Could not save growth predictions: {e}")
            warning = 'Predictions were generated but could not be saved to Firebase.'

    return jsonify({
        'success': True,
        'plant': plant,
        'predictions': predictions,
        'forecast_summary': forecast['summary'],
        'predictions_saved': saved,
        'warning': warning,
    }), 200


@app.route('/api/admin/forecast', methods=['GET'])
@admin_required
def get_admin_forecast():
    """Return saved forecast results for a user to the Super Admin view."""
    if request.current_user.get('role') != 'super_admin':
        return jsonify({'error': 'Super Admin access required.'}), 403

    owner_email = (request.args.get('email') or 'agripinyaa@gmail.com').strip().lower()
    owner_id = to_firebase_user_id(owner_email)
    if not owner_id:
        return jsonify({'error': 'A valid account email is required.'}), 400

    try:
        plants = monitoring_store.list_plants(owner_id)
        forecasts = []
        for plant in plants:
            logs = monitoring_store.list_status_logs(plant['id'])
            forecast, predictions = _compute_growth_outlook(plant, logs, {})
            forecasts.append({
                'plant': plant,
                'summary': forecast.get('summary', {}),
                'warnings': forecast.get('warnings', []),
                'predictions': predictions.get('months', []),
            })
        return jsonify({
            'success': True,
            'email': owner_email,
            'forecasts': forecasts,
            'storage': {'provider': 'firebase', 'connected': monitoring_store.available},
        }), 200
    except MonitoringStoreUnavailable as e:
        return _monitoring_error(str(e), 503)
    except Exception as e:
        print(f"❌ Could not load admin forecast: {e}")
        return _monitoring_error('Forecast results could not be loaded from Firebase.', 500)

# ============================================
# NEW FEATURES: BATCH, TRENDS, EXPORT, WEATHER, SPREAD RISK
# ============================================

@app.route('/api/detect-batch', methods=['POST'])
@staff_access_required
def detect_batch():
    """Process multiple image uploads for batch detection"""
    try:
        user_id = get_current_firebase_user_id()
        files = request.files.getlist('files')
        
        if not files or len(files) == 0:
            return jsonify({'error': 'No files uploaded'}), 400

        if len(files) < 2:
            return jsonify({'error': 'Batch upload requires at least 2 images'}), 400
        
        results = []
        errors = []
        farm = request.form.get('farm') or request.args.get('farm') or request.headers.get('X-Farm')
        
        for file in files:
            if file.filename == '':
                continue
            
            if '.' not in file.filename or file.filename.rsplit('.', 1)[1].lower() not in ALLOWED_IMAGE_EXTENSIONS:
                errors.append(f'{file.filename}: Invalid file type')
                continue
            
            try:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                filename = secure_filename(file.filename)
                unique_filename = f'{timestamp}_{filename}'
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(filepath)
                
                # Detect disease
                detection_result = detector.detect(filepath)
                if detection_result.get('error') or detection_result.get('not_pineapple'):
                    errors.append(f'{file.filename}: {detection_result.get("error", "Not a pineapple image")}')
                    continue
                detection_result['timestamp'] = datetime.now().isoformat()
                detection_result['image_path'] = unique_filename
                detection_result['media_path'] = unique_filename
                detection_result['media_type'] = 'image'
                if farm:
                    detection_result['farm'] = farm
                
                _persist_detection_result(detection_result)
                
                results.append(detection_result)
                
            except Exception as e:
                errors.append(f'{file.filename}: {str(e)}')
        
        return jsonify({
            'batch_count': len(results),
            'error_count': len(errors),
            'results': results,
            'errors': errors if errors else None
        }), 200 if results else 400
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/detect-video', methods=['POST'])
@staff_access_required
def detect_video():
    """Process video upload and extract frames for detection"""
    try:
        user_id = get_current_firebase_user_id()
        
        if 'file' not in request.files:
            return jsonify({'error': 'No video file uploaded'}), 400
        
        file = request.files['file']
        
        if file.filename == '' or not is_video_file(file.filename):
            return jsonify({'error': 'Invalid video file'}), 400
        
        # Save video
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        filename = secure_filename(file.filename)
        unique_filename = f'{timestamp}_{filename}'
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)
        farm = request.form.get('farm') or request.args.get('farm') or request.headers.get('X-Farm')
        
        # Process video
        video_result = process_video_for_detection(filepath, max_frames=10)
        
        if not video_result:
            return jsonify({'error': 'Unable to process video'}), 400
        
        # Save aggregated result to Firebase
        aggregated = {
            'disease': video_result['final_disease'],
            'confidence': video_result['avg_confidence'],
            'method': 'video-batch',
            'media_type': 'video',
            'media_path': unique_filename,
            'timestamp': datetime.now().isoformat(),
            'frame_count': video_result['frame_count'],
            'disease_distribution': video_result['disease_distribution']
        }
        if farm:
            aggregated['farm'] = farm
        
        _persist_detection_result(aggregated)
        
        return jsonify(aggregated), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/trends', methods=['GET'])
@staff_access_required
def get_trends():
    """Get historical trend analysis"""
    try:
        user_id = get_current_firebase_user_id()
        days = request.args.get('days', default=30, type=int)
        
        trends = analyze_detection_trends(user_id=user_id, days=days)
        
        if not trends:
            return jsonify({
                'daily_trends': {},
                'disease_timeline': {},
                'total_detections': 0,
                'unique_diseases': 0,
                'period_days': days,
                'message': 'No trend data available yet'
            }), 200
        
        return jsonify(trends), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/export/csv', methods=['GET'])
@staff_access_required
def export_csv():
    """Export detection history as CSV"""
    try:
        user_id = get_current_firebase_user_id()
        limit = request.args.get('limit', default=1000, type=int)
        filters = _build_report_filters_from_request()
        filters['scope'] = request.args.get('scope', 'detections')

        csv_data = generate_csv_report(user_id=user_id, limit=limit, filters=filters)
        
        response = make_response(csv_data)
        response.headers['Content-Disposition'] = 'attachment; filename=agripinya_report.csv'
        response.headers['Content-Type'] = 'text/csv'
        return response, 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/export/pdf', methods=['GET'])
@staff_access_required
def export_pdf():
    """Export detection history as PDF report"""
    try:
        if not REPORTLAB_AVAILABLE:
            return jsonify({'error': 'PDF generation not available'}), 501
        
        user_id = get_current_firebase_user_id()
        limit = request.args.get('limit', default=100, type=int)
        filters = _build_report_filters_from_request()
        filters['scope'] = request.args.get('scope', 'detections')

        pdf_buffer = generate_pdf_report(user_id=user_id, limit=limit, filters=filters)
        
        if not pdf_buffer:
            return jsonify({'error': 'PDF generation failed'}), 500
        
        response = make_response(pdf_buffer.getvalue())
        response.headers['Content-Disposition'] = 'attachment; filename=agripinya_report.pdf'
        response.headers['Content-Type'] = 'application/pdf'
        return response, 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/weather-recommendations', methods=['GET'])
@staff_access_required
def get_weather_based_recommendations():
    """Use recorded live readings; unavailable weather is not an internal error."""
    readings = sensor_monitor.get_readings('temp_humidity', hours=1)
    for reading in reversed(readings):
        if not reading.get('sensor_live') or reading.get('error'):
            continue
        temp = reading.get('temperature')
        humidity = reading.get('humidity')
        temp = temp.get('value') if isinstance(temp, dict) else temp
        humidity = humidity.get('value') if isinstance(humidity, dict) else humidity
        if (isinstance(temp, (int, float)) and isinstance(humidity, (int, float))
                and math.isfinite(temp) and math.isfinite(humidity)):
            recommendations = get_weather_recommendations(temp, humidity)
            recommendations.update(current_temperature=temp, current_humidity=humidity,
                                   timestamp=reading.get('timestamp'), available=True)
            return jsonify(recommendations), 200
    return jsonify({'available': False, 'message': 'No recent live temperature and humidity readings.',
                    'actions': [], 'warnings': []}), 200

@app.route('/api/disease-spread-risk', methods=['GET'])
@staff_access_required
def get_disease_spread_risk():
    """Calculate disease spread risk based on detection history"""
    try:
        user_id = get_current_firebase_user_id()
        history = get_detection_results_firestore(user_id=user_id, limit=100)
        
        if not history:
            return jsonify({'risk_level': 'low', 'message': 'No detection history'}), 200
        
        spread_risk = calculate_disease_spread_risk(history)
        
        return jsonify(spread_risk), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/translations/<language>', methods=['GET'])
def get_translations(language):
    """Get translations for specified language"""
    try:
        if language not in TRANSLATIONS:
            return jsonify({'error': f'Language {language} not supported'}), 400
        
        return jsonify(TRANSLATIONS[language]), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/supported-languages', methods=['GET'])
def get_supported_languages():
    """Get list of supported languages"""
    return jsonify({
        'languages': list(TRANSLATIONS.keys()),
        'available': ['en', 'tl', 'es']
    }), 200

if __name__ == '__main__':
    use_https = os.getenv('USE_HTTPS', '0') == '1'
    port = int(os.getenv('PORT', '5001'))

    if use_https:
        ssl_context = ('cert.pem', 'key.pem')
        print('🔒 HTTPS mode enabled for camera access')
    else:
        ssl_context = None
        print('🌐 HTTP mode enabled for local laptop access')

    if firestore_ready():
        for user_email in load_users():
            try:
                sync_user_firestore(user_email)
            except Exception as firestore_error:
                print(f'⚠️ Unable to sync existing user {user_email} to Firestore: {firestore_error}')

    app.run(debug=False, use_reloader=False, host='0.0.0.0', port=port, ssl_context=ssl_context)
