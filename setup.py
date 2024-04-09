from setuptools import setup

__version = "1.2.3"

spec = {
    "name": "oc-ldap-user-locker",
    "version": __version,
    "license": "LGPLv2",
    "description": "LDAP user locker for use in scheduler",
    "long_description": "",
    "long_description_content_type": "text/plain",
    "packages": ["oc_ldap_user_locker"],
    "install_requires": [ 
        'oc-ldap-client >= 1.0.0',
        'oc-mailer'
      ],
    "python_requires": ">=3.6"
}

setup( **spec )
