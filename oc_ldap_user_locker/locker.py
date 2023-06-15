import json
import os
import logging
from oc_ldap_client.oc_ldap_objects import OcLdapUserCat, OcLdapUserRecord
import re
import datetime
from copy import copy
from .mailer import LockMailer

class OcLdapUserLocker:
    def __init__(self, config_path):
        """
        Initialization
        :param str config_path: path to JSON locker configuration
        """
        if not config_path:
            raise ValueError("No configuration path provided")

        config_path = os.path.abspath(config_path)
        logging.info("Configuration path: '%s'" % config_path)
        self._config_path = config_path

        with open(config_path, mode='rt') as _fl_in:
            self.config = json.load(_fl_in)

        self._check_ldap_params()
        self._mailer = None

    def _check_ldap_params(self):
        """
        Check LDAP parameters are set
        update them from environment if not
        """
        _ldap_params = self.config.get("LDAP")

        if not _ldap_params:
            logging.debug("LDAP configuration missing, trying to create it from environment")
            self.config["LDAP"] = dict()
            _ldap_params = self.config.get("LDAP")

        _ldap_env = {
                "url": "LDAP_URL",
                "user_cert": "LDAP_TLS_CERT",
                "user_key": "LDAP_TLS_KEY",
                "ca_chain": "LDAP_TLS_CACERT",
                "baseDn": "LDAP_BASE_DN"}

        for _key in _ldap_env.keys():
            _value = _ldap_params.get(_key) or os.getenv(_ldap_env.get(_key))

            if not _value:
                raise ValueError("%s not set", _ldap_env.get(_key))

            if _key in ["user_cert", "ca_chain", "user_key"]:
                # this is a path to file, make sure it is absolute
                if not os.path.isabs(_value):
                    _value = os.path.join(os.path.dirname(self._config_path), _value)

            logging.debug("%s: '%s'" % (_ldap_env.get(_key), _value))
            self.config["LDAP"][_key] = _value

    def _compare_attribute(self, values, match_conf):
        """
        Compare a values to match configuration
        :param list values: values to compare
        :param dict match_conf: configuration dictionary
        """
        if not values:
            logging.debug("No values")
            return False

        if not match_conf:
            # sure it is a bug
            raise ValueError("No match configuration given")

        # check what type of comarison do we need
        _comparison = match_conf.get('comparison') or dict()
        _comparison_type = _comparison.get('type') or 'flat'
        _comparison_condition = _comparison.get('condition') or 'all'

        if _comparison_type not in ['flat', 'regexp']:
            raise NotImplementedError("Comparison of type '%s' is not supported" % (_comparison_type))

        if _comparison_condition not in ['all', 'any']:
            raise NotImplementedError("Comparison condition '%s' is not supported" % (_comparison_condition))

        logging.debug("Comparison type '%s', condtion '%s'" % (_comparison_type, _comparison_condition))

        # may be flat value given, convert it to list for looping below
        if not isinstance(values, list):
            values = [values]

        # raise an exception if no 'values' given
        _condition_values = match_conf['values']
        _result = False

        for _condition_value in _condition_values:
            if not _condition_value:
                raise ValueError("Empty or inapplicable condition value: '%s'" % str(_condition_value))

            if not isinstance(_condition_value, str):
                raise ValueError("Non-string comparison is not supported (type: '%s')" % type(_condition_value))

            # compare this value with LDAP
            for _value in values:
                if not _value:
                    # empty values are OK for LDAP, just skip it
                    continue

                if not isinstance(_value, str):
                    raise NotImplementedError("Comparison of non-string attributes is not supported")

                # all comparison are case-insensitive
                if _comparison_type == 'flat':
                    if _condition_value.lower() == _value.lower():

                        if _comparison_condition == 'any':
                            logging.debug("Match, returning True: '%s' === '%s'" % (_condition_value, _value))
                            return True
                        else:
                            _result = True

                    elif _comparison_condition == 'all':
                        logging.debug("Mismatch, returning False: '%s' != '%s'" % (_condition_value, _value))
                        return False

                    continue

                # comapring as case-insensitive regexp
                if re.match(_condition_value, _value, flags=re.I):

                    if _comparison_condition == 'any':
                        logging.debug("Match regexp, returning True: '%s' <<== '%s'" % (_condition_value, _value))
                        return True
                    else:
                        _result = True

                elif _comparison_condition == 'all':
                    logging.debug("Mismatch regexp, returning False: '%s' !<<= '%s'" % (_condition_value, _value))
                    return False

        logging.debug("Finall check: returning '%s'" % str(_result))
        return _result

    def _check_user_conf(self, user_rec, conf):
        """
        Check user configuration is suitable for our case
        :param OcLdapRecord user_rec: LDAP record for user account
        :param dict conf: user configuration
        :return int: number of attributes matched, or None if configuration is not applicable
        """

        # if no 'condition_attributes' specified - it is our case
        if not conf.get('condition_attributes'):
            return 0

        # search for attribute otherwise
        # all of attributes are to be matched
        # we have to raise an exception if one of mandatory values is not specified
        _matched_attributes = 0
        for _attrib in conf['condition_attributes'].keys():
            logging.debug("Comparing attribute: '%s'" % _attrib)
            _vals_from_rec = user_rec.get_attribute(_attrib)
            _match_conf = conf['condition_attributes'][_attrib]

            if not self._compare_attribute(_vals_from_rec, _match_conf):
                logging.debug("Failed on attribute: '%s'" % _attrib)
                return None

            _matched_attributes += 1

        return _matched_attributes

    def _find_valid_conf(self, user_rec):
        """
        Parse users configuration and find valid days
        :param OcLdapRecord user_rec: LDAP record for user account
        :return int:
        """
        logging.debug("Started configuration analysis for %s" % user_rec.get_attribute('cn'))
        _users_conf = self.config.get("users")
        _conf_f = None

        # analyse all cases one-by-one
        _matched_attributes = None

        for _conf in _users_conf:
            _matched_attributes_c = self._check_user_conf(user_rec, _conf)

            if _matched_attributes_c is None:
                # this configuration can not be applied
                continue

            # NOTE: checking '_matched_attributes' for 'None' is a sort of paranoia since
            #       it should never happen
            if _conf_f is None or _matched_attributes_c > _matched_attributes:
                # we found at least one suitable configration:
                _conf_f = _conf
                _matched_attributes = _matched_attributes_c
            
        return _conf_f

    def _process_single_user(self, ldap_c, user_dn):
        """
        Process single user record
        :param OCLDAPUSERCAT ldap_c: ldap client instance
        :param str user_dn: user record distinct name (DN)
        """
        logging.info("Processing user: DN=%s" % user_dn)
        _users_conf = self.config.get("users")
        _user_rec = ldap_c.get_record(user_dn, OcLdapUserRecord)
        logging.debug("User login: '%s'" % _user_rec.get_attribute('cn'))
        logging.debug("User e-mail: '%s'" % _user_rec.get_attribute('mail'))
        logging.debug("User created: '%s'" % _user_rec.get_attribute('createTimeStamp'))
        logging.debug("User modified: '%s'" % _user_rec.get_attribute('modifyTimeStamp'))
        logging.debug("User last login: '%s'" % _user_rec.get_attribute("authTimestamp"))
        logging.debug("User created: '%s'" % _user_rec.get_attribute("createTimestamp"))
        logging.debug("Locked time: '%s'" % _user_rec.get_attribute("pwdAccountLockedTime"))
        logging.debug("Type of user created: '%s'" % type(_user_rec.get_attribute('createTimeStamp')))
        logging.debug("Type of user last login: '%s'" % type (_user_rec.get_attribute("authTimestamp")))
        logging.debug("Type of user modification date: '%s'" % type(_user_rec.get_attribute("modifyTimeStamp")))

        # search configuration to apply by attributes given
        _conf = self._find_valid_conf(_user_rec)

        # if no configuration found - do nothing
        if _conf is None:
            logging.info("No suitable locking configuration for '%s'" %  _user_rec.get_attribute('cn'))
            return

        # this will raise an exception if any of mandatory parameter is missing or has wrong type
        logging.info("User '%s' is valid for '%d' days, time attributes: '%s'" % (
            _user_rec.get_attribute('cn'), _conf['days_valid'], ':'.join(_conf['time_attributes'])))

        # now check the time attributes specified in the conf and find out the nearest one
        # note that 'tzinfo' is to be discarged because of possible datetime exception while
        #   subtracting them
        _lock_date = self._get_account_lock_date(_user_rec, _conf['days_valid'], _conf['time_attributes'])

        if not _lock_date:
            # should never happen
            logging.debug("Account '%s' is not to be locked ever", _user_rec.get_attribute('cn'))
            return

        logging.debug("Account lock date for '%s': '%s'" % (
            _user_rec.get_attribute('cn'), _lock_date.isoformat(sep=" ")))

        _days_before_lock = self._get_days_before_lock(_lock_date)
        logging.debug("Days before lock account '%s': %d" % (
            _user_rec.get_attribute('cn'), _days_before_lock))

        # check lock e-mail notifications
        self._check_lock_notifications(
                _user_rec, _conf, lock_date=_lock_date, days_before_lock=_days_before_lock)

        if _days_before_lock > 0:
            logging.debug("Is not the time to lock '%s', returning" % _user_rec.get_attribute('cn'))
            return

        logging.info("Locking '%s', days: '%d'" % (
            _user_rec.get_attribute('cn'), _days_before_lock))

        _user_rec.lock()
        ldap_c.put_record(_user_rec)
       
    def _check_lock_notifications(self, user_rec, conf, lock_date, days_before_lock):
        """
        Check if user is to be notified about account locking
        Send mail notifications is so
        :param OcLdapRecord user_rec: user record from LDAP catalogue
        :param dict conf: configuration to check agianst
        :param datetime.datetime lock_date: date when account will be locked
        :param int days_before_lock: days left for the date when account will be locked
        """
        # if any of argumets absent then we should have an exception.
        # so do not check

        if not conf.get("lock_notifications"):
            logging.debug("Notifications are not configured for '%s'" % user_rec.get_attribute('cn'))
            return

        if not user_rec.get_attribute("mail"):
            logging.debug("User '%s' nas no mail, nothing to do" % user_rec.get_attribute('cn')) 
            return

        # if 'days_before_lock' is negative - use zero-value notification since account is to be locked now
        if days_before_lock < 0:
            days_before_lock = 0

        # if no suitable configuration for 'days_before_lock' - skip
        _conf = list(filter(lambda x: x.get("days_before") == days_before_lock, conf.get("lock_notifications")))

        if not _conf:
            #empty list?
            logging.debug("No notification for '%s' in %d days before lock" %
                    (user_rec.get_attribute('cn'), days_before_lock))
            return
        
        _conf = _conf.pop()

        if not self._mailer:
            self._mailer = LockMailer(self.config.get("SMTP") or dict(), os.path.dirname(self._config_path))

        # filter substitutes for mail template
        _substitutes = dict((_k, user_rec.get_attribute(_k)) for _k in [
            'cn', 'givenName', 'sn', 'displayName'])

        _substitutes.update({
                "lockDate": lock_date.strftime("%Y-%d-%m"),
                "lockDays": str(days_before_lock)})

        self._mailer.send_notification(user_rec.get_attribute('mail'), _conf.get("template"), _substitutes)


    def _get_days_before_lock(self, lock_date):
        """
        Check if user is to be locked or not
        :param datetime.datetime lock_date: the date account should be locked at, without timezone, not None
        :reurn int: days before lock, negative if 'after' lock
        """
        _today = datetime.datetime.now()
        _today = _today.replace(tzinfo=None)
        _diff = lock_date - _today

        return _diff.days

    def _get_account_lock_date(self, user_rec, days_valid, time_attributes):
        """
        Calculate account lock date basing on current 'time_attribute' values
        :param OcLdapRecord user_rec: record from LDAP
        :param int days_valid: how many days record is valid
        :param list time_attributes: list of time attributes to check (strings)
        :return datetime.datetime: the date and time account should be locked; 'None' means 'never'
        """

        _result = None
        _append = datetime.timedelta(days=days_valid)

        for _time_attrib in time_attributes:
            # note that list of time attributes is not supported, so assuming it is a datetime.datetime value
            # note that we are doing 'copy' - to get rid of record attribute get changed and then raise LDAP error
            #   on saving it
            _time_value = copy(user_rec.get_attribute(_time_attrib))

            # time value may be "None" - assuming attribute is not set and skipping comparison
            if not _time_value:
                continue

            # appending 'days'
            _time_value = _time_value.replace(tzinfo=None)
            _time_value = _time_value + _append

            # we have to choose the value in the farest future of possibles
            if not _result or _result < _time_value:
                _result = _time_value

        logging.debug("Locking date for '%s': '%s'" % (user_rec.get_attribute('cn'),
            'None' if not _result else _result.isoformat(sep=' ')))

        return _result

    def run(self):
        """
        Run the process
        """
        logging.debug("Started")

        # init LDAP client
        _ldap_params = self.config.get("LDAP")
        _ldap_c = OcLdapUserCat(**_ldap_params)


        # list all non-locked users and find the smallest days valid interval
        for _user in _ldap_c.list_users(add_filter="(!(pwdAccountLockedTime=000001010000Z))"):
            self._process_single_user(_ldap_c, _user)
