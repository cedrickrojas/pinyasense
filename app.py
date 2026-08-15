from flask import Flask, render_template, request, jsonify, make_response, send_from_directory
from flask_cors import CORS
import os
from werkzeug.utils import secure_filename
import cv2
import numpy as np
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
from core.auth import register_user, verify_login, verify_session, get_user_info, invalidate_session, update_user_fullname, generate_reset_code, verify_reset_code, reset_password
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
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
RESULTS_FOLDER = 'results'
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
os.makedirs('static/images', exist_ok=True)

# Initialize disease detector
MODEL_PATH = os.getenv('PINEAPPLE_MODEL_PATH') or os.getenv('MODEL_PATH')
detector = PineappleDiseaseDetector(model_path=MODEL_PATH)


# Official Firestore setup using service account
FIREBASE_SERVICE_ACCOUNT_KEY = os.getenv('FIREBASE_SERVICE_ACCOUNT_KEY')
FIREBASE_KEY_CANDIDATES = [
    FIREBASE_SERVICE_ACCOUNT_KEY,
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
    }
    firestore_db.collection('disease_results').document(str(timestamp)).set(data)
    return True


def get_detection_results_firestore(user_id=None, limit=50):
    if not firestore_ready():
        return []

    query = firestore_db.collection('disease_results').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(limit)
    if user_id:
        query = query.where('user_id', '==', user_id)

    docs = query.stream()
    results = []
    for doc in docs:
        item = doc.to_dict() or {}
        item['id'] = doc.id
        results.append(item)
    return results


def _parse_report_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        try:
            return datetime.strptime(value, '%Y-%m-%d')
        except ValueError:
            return None


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
        if filters.get('start_date') and timestamp and timestamp < filters['start_date']:
            continue
        if filters.get('end_date') and timestamp and timestamp > filters['end_date'] + timedelta(days=1):
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
        if filters.get('start_date') and timestamp and timestamp < filters['start_date']:
            continue
        if filters.get('end_date') and timestamp and timestamp > filters['end_date'] + timedelta(days=1):
            continue

        if filters.get('sensor_type'):
            sensor_value = str(result.get('sensor_type') or '').strip().lower()
            if sensor_value != filters['sensor_type'].lower():
                continue

        filtered.append(result)
    return filtered


def aggregate_statistics_firestore(user_id=None):
    results = get_detection_results_firestore(user_id=user_id, limit=1000)
    if not results:
        return {
            'total_detections': 0,
            'disease_counts': {},
            'avg_confidence': 0,
        }

    disease_counts = {}
    total_confidence = 0
    for result in results:
        disease = result.get('disease', 'Unknown')
        disease_counts[disease] = disease_counts.get(disease, 0) + 1
        total_confidence += result.get('confidence', 0) or 0

    return {
        'total_detections': len(results),
        'disease_counts': disease_counts,
        'avg_confidence': round(total_confidence / len(results), 4),
        'last_updated': datetime.now().isoformat(),
    }


def save_sensor_data_firestore(sensor_type, data, user_id=None):
    if not firestore_ready():
        return False

    payload = {
        'sensor_type': sensor_type,
        'user_id': user_id,
        'timestamp': data.get('timestamp', datetime.now().isoformat()),
        'data': data,
    }
    firestore_db.collection('sensor_data').add(payload)
    return True


def get_sensor_data_firestore(sensor_type, user_id=None, limit=100):
    if not firestore_ready():
        return []

    query = firestore_db.collection('sensor_data').where('sensor_type', '==', sensor_type).order_by('timestamp', direction=firestore.Query.DESCENDING).limit(limit)
    if user_id:
        query = query.where('user_id', '==', user_id)

    readings = []
    for doc in query.stream():
        item = doc.to_dict() or {}
        item['id'] = doc.id
        readings.append(item)
    return readings


def save_report_firestore(report, user_id=None):
    if not firestore_ready():
        return False

    report_id = report.get('id') or datetime.now().strftime('%Y%m%d_%H%M%S')
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
    firestore_db.collection('reports').document(report_id).set(data)
    return True


def get_reports_firestore(user_id=None, limit=50):
    if not firestore_ready():
        return []

    query = firestore_db.collection('reports').order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit)
    if user_id:
        query = query.where('user_id', '==', user_id)

    reports = []
    for doc in query.stream():
        item = doc.to_dict() or {}
        item['id'] = doc.id
        reports.append(item)
    return reports


