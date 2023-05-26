import unittest
import unittest.mock
from ..mailer import LockMailer
import os
import tempfile
from .mocks.randomizer import Randomizer

# remove unnecessary log output
import logging
logging.getLogger().propagate = False
logging.getLogger().disabled = True

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

    def test_check_path(self):
        _config = {
                "url": "smtp://another.smtp.example.com:625",
                "user": "another_test_user",
                "password": "test_user_password",
                "from": "another_test@example.com"}
        _config_pth = "/tmp"
        _mailer = LockMailer(_config, _config_pth)

        with self.assertRaises(ValueError):
            _mailer._check_path(None)

        with self.assertRaises(ValueError):
            _mailer._check_path("")

        self.assertEqual(os.path.join(_config_pth, "bla", "bla", "bla.txt"), 
                _mailer._check_path(os.path.join("bla", "bla", "bla.txt")))

        self.assertEqual(os.path.join(os.path.sep, "bla", "bla", "bla.txt"), 
                _mailer._check_path(os.path.join(os.path.sep, "bla", "bla", "bla.txt")))

    def test_check_template_conf__no_file(self):
        _config = {
                "url": "smtp://another.smtp.example.com:625",
                "user": "another_test_user",
                "password": "test_user_password",
                "from": "another_test@example.com"}
        _config_pth = "/tmp"
        _mailer = LockMailer(_config, _config_pth)

        with self.assertRaises(TypeError):
            _mailer._check_template_configuration(None)

        with self.assertRaises(KeyError):
            _mailer._check_template_configuration(dict())

        with self.assertRaises(KeyError):
            _mailer._check_template_configuration({"type":"plain"})

    def test_check_templater_conf__ok(self):
        _config = {
                "url": "smtp://another.smtp.example.com:625",
                "user": "another_test_user",
                "password": "test_user_password",
                "from": "another_test@example.com"}
        _config_pth = "/tmp"
        _mailer = LockMailer(_config, _config_pth)

        # relative path
        _expected = {
                "file": os.path.join(_config_pth, "bla-bla-bla.txt.template"),
                "type": "plain"}
        self.assertEqual(_expected, _mailer._check_template_configuration({
            "file": "bla-bla-bla.txt.template"}))

        # mixed path with signature
        _expected = {
                "file": os.path.join(_config_pth, "bla-bla-bla.html.template"),
                "type": "html",
                "signature": os.path.join(os.path.sep, "bla-bla-bla.png")}
        self.assertEqual(_expected, _mailer._check_template_configuration({
            "file": "bla-bla-bla.html.template",
            "type": "html",
            "signature": os.path.join(os.path.sep, "bla-bla-bla.png")}))

    def test_get_smtp_client__invalid_url(self):
        _config = {
                "url": "smtp://",
                "user": "another_test_user",
                "password": "test_user_password",
                "from": "another_test@example.com"}
        _config_pth = "/tmp"
        _mailer = LockMailer(_config, _config_pth)

        with self.assertRaises(ValueError):
            _mailer._get_smtp_client()

    def test_get_smtp_client__default_port(self):
        _config = {
                "url": "another.smtp.example.com",
                "user": "another_test_user",
                "password": "test_user_password",
                "from": "another_test@example.com"}
        _config_pth = "/tmp"
        _mailer = LockMailer(_config, _config_pth)
        _smtp = unittest.mock.MagicMock()
        _smtp.login = unittest.mock.MagicMock()

        with unittest.mock.patch("oc_ldap_user_locker.mailer.smtplib.SMTP", return_value=_smtp) as _smtp_i:
            self.assertIsNotNone(_mailer._get_smtp_client())
            _smtp_i.assert_called_once_with(host="another.smtp.example.com", port=25)
            _smtp.login.assert_called_once_with("another_test_user", "test_user_password")

    def test_get_smtp_client__ok(self):
        _config = {
                "url": "smtp://another.smtp.example.com:625",
                "user": "another_test_user",
                "password": "test_user_password",
                "from": "another_test@example.com"}
        _config_pth = "/tmp"
        _mailer = LockMailer(_config, _config_pth)
        _smtp = unittest.mock.MagicMock()
        _smtp.login = unittest.mock.MagicMock()

        with unittest.mock.patch("oc_ldap_user_locker.mailer.smtplib.SMTP", return_value=_smtp) as _smtp_i:
            self.assertIsNotNone(_mailer._get_smtp_client())
            _smtp_i.assert_called_once_with(host="another.smtp.example.com", port=625)
            _smtp.login.assert_called_once_with("another_test_user", "test_user_password")

    def test_send_notif__invalid_mail(self):
        _config = {
                "url": "smtp://another.smtp.example.com:625",
                "user": "another_test_user",
                "password": "test_user_password",
                "from": "another_test@example.com"}
        _config_pth = "/tmp"
        _mailer = LockMailer(_config, _config_pth)

        with self.assertRaises(ValueError):
            _mailer.send_notification(None, None, None)

        with self.assertRaises(ValueError):
            _mailer.send_notification("", None, None)

        with self.assertRaises(ValueError):
            _mailer.send_notification("invalidmail", None, None)

    def test_send_notif__template_file_missing(self):
        _config = {
                "url": "smtp://another.smtp.example.com:625",
                "user": "another_test_user",
                "password": "test_user_password",
                "from": "another_test@example.com"}
        _config_pth = "/tmp"
        _mailer = LockMailer(_config, _config_pth)
        _t = tempfile.NamedTemporaryFile()
        _tfn = os.path.abspath(_t.name)
        _t.close()
        self.assertFalse(os.path.exists(_tfn))
        _template_conf = {"file": _tfn}

        with self.assertRaises(FileNotFoundError):
            _mailer.send_notification(Randomizer().random_email(), _template_conf, dict()) 

    def test_send_notif__signature_file_missing(self):
        _config = {
                "url": "smtp://another.smtp.example.com:625",
                "user": "another_test_user",
                "password": "test_user_password",
                "from": "another_test@example.com"}
        _config_pth = "/tmp"
        _mailer = LockMailer(_config, _config_pth)
        _tpl = tempfile.NamedTemporaryFile(mode='w+t')
        _tfn = os.path.abspath(_tpl.name)
        _spl = tempfile.NamedTemporaryFile()
        _sfn = os.path.abspath(_spl.name)
        _tpl.write("the template")
        _tpl.flush()
        _spl.close()
        self.assertTrue(os.path.exists(_tfn))
        self.assertFalse(os.path.exists(_sfn))
        _template_conf = {"file": _tfn, "type": "html", "signature": _sfn}

        with self.assertRaises(FileNotFoundError):
            _mailer.send_notification(Randomizer().random_email(), _template_conf, dict()) 

        _tpl.close()

    def test_send_notif__ok(self):
        pass
