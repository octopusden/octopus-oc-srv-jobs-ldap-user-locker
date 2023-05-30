from oc_mailer import Mailer
import logging
import os
import smtplib
import urllib.parse as urlparse
import re
import posixpath

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

            if _value:
                logging.debug("%s: '%s'" % (_env, _value))
                self._config[_key] = _value

        # 'url' and 'from' are required, 'user' and 'password' may be omitted for anonymous SMTP
        for _k in ["url", "from"]:
            if not self._config.get(_k):
                raise ValueError("Required '%s' is not set for SMTP" % _k)

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
        if not isinstance(template_conf, dict):
            raise TypeError("Dictinary required, %s provided" % type(template_conf))

        template_conf["file"] = self._check_path(template_conf["file"])
        template_conf["type"] = template_conf.get("type") or "plain"

        if "signature" in template_conf.keys():
            template_conf["signature"] = self._check_path(template_conf["signature"])

        return template_conf

    def _get_smtp_client(self):
        """
        Return SMTP connection instance
        """
        _url = self._config.get("url")

        if not re.match("(.*?:)?" + posixpath.sep + posixpath.sep, _url):
            _schema_default = "smtp:%s" % (posixpath.sep * 2)
            logging.warning("No schema specified at SMTP_URL: '%s', using default '%s'" % (_url, _schema_default))
            _url = ''.join([_schema_default, _url])

        _parse_result = urlparse.urlparse(_url)
        _host = _parse_result.hostname
        _port = _parse_result.port

        if not _host:
            raise ValueError("Invalid SMTP_URL '%s': host not parsed" % _url)

        logging.debug("Parsing SMTP_URL, host='%s'" % _host)

        if not _port:
            logging.debug("No port specified, assiging default")
            _port = 25

        logging.debug("Port: %d" % _port)

        _client = smtplib.SMTP(host=_host, port=_port)

        # login to SMTP if credentials given
        if all(list(map(lambda x: self._config.get(x), ["user", "password"]))): 
            logging.debug("SMTP auth as '%s'" % self._config.get("user"))
            _client.login(self._config.get("user"), self._config.get("password"))

        return _client        

    def send_notification(self, mail_to, template_conf, template_substitutes):
        """
        Send mail notification as specified in the arguments
        :param str mail_to: e-mail address to send
        :param dict template_conf: template configuration
        :param dict template_substitutes: template substitutes
        """

        if not mail_to or '@' not in mail_to:
            raise ValueError("Invalid e-mail address: '%s'" % mail_to)

        template_conf = self._check_template_configuration(template_conf)

        # load all resources
        _signature = None
        _template = None

        logging.info("Sending message to '%s', template '%s'" % (mail_to, template_conf.get("file")))
        with open(template_conf.get("file"), mode='rt') as _tpl_in:
            _template = _tpl_in.read()

        if template_conf.get("signature"):
            with open(template_conf.get("signature"), mode='rb') as _sg_in:
                _signature = _sg_in.read()

        _smtp = self._get_smtp_client()
        Mailer.Mailer(_smtp, 
                self._config.get("from"),
                template_conf.get("type"),
                template=_template,
                signature_image=_signature).send_email(mail_to,
                        template_conf.get("subject") or self._config.get("subject") or "Account lock warning",
                        split=False,
                        **template_substitutes)
