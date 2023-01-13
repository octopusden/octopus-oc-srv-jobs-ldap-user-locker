from setuptools import setup

__version = "0.0.0.2"

spec = {
    "name": "oc_ldap_user_locker",
    "version": __version,
    "license": "LGPLv2",
    "description": "LDAP user locker for use in scheduler",
    "packages": ["oc_ldap_user_locker"],
    "install_requires": [ 
        'oc_ldap_client >= 1.0.0.0',
      ],
    "python_requires": ">=3.6"
}

setup( **spec )
