# LDAP USER LOCKER

## Goal

Lock LDAP user accounts automatically by some reason. To be used as scheduled task.

## Limitations:

Depends on *oc_ldap_client*, so all its limitations are actual here.

## Configuration
To be written separatley and provided with _--config_ argument. Is a JSON file.
Example:

```
{
    "LDAP": {
        "url": "ldap://ldap-test.example.local",
        "user_cert": "/home/user/ssl/test/user.pem",
        "user_key": "/home/user/ssl/test/user.priv.key",
        "ca_chain": "/home/user/ssl/test/CA.chain.pem",
        "baseDn": "dc=domain,dc=example,dc=local"
    },
    "users": [
        {
            "days_valid": 30, 
            "time_attributes": ["authTimestamp", "modifyTimeStamp", "createTimestamp"],
            "lock_notifications": [
                {"days_before": 30, "mail_template": "default_en.html.template"},
                {"days_before": 10, "mail_template": "defualt_en.html.template"}
            ]
        },
        {
            "days_valid": 0, 
            "time_attributes": ["modifyTimeStamp", "createTimestamp"], 
            "condition_attributes": 
            {
                "mail": {
                    "comparison": {
                        "type": "regexp",
                        "condition": "any"
                    },
                    "values": [
                        ".*@gmail\\.[a-z]+", 
                        ".*@mail\\.[a-z]+", 
                        ".*@inbox\\.ru",
                        ".*@yandex\\.ru",
                        ".*@yahoo(mail|\\-inc)?\\.[a-z]+",
                        ".*@ymail\\.[a-z]+",
                        ".*@rocketmail\\.[a-z]+",
                        ".*@hotmail\\.[a-z]+",
                        ".*@rambler\\.ru",
                        ".*@qip\\.ru",
                        ".*@bigmir\\.net",
                        ".*@ukr\\.net",
                        ".*@usa\\.net",
                        ".*@live\\.[a-z]+",
                        ".*@msn\\.[a-z]+",
                        ".*@googlemail\\.[a-z]+"
                    ]
                }
            }
        }
    ]
}

```
Possible values _comparison_ sub-parameters:
    * _type_: **regexp**, **plain** (default)
    * _condition_: **all** (default), **any**

If _type_ is **regexp** then _Python_ regular expressions are required in _values_ section.
Non-string attributes comparison is not supported.
All comparisons are case-insensitive.
