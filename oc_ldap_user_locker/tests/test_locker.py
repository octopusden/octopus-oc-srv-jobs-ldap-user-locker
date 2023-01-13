from unittest import TestCase
from unittest import mock
from .mocks.ldap3 import MockLdapConnection
from .mocks.randomizer import Randomizer
import os
import ldap3
from oc_ldap_client.oc_ldap_objects import OcLdapUserCat
from oc_ldap_client.oc_ldap_objects import OcLdapUserRecord
from oc_ldap_user_locker.locker import OcLdapUserLocker
from tempfile import NamedTemporaryFile
import json
import datetime

# remove unnecessary log output
import logging
logging.getLogger().propagate = False
logging.getLogger().disabled = True

class OcLdapUserLockerTest(TestCase):
    def _get_ldap_user_cat(self):
        # return patched OcLdapUserCat
        self_dir = os.path.dirname(os.path.abspath(__file__))
        key_path = os.path.join(self_dir, 'ssl_keys')

        with mock.patch('ldap3.Connection', new=MockLdapConnection):
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
        _config = NamedTemporaryFile(mode='w+t')
        _config.write(json.dumps({
            "LDAP": {
                "url": "ldap://localhost:389",
                "user_cert": os.path.join(key_path, 'user.pem'),
                "user_key": os.path.join(key_path, 'user.priv.key'),
                "ca_chain": os.path.join(key_path, 'ca_chain.pem'),
                "baseDn": "dc=some,dc=test,dc=domain,dc=local"
                }}))
        _config.flush()

        return OcLdapUserLocker(os.path.abspath(_config.name))

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
        _locker._process_single_user = mock.MagicMock()

        def _cat_ret(*args, **kwargs):
            return ldap_t

        with mock.patch('oc_ldap_user_locker.locker.OcLdapUserCat', new=_cat_ret):
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
        usr.set_attribute('cn', rnd.random_letters(rnd.random_number(10,17)))
        usr = ldap_t.put_record(usr)

        # now get the locker, mock called functions and do asserts
        _locker = self._get_locker()
        _locker._find_valid_conf = mock.MagicMock(return_value=None)
        _locker._check_lock_conf = mock.MagicMock()

        _locker._process_single_user(ldap_t, usr.dn)
        _locker._find_valid_conf.assert_called_once()
        _locker._check_lock_conf.assert_not_called()
        _usr_modified = ldap_t.get_record(usr.dn, OcLdapUserRecord)
        self.assertIsNone(_usr_modified.is_locked)

    def test_process_single_user__do_lock(self):
        # sould be locked
        ldap_t = self._get_ldap_user_cat()
        rnd = Randomizer()

        # generate test user record
        usr = OcLdapUserRecord()
        usr.set_attribute('cn', rnd.random_letters(rnd.random_number(10,17)))
        usr = ldap_t.put_record(usr)

        # now get the locker, mock called functions and do asserts
        _locker = self._get_locker()
        _conf = {'days_valid': 0, 'time_attributes': ['modifyTimeStamp']}
        _locker._find_valid_conf = mock.MagicMock(return_value=_conf)
        _locker._check_lock_conf = mock.MagicMock(return_value=True)

        _locker._process_single_user(ldap_t, usr.dn)
        _locker._find_valid_conf.assert_called_once()
        _locker._check_lock_conf.assert_called_once()
        _usr_modified = ldap_t.get_record(usr.dn, OcLdapUserRecord)
        self.assertIsNotNone(_usr_modified.is_locked)
        self.assertEqual(_usr_modified.is_locked, '000001010000Z') 

    def test_process_single_user__no_lock(self):
        # sould not be locked
        ldap_t = self._get_ldap_user_cat()
        rnd = Randomizer()

        # generate test user record
        usr = OcLdapUserRecord()
        usr.set_attribute('cn', rnd.random_letters(rnd.random_number(10,17)))
        usr = ldap_t.put_record(usr)

        # now get the locker, mock called functions and do asserts
        _locker = self._get_locker()
        _conf = {'days_valid': 30, 'time_attributes': ['modifyTimeStamp', 'createTimeStamp']}
        _locker._find_valid_conf = mock.MagicMock(return_value=_conf)
        _locker._check_lock_conf = mock.MagicMock(return_value=False)

        _locker._process_single_user(ldap_t, usr.dn)
        _locker._find_valid_conf.assert_called_once()
        _locker._check_lock_conf.assert_called_once()
        _usr_modified = ldap_t.get_record(usr.dn, OcLdapUserRecord)
        self.assertIsNone(_usr_modified.is_locked)

    ## check_lock_conf
    def test_check_lock_conf__no_time_attributes(self):
        # this case user should raise an error if time attributes is None
        # or lock user if it is an empty list
        rnd = Randomizer()

        # generate test user record
        usr = OcLdapUserRecord()
        usr.set_attribute('cn', rnd.random_letters(rnd.random_number(10,17)))
        usr.set_attribute('authTimeStamp', datetime.datetime.now())

        # now get the locker, mock called functions and do asserts
        _locker = self._get_locker()

        # 'None'
        with self.assertRaises(TypeError):
            _locker._check_lock_conf(usr, rnd.random_number(30, 90), None)

        self.assertTrue( _locker._check_lock_conf(usr, rnd.random_number(30, 90), list()))

    def test_check_lock_conf__one_attribute_lock(self):
        # should be locked if one single attribute is older than days specified
        # and not locked otherwise
        rnd = Randomizer()
        _now_t = datetime.datetime.now()

        # generate test user record
        usr = OcLdapUserRecord()
        usr.set_attribute('cn', rnd.random_letters(rnd.random_number(10,17)))

        # now get the locker, mock called functions and do asserts
        _locker = self._get_locker()

        # set 'right' attribute far away and another attribute below 'days_valid' value
        # second one is to be ignored
        usr.set_attribute('authTimeStamp', _now_t - datetime.timedelta(days=30))
        usr.set_attribute('modifyTimeStamp', _now_t - datetime.timedelta(days=10))
        self.assertTrue(_locker._check_lock_conf(usr, 15, ['authTimeStamp']))

        # vice-versa
        usr.set_attribute('authTimeStamp', _now_t - datetime.timedelta(days=10))
        usr.set_attribute('modifyTimeStamp', _now_t - datetime.timedelta(days=30))
        self.assertFalse(_locker._check_lock_conf(usr, 15, ['authTimeStamp']))

        # attribute is equal
        self.assertTrue(_locker._check_lock_conf(usr, 10, ['authTimeStamp']))

    def test_check_lock_conf__two_attributes_lock(self):
        # See two attributes. If one of them is less than 'days' - do not lock
        rnd = Randomizer()
        _now_t = datetime.datetime.now()

        # generate test user record
        usr = OcLdapUserRecord()
        usr.set_attribute('cn', rnd.random_letters(rnd.random_number(10,17)))

        # now get the locker, mock called functions and do asserts
        _locker = self._get_locker()

        # set both attributes far away
        usr.set_attribute('authTimeStamp', _now_t - datetime.timedelta(days=30))
        usr.set_attribute('modifyTimeStamp', _now_t - datetime.timedelta(days=20))
        self.assertTrue(_locker._check_lock_conf(usr, 15, ['authTimeStamp', 'modifyTimeStamp']))
        # one is below
        self.assertFalse(_locker._check_lock_conf(usr, 25, ['authTimeStamp', 'modifyTimeStamp'])) 
        # both are below
        self.assertFalse(_locker._check_lock_conf(usr, 35, ['authTimeStamp', 'modifyTimeStamp'])) 

        # both are above
        usr.set_attribute('authTimeStamp', _now_t - datetime.timedelta(days=10))
        usr.set_attribute('modifyTimeStamp', _now_t - datetime.timedelta(days=5))
        self.assertFalse(_locker._check_lock_conf(usr, 15, ['authTimeStamp', 'modifyTimeStamp']))
        # one is equal, second is above
        self.assertFalse(_locker._check_lock_conf(usr, 10, ['authTimeStamp', 'modifyTimeStamp']))
        # both are below
        self.assertTrue(_locker._check_lock_conf(usr, 5, ['authTimeStamp', 'modifyTimeStamp']))

    ## find_valid_conf
    # NOTE: tests for 'find_valid_conf' also tests 'check_user_conf' and 'compare_attribute'
    def test_find_valid_conf__notstring_attribute(self):
        rnd = Randomizer()
        _now_t = datetime.datetime.now()

        # generate test user record
        usr = OcLdapUserRecord()
        usr.set_attribute('cn', rnd.random_letters(rnd.random_number(10,17)))

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
        usr.set_attribute('cn', rnd.random_letters(rnd.random_number(10,17)))

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
                                }}}]}

        # match the first conf unconditionally
        usr.set_attribute("mail", "TEST@EXAMPLE.LOCAL")
        self.assertEqual(_locker._find_valid_conf(usr).get("days_valid"), 30)

        # match by "displayName" should return it because 'days_valid' is lower
        usr.set_attribute("displayName", "test_display_name")
        self.assertEqual(_locker._find_valid_conf(usr).get("days_valid"), 10)

    def test_find_valid_conf__one_attribute_plain(self):
        # searching the configuration based on one attribute
        # comparison is plain-text, case-insensitive
        rnd = Randomizer()
        _now_t = datetime.datetime.now()

        # generate test user record
        usr = OcLdapUserRecord()
        usr.set_attribute('cn', rnd.random_letters(rnd.random_number(10,17)))

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
                                }}}]}

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
        usr.set_attribute('cn', rnd.random_letters(rnd.random_number(10,17)))

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
        usr.set_attribute('cn', rnd.random_letters(rnd.random_number(10,17)))

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
                                }}}]}

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