def save_notification_firestore(notification, user_id=None):
    if not firestore_ready():
        return False

    notification_id = notification.get('id') or datetime.now().strftime('%Y%m%d_%H%M%S')
    data = {
        'id': notification_id,
        'title': notification.get('title', ''),
        'message': notification.get('message', ''),
        'type': notification.get('type', 'info'),
        'read': bool(notification.get('read', False)),
        'user_id': user_id,
        'created_at': notification.get('created_at', datetime.now().isoformat()),
    }
    firestore_db.collection('notifications').document(notification_id).set(data)
    return True


def get_notifications_firestore(user_id=None, limit=50):
    if not firestore_ready():
        return []

    query = firestore_db.collection('notifications').order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit)
    if user_id:
        query = query.where('user_id', '==', user_id)

    notifications = []
    for doc in query.stream():
        item = doc.to_dict() or {}
        item['id'] = doc.id
        notifications.append(item)
    return notifications


def mark_notification_read_firestore(notification_id):
    if not firestore_ready():
        return False

    firestore_db.collection('notifications').document(notification_id).set({'read': True}, merge=True)
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


@app.route("/save_sensor")
def save_sensor():
    data = {
        "temperature": 29,
        "humidity": 84,
        "soil_moisture": 63,
        "timestamp": datetime.now()
    }

    if firestore_db is None:
        return jsonify({"message": "Firestore is not initialized", "data": data}), 503

    firestore_db.collection("sensor_data").add(data)

    return jsonify({"message": "Sensor data saved!", "data": data})

