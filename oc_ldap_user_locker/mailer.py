import json
from copy import deepcopy
from oc_mailer import Mailer
import logging
import os

class LockMailer:
    def __init__(self, config, config_path):
        """
        Basic initialization, configuration checking
        :param dict config: configuration for mailer
        :param str base_path: path to a directory with basic configuration
        """
        self._config = config
        self._config_path = os.path.abspath(config_path)
        logging.debug("Base configutaion path: '%s'" % self._config_path)
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
            _env = _smtp_env.get(_key) or '_'.join(["SMTP", _key.upper()])
            _value = self._config.get(_key, os.getenv(_env))

            if not _value:
                raise ValueError("%s not set", _env)

            logging.debug("%s: '%s'" % (_env, _value))
            self._config[_key] = _value

    def _check_path(self, path):
        """
        Check if path provided is absolute.
        Make it absolute if not.
        Do not check for file existence since it will be raised while try to open
        :param str path: path to check
        :return str: adjusted path
        """
        if not path:
            raise ValueError("Empty or incompatible path provided")

        if not os.path.isabs(path):
            path = os.path.join(self._config_path, path)

        return path

    def _check_template_configuration(self, template_conf):
        """
        Check template configuration
        :param dict template_conf: template configuration
        :return dict: adjusted template configuration
        """
        if any([not template_conf, not isinstance(template_conf, dict)]):
            raise ValueError("Invalid template configuration. At least 'file' is required")

        if 'file' not in template_conf.keys():
            raise ValueError("Invalid template configuration. At least 'file' is required")

        print("fuckoff")

        return template_conf

    def send_notification(self, mail_to, template_conf, template_substitutes):
        """
        Send mail notification as specified in the arguments
        :param str mail_to: e-mail address to send
        :param dict template_conf: template configuration
        :param dict template_substitutes: template substitutes
        """

        if not mail_to or not '@' in mail_to:
            raise ValueError("Invalid e-mail address: '%s'" % mail_to)

        template_conf = self._check_template_configuration(template_conf)
