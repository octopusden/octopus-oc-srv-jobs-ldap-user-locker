import unittest
import unittest.mock
from ..mailer import LockMailer

class MailerTestCase(unittest.TestCase):
    def test_check_config__none(self):
        _config = dict()
        _config_pth = ""

        with self.assertRaises(ValueError):
            _mailer = LockMailer(_config, _config_pth)

    def test_check_config__partial_env(self):
        _config = dict()
        _config_pth = ""
        _env_patch = {
                "SMTP_URL": "smtp://smtp.example.com:25",
                "SMTP_USER": "test_user"
                }

        with unittest.mock.patch.dict('os.environ', _env_patch):
            with self.assertRaises(ValueError):
                _mailer = LockMailer(_config, _config_pth)

    def test_check_config__partial_env_cnf(self):
        _config = {"user": "another_test_user"}
        _config_pth = ""
        _env_patch = {
                "SMTP_URL": "smtp://smtp.example.com:25",
                "SMTP_USER": "test_user"
                }

        with unittest.mock.patch.dict('os.environ', _env_patch):
            with self.assertRaises(ValueError):
                _mailer = LockMailer(_config, _config_pth)

    def test_check_config__all_env_cnf__mutual(self):
        _config = {"password": "test_user_password"}
        _config_pth = ""
        _env_patch = {
                "SMTP_URL": "smtp://smtp.example.com:25",
                "SMTP_USER": "test_user",
                "MAIL_FROM": "test@example.com"}

        with unittest.mock.patch.dict('os.environ', _env_patch):
            _mailer = LockMailer(_config, _config_pth)
            self.assertEqual(_mailer._config.get("password"), _config.get("password"))
            self.assertEqual(_mailer._config.get("url"), _env_patch.get("SMTP_URL"))
            self.assertEqual(_mailer._config.get("user"), _env_patch.get("SMTP_USER"))
            self.assertEqual(_mailer._config.get("from"), _env_patch.get("MAIL_FROM"))

    def test_check_config__all_env_cnf__overwrite(self):
        _config = {
                "url": "smtp://another.smtp.example.com:625",
                "user": "another_test_user",
                "password": "test_user_password",
                "from": "another_test@example.com"}
        _config_pth = ""
        _env_patch = {
                "SMTP_URL": "smtp://smtp.example.com:25",
                "SMTP_USER": "test_user",
                "SMTP_PASSWORD": "test_password",
                "MAIL_FROM": "test@example.com"}

        with unittest.mock.patch.dict('os.environ', _env_patch):
            _mailer = LockMailer(_config, _config_pth)
            self.assertEqual(_mailer._config.get("password"), _config.get("password"))
            self.assertEqual(_mailer._config.get("url"), _config.get("url"))
            self.assertEqual(_mailer._config.get("user"), _config.get("user"))
            self.assertEqual(_mailer._config.get("from"), _config.get("from"))
