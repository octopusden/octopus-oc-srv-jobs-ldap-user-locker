import json
from copy import deepcopy
from oc_mailer import Mailer
import logging
import os

class LockMailer:
    def __init__(self, config, base_path):
        """
        Basic initialization, configuration checking
        :param dict config: configuration for mailer
        :param str base_path: path to a directory with basic configuration
        """
        self._config = config
        self._base_path = os.path.abspath(base_path)
        logging.debug("Base configutaion path: '%s'" % _self._base_path)
        self._check_config()

    def _check_config(self):
        """
        Check mailer configuration and adjust paths if necessary
        """

        _smtp_env = {
                "url": None,
                "user": None,
                "password": None,
                "from": "MAIL_FROM"
                }

        if not self._config:
            logging.debug("SMTP configuration missing, trying to create it from environment")
            self._config = dict()

        for _key in _smtp_env.keys():
            _env = _smtp_env.get(_key, '_'.join(["SMTP", _key.upper()]))
            _value = self._config.get(_key, os.getenv(_env))

            if not _value:
                raise ValueError("%s not set", _env)

            logging.debug("%s: '%s'" % (_env, _value))
            self.config[_key] = _value
