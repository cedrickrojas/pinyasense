"""Authentication module for AgriPinya"""
import json
import os
import hashlib
from datetime import datetime, timedelta
import secrets

# Users database file
USERS_DB = 'data/users.json'
SESSIONS_DB = 'data/sessions.json'
RESET_CODES_DB = 'data/reset_codes.json'

def load_users():
    """Load users from JSON file"""
    if os.path.exists(USERS_DB):
        with open(USERS_DB, 'r') as f:
            return json.load(f)
    return {}

def save_users(users):
    """Save users to JSON file"""
    os.makedirs(os.path.dirname(USERS_DB), exist_ok=True)
    with open(USERS_DB, 'w') as f:
        json.dump(users, f, indent=2)

def load_sessions():
    """Load sessions from JSON file"""
    if os.path.exists(SESSIONS_DB):
        with open(SESSIONS_DB, 'r') as f:
            return json.load(f)
    return {}

def save_sessions(sessions):
    """Save sessions to JSON file"""
    os.makedirs(os.path.dirname(SESSIONS_DB), exist_ok=True)
    with open(SESSIONS_DB, 'w') as f:
        json.dump(sessions, f, indent=2)

def hash_password(password):
    """Hash password using SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()

def create_session(email):
    """Create a new session for user"""
    sessions = load_sessions()
    session_token = secrets.token_urlsafe(32)
    
    # Set session to expire in 30 days
    expiry = (datetime.now() + timedelta(days=30)).isoformat()
    
    sessions[session_token] = {
        'email': email,
        'created_at': datetime.now().isoformat(),
        'expires_at': expiry
    }
    save_sessions(sessions)
    return session_token

def verify_session(session_token):
    """Verify if session is valid"""
    if not session_token:
        return None
    
    sessions = load_sessions()
    if session_token not in sessions:
        return None
    
    session = sessions[session_token]
    expiry = datetime.fromisoformat(session['expires_at'])
    
    # Check if session is expired
    if datetime.now() > expiry:
        del sessions[session_token]
        save_sessions(sessions)
        return None
    
    return session['email']

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

def register_user(fullname, email, password, phone=None):
    """Register a new user"""
    users = load_users()
    email_lower = email.lower()
    
    # Check if user already exists
    if email_lower in users:
        return {'success': False, 'message': 'Email already registered'}
    
    # Create new user
    users[email_lower] = {
        'fullname': fullname,
        'email': email,
        'password': hash_password(password),
        'phone': phone or '',
        'created_at': datetime.now().isoformat(),
        'last_login': None
    }
    
    save_users(users)
    return {'success': True, 'message': 'User registered successfully'}

def verify_login(email, password):
    """Verify user login credentials"""
    users = load_users()
    email_lower = email.lower()
    
    if email_lower not in users:
        return {'success': False, 'message': 'Invalid email or password'}
    
    user = users[email_lower]
    
    if user['password'] != hash_password(password):
        return {'success': False, 'message': 'Invalid email or password'}
    
    # Update last login
    user['last_login'] = datetime.now().isoformat()
    save_users(users)
    
    # Create session
    session_token = create_session(email_lower)
    
    return {
        'success': True,
        'message': 'Login successful',
        'session_token': session_token,
        'user': {
            'email': user['email'],
            'fullname': user['fullname']
        }
    }

def get_user_info(email):
    """Get user information"""
    users = load_users()
    email_lower = email.lower()
    
    if email_lower not in users:
        return None
    
    user = users[email_lower]
    return {
        'email': user['email'],
        'fullname': user['fullname'],
        'phone': user['phone'],
        'created_at': user['created_at']
    }

def update_user_fullname(email, fullname):
    """Update user's full name"""
    users = load_users()
    email_lower = email.lower()

    if email_lower not in users:
        return {'success': False, 'message': 'User not found'}

    users[email_lower]['fullname'] = fullname
    save_users(users)

    updated_user = users[email_lower]
    return {
        'success': True,
        'message': 'Profile updated successfully',
        'user': {
            'email': updated_user['email'],
            'fullname': updated_user['fullname'],
            'phone': updated_user.get('phone', ''),
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
    with open(RESET_CODES_DB, 'w') as f:
        json.dump(codes, f, indent=2)

def generate_reset_code(email):
    """Generate a password reset code for user"""
    users = load_users()
    email_lower = email.lower()
    
    if email_lower not in users:
        return {'success': False, 'message': 'Email not found'}
    
    # Generate 6-digit reset code
    reset_code = secrets.token_hex(3).upper()  # 6 character hex code
    
    # Store reset code with 1 hour expiry
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
        'reset_code': reset_code,  # For demo purposes
        'email': email
    }

def verify_reset_code(email, code):
    """Verify if reset code is valid"""
    email_lower = email.lower()
    reset_codes = load_reset_codes()
    
    if email_lower not in reset_codes:
        return {'success': False, 'message': 'No reset code found for this email'}
    
    reset_data = reset_codes[email_lower]
    
    # Check if code matches
    if reset_data['code'] != code.upper():
        return {'success': False, 'message': 'Invalid reset code'}
    
    # Check if code is expired
    expiry = datetime.fromisoformat(reset_data['expires_at'])
    if datetime.now() > expiry:
        del reset_codes[email_lower]
        save_reset_codes(reset_codes)
        return {'success': False, 'message': 'Reset code has expired'}
    
    return {'success': True, 'message': 'Reset code is valid'}

def reset_password(email, code, new_password):
    """Reset user password with valid reset code"""
    email_lower = email.lower()
    
    # Verify code first
    verify_result = verify_reset_code(email_lower, code)
    if not verify_result['success']:
        return verify_result
    
    # Update password
    users = load_users()
    if email_lower not in users:
        return {'success': False, 'message': 'User not found'}
    
    users[email_lower]['password'] = hash_password(new_password)
    save_users(users)
    
    # Remove used reset code
    reset_codes = load_reset_codes()
    del reset_codes[email_lower]
    save_reset_codes(reset_codes)
    
    return {'success': True, 'message': 'Password reset successfully'}