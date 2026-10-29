# -*- coding: utf-8 -*-
"""
Minimal settings used during testing.

These override the real src/settings.py so that tests don't need a live
MongoDB, Elasticsearch or any external service.
"""

from os import path
from aiocache import caches

DEBUG = True

# Use a temp directory as BASEDIR so file-related settings don't break
import tempfile
BASEDIR = tempfile.gettempdir()

ALLOW_ANONYMOUS_ACCESS = True

INSTALLED_APPS = (
    'wirecloud.commons',
    'wirecloud.platform',
    'wirecloud.catalogue',
    'wirecloud.proxy',
    'wirecloud.fiware',
    'wirecloud.keycloak',
    'wirecloud.oauth2provider',
)

DATABASE = {
    'DRIVER': 'mongodb',
    'NAME': 'wirecloud_test',
    'HOST': 'localhost',
    'PORT': '',
    'USER': '',
    'PASSWORD': '',
    'USE_TRANSACTIONS': False,  # mongomock does not support transactions
}

ELASTICSEARCH = {
    'HOST': 'localhost',
    'PORT': 9200,
    'USER': '',
    'PASSWORD': '',
    'SECURE': False,
}

LANGUAGES = (
    ('es', 'Spanish'),
    ('en', 'English'),
    ('pt', 'Portuguese'),
)

DEFAULT_LANGUAGE = 'en'

JWT_KEY = 'test-secret-key-do-not-use-in-production'

SESSION_AGE = 60 * 60 * 24 * 14  # 2 weeks

OID_CONNECT_ENABLED = False
OID_CONNECT_DISCOVERY_URL = ''
OID_CONNECT_CLIENT_ID = ''
OID_CONNECT_CLIENT_SECRET = ''
OID_CONNECT_FULLY_SYNC_GROUPS = False
OID_CONNECT_BACKCHANNEL_LOGOUT = False
OID_CONNECT_PLUGIN = 'keycloak'

CATALOGUE_MEDIA_ROOT = path.join(BASEDIR, 'wirecloud_test_catalogue')
CACHE_DIR = path.join(BASEDIR, 'wirecloud_test_cache')
WIDGET_DEPLOYMENT_DIR = path.join(BASEDIR, 'wirecloud_test_deployment')

WIRECLOUD_HTTPS_VERIFY = False

AVAILABLE_THEMES = ['defaulttheme']
THEME_ACTIVE = 'defaulttheme'

PROXY_WS_MAX_MSG_SIZE = 4 * 1024 * 1024

caches.set_config({
    'default': {
        'cache': 'aiocache.SimpleMemoryCache',
        'ttl': 3600,
    }
})
cache = caches.get('default')

SECRET_KEY = 'test-super-secret'

PROXY_WHITELIST_ENABLED = False
PROXY_WHITELIST = []
PROXY_BLACKLIST_ENABLED = False
PROXY_BLACKLIST = []
