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
        pass

    def test_check_config__all_env_cnf__mutual(self):
        pass

    def test_check_config__all_env_cnf__overwrite(self):
        pass
