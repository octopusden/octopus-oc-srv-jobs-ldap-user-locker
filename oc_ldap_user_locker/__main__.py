import argparse
import logging
from .locker import OcLdapUserLocker

_p = argparse.ArgumentParser(description="LDAP user locker job for Scheduler usage")
_p.add_argument("--config", type=str, required=True, help="Path to JSON configuration")
_p.add_argument("--log-level", type=int, default=20, help="Logging level (integer)")
_args=_p.parse_args()

logging.basicConfig(format = "%(pathname)s: %(asctime)-15s: %(levelname)s: %(funcName)s: %(lineno)d: %(message)s", level = _args.log_level)

OcLdapUserLocker(_args.config).run()
