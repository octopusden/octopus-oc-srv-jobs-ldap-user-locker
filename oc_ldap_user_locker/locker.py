import json
import os
import logging
from oc_ldap_client.oc_ldap_objects import OcLdapUserCat, OcLdapUserRecord
import re
import datetime
from copy import copy

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

        with open(config_path, mode='rt') as _fl_in:
            self.config = json.load(_fl_in)

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
        :return bool:
        """

        # if no 'condition_attributes' specified - it is our case
        if not conf.get('condition_attributes'):
            return True

        # search for attribute otherwise
        # all of attributes are to be matched
        # we have to raise an exception if one of mandatory values is not specified
        for _attrib in conf['condition_attributes'].keys():
            logging.debug("Comparing attribute: '%s'" % _attrib)
            _vals_from_rec = user_rec.get_attribute(_attrib)
            _match_conf = conf['condition_attributes'][_attrib]

            if not self._compare_attribute(_vals_from_rec, _match_conf):
                logging.debug("Failed on attribute: '%s'" % _attrib)
                return False

        return True

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
        for _conf in _users_conf:
            _applicable = self._check_user_conf(user_rec, _conf)

            if not _applicable:
                # this configuration can not be applied
                continue

            if _conf_f is None:
                # we found at least one suitable configration:
                _conf_f = _conf
                continue
            
            # select one with minimum valid days
            # the default value is not applicable for this parameter, so we have to raise an exception
            # for case it is not specified or has wrong type
            if _conf_f['days_valid'] > _conf['days_valid']:
                _conf_f = _conf

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
        _lock = self._check_lock_conf(_user_rec, _conf['days_valid'], _conf['time_attributes'])

        if not _lock:
            return

        _user_rec.lock()
        ldap_c.put_record(_user_rec)

    def _check_lock_conf(self, user_rec, days_valid, time_attributes):
        """
        Check if user is to be locked or not
        :param OcLdapRecord user_rec: record from LDAP
        :param int days_valid: how many days record is valid
        :param list time_attributes: list of time attributes to check (strings)
        :return bool: True if user is to be locked
        """
        _today = datetime.datetime.now()
        _today = _today.replace(tzinfo=None)

        for _time_attrib in time_attributes:
            # note that list of time attributes is not supported, so assuming it is a datetime.datetime value
            # note that we are doing 'copy' - to get rid of record attribute get changed and then raise LDAP error
            #   on saving it
            _time_value = copy(user_rec.get_attribute(_time_attrib))

            # time value may be "None" - assuming attribute is not set and skipping comparison
            if not _time_value:
                continue

            # if any of attribute is 'less' than 'days' - do not lock an account
            _time_value = _time_value.replace(tzinfo=None)
            _diff = _today - _time_value

            if _diff.days < days_valid:
                logging.info("Not locking: '%s'" % user_rec.get_attribute('cn'))
                return False

        logging.info("Locking '%s'" % user_rec.get_attribute('cn'))

        return True

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
