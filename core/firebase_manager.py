"""
Firebase Integration Module
Handles real-time database operations for AgriPinya
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Any, Optional

class FirebaseManager:
    """Manages Firebase Realtime Database operations"""

    DISEASE_RESULTS_NODE = 'disease_results'
    SENSOR_DATA_NODE = 'sensor_data'
    LEGACY_DETECTIONS_NODE = 'detections'
    LEGACY_SENSORS_NODE = 'sensors'
    
    def __init__(self, firebase_config=None, enable_offline=True):
        """
        Initialize Firebase Manager
        
        Args:
            firebase_config: Firebase configuration dict or path to JSON file
            enable_offline: Enable offline persistence
        """
        self.db = None
        self.enable_offline = enable_offline
        self.app = None
        
        try:
            import firebase_admin
            from firebase_admin import db, credentials
            self.firebase_admin = firebase_admin
            self.db_module = db
            self.credentials = credentials
            
            # Load config from file or dict
            if isinstance(firebase_config, str):
                with open(firebase_config, 'r') as f:
                    config = json.load(f)
            else:
                config = firebase_config or self._load_from_env()
            
            # Validate required config keys early for clearer errors.
            service_account_key = config.get('service_account_key')
            database_url = config.get('database_url')

            if not service_account_key:
                raise ValueError("Missing FIREBASE_SERVICE_ACCOUNT_KEY")
            if not database_url:
                raise ValueError("Missing FIREBASE_DATABASE_URL")
            if not os.path.exists(service_account_key):
                raise FileNotFoundError(
                    f"Service account key not found: {service_account_key}"
                )

            # Initialize app once, otherwise reuse existing named app.
            try:
                self.app = self.firebase_admin.get_app(name='agripinya')
            except ValueError:
                cred = self.credentials.Certificate(service_account_key)
                self.app = self.firebase_admin.initialize_app(
                    cred,
                    {
                        'databaseURL': database_url,
                        'storageBucket': config.get('storage_bucket', '')
                    },
                    name='agripinya'
                )

            self.db = self.db_module.reference('/', app=self.app)
            
            print("✅ Firebase initialized successfully")
            
        except ImportError:
            print("⚠️  Firebase Admin SDK not installed. Install with: pip install firebase-admin")
            return
        except Exception as e:
            print(f"⚠️  Firebase initialization failed: {e}")
            print("   Using local storage fallback")
    
    def _load_from_env(self) -> Dict:
        """Load Firebase config from environment variables"""
        return {
            'service_account_key': os.getenv('FIREBASE_SERVICE_ACCOUNT_KEY'),
            'database_url': os.getenv('FIREBASE_DATABASE_URL'),
            'storage_bucket': os.getenv('FIREBASE_STORAGE_BUCKET', '')
        }
    
    def is_connected(self) -> bool:
        """Check if connected to Firebase"""
        return self.db is not None
    
    # ============================================
    # DETECTION RESULTS OPERATIONS
    # ============================================
    
    def save_detection_result(self, result: Dict, user_id: str = None) -> bool:
        """
        Save detection result to Firebase
        
        Args:
            result: Detection result dictionary
            user_id: User ID (optional)
        
        Returns:
            Success status
        """
        if not self.is_connected():
            print("⚠️  Firebase not connected")
            return False
        
        try:
            timestamp = result.get('timestamp', datetime.now().strftime('%Y%m%d_%H%M%S'))
            
            # Prepare data
            data = {
                'disease': result.get('disease'),
                'confidence': result.get('confidence'),
                'severity': result.get('severity'),
                'timestamp': timestamp,
                'media_type': result.get('media_type'),
                'media_path': result.get('media_path')
            }
            
            # Choose path
            if user_id:
                path = f'users/{user_id}/{self.DISEASE_RESULTS_NODE}/{timestamp}'
            else:
                path = f'{self.DISEASE_RESULTS_NODE}/{timestamp}'
            
            # Save to Firebase
            self.db.child(path).set(data)
            
            print(f"✅ Result saved to Firebase: {path}")
            return True
            
        except Exception as e:
            print(f"❌ Error saving result: {e}")
            return False
    
    def get_detection_results(self, user_id: str = None, limit: int = 50) -> List[Dict]:
        """
        Get detection results from Firebase
        
        Args:
            user_id: User ID (optional)
            limit: Maximum number of results
        
        Returns:
            List of detection results
        """
        if not self.is_connected():
            return []

        def _read_results(path: str) -> List[Dict]:
            ref = self.db.child(path).order_by_child('timestamp').limit_to_last(limit)
            data = ref.get()
            if not data:
                return []

            results = []
            for key, val in data.items():
                if isinstance(val, dict):
                    val['id'] = key
                    results.append(val)

            return sorted(results, key=lambda x: x.get('timestamp', ''), reverse=True)
        
        try:
            if user_id:
                path = f'users/{user_id}/{self.DISEASE_RESULTS_NODE}'
                legacy_path = f'users/{user_id}/{self.LEGACY_DETECTIONS_NODE}'
            else:
                path = self.DISEASE_RESULTS_NODE
                legacy_path = self.LEGACY_DETECTIONS_NODE

            results = _read_results(path)
            if results:
                return results

            # Backward compatibility for previously stored data.
            return _read_results(legacy_path)
            
        except Exception as e:
            print(f"❌ Error fetching results: {e}")
            return []
    
    # ============================================
    # SENSOR DATA OPERATIONS
    # ============================================
    
    def save_sensor_data(self, sensor_type: str, data: Dict, user_id: str = None) -> bool:
        """
        Save sensor data to Firebase
        
        Args:
            sensor_type: Type of sensor (soil_moisture, temperature_humidity)
            data: Sensor data
            user_id: User ID (optional)
        
        Returns:
            Success status
        """
        if not self.is_connected():
            return False
        
        try:
            timestamp = datetime.now().isoformat()
            
            if user_id:
                path = f'users/{user_id}/{self.SENSOR_DATA_NODE}/{sensor_type}/data/{timestamp}'
            else:
                path = f'{self.SENSOR_DATA_NODE}/{sensor_type}/data/{timestamp}'
            
            self.db.child(path).set(data)
            
            return True
            
        except Exception as e:
            print(f"❌ Error saving sensor data: {e}")
            return False
    
    def get_sensor_data(self, sensor_type: str, user_id: str = None, 
                       hours: int = 24, limit: int = 100) -> List[Dict]:
        """
        Get sensor data from Firebase
        
        Args:
            sensor_type: Type of sensor
            user_id: User ID (optional)
            hours: Hours to look back
            limit: Maximum results
        
        Returns:
            List of sensor readings
        """
        if not self.is_connected():
            return []

        def _read_sensor(path: str) -> List[Dict]:
            ref = self.db.child(path).order_by_child('timestamp').limit_to_last(limit)
            data = ref.get()
            if not data:
                return []

            readings = []
            for key, val in data.items():
                if isinstance(val, dict):
                    val['id'] = key
                    readings.append(val)

            return sorted(readings, key=lambda x: x.get('timestamp', ''), reverse=True)
        
        try:
            if user_id:
                path = f'users/{user_id}/{self.SENSOR_DATA_NODE}/{sensor_type}/data'
                legacy_path = f'users/{user_id}/{self.LEGACY_SENSORS_NODE}/{sensor_type}/data'
            else:
                path = f'{self.SENSOR_DATA_NODE}/{sensor_type}/data'
                legacy_path = f'{self.LEGACY_SENSORS_NODE}/{sensor_type}/data'

            readings = _read_sensor(path)
            if readings:
                return readings

            # Backward compatibility for previously stored data.
            return _read_sensor(legacy_path)
            
        except Exception as e:
            print(f"❌ Error fetching sensor data: {e}")
            return []
    
    # ============================================
    # USER DATA OPERATIONS
    # ============================================
    
    def save_user_profile(self, user_id: str, user_data: Dict) -> bool:
        """Save or update user profile"""
        if not self.is_connected():
            return False
        
        try:
            path = f'users/{user_id}/profile'
            self.db.child(path).set(user_data)
            return True
        except Exception as e:
            print(f"❌ Error saving user profile: {e}")
            return False
    
    def get_user_profile(self, user_id: str) -> Optional[Dict]:
        """Get user profile from Firebase"""
        if not self.is_connected():
            return None
        
        try:
            path = f'users/{user_id}/profile'
            data = self.db.child(path).get()
            return data
        except Exception as e:
            print(f"❌ Error fetching user profile: {e}")
            return None
    
    # ============================================
    # STATISTICS OPERATIONS
    # ============================================
    
    def aggregate_statistics(self, user_id: str = None) -> Dict:
        """
        Get aggregated statistics
        
        Args:
            user_id: User ID (optional)
        
        Returns:
            Statistics dictionary
        """
        if not self.is_connected():
            return {}
        
        try:
            results = self.get_detection_results(user_id=user_id, limit=1000)
            
            if not results:
                return {
                    'total_detections': 0,
                    'disease_counts': {},
                    'avg_confidence': 0
                }
            
            # Calculate stats
            disease_counts = {}
            total_confidence = 0
            
            for result in results:
                disease = result.get('disease', 'Unknown')
                disease_counts[disease] = disease_counts.get(disease, 0) + 1
                total_confidence += result.get('confidence', 0)
            
            avg_confidence = total_confidence / len(results) if results else 0
            
            return {
                'total_detections': len(results),
                'disease_counts': disease_counts,
                'avg_confidence': round(avg_confidence, 4),
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ Error calculating statistics: {e}")
            return {}
    
    def export_data(self, user_id: str = None) -> Dict:
        """Export all user data"""
        if not self.is_connected():
            return {}
        
        try:
            data = {
                'profile': self.get_user_profile(user_id),
                'detections': self.get_detection_results(user_id=user_id, limit=1000),
                'sensor_data': {
                    'soil_moisture': self.get_sensor_data('soil_moisture', user_id=user_id, limit=100),
                    'temperature_humidity': self.get_sensor_data('temperature_humidity', user_id=user_id, limit=100)
                },
                'statistics': self.aggregate_statistics(user_id=user_id)
            }
            return data
        except Exception as e:
            print(f"❌ Error exporting data: {e}")
            return {}

    # ============================================
    # REPORTS OPERATIONS
    # ============================================

    def save_report(self, report: Dict, user_id: str = None) -> bool:
        """
        Save report data to Firebase.

        Args:
            report: Report payload
            user_id: User ID (optional)
        """
        if not self.is_connected():
            return False

        try:
            report_id = report.get('id') or datetime.now().strftime('%Y%m%d_%H%M%S')
            data = {
                'id': report_id,
                'title': report.get('title', ''),
                'type': report.get('type', 'general'),
                'content': report.get('content', ''),
                'status': report.get('status', 'open'),
                'created_at': report.get('created_at', datetime.now().isoformat()),
                'updated_at': datetime.now().isoformat(),
            }

            if user_id:
                path = f'users/{user_id}/reports/{report_id}'
            else:
                path = f'reports/{report_id}'

            self.db.child(path).set(data)
            return True
        except Exception as e:
            print(f"❌ Error saving report: {e}")
            return False

    def get_reports(self, user_id: str = None, limit: int = 50) -> List[Dict]:
        """Get reports from Firebase"""
        if not self.is_connected():
            return []

        try:
            if user_id:
                path = f'users/{user_id}/reports'
            else:
                path = 'reports'

            ref = self.db.child(path).order_by_child('created_at').limit_to_last(limit)
            data = ref.get()

            if not data:
                return []

            reports = []
            for key, val in data.items():
                if isinstance(val, dict):
                    val['id'] = val.get('id', key)
                    reports.append(val)

            return sorted(reports, key=lambda x: x.get('created_at', ''), reverse=True)
        except Exception as e:
            print(f"❌ Error fetching reports: {e}")
            return []

    # ============================================
    # NOTIFICATIONS OPERATIONS
    # ============================================

    def save_notification(self, notification: Dict, user_id: str = None) -> bool:
        """
        Save notification to Firebase.

        Args:
            notification: Notification payload
            user_id: User ID (optional)
        """
        if not self.is_connected():
            return False

        try:
            notification_id = notification.get('id') or datetime.now().strftime('%Y%m%d_%H%M%S')
            data = {
                'id': notification_id,
                'title': notification.get('title', ''),
                'message': notification.get('message', ''),
                'type': notification.get('type', 'info'),
                'read': bool(notification.get('read', False)),
                'created_at': notification.get('created_at', datetime.now().isoformat()),
            }

            if user_id:
                path = f'users/{user_id}/notifications/{notification_id}'
            else:
                path = f'notifications/{notification_id}'

            self.db.child(path).set(data)
            return True
        except Exception as e:
            print(f"❌ Error saving notification: {e}")
            return False

    def get_notifications(self, user_id: str = None, limit: int = 50) -> List[Dict]:
        """Get notifications from Firebase"""
        if not self.is_connected():
            return []

        try:
            if user_id:
                path = f'users/{user_id}/notifications'
            else:
                path = 'notifications'

            ref = self.db.child(path).order_by_child('created_at').limit_to_last(limit)
            data = ref.get()

            if not data:
                return []

            notifications = []
            for key, val in data.items():
                if isinstance(val, dict):
                    val['id'] = val.get('id', key)
                    notifications.append(val)

            return sorted(notifications, key=lambda x: x.get('created_at', ''), reverse=True)
        except Exception as e:
            print(f"❌ Error fetching notifications: {e}")
            return []

    def mark_notification_read(self, notification_id: str, user_id: str = None) -> bool:
        """Mark a notification as read"""
        if not self.is_connected():
            return False

        try:
            if user_id:
                path = f'users/{user_id}/notifications/{notification_id}/read'
            else:
                path = f'notifications/{notification_id}/read'

            self.db.child(path).set(True)
            return True
        except Exception as e:
            print(f"❌ Error marking notification as read: {e}")
            return False


class LocalDataManager:
    """Fallback local data manager when Firebase is not available"""
    
    def __init__(self, storage_dir='data'):
        """Initialize local storage manager"""
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)
    
    def save_detection_result(self, result: Dict, user_id: str = None) -> bool:
        """Save result to local JSON file"""
        try:
            timestamp = result.get('timestamp', datetime.now().strftime('%Y%m%d_%H%M%S'))
            
            if user_id:
                user_dir = os.path.join(self.storage_dir, user_id)
                os.makedirs(user_dir, exist_ok=True)
                filepath = os.path.join(user_dir, f'result_{timestamp}.json')
            else:
                filepath = os.path.join(self.storage_dir, f'result_{timestamp}.json')
            
            with open(filepath, 'w') as f:
                json.dump(result, f, indent=2)
            
            return True
        except Exception as e:
            print(f"❌ Error saving result: {e}")
            return False
    
    def get_detection_results(self, user_id: str = None, limit: int = 50) -> List[Dict]:
        """Get results from local storage"""
        results = []
        try:
            if user_id:
                user_dir = os.path.join(self.storage_dir, user_id)
            else:
                user_dir = self.storage_dir
            
            if os.path.exists(user_dir):
                files = sorted(
                    [f for f in os.listdir(user_dir) if f.startswith('result_')],
                    reverse=True
                )[:limit]
                
                for filename in files:
                    filepath = os.path.join(user_dir, filename)
                    with open(filepath, 'r') as f:
                        results.append(json.load(f))
            
            return results
        except Exception as e:
            print(f"❌ Error fetching results: {e}")
            return []

    def save_report(self, report: Dict, user_id: str = None) -> bool:
        """Save report to local JSON file"""
        try:
            report_id = report.get('id') or datetime.now().strftime('%Y%m%d_%H%M%S')
            data = {
                'id': report_id,
                'title': report.get('title', ''),
                'type': report.get('type', 'general'),
                'content': report.get('content', ''),
                'status': report.get('status', 'open'),
                'created_at': report.get('created_at', datetime.now().isoformat()),
                'updated_at': datetime.now().isoformat(),
            }

            if user_id:
                user_dir = os.path.join(self.storage_dir, user_id)
                os.makedirs(user_dir, exist_ok=True)
                filepath = os.path.join(user_dir, 'reports.json')
            else:
                filepath = os.path.join(self.storage_dir, 'reports.json')

            reports = []
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    reports = json.load(f)

            reports = [r for r in reports if r.get('id') != report_id]
            reports.append(data)

            with open(filepath, 'w') as f:
                json.dump(reports, f, indent=2)

            return True
        except Exception as e:
            print(f"❌ Error saving local report: {e}")
            return False

    def get_reports(self, user_id: str = None, limit: int = 50) -> List[Dict]:
        """Get reports from local storage"""
        try:
            if user_id:
                filepath = os.path.join(self.storage_dir, user_id, 'reports.json')
            else:
                filepath = os.path.join(self.storage_dir, 'reports.json')

            if not os.path.exists(filepath):
                return []

            with open(filepath, 'r') as f:
                reports = json.load(f)

            return sorted(reports, key=lambda x: x.get('created_at', ''), reverse=True)[:limit]
        except Exception as e:
            print(f"❌ Error fetching local reports: {e}")
            return []

    def save_notification(self, notification: Dict, user_id: str = None) -> bool:
        """Save notification to local JSON file"""
        try:
            notification_id = notification.get('id') or datetime.now().strftime('%Y%m%d_%H%M%S')
            data = {
                'id': notification_id,
                'title': notification.get('title', ''),
                'message': notification.get('message', ''),
                'type': notification.get('type', 'info'),
                'read': bool(notification.get('read', False)),
                'created_at': notification.get('created_at', datetime.now().isoformat()),
            }

            if user_id:
                user_dir = os.path.join(self.storage_dir, user_id)
                os.makedirs(user_dir, exist_ok=True)
                filepath = os.path.join(user_dir, 'notifications.json')
            else:
                filepath = os.path.join(self.storage_dir, 'notifications.json')

            notifications = []
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    notifications = json.load(f)

            notifications = [n for n in notifications if n.get('id') != notification_id]
            notifications.append(data)

            with open(filepath, 'w') as f:
                json.dump(notifications, f, indent=2)

            return True
        except Exception as e:
            print(f"❌ Error saving local notification: {e}")
            return False

    def get_notifications(self, user_id: str = None, limit: int = 50) -> List[Dict]:
        """Get notifications from local storage"""
        try:
            if user_id:
                filepath = os.path.join(self.storage_dir, user_id, 'notifications.json')
            else:
                filepath = os.path.join(self.storage_dir, 'notifications.json')

            if not os.path.exists(filepath):
                return []

            with open(filepath, 'r') as f:
                notifications = json.load(f)

            return sorted(notifications, key=lambda x: x.get('created_at', ''), reverse=True)[:limit]
        except Exception as e:
            print(f"❌ Error fetching local notifications: {e}")
            return []
