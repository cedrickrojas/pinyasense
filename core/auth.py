"""Authentication module for AgriPinya"""
import json
import os
import hashlib
from datetime import datetime, timedelta
import secrets
import hmac
from functools import wraps
from threading import RLock
from werkzeug.security import generate_password_hash, check_password_hash
from core.json_storage import write_json_atomic

# Keep auth storage tied to this project instead of the shell's current directory.
AUTH_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
USERS_DB = os.path.join(AUTH_DATA_DIR, 'users.json')
SESSIONS_DB = os.path.join(AUTH_DATA_DIR, 'sessions.json')
RESET_CODES_DB = os.path.join(AUTH_DATA_DIR, 'reset_codes.json')
VALID_ROLES = {'admin', 'super_admin', 'staff'}
VALID_STAFF_STATUSES = {'pending', 'approved', 'rejected', 'inactive'}
DEFAULT_ADMIN_EMAILS = {'agripinyaa@gmail.com', 'admin@agripinya.com', 'admin@example.com'}
_AUTH_LOCK = RLock()


def _locked(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with _AUTH_LOCK:
            return function(*args, **kwargs)
    return wrapped


def _invalidate_user_sessions(email):
    sessions = load_sessions()
    save_sessions({token: session for token, session in sessions.items()
                   if isinstance(session, dict) and session.get('email', '').lower() != email.lower()})


def _normalize_user(email, user):
    """Normalize stored account data and enforce role/status defaults."""
    if not isinstance(user, dict):
        return {}

    normalized = dict(user)
    normalized['email'] = (email or '').lower()
    normalized['fullname'] = normalized.get('fullname') or 'User'
    normalized['phone'] = normalized.get('phone', '')
    normalized['created_at'] = normalized.get('created_at') or datetime.now().isoformat()
    normalized['last_login'] = normalized.get('last_login')

    role = str(normalized.get('role', '') or '').strip().lower()
    if role not in VALID_ROLES:
        role = 'admin' if normalized['email'] in DEFAULT_ADMIN_EMAILS else 'staff'
    normalized['role'] = role

    if role in {'admin', 'super_admin'}:
        normalized['status'] = 'approved'
    else:
        status = str(normalized.get('status', '') or '').strip().lower()
        if status not in VALID_STAFF_STATUSES:
            status = 'pending'
        normalized['status'] = status

    return normalized


@_locked
def load_users():
    """Load users from JSON file and normalize role/status fields."""
    if os.path.exists(USERS_DB):
        with open(USERS_DB, 'r') as f:
            raw_users = json.load(f)
        normalized = {}
        for email, user in (raw_users or {}).items():
            normalized[email.lower()] = _normalize_user(email, user)
        if normalized != (raw_users or {}):
            save_users(normalized)
        return normalized
    return {}


def save_users(users):
    """Save users to JSON file"""
    os.makedirs(os.path.dirname(USERS_DB), exist_ok=True)
    normalized = {}
    for email, user in (users or {}).items():
        normalized[email.lower()] = _normalize_user(email, user)
    write_json_atomic(USERS_DB, normalized)


def load_sessions():
    """Load sessions from JSON file"""
    if os.path.exists(SESSIONS_DB):
        with open(SESSIONS_DB, 'r') as f:
            return json.load(f)
    return {}


def save_sessions(sessions):
    """Save sessions to JSON file"""
    write_json_atomic(SESSIONS_DB, sessions)


def hash_password(password):
    """Hash new passwords with a unique salt; legacy hashes remain readable."""
    return generate_password_hash(password, method='pbkdf2:sha256:600000')


@_locked
def create_session(email):
    """Create a new session for user"""
    sessions = load_sessions()
    session_token = secrets.token_urlsafe(32)

    expiry = (datetime.now() + timedelta(days=30)).isoformat()
    sessions[session_token] = {
        'email': email,
        'created_at': datetime.now().isoformat(),
        'expires_at': expiry
    }
    save_sessions(sessions)
    return session_token


@_locked
def verify_session(session_token):
    """Verify if session is valid"""
    if not session_token:
        return None

    sessions = load_sessions()
    if session_token not in sessions:
        return None

    session = sessions[session_token]
    try:
        expiry = datetime.fromisoformat(session['expires_at'])
        expired = datetime.now(expiry.tzinfo) >= expiry
    except (KeyError, TypeError, ValueError):
        expired = True

    user = get_user_info(session.get('email')) if isinstance(session, dict) else None
    authorized = user and (user['role'] in {'admin', 'super_admin'} or
                           (user['role'] == 'staff' and user['status'] == 'approved'))
    if expired or not authorized:
        del sessions[session_token]
        save_sessions(sessions)
        return None

    return session['email']


@_locked
def invalidate_session(session_token):
    """Remove a session (logout)"""
    sessions = load_sessions()
    if session_token in sessions:
        del sessions[session_token]
        save_sessions(sessions)


def user_exists(email):
    """Check if user already exists"""
    users = load_users()
    return email.lower() in users


@_locked
def register_user(fullname, email, password, phone=None):
    """Register a new user and default staff members to pending approval."""
    users = load_users()
    email_lower = email.lower()

    if email_lower in users:
        existing = _normalize_user(email_lower, users[email_lower])
        if existing.get('role') == 'staff' and existing.get('status') in {'pending', 'rejected', 'inactive'}:
            return {'success': False, 'message': 'Email already registered. Your account is still waiting for Admin approval.'}
        return {'success': False, 'message': 'Email already registered'}

    user = {
        'fullname': fullname,
        'email': email,
        'password': hash_password(password),
        'phone': phone or '',
        'role': 'staff',
        'status': 'pending',
        'created_at': datetime.now().isoformat(),
        'last_login': None
    }
    users[email_lower] = user
    save_users(users)
    return {
        'success': True,
        'message': 'Registration successful. Your account is currently pending Admin approval.'
    }


@_locked
def create_super_admin(fullname, email, password, phone=None):
    """Create an approved Super Admin account from an authorized admin flow."""
    users = load_users()
    email_lower = (email or '').strip().lower()

    if not fullname or not email_lower or not password:
        return {'success': False, 'message': 'Full name, email, and password are required'}
    if email_lower in users:
        return {'success': False, 'message': 'Email already registered'}

    users[email_lower] = {
        'fullname': fullname.strip(),
        'email': email_lower,
        'password': hash_password(password),
        'phone': phone or '',
        'role': 'super_admin',
        'status': 'approved',
        'created_at': datetime.now().isoformat(),
        'last_login': None,
    }
    save_users(users)
    return {
        'success': True,
        'message': 'Super Admin account created successfully.',
        'user': {'email': email_lower, 'fullname': fullname.strip(), 'role': 'super_admin', 'status': 'approved'},
    }


@_locked
def verify_login(email, password):
    """Verify user login credentials and enforce role/status authorization."""
    users = load_users()
    email_lower = (email or '').lower()

    if email_lower not in users:
        return {'success': False, 'message': 'Invalid email or password'}

    user = _normalize_user(email_lower, users[email_lower])
    stored_password = user.get('password') or ''
    if not isinstance(stored_password, str):
        return {'success': False, 'message': 'Invalid email or password'}
    legacy_hash = len(stored_password) == 64 and all(c in '0123456789abcdef' for c in stored_password)
    if legacy_hash:
        password_matches = hmac.compare_digest(stored_password, hashlib.sha256(password.encode()).hexdigest())
    else:
        try:
            password_matches = check_password_hash(stored_password, password)
        except (ValueError, TypeError):
            password_matches = False
    if not password_matches:
        return {'success': False, 'message': 'Invalid email or password'}

    role = user.get('role', 'staff')
    status = user.get('status', 'pending')

    if role == 'staff':
        if status == 'pending':
            return {'success': False, 'message': 'Your account is still waiting for Admin approval.'}
        if status == 'rejected':
            return {'success': False, 'message': 'Your account registration has been rejected. Please contact the Administrator.'}
        if status == 'inactive':
            return {'success': False, 'message': 'Your account has been deactivated. Please contact the Administrator.'}
        if status != 'approved':
            return {'success': False, 'message': 'This account is not authorized to access PinyaSense.'}

    elif role in {'admin', 'super_admin'}:
        user['status'] = 'approved'
    else:
        return {'success': False, 'message': 'This account is not authorized to access PinyaSense.'}

    user['last_login'] = datetime.now().isoformat()
    if legacy_hash:
        user['password'] = hash_password(password)
    users[email_lower] = user
    save_users(users)

    session_token = create_session(email_lower)
    return {
        'success': True,
        'message': 'Login successful',
        'session_token': session_token,
        'user': {
            'email': user['email'],
            'fullname': user['fullname'],
            'role': user['role'],
            'status': user['status']
        }
    }


def get_user_info(email):
    """Get user information and normalized authorization metadata."""
    users = load_users()
    email_lower = (email or '').lower()

    if email_lower not in users:
        return None

    user = _normalize_user(email_lower, users[email_lower])
    return {
        'email': user['email'],
        'fullname': user['fullname'],
        'phone': user.get('phone', ''),
        'role': user.get('role', 'staff'),
        'status': user.get('status', 'pending'),
        'created_at': user.get('created_at')
    }


def list_staff_accounts():
    """List all staff accounts for admin review."""
    users = load_users()
    staff = []
    for email, user in users.items():
        normalized = _normalize_user(email, user)
        if normalized.get('role') == 'staff':
            staff.append({
                'email': normalized['email'],
                'fullname': normalized['fullname'],
                'phone': normalized.get('phone', ''),
                'role': normalized.get('role'),
                'status': normalized.get('status'),
                'created_at': normalized.get('created_at'),
                'last_login': normalized.get('last_login')
            })
    return sorted(staff, key=lambda item: item.get('created_at', ''))


@_locked
def update_staff_account_status(email, status):
    """Update a staff account status and keep role locked to staff."""
    users = load_users()
    email_lower = (email or '').lower()

    if email_lower not in users:
        return {'success': False, 'message': 'User not found'}

    normalized = _normalize_user(email_lower, users[email_lower])
    if normalized.get('role') != 'staff':
        return {'success': False, 'message': 'This is not a staff account'}

    status = (status or '').strip().lower()
    if status not in VALID_STAFF_STATUSES:
        return {'success': False, 'message': 'Invalid account status'}

    if status == 'rejected':
        del users[email_lower]
        save_users(users)

        _invalidate_user_sessions(email_lower)
        return {
            'success': True,
            'message': 'Staff account rejected and deleted.',
            'user': {
                'email': normalized['email'],
                'fullname': normalized['fullname'],
                'role': normalized['role'],
                'status': 'deleted',
            }
        }

    normalized['status'] = status
    users[email_lower] = normalized
    save_users(users)
    if status != 'approved':
        _invalidate_user_sessions(email_lower)
    return {
        'success': True,
        'message': f'Staff account updated to {status}.',
        'user': {
            'email': normalized['email'],
            'fullname': normalized['fullname'],
            'role': normalized['role'],
            'status': normalized['status'],
        }
    }


@_locked
def update_user_fullname(email, fullname):
    """Update user's full name"""
    users = load_users()
    email_lower = email.lower()

    if email_lower not in users:
        return {'success': False, 'message': 'User not found'}

    users[email_lower]['fullname'] = fullname
    save_users(users)

    updated_user = _normalize_user(email_lower, users[email_lower])
    return {
        'success': True,
        'message': 'Profile updated successfully',
        'user': {
            'email': updated_user['email'],
            'fullname': updated_user['fullname'],
            'phone': updated_user.get('phone', ''),
            'role': updated_user.get('role'),
            'status': updated_user.get('status'),
            'created_at': updated_user.get('created_at')
        }
    }
# ========== PASSWORD RESET FUNCTIONS ==========

def load_reset_codes():
    """Load reset codes from JSON file"""
    if os.path.exists(RESET_CODES_DB):
        with open(RESET_CODES_DB, 'r') as f:
            return json.load(f)
    return {}


def save_reset_codes(codes):
    """Save reset codes to JSON file"""
    write_json_atomic(RESET_CODES_DB, codes)


@_locked
def generate_reset_code(email):
    """Generate a password reset code for user"""
    users = load_users()
    email_lower = email.lower()

    if email_lower not in users:
        return {'success': False, 'message': 'Email not found'}

    reset_code = secrets.token_hex(3).upper()
    reset_codes = load_reset_codes()
    reset_codes[email_lower] = {
        'code': reset_code,
        'created_at': datetime.now().isoformat(),
        'expires_at': (datetime.now() + timedelta(hours=1)).isoformat()
    }
    save_reset_codes(reset_codes)

    return {
        'success': True,
        'message': 'Reset code generated',
        'reset_code': reset_code,
        'email': email
    }


@_locked
def verify_reset_code(email, code):
    """Verify if reset code is valid"""
    email_lower = email.lower()
    reset_codes = load_reset_codes()

    if email_lower not in reset_codes:
        return {'success': False, 'message': 'No reset code found for this email'}

    reset_data = reset_codes[email_lower]
    if not hmac.compare_digest(reset_data['code'], code.upper()):
        reset_data['attempts'] = reset_data.get('attempts', 0) + 1
        if reset_data['attempts'] >= 5:
            del reset_codes[email_lower]
        save_reset_codes(reset_codes)
        return {'success': False, 'message': 'Invalid reset code'}

    expiry = datetime.fromisoformat(reset_data['expires_at'])
    if datetime.now(expiry.tzinfo) >= expiry:
        del reset_codes[email_lower]
        save_reset_codes(reset_codes)
        return {'success': False, 'message': 'Reset code has expired'}

    return {'success': True, 'message': 'Reset code is valid'}


@_locked
def reset_password(email, code, new_password):
    """Reset user password with valid reset code"""
    email_lower = email.lower()
    if not isinstance(new_password, str) or len(new_password) < 8:
        return {'success': False, 'message': 'Password must be at least 8 characters'}

    verify_result = verify_reset_code(email_lower, code)
    if not verify_result['success']:
        return verify_result

    users = load_users()
    if email_lower not in users:
        return {'success': False, 'message': 'User not found'}

    users[email_lower]['password'] = hash_password(new_password)
    save_users(users)
    # Remove used reset code
    reset_codes = load_reset_codes()
    del reset_codes[email_lower]
    save_reset_codes(reset_codes)
    _invalidate_user_sessions(email_lower)
    
    return {'success': True, 'message': 'Password reset successfully'}
