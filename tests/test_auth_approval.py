import importlib


def setup_auth_module(monkeypatch, tmp_path):
    import core.auth as auth

    monkeypatch.setattr(auth, 'USERS_DB', str(tmp_path / 'users.json'))
    monkeypatch.setattr(auth, 'SESSIONS_DB', str(tmp_path / 'sessions.json'))
    monkeypatch.setattr(auth, 'RESET_CODES_DB', str(tmp_path / 'reset_codes.json'))
    return auth


def test_register_user_sets_pending_staff(monkeypatch, tmp_path):
    auth = setup_auth_module(monkeypatch, tmp_path)

    result = auth.register_user('Staff User', 'staff@example.com', 'Password123', '09999999999')

    assert result['success'] is True
    user = auth.load_users()['staff@example.com']
    assert user['role'] == 'staff'
    assert user['status'] == 'pending'


def test_pending_staff_cannot_login(monkeypatch, tmp_path):
    auth = setup_auth_module(monkeypatch, tmp_path)

    auth.register_user('Staff User', 'staff@example.com', 'Password123', '09999999999')
    result = auth.verify_login('staff@example.com', 'Password123')

    assert result['success'] is False
    assert 'Admin approval' in result['message']


def test_admin_login_is_allowed(monkeypatch, tmp_path):
    auth = setup_auth_module(monkeypatch, tmp_path)

    users = auth.load_users()
    users['admin@example.com'] = {
        'fullname': 'Admin User',
        'email': 'admin@example.com',
        'password': auth.hash_password('AdminPass123'),
        'phone': '09000000000',
        'role': 'admin',
        'status': 'approved',
        'created_at': '2026-01-01T00:00:00',
        'last_login': None,
    }
    auth.save_users(users)

    result = auth.verify_login('admin@example.com', 'AdminPass123')

    assert result['success'] is True
    assert result['user']['email'] == 'admin@example.com'


def test_reject_staff_deletes_account(monkeypatch, tmp_path):
    auth = setup_auth_module(monkeypatch, tmp_path)

    auth.register_user('Staff User', 'staff@example.com', 'Password123', '09999999999')
    result = auth.update_staff_account_status('staff@example.com', 'rejected')

    assert result['success'] is True
    assert result['user']['status'] == 'deleted'
    assert 'staff@example.com' not in auth.load_users()


def test_create_super_admin_is_approved(monkeypatch, tmp_path):
    auth = setup_auth_module(monkeypatch, tmp_path)

    result = auth.create_super_admin('System Owner', 'owner@example.com', 'Password123')

    assert result['success'] is True
    user = auth.load_users()['owner@example.com']
    assert user['role'] == 'super_admin'
    assert user['status'] == 'approved'
    assert auth.verify_login('owner@example.com', 'Password123')['success'] is True