def allowed_file(filename):
    """Check if uploaded file has allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_video_file(filename):
    """Check if uploaded file is a supported video type"""
    if '.' not in filename:
        return False
    return filename.rsplit('.', 1)[1].lower() in ALLOWED_VIDEO_EXTENSIONS

def login_required(f):
    """Decorator to check if user is logged in"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        session_token = request.cookies.get('session_token')
        email = verify_session(session_token)
        
        if not email:
            return jsonify({'error': 'Unauthorized. Please log in.'}), 401
        
        request.user_email = email
        return f(*args, **kwargs)
    return decorated_function


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
    """Extract multiple frames from video and analyze each"""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None
    
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    results = []
    
    # Sample frames at intervals
    frame_interval = max(1, total_frames // max_frames)
    
    for i in range(0, total_frames, frame_interval):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        success, frame = cap.read()
        
        if not success or frame is None:
            continue
        
        # Save frame temporarily
        temp_frame_path = os.path.join(app.config['UPLOAD_FOLDER'], f'temp_frame_{i}.jpg')
        cv2.imwrite(temp_frame_path, frame)
        
        # Detect disease in frame
        try:
            result = detector.detect(temp_frame_path)
            result['frame_number'] = i
            result['frame_timestamp'] = i / cap.get(cv2.CAP_PROP_FPS)
            results.append(result)
            os.remove(temp_frame_path)
        except:
            pass
    
    cap.release()
    
    # Aggregate results
    if not results:
        return None
    
    # Find most common disease
    diseases = [r.get('disease') for r in results]
    disease_counts = {}
    for d in diseases:
        disease_counts[d] = disease_counts.get(d, 0) + 1
    
    final_disease = max(disease_counts, key=disease_counts.get)
    avg_confidence = np.mean([r.get('confidence', 0) for r in results])
    
    return {
        'final_disease': final_disease,
        'avg_confidence': float(avg_confidence),
        'frame_count': len(results),
        'disease_distribution': disease_counts,
        'frame_results': results
    }

# ============================================
# HISTORICAL TREND ANALYSIS
# ============================================
def analyze_detection_trends(user_id=None, days=30):
    """Analyze detection trends over time"""
    results = get_detection_results_firestore(user_id=user_id, limit=1000)
    
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
        if datetime.fromisoformat(r.get('timestamp', datetime.now().isoformat())) > cutoff_date
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
        date = result.get('timestamp', '').split('T')[0]
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
    results = get_detection_results_firestore(user_id=user_id, limit=limit)
    filters = filters or {'scope': 'detections'}
    scope = filters.get('scope', 'detections')
    if scope == 'detections':
        results = _filter_detection_results(results, filters)
    else:
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
        timestamp = result.get('timestamp', '').split('T')
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
                sensor_data.get('humidity') or sensor_data.get('temperature') or result.get('value', 'Unknown'),
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
            recipients_value = 'agripinyaa@gmail.com'

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
        filters['scope'] = os.getenv('REPORT_SCOPE', 'detections')

        print(f'Starting scheduled report generation for: {recipients}')

        # Generate CSV
        csv_content = generate_csv_report(limit=1000, filters=filters)

        # Generate PDF if available
        pdf_content = None
        if REPORTLAB_AVAILABLE:
            pdf_content = generate_pdf_report(limit=200, filters=filters)

        # Send to each recipient
        for r in recipients:
            subject = f'AgriPinya - Scheduled Detection Report ({datetime.utcnow().date().isoformat()})'
            body = 'Attached are the scheduled detection reports (CSV and PDF if available).'
            attachments = {'detections_report.csv': csv_content}
            if pdf_content:
                attachments['detections_report.pdf'] = pdf_content

            send_report_email(r, subject, body, attachments=attachments)

        print('Scheduled reports sent.')
        return True
    except Exception as e:
        print('Error in scheduled report job:', str(e))
        return False


WATER_PUMP_SCHEDULES_FILE = os.path.join('data', 'water_pump_schedules.json')


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
    with open(path, 'w') as f:
        json.dump(schedules, f, indent=2)


def _normalize_days_of_week(days) -> List[str]:
    if not days:
        return []

    if isinstance(days, str):
        days = [item.strip() for item in days.split(',')]

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

    days_of_week = _normalize_days_of_week(schedule.get('days_of_week', []))
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


def _auto_pump_enabled() -> bool:
    return os.getenv('AUTO_PUMP_ENABLED', '0').strip().lower() in ('1', 'true', 'yes', 'on')


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
        reading = sensor_monitor.read_soil_moisture()
        _AUTO_PUMP_STATE['last_seen_ts'] = now.isoformat()

        if not isinstance(reading, dict) or reading.get('error'):
            _AUTO_PUMP_STATE['last_seen_status'] = 'error'
            _AUTO_PUMP_STATE['consecutive_dry'] = 0
            return False

        status = str(reading.get('status') or '').strip().lower()
        _AUTO_PUMP_STATE['last_seen_status'] = status

        if status == 'dry':
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

        # Optional: auto irrigation trigger (disabled by default)
        if _auto_pump_enabled():
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
            print(f"Scheduler: auto irrigation enabled every {pump_interval_seconds}s")

        _sync_water_pump_schedules_to_scheduler()
        scheduler.start()
        print('Scheduler started: weekly report job scheduled every 7 days')
    except Exception as e:
        print('Failed to start scheduler:', str(e))
else:
    print('APScheduler not available. Weekly scheduled reports are disabled. You can still trigger via /api/admin/trigger-weekly-report')


@app.route('/api/admin/trigger-weekly-report', methods=['POST'])
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
        results = get_detection_results_firestore(user_id=user_id, limit=limit)
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
        if datetime.fromisoformat(d.get('timestamp', datetime.now().isoformat())) > cutoff
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
    """Render main dashboard - requires authentication"""
    session_token = request.cookies.get('session_token')
    email = verify_session(session_token)
    
    if not email:
        return render_template('login.html')  # Redirect to login if not authenticated
    
    return render_template('index.html')

@app.route('/about')
def about():
    """Render about page"""
    return render_template('about.html')

@app.route('/diseases')
def diseases():
    """Render diseases page"""
    return render_template('diseases.html')

@app.route('/login')
def login():
    """Render login page"""
    return render_template('login.html')

@app.route('/signup')
def signup():
    """Render signup page"""
    return render_template('signup.html')


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
    """Render training results/history page"""
    return render_template('training_results.html')

@app.route('/api/signup', methods=['POST'])
def api_signup():
    """API endpoint for user registration"""
    try:
        data = request.get_json()
        
        # Validate input
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
        
        fullname = data.get('fullname', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        confirm_password = data.get('confirmPassword', '')
        phone = data.get('phone', '').strip()
        
        # Validation
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
        
        # Register user
        result = register_user(fullname, email, password, phone)
        
        if result['success']:
            # Send welcome email
            send_welcome_email(email, fullname)
            return jsonify(result), 201
        else:
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
    """API endpoint to verify if user is logged in"""
    try:
        session_token = request.cookies.get('session_token')
        email = verify_session(session_token)
        
        if email:
            user_info = get_user_info(email)
            return jsonify({'authenticated': True, 'user': user_info}), 200
        else:
            return jsonify({'authenticated': False}), 200
    
    except Exception as e:
        return jsonify({'authenticated': False, 'message': str(e)}), 500

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
def api_training_results():
    """API endpoint to get all training/detection results"""
    try:
        results = []
        results_path = 'results'
        
        if os.path.exists(results_path):
            for filename in sorted(os.listdir(results_path), reverse=True):
                if filename.endswith('.json') and filename != '.gitkeep':
                    filepath = os.path.join(results_path, filename)
                    try:
                        with open(filepath, 'r') as f:
                            data = json.load(f)
                            # Extract timestamp from filename (format: YYYYMMDD_HHMMSS_result.json)
                            timestamp_str = filename.split('_result.json')[0]
                            data['filename'] = filename
                            data['timestamp'] = timestamp_str
                            results.append(data)
                    except:
                        continue
        
        return jsonify({
            'success': True,
            'total_results': len(results),
            'results': results
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/detect', methods=['POST'])
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
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
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
            return jsonify(result), 200
        
        # Save result
        result_filename = f"{timestamp}_result.json"
        result_path = os.path.join(app.config['RESULTS_FOLDER'], result_filename)
        with open(result_path, 'w') as f:
            json.dump(result, f, indent=2)
        
        # Add media metadata to result
        result['image_path'] = preview_image_filename
        result['media_type'] = detection_media_type
        result['media_path'] = unique_filename
        result['timestamp'] = timestamp
        if farm:
            result['farm'] = farm

        # Also store in Firestore when available.
        if firestore_ready():
            save_detection_result_firestore(
                result,
                user_id=get_current_firebase_user_id()
            )
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    """Get detection history"""
    try:
        if firestore_ready():
            firebase_results = get_detection_results_firestore(
                user_id=get_current_firebase_user_id(),
                limit=50
            )
            if firebase_results:
                return jsonify({'results': firebase_results}), 200

        results = []
        if os.path.exists(app.config['RESULTS_FOLDER']):
            for filename in sorted(os.listdir(app.config['RESULTS_FOLDER']), reverse=True):
                if filename.endswith('.json'):
                    filepath = os.path.join(app.config['RESULTS_FOLDER'], filename)
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                        results.append(data)
        
        return jsonify({'results': results[:50]}), 200  # Return last 50 results
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/diseases', methods=['GET'])
def get_diseases():
    """Get list of pineapple diseases information"""
    diseases = {
        'diseases': [
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
    }
    return jsonify(diseases), 200

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get detection statistics"""
    try:
        if firestore_ready():
            firebase_stats = aggregate_statistics_firestore(
                user_id=get_current_firebase_user_id()
            )
            if firebase_stats:
                return jsonify({
                    'total_detections': firebase_stats.get('total_detections', 0),
                    'disease_count': firebase_stats.get('disease_counts', {}),
                    'recent_detections': get_detection_results_firestore(
                        user_id=get_current_firebase_user_id(),
                        limit=10
                    )
                }), 200

        stats = {
            'total_detections': 0,
            'disease_count': {},
            'recent_detections': []
        }
        
        if os.path.exists(app.config['RESULTS_FOLDER']):
            files = [f for f in os.listdir(app.config['RESULTS_FOLDER']) if f.endswith('.json')]
            stats['total_detections'] = len(files)
            
            for filename in sorted(files, reverse=True)[:10]:
                filepath = os.path.join(app.config['RESULTS_FOLDER'], filename)
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    disease = data.get('disease', 'Unknown')
                    
                    # Count diseases
                    if disease not in stats['disease_count']:
                        stats['disease_count'][disease] = 0
                    stats['disease_count'][disease] += 1
                    
                    # Add to recent detections
                    stats['recent_detections'].append({
                        'disease': disease,
                        'confidence': data.get('confidence', 0),
                        'timestamp': data.get('timestamp', '')
                    })
        
        return jsonify(stats), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# SENSOR MONITORING ROUTES
# ============================================

@app.route('/sensors')
def sensors_dashboard():
    """Render sensor dashboard page"""
    return render_template('sensors.html')

@app.route('/sensors/soil-moisture')
def soil_moisture_page():
    """Render soil moisture monitoring page"""
    return render_template('soil_moisture.html')

@app.route('/sensors/temperature-humidity')
def temperature_humidity_page():
    """Render temperature & humidity monitoring page"""
    return render_template('temp_humidity.html')

@app.route('/sensors/water-pump')
def water_pump_page():
    """Render water pump control page"""
    return render_template('water_pump.html')

# Sensor API Endpoints

@app.route('/api/sensors/soil-moisture', methods=['GET'])
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

@app.route('/api/water-pump/on', methods=['POST'])
def water_pump_on():
    """Turn the water pump on."""
    try:
        return jsonify(sensor_monitor.water_pump_on()), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/water-pump/off', methods=['POST'])
def water_pump_off():
    """Turn the water pump off."""
    try:
        return jsonify(sensor_monitor.water_pump_off()), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/water-pump/run', methods=['POST'])
def water_pump_run():
    """Run the water pump for a short duration."""
    try:
        payload = request.get_json(silent=True) or {}
        duration_seconds = payload.get('duration_seconds', request.args.get('duration_seconds'))
        duration_seconds = int(duration_seconds) if duration_seconds not in (None, '') else None
        return jsonify(sensor_monitor.run_water_pump_for_seconds(duration_seconds)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/water-pump/status', methods=['GET'])
def water_pump_status():
    """Get best-effort water pump status."""
    try:
        device = getattr(sensor_monitor, 'water_pump_device', None)
        logical_on = bool(getattr(sensor_monitor, 'water_pump_state', False))
        try:
            if device is not None and hasattr(device, 'value'):
                logical_on = bool(device.value)
        except Exception:
            pass

        return jsonify({
            'status': 'on' if logical_on else 'off',
            'logical_on': logical_on,
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


@app.route('/api/water-pump/schedules', methods=['GET', 'POST'])
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
        duration_seconds = int(payload.get('duration_seconds') or sensor_monitor.WATER_PUMP_DEFAULT_DURATION)
        enabled = bool(payload.get('enabled', True))
        days_of_week = _normalize_days_of_week(payload.get('days_of_week', []))

        if schedule_type not in ('daily', 'weekly'):
            raise ValueError('schedule_type must be daily or weekly')

        if schedule_type == 'weekly' and not days_of_week:
            raise ValueError('Select at least one day for weekly schedules')

        if duration_seconds < 1:
            raise ValueError('duration_seconds must be at least 1')

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

@app.route('/api/sensors/temperature-humidity', methods=['GET'])
def get_temperature_humidity():
    """Get current temperature and humidity reading"""
    try:
        reading = sensor_monitor.read_temperature_humidity()
        # Save only valid live reading
        if 'error' not in reading and reading.get('sensor_live', False):
            sensor_monitor.save_reading('temp_humidity', reading)
            if firestore_ready():
                save_sensor_data_firestore(
                    'temp_humidity',
                    reading,
                    user_id=get_current_firebase_user_id()
                )
        return jsonify(reading), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/sensors/soil-moisture/diagnose', methods=['GET'])
def diagnose_soil_moisture():
    """Diagnose soil moisture sensor connectivity"""
    try:
        diagnosis = sensor_monitor.diagnose_soil_moisture_sensor()
        return jsonify(diagnosis), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/sensors/soil-moisture/history', methods=['GET'])
def get_soil_moisture_history():
    """Get soil moisture history"""
    try:
        hours = int(request.args.get('hours', 24))
        readings = sensor_monitor.get_readings('soil_moisture', hours)
        stats = sensor_monitor.get_statistics('soil_moisture', hours)
        return jsonify({
            'readings': readings,
            'statistics': stats
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/sensors/temperature-humidity/history', methods=['GET'])
def get_temperature_humidity_history():
    """Get temperature and humidity history"""
    try:
        hours = int(request.args.get('hours', 24))
        readings = sensor_monitor.get_readings('temp_humidity', hours)
        stats = sensor_monitor.get_statistics('temp_humidity', hours)
        return jsonify({
            'readings': readings,
            'statistics': stats
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/sensors/all', methods=['GET'])
def get_all_sensors():
    """Get all sensor readings at once"""
    try:
        soil = sensor_monitor.read_soil_moisture()
        temp_humid = sensor_monitor.read_temperature_humidity()
        
        # Save readings
        sensor_monitor.save_reading('soil_moisture', soil)
        try:
            sensor_monitor.check_and_notify_all_users()
        except Exception:
            pass
        sensor_monitor.save_reading('temp_humidity', temp_humid)

        if firestore_ready():
            user_id = get_current_firebase_user_id()
            if 'error' not in soil:
                save_sensor_data_firestore('soil_moisture', soil, user_id=user_id)
            if 'error' not in temp_humid:
                save_sensor_data_firestore('temp_humidity', temp_humid, user_id=user_id)
        
        return jsonify({
            'soil_moisture': soil,
            'temperature_humidity': temp_humid,
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

        updated = mark_notification_read_firestore(notification_id)
        if not updated:
            return jsonify({'success': False, 'message': 'Failed to update notification'}), 500

        return jsonify({'success': True, 'message': 'Notification marked as read'}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================
# GROWTH FORECASTING ROUTES
# ============================================

@app.route('/forecast')
def forecast_page():
    """Render growth and harvest forecast page"""
    return render_template('forecast.html')

@app.route('/api/forecast/growth-harvest', methods=['GET'])
def get_growth_harvest_forecast():
    """Forecast pineapple growth stage and optimal harvest date."""
    try:
        planting_date = request.args.get('planting_date', '').strip() or None
        horizon_days = int(request.args.get('horizon_days', 30))
        history_days = int(request.args.get('history_days', 90))
        profile = request.args.get('profile', 'standard').strip().lower()
        actual_height_cm_raw = request.args.get('actual_height_cm')
        actual_canopy_cm_raw = request.args.get('actual_canopy_cm')

        cycle_days_raw = request.args.get('cycle_days')
        stage_vegetative_end_raw = request.args.get('stage_vegetative_end')
        stage_pre_flowering_end_raw = request.args.get('stage_pre_flowering_end')
        stage_fruit_development_end_raw = request.args.get('stage_fruit_development_end')
        stage_ripening_end_raw = request.args.get('stage_ripening_end')

        cycle_days = int(cycle_days_raw) if cycle_days_raw else None
        stage_vegetative_end = int(stage_vegetative_end_raw) if stage_vegetative_end_raw else None
        stage_pre_flowering_end = int(stage_pre_flowering_end_raw) if stage_pre_flowering_end_raw else None
        stage_fruit_development_end = int(stage_fruit_development_end_raw) if stage_fruit_development_end_raw else None
        stage_ripening_end = int(stage_ripening_end_raw) if stage_ripening_end_raw else None
        actual_height_cm = float(actual_height_cm_raw) if actual_height_cm_raw not in (None, '') else None
        actual_canopy_cm = float(actual_canopy_cm_raw) if actual_canopy_cm_raw not in (None, '') else None

        forecast = growth_forecaster.forecast_growth_and_harvest(
            planting_date=planting_date,
            horizon_days=horizon_days,
            history_days=history_days,
            profile=profile,
            cycle_days=cycle_days,
            stage_vegetative_end=stage_vegetative_end,
            stage_pre_flowering_end=stage_pre_flowering_end,
            stage_fruit_development_end=stage_fruit_development_end,
            stage_ripening_end=stage_ripening_end,
            actual_height_cm=actual_height_cm,
            actual_canopy_cm=actual_canopy_cm,
        )
        return jsonify(forecast), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# NEW FEATURES: BATCH, TRENDS, EXPORT, WEATHER, SPREAD RISK
# ============================================

@app.route('/api/detect-batch', methods=['POST'])
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
            
            if not allowed_file(file.filename):
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
                detection_result['timestamp'] = datetime.now().isoformat()
                detection_result['media_path'] = unique_filename
                detection_result['media_type'] = 'image'
                if farm:
                    detection_result['farm'] = farm
                
                # Save to Firebase
                if firestore_ready():
                    save_detection_result_firestore(detection_result, user_id=user_id)
                
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
        
        if firestore_ready():
            save_detection_result_firestore(aggregated, user_id=user_id)
        
        return jsonify(aggregated), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/trends', methods=['GET'])
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
def get_weather_based_recommendations():
    """Get disease recommendations based on current weather"""
    try:
        # Get latest sensor data
        latest_data = sensor_monitor.read_sensor_data()
        
        if not latest_data or 'temp_humidity' not in latest_data:
            return jsonify({'message': 'No sensor data available'}), 204
        
        temp_humidity = latest_data['temp_humidity']
        temp = temp_humidity.get('temperature')
        humidity = temp_humidity.get('humidity')
        
        if temp is None or humidity is None:
            return jsonify({'message': 'Incomplete sensor data'}), 204
        
        recommendations = get_weather_recommendations(temp, humidity)
        recommendations['current_temperature'] = temp
        recommendations['current_humidity'] = humidity
        recommendations['timestamp'] = datetime.now().isoformat()
        
        return jsonify(recommendations), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/disease-spread-risk', methods=['GET'])
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

    app.run(debug=False, use_reloader=False, host='0.0.0.0', port=port, ssl_context=ssl_context)
