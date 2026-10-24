import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import auth
from core.json_storage import write_json_atomic


class AuthSecurityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        replacement = patch.multiple(auth, USERS_DB=str(root / 'data/users.json'),
                                     SESSIONS_DB=str(root / 'data/sessions.json'),
                                     RESET_CODES_DB=str(root / 'data/reset_codes.json'))
        replacement.start()
        self.addCleanup(replacement.stop)

    def approved_account(self):
        auth.register_user('Test User', 'test@example.com', 'Password123')
        auth.update_staff_account_status('test@example.com', 'approved')

    def test_reset_code_is_single_use_and_revokes_existing_sessions(self):
        self.approved_account()
        token = auth.verify_login('test@example.com', 'Password123')['session_token']
        code = auth.generate_reset_code('test@example.com')['reset_code']
        self.assertTrue(auth.reset_password('test@example.com', code, 'NewPassword123')['success'])
        self.assertFalse(auth.reset_password('test@example.com', code, 'AnotherPassword123')['success'])
        self.assertIsNone(auth.verify_session(token))
        self.assertTrue(auth.verify_login('test@example.com', 'NewPassword123')['success'])

    def test_deactivation_revokes_sessions_and_reactivation_does_not_restore_them(self):
        self.approved_account()
        token = auth.verify_login('test@example.com', 'Password123')['session_token']
        auth.update_staff_account_status('test@example.com', 'inactive')
        auth.update_staff_account_status('test@example.com', 'approved')
        self.assertIsNone(auth.verify_session(token))

    def test_legacy_sha256_accounts_can_login_and_upgrade_without_password_reset(self):
        legacy = hashlib.sha256(b'Password123').hexdigest()
        auth.save_users({'legacy@example.com': {'password': legacy, 'role': 'admin'}})
        self.assertFalse(auth.verify_login('legacy@example.com', 'Incorrect123')['success'])
        self.assertEqual(auth.load_users()['legacy@example.com']['password'], legacy)
        self.assertTrue(auth.verify_login('legacy@example.com', 'Password123')['success'])
        upgraded = auth.load_users()['legacy@example.com']['password']
        self.assertTrue(upgraded.startswith('pbkdf2:'))
        self.assertTrue(auth.verify_login('legacy@example.com', 'Password123')['success'])

    def test_new_password_hashes_have_independent_salts(self):
        self.assertNotEqual(auth.hash_password('Password123'), auth.hash_password('Password123'))

    def test_reset_code_is_invalidated_after_five_wrong_attempts(self):
        self.approved_account()
        code = auth.generate_reset_code('test@example.com')['reset_code']
        for _ in range(5):
            self.assertFalse(auth.verify_reset_code('test@example.com', 'wrong')['success'])
        self.assertFalse(auth.verify_reset_code('test@example.com', code)['success'])

    def test_reset_storage_is_created_on_a_new_installation(self):
        auth.save_reset_codes({'test@example.com': {'code': 'EXAMPLE'}})
        self.assertEqual(auth.load_reset_codes()['test@example.com']['code'], 'EXAMPLE')

    def test_malformed_or_deleted_account_sessions_fail_closed(self):
        auth.save_sessions({'broken': None, 'unknown': {'expires_at': '2099-01-01', 'email': 'missing@example.com'}})
        self.assertIsNone(auth.verify_session('broken'))
        self.assertIsNone(auth.verify_session('unknown'))

    def test_failed_serialization_keeps_the_original_file(self):
        target = Path(self.directory.name) / 'settings.json'
        write_json_atomic(target, {'saved': True})
        with self.assertRaises(TypeError):
            write_json_atomic(target, {'invalid': object()})
        self.assertEqual(json.loads(target.read_text()), {'saved': True})
        self.assertEqual(list(target.parent.glob('*.tmp')), [])


if __name__ == '__main__':
    unittest.main()
