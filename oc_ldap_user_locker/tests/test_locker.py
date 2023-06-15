import unittest
import unittest.mock
from .mocks.ldap3 import MockLdapConnection
from .mocks.randomizer import Randomizer
import os
import ldap3
from oc_ldap_client.oc_ldap_objects import OcLdapUserCat
from oc_ldap_client.oc_ldap_objects import OcLdapUserRecord
from ..locker import OcLdapUserLocker
import tempfile
import json
import datetime

# remove unnecessary log output
import logging
logging.getLogger().propagate = False
logging.getLogger().disabled = True

class OcLdapUserLockerTest(unittest.TestCase):
    def _get_ldap_user_cat(self):
        # return patched OcLdapUserCat
        self_dir = os.path.dirname(os.path.abspath(__file__))
        key_path = os.path.join(self_dir, 'ssl_keys')

        with unittest.mock.patch('ldap3.Connection', new=MockLdapConnection):
            ldap_t = OcLdapUserCat(url='ldap://localhost:389', 
                user_cert=os.path.join(key_path, 'user.pem'),
                user_key=os.path.join(key_path, 'user.priv.key'),
                ca_chain=os.path.join(key_path, 'ca_chain.pem'),
                baseDn='dc=some,dc=test,dc=domain,dc=local')

        return ldap_t

    def _get_locker(self):
        # return OcLdapUserLocker object with our config
        self_dir = os.path.dirname(os.path.abspath(__file__))
        key_path = os.path.join(self_dir, 'ssl_keys')

        # first write configuration in temporary file
        _config = tempfile.NamedTemporaryFile(mode='w+t')
        _config.write(json.dumps({
            "LDAP": {
                "url": "ldap://localhost:389",
                "user_cert": os.path.join(key_path, 'user.pem'),
                "user_key": os.path.join(key_path, 'user.priv.key'),
                "ca_chain": os.path.join(key_path, 'ca_chain.pem'),
                "baseDn": "dc=some,dc=test,dc=domain,dc=local"
                }}))
        _config.flush()

        _result = OcLdapUserLocker(os.path.abspath(_config.name))

        # to get rid of 'unclosed resource' wraning it is better to close tempfile explicitly
        _config.close()
        _result._mailer = unittest.mock.MagicMock()
        return _result

    def test_run(self):
        # put many records and check _process_single_user runs exactly the number of unlocked records stored
        # do not add extra records to MockLdapConnection
        ldap_t = self._get_ldap_user_cat()
        rnd = Randomizer()
        self.assertEqual(0, len(ldap_t.list_users()))

        # get initial users list
        # append users one-by-one and test its dn is in list
        list_dns = ldap_t.list_users()

        for idx in range(17, 37):
            usr = OcLdapUserRecord()
            usr.set_attribute('cn', rnd.random_letters(idx))
            usr = ldap_t.put_record(usr)
            self.assertIsNotNone(usr.dn)
            list_dns.append(usr.dn)

        # now construct OcLdapUserLocker object
        _locker = self._get_locker()
        _locker._process_single_user = unittest.mock.MagicMock()

        def _cat_ret(*args, **kwargs):
            return ldap_t

        with unittest.mock.patch('oc_ldap_user_locker.locker.OcLdapUserCat', new=_cat_ret):
            _locker.run()

        self.assertEqual(_locker._process_single_user.call_count, len(list_dns))

        for _dn in list_dns:
            _locker._process_single_user.assert_any_call(ldap_t, _dn)

    ## process_single_user
    def test_process_single_user__no_valid_conf(self):
        ldap_t = self._get_ldap_user_cat()
        rnd = Randomizer()

        # generate test user record
        usr = OcLdapUserRecord()
        usr.set_attribute('cn', rnd.random_letters(rnd.random_number(10, 17)))
        usr = ldap_t.put_record(usr)

        # now get the locker, mock called functions and do asserts
        _locker = self._get_locker()
        _locker._find_valid_conf = unittest.mock.MagicMock(return_value=None)
        _locker._get_account_lock_date = unittest.mock.MagicMock()

        _locker._process_single_user(ldap_t, usr.dn)
        _locker._find_valid_conf.assert_called_once()
        _locker._get_account_lock_date.assert_not_called()
        _usr_modified = ldap_t.get_record(usr.dn, OcLdapUserRecord)
        self.assertIsNone(_usr_modified.is_locked)

    def test_process_single_user__do_lock(self):
        # sould be locked
        ldap_t = self._get_ldap_user_cat()
        rnd = Randomizer()

        # generate test user record
        usr = OcLdapUserRecord()
        usr.set_attribute('cn', rnd.random_letters(rnd.random_number(10, 17)))
        usr = ldap_t.put_record(usr)

        # now get the locker, mock called functions and do asserts
        _locker = self._get_locker()
        _conf = {'days_valid': 0, 'time_attributes': ['modifyTimeStamp']}
        _locker._find_valid_conf = unittest.mock.MagicMock(return_value=_conf)
        _lock_date = datetime.datetime.now() - datetime.timedelta(days=rnd.random_number(2, 4))
        _locker._get_account_lock_date = unittest.mock.MagicMock(return_value=_lock_date)

        _locker._process_single_user(ldap_t, usr.dn)
        _locker._find_valid_conf.assert_called_once()
        _locker._get_account_lock_date.assert_called_once()
        _usr_modified = ldap_t.get_record(usr.dn, OcLdapUserRecord)
        self.assertIsNotNone(_usr_modified.is_locked)
        self.assertEqual(_usr_modified.is_locked, '000001010000Z') 

    def test_process_single_user__no_lock(self):
        # sould not be locked
        ldap_t = self._get_ldap_user_cat()
        rnd = Randomizer()

        # generate test user record
        usr = OcLdapUserRecord()
        usr.set_attribute('cn', rnd.random_letters(rnd.random_number(10, 17)))
        usr = ldap_t.put_record(usr)

        # now get the locker, mock called functions and do asserts
        _locker = self._get_locker()
        _conf = {'days_valid': 30, 'time_attributes': ['modifyTimeStamp', 'createTimeStamp']}
        _locker._find_valid_conf = unittest.mock.MagicMock(return_value=_conf)
        _lock_date = datetime.datetime.now() + datetime.timedelta(days=rnd.random_number(37, 53))
        _locker._get_account_lock_date = unittest.mock.MagicMock(return_value=_lock_date)

        _locker._process_single_user(ldap_t, usr.dn)
        _locker._find_valid_conf.assert_called_once()
        _locker._get_account_lock_date.assert_called_once()
        _usr_modified = ldap_t.get_record(usr.dn, OcLdapUserRecord)
        self.assertIsNone(_usr_modified.is_locked)

    ## get_account_lock_date
    ## accuracy is 'days', so it is possible to assert with 'get_days_before_lock'
    ## which is unit-tested separately
    def test_get_account_lock_date__no_time_attributes(self):
        # this case user should raise an error if time attributes is None
        # or lock user if it is an empty list
        rnd = Randomizer()

        # generate test user record
        usr = OcLdapUserRecord()
        usr.set_attribute('cn', rnd.random_letters(rnd.random_number(10, 17)))
        usr.set_attribute('authTimeStamp', datetime.datetime.now())

        # now get the locker, mock called functions and do asserts
        _locker = self._get_locker()

        # 'None'
        with self.assertRaises(TypeError):
            _locker._get_account_lock_date(usr, rnd.random_number(30, 90), None)

        self.assertIsNone(_locker._get_account_lock_date(usr, rnd.random_number(30, 90), list()))

    def test_get_account_lock_date__one_attribute_lock(self):
        # should be locked if one single attribute is older than days specified
        # and not locked otherwise
        rnd = Randomizer()
        _now_t = datetime.datetime.now()

        # generate test user record
        usr = OcLdapUserRecord()
        usr.set_attribute('cn', rnd.random_letters(rnd.random_number(10, 17)))

        # now get the locker, mock called functions and do asserts
        _locker = self._get_locker()

        # set 'right' attribute far away and another attribute below 'days_valid' value
        # second one is to be ignored
        usr.set_attribute('authTimeStamp', _now_t - datetime.timedelta(days=30))
        usr.set_attribute('modifyTimeStamp', _now_t - datetime.timedelta(days=10))
        # auth was 30 days before, and valid is 15 days: diff is 15 days + 1 since a little time has gone
        self.assertEqual(0-(30-(15-1)), 
                _locker._get_days_before_lock(_locker._get_account_lock_date(usr, 15, ['authTimeStamp'])))

        # vice-versa
        usr.set_attribute('authTimeStamp', _now_t - datetime.timedelta(days=10))
        usr.set_attribute('modifyTimeStamp', _now_t - datetime.timedelta(days=30))
        # auth was 10 days before, valid 15 days: should be 5 days (-1)
        self.assertEqual(0-(10-(15-1)), 
                _locker._get_days_before_lock(_locker._get_account_lock_date(usr, 15, ['authTimeStamp'])))

        # attribute is equal
        self.assertEqual(0-1, 
                _locker._get_days_before_lock(_locker._get_account_lock_date(usr, 10, ['authTimeStamp'])))

    def test_get_account_lock_date__two_attributes_lock(self):
        # See two attributes. If one of them is less than 'days' - do not lock
        rnd = Randomizer()
        _now_t = datetime.datetime.now()

        # generate test user record
        usr = OcLdapUserRecord()
        usr.set_attribute('cn', rnd.random_letters(rnd.random_number(10, 17)))

        # now get the locker, mock called functions and do asserts
        _locker = self._get_locker()

        # set both attributes far away
        usr.set_attribute('authTimeStamp', _now_t - datetime.timedelta(days=30))
        usr.set_attribute('modifyTimeStamp', _now_t - datetime.timedelta(days=20))
        # 20 days is less then 30, so check against it
        self.assertEqual(0-(20-(15-1)), _locker._get_days_before_lock(
            _locker._get_account_lock_date(usr, 15, ['authTimeStamp', 'modifyTimeStamp'])))
        # one is below
        self.assertEqual(0-(20-(25-1)), _locker._get_days_before_lock(
                _locker._get_account_lock_date(usr, 25, ['authTimeStamp', 'modifyTimeStamp'])))
        # both are below
        self.assertEqual(0-(20-(35-1)), _locker._get_days_before_lock(
                _locker._get_account_lock_date(usr, 35, ['authTimeStamp', 'modifyTimeStamp'])))

        # both are above
        usr.set_attribute('authTimeStamp', _now_t - datetime.timedelta(days=10))
        usr.set_attribute('modifyTimeStamp', _now_t - datetime.timedelta(days=5))
        self.assertEqual(0-(5-(15-1)), _locker._get_days_before_lock(
                _locker._get_account_lock_date(usr, 15, ['authTimeStamp', 'modifyTimeStamp'])))
        # one is equal, second is above
        self.assertEqual(0-(5-(10-1)), _locker._get_days_before_lock(
                _locker._get_account_lock_date(usr, 10, ['authTimeStamp', 'modifyTimeStamp'])))
        # both are below
        self.assertEqual(0-(5-(5-1)), _locker._get_days_before_lock(
                _locker._get_account_lock_date(usr, 5, ['authTimeStamp', 'modifyTimeStamp'])))

    ## get_days_before_lock
    def test_get_days_before_lock__none(self):
        # should raise TypeError
        with self.assertRaises(TypeError):
            self._get_locker()._get_days_before_lock(None)

    def test_get_days_before_lock__past(self):
        # lock date is in the past, should be negative value
        rnd = Randomizer()
        _now_t = datetime.datetime.now()
        _days = rnd.random_number(10, 17)
        _lock_t = _now_t - datetime.timedelta(days=_days)
        _locker = self._get_locker()
        # note: append one day sinc a time is gone between '_now_t' and _get_days...
        self.assertEqual(0 - (_days + 1), _locker._get_days_before_lock(_lock_t))

    def test_get_days_before_lock__future(self):
        # lock date is in the future
        rnd = Randomizer()
        _now_t = datetime.datetime.now()
        _days = rnd.random_number(10, 17)
        _lock_t = _now_t + datetime.timedelta(days=_days)
        _locker = self._get_locker()
        # note: subtract one day sinc a time is gone between '_now_t' and _get_days...
        self.assertEqual(_days - 1, _locker._get_days_before_lock(_lock_t))

    def test_get_days_before_lock__now(self):
        # equal
        rnd = Randomizer()
        _now_t = datetime.datetime.now()
        _lock_t = _now_t + datetime.timedelta(seconds=rnd.random_number(10, 17))
        _locker = self._get_locker()
        self.assertEqual(0, _locker._get_days_before_lock(_lock_t))

    ## find_valid_conf
    # NOTE: tests for 'find_valid_conf' also tests 'check_user_conf' and 'compare_attribute'
    def test_find_valid_conf__notstring_attribute(self):
        rnd = Randomizer()
        _now_t = datetime.datetime.now()

        # generate test user record
        usr = OcLdapUserRecord()
        usr.set_attribute('cn', rnd.random_letters(rnd.random_number(10, 17)))

        # now get the locker, mock called functions and do asserts
        _locker = self._get_locker()

        # non-string comparison value in configuration
        _locker.config = {
                "users": [
                    {
                        "days_valid": 30, 
                        "time_attributes": ["authTimestamp"],
                        "condition_attributes": {
                            "pwdAccountLockedTime": {"values": [19000000]}
                            }
                        }]}

        usr.set_attribute("pwdAccountLockedTime", "000100001Z")

        with self.assertRaises(ValueError):
            _locker._find_valid_conf(usr)

        # non-string value in LDAP
        _locker.config = {
                "users": [
                    {
                        "days_valid": 30, 
                        "time_attributes": ["authTimestamp"],
                        "condition_attributes": {
                            "pwdAccountLockedTime": {"values": ["19000000"]}
                            }
                        }]}

        usr.set_attribute("pwdAccountLockedTime", datetime.datetime.now())

        with self.assertRaises(NotImplementedError):
            _locker._find_valid_conf(usr)

    def test_find_valid_conf__no_attributes(self):
        # should return the configuration with lowest 'days_valid'
        rnd = Randomizer()
        _now_t = datetime.datetime.now()

        # generate test user record
        usr = OcLdapUserRecord()
        usr.set_attribute('cn', rnd.random_letters(rnd.random_number(10, 17)))

        # now get the locker, mock called functions and do asserts
        _locker = self._get_locker()

        # non-string comparison value in configuration
        _locker.config = {
                "users": [
                    {
                        "days_valid": 30, 
                        "time_attributes": ["authTimestamp"]
                    },
                    {
                        "days_valid": 10,
                        "time_attributes": ["modifyTimeStamp"],
                        "condition_attributes": {
                            "displayName": 
                            {
                                "comparison": {"type": "flat", "condition": "any"},
                                "values": ["Test_Display_name"]
                            }
                        }
                    }]}

        # match the first conf unconditionally
        usr.set_attribute("mail", "TEST@EXAMPLE.LOCAL")
        self.assertEqual(_locker._find_valid_conf(usr).get("days_valid"), 30)

        # match by "displayName" should return it because one attribute is matched while zero at first
        usr.set_attribute("displayName", "test_display_name")
        self.assertEqual(_locker._find_valid_conf(usr).get("days_valid"), 10)

    def test_find_valid_conf__one_attribute_plain(self):
        # searching the configuration based on one attribute
        # comparison is plain-text, case-insensitive
        rnd = Randomizer()
        _now_t = datetime.datetime.now()

        # generate test user record
        usr = OcLdapUserRecord()
        usr.set_attribute('cn', rnd.random_letters(rnd.random_number(10, 17)))

        # now get the locker, mock called functions and do asserts
        _locker = self._get_locker()

        # non-string comparison value in configuration
        _locker.config = {
                "users": [
                    {
                        "days_valid": 30, 
                        "time_attributes": ["authTimestamp"],
                        "condition_attributes": {
                            "mail": {"values": ["test@example.local"]}
                        }
                    },
                    {
                        "days_valid": 10,
                        "time_attributes": ["modifyTimeStamp"],
                        "condition_attributes": {
                            "displayName": 
                            {
                                "comparison": {"type": "flat", "condition": "any"},
                                "values": ["Test_Display_name"]
                            }
                        }
                    }]}

        # match the first conf by "mail"
        usr.set_attribute("mail", "TEST@EXAMPLE.LOCAL")
        self.assertEqual(_locker._find_valid_conf(usr).get("days_valid"), 30)

        # break previous match and make it by "displayName"
        usr.set_attribute("mail", "test@another.example.local")
        usr.set_attribute("displayName", "test_display_name")
        self.assertEqual(_locker._find_valid_conf(usr).get("days_valid"), 10)

    def test_find_valid_conf__one_attribute_regexp(self):
        # searching the configuration based on one attribute
        # comparison is plain-text, case-insensitive
        rnd = Randomizer()
        _now_t = datetime.datetime.now()

        # generate test user record
        usr = OcLdapUserRecord()
        usr.set_attribute('cn', rnd.random_letters(rnd.random_number(10, 17)))

        # now get the locker, mock called functions and do asserts
        _locker = self._get_locker()

        # non-string comparison value in configuration
        _locker.config = {
                "users": [
                    {
                        "days_valid": 30, 
                        "time_attributes": ["authTimestamp"],
                        "condition_attributes": {
                            "mail": {
                                "comparison": {"type": "regexp", "condition": "all"},
                                "values": ["test@.*", "[^@]+@example\..*", "[^\.]+\.local"]
                            }
                        }
                    },
                    {
                        "days_valid": 10,
                        "time_attributes": ["modifyTimeStamp"],
                        "condition_attributes": {
                            "displayName": 
                            {
                                "comparison": {"type": "regexp", "condition": "any"},
                                "values": [".*test.*", ".*thisShouldNotMatch.*"]
                                }}}]}

        # match the first conf by "mail"
        usr.set_attribute("mail", "TEST@EXAMPLE.LOCAL")
        self.assertEqual(_locker._find_valid_conf(usr).get("days_valid"), 30)

        # break previous match and make it by "displayName"
        usr.set_attribute("mail", "test@another.example.local")
        usr.set_attribute("displayName", "TEST_DISPLAY_NAME")
        self.assertEqual(_locker._find_valid_conf(usr).get("days_valid"), 10)

    def test_find_valid_conf__two_attributes_mixed(self):
        # make two-attirbutes match configuration and check various combinations
        # searching the configuration based on one attribute
        # comparison is plain-text, case-insensitive
        rnd = Randomizer()
        _now_t = datetime.datetime.now()

        # generate test user record
        usr = OcLdapUserRecord()
        usr.set_attribute('cn', rnd.random_letters(rnd.random_number(10, 17)))

        # now get the locker, mock called functions and do asserts
        _locker = self._get_locker()

        # non-string comparison value in configuration
        _locker.config = {
                "users": [
                    {
                        "days_valid": 30, 
                        "time_attributes": ["authTimestamp"],
                        "condition_attributes": {
                            "mail": {
                                "comparison": {"type": "flat", "condition": "any"},
                                "values": [
                                    "test@example.local", 
                                    "another-test@example.local", 
                                    "yet-another-test@example.local"]
                                },
                            "displayName": {
                                "comparison": {"type": "regexp", "condition": "any"},
                                "values": [".*test.*", ".*thisShouldNotMatch.*"]
                            }
                        }
                    }]}

        # first match, second not
        usr.set_attribute("mail", "TEST@EXAMPLE.LOCAL")
        usr.set_attribute("displayName", "SURELY_UNMATCHED")
        self.assertIsNone(_locker._find_valid_conf(usr))

        # first mismatch, second match
        usr.set_attribute("mail", "TEST-but-not-match@EXAMPLE.LOCAL")
        usr.set_attribute("displayName", "SURELY_TEST_MATCH")
        self.assertIsNone(_locker._find_valid_conf(usr))

        # both mismatch
        usr.set_attribute("mail", "TEST-but-not-match@EXAMPLE.LOCAL")
        usr.set_attribute("displayName", "SURELY_NOT_MATCH")
        self.assertIsNone(_locker._find_valid_conf(usr))

        # both match
        usr.set_attribute("mail", "Yet-Another-TEST@EXAMPLE.LOCAL")
        usr.set_attribute("displayName", "Surely_TEST_Match")
        self.assertEqual(_locker._find_valid_conf(usr).get("days_valid"), 30)

    def _close_tempfile(self, tf, delete=False):
        if not isinstance(tf, str):
            _fd, _pth = tf
            os.close(_fd)
        else:
            _pth = tf

        if delete:
            os.remove(_pth)

        return _pth

    def test_check_ldap_params__nothing(self):
        _locker = self._get_locker()

        # no parameters
        _locker.config = dict()
        with self.assertRaises(ValueError):
            _locker._check_ldap_params()

    def test_check_ldap_params__partial_env(self):
        _locker = self._get_locker()

        # no parameters but environment set - partially
        _locker.config = dict()
        with unittest.mock.patch.dict(os.environ, {"LDAP_URL": "ldap://ldap.example.com"}):
            with self.assertRaises(ValueError):
                _locker._check_ldap_params()

    def test_check_ldap_params__full_env_files_present_abs(self):
        _locker = self._get_locker()

        # no parameter but files all exist - absolute path from env
        _locker.config = dict()
        _tempfiles = list(self._close_tempfile(tempfile.mkstemp(suffix=".pem"), delete=False) for __t in range(0, 3))
        _env_patch = {
                "LDAP_URL": "ldap://ldap.example.com",
                "LDAP_TLS_CERT": _tempfiles[0],
                "LDAP_TLS_KEY": _tempfiles[1],
                "LDAP_TLS_CACERT": _tempfiles[2],
                "LDAP_BASE_DN": "dc=example,dc=com"}

        with unittest.mock.patch.dict(os.environ, _env_patch):
            _locker._check_ldap_params()
            self.assertEqual(_locker.config["LDAP"]["url"], _env_patch.get("LDAP_URL"))
            self.assertEqual(_locker.config["LDAP"]["user_cert"], _env_patch.get("LDAP_TLS_CERT"))
            self.assertEqual(_locker.config["LDAP"]["user_key"], _env_patch.get("LDAP_TLS_KEY"))
            self.assertEqual(_locker.config["LDAP"]["ca_chain"], _env_patch.get("LDAP_TLS_CACERT"))
            self.assertEqual(_locker.config["LDAP"]["baseDn"], _env_patch.get("LDAP_BASE_DN"))

        for _t in _tempfiles:
            self._close_tempfile(_t, delete=True)

    def test_check_ldap_params__full_env_files_present_rel(self):
        _locker = self._get_locker()

        # no parameter but files all exist - relative path
        _locker.config = dict()
        _tempfiles = list(self._close_tempfile(tempfile.mkstemp(suffix=".pem"), delete=False) for __t in range(0, 3))
        _confdir = os.path.dirname(_tempfiles[0])

        _subst_tempfiles = list(map(lambda x: x if not x.startswith(_confdir) else os.path.relpath(x, _confdir), 
            _tempfiles))

        _env_patch = {
                "LDAP_URL": "ldap://ldap.example.com",
                "LDAP_TLS_CERT": _subst_tempfiles[0],
                "LDAP_TLS_KEY": _subst_tempfiles[1],
                "LDAP_TLS_CACERT": _subst_tempfiles[2],
                "LDAP_BASE_DN": "dc=example,dc=com"}

        with unittest.mock.patch.dict(os.environ, _env_patch):
            _locker._check_ldap_params()
            _locker._config_path = os.path.join(_confdir, "config.json")
            #paths have tobe absolute! so we are forced to take it from _tempfiles list
            self.assertEqual(_locker.config["LDAP"]["url"], _env_patch.get("LDAP_URL"))
            self.assertEqual(_locker.config["LDAP"]["user_cert"], _tempfiles[0])
            self.assertEqual(_locker.config["LDAP"]["user_key"], _tempfiles[1])
            self.assertEqual(_locker.config["LDAP"]["ca_chain"], _tempfiles[2])
            self.assertEqual(_locker.config["LDAP"]["baseDn"], _env_patch.get("LDAP_BASE_DN"))

        for _t in _tempfiles:
            self._close_tempfile(_t, delete=True)

    def test_check_ldap_params__partial_env_files_present_mix(self):
        _locker = self._get_locker()

        # partial parameters set, mixed path
        _tempfiles = list(self._close_tempfile(tempfile.mkstemp(suffix=".pem"), delete=False) for __t in range(0, 3))
        _confdir = os.path.dirname(_tempfiles[0])

        _subst_tempfiles = list(map(lambda x: x if not x.startswith(_confdir) else os.path.relpath(x, _confdir), 
            _tempfiles))

        _env_patch = {
                "LDAP_URL": "ldap://ldap.example.com",
                "LDAP_TLS_KEY": _subst_tempfiles[1],
                "LDAP_TLS_CACERT": _subst_tempfiles[2],
                "LDAP_BASE_DN": "dc=example,dc=com"}

        _conf_patch = {
                "url": "ldap://another.ldap.example.com:389",
                "user_cert": _tempfiles[1]} # note on index

        _locker.config = {"LDAP": _conf_patch}

        with unittest.mock.patch.dict(os.environ, _env_patch):
            _locker._check_ldap_params()
            _locker._config_path = os.path.join(_confdir, "config.json")
            #paths have tobe absolute! so we are forced to take it from _tempfiles list
            self.assertEqual(_locker.config["LDAP"]["url"], _conf_patch.get("url"))
            self.assertEqual(_locker.config["LDAP"]["user_cert"], _tempfiles[1])
            self.assertEqual(_locker.config["LDAP"]["user_key"], _tempfiles[1])
            self.assertEqual(_locker.config["LDAP"]["ca_chain"], _tempfiles[2])
            self.assertEqual(_locker.config["LDAP"]["baseDn"], _env_patch.get("LDAP_BASE_DN"))

        for _t in _tempfiles:
            self._close_tempfile(_t, delete=True)

    def test_check_ldap_params__full_conf_files_present_mix(self):
        _locker = self._get_locker()
        # all parameters set, mixed path
        # check values are taken from config

        # partial parameters set, mixed path
        _tempfiles = list(self._close_tempfile(tempfile.mkstemp(suffix=".pem"), delete=False) for __t in range(0, 6))
        _confdir = os.path.dirname(_tempfiles[0])

        _subst_tempfiles = list(map(lambda x: x if not x.startswith(_confdir) else os.path.relpath(x, _confdir), 
            _tempfiles))

        _env_patch = {
                "LDAP_URL": "ldap://ldap.example.com",
                "LDAP_TLS_KEY": _subst_tempfiles[1],
                "LDAP_TLS_CERT": _tempfiles[0],
                "LDAP_TLS_CACERT": _subst_tempfiles[2],
                "LDAP_BASE_DN": "dc=example,dc=com"}

        _conf_patch = {
                "url": "ldap://another.ldap.example.com:389",
                "user_cert": _subst_tempfiles[3],
                "user_key": _tempfiles[4],
                "ca_chain": _tempfiles[5],
                "baseDn": "dc=another,dc=example,dc=com"}

        _locker.config = {"LDAP": _conf_patch}

        with unittest.mock.patch.dict(os.environ, _env_patch):
            _locker._check_ldap_params()
            _locker._config_path = os.path.join(_confdir, "config.json")
            #paths have tobe absolute! so we are forced to take it from _tempfiles list
            self.assertEqual(_locker.config["LDAP"]["url"], _conf_patch.get("url"))
            self.assertEqual(_locker.config["LDAP"]["user_cert"], _tempfiles[3])
            self.assertEqual(_locker.config["LDAP"]["user_key"], _tempfiles[4])
            self.assertEqual(_locker.config["LDAP"]["ca_chain"], _tempfiles[5])
            self.assertEqual(_locker.config["LDAP"]["baseDn"], _conf_patch.get("baseDn"))

        for _t in _tempfiles:
            self._close_tempfile(_t, delete=True)

    # send e-mail notifications
    def test_check_mail__no_conf(self):
        _rnd = Randomizer()
        _locker = self._get_locker()
        _usr = OcLdapUserRecord()
        _usr.set_attribute('cn', _rnd.random_letters(_rnd.random_number(7, 17)))
        _locker._check_lock_notifications(_usr, dict(), None, None)
        _locker._mailer.send_notification.assert_not_called()

    def test_check_mail__no_address(self):
        _rnd = Randomizer()
        _locker = self._get_locker()
        _usr = OcLdapUserRecord()
        _usr.set_attribute('cn', _rnd.random_letters(_rnd.random_number(7, 17)))
        _locker._check_lock_notifications(_usr, {"lock_notifications": [
            { "days_before": 1, "template": {"file": "nonexistent.html.template"}}]}, None, None)
        _locker._mailer.send_notification.assert_not_called()

    def test_check_mail__no_siutable_conf(self):
        _rnd = Randomizer()
        _locker = self._get_locker()
        _usr = OcLdapUserRecord()
        _usr.set_attribute('cn', _rnd.random_letters(_rnd.random_number(7, 17)))
        _usr.set_attribute('mail', _rnd.random_email())
        _locker._check_lock_notifications(_usr, {"lock_notifications": [
            { "days_before": 1, "template": {"file": "nonexistent.html.template"}}]}, None, 3)
        _locker._mailer.send_notification.assert_not_called()

    def test_check_mail__ok(self):
        _rnd = Randomizer()
        _locker = self._get_locker()
        _usr = OcLdapUserRecord()
        _usr.set_attribute('cn', _rnd.random_letters(_rnd.random_number(7, 17)))
        _usr.set_attribute('mail', _rnd.random_email())
        _usr.set_attribute('givenName', _rnd.random_letters(_rnd.random_number(3, 7)))
        _usr.set_attribute('sn', _rnd.random_letters(_rnd.random_number(2, 10)))
        _usr.set_attribute('displayName', " ".join([
            _usr.get_attribute('givenName'), _usr.get_attribute('sn')]))
        _days_to_lock = 3
        _lock_date = datetime.datetime.now() + datetime.timedelta(days=3)
        _locker._check_lock_notifications(_usr, {"lock_notifications": [
            { "days_before": 3, "template": {"file": "nonexistent.html.template"}}]}, _lock_date, _days_to_lock)

        # make expected substitutes for call mailer
        _substitutes_expected = dict((_k, _usr.get_attribute(_k)) for _k in [
            'cn', 'givenName', 'sn', 'displayName'])
        _substitutes_expected.update({
                "lockDate": _lock_date.strftime("%Y-%d-%m"),
                "lockDays": str(_days_to_lock)})

        _locker._mailer.send_notification.assert_called_once_with(
                _usr.get_attribute('mail'), {"file": "nonexistent.html.template"}, _substitutes_expected)
