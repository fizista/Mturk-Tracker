import os
from defaults import *

TEMPLATE_DEBUG = JS_DEBUG = DEBUG = True

LOG_LEVEL = 'DEBUG' if DEBUG else 'INFO'
for _ in [l for l in LOGGING['loggers'] if l.startswith('mturk')]:
    LOGGING['loggers'][l]['level'] = LOG_LEVEL

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(ROOT_PATH, 'database.sqlite3.db'),
    }
}

DATABASES.update({
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'mturk_tracker_db',
        'USER': 'mturk_tracker',
        'PASSWORD': 'asd',
        'HOST': 'localhost',
        'PORT': '',
    },
})
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

try:
    import devserver

    DEVSERVER_MODULES = (
        'devserver.modules.sql.SQLRealTimeModule',
        'devserver.modules.sql.SQLSummaryModule',
        'devserver.modules.profile.ProfileSummaryModule',

        # Modules not enabled by default
        'devserver.modules.ajax.AjaxDumpModule',
        'devserver.modules.profile.MemoryUseModule',
        'devserver.modules.cache.CacheSummaryModule',
        'devserver.modules.profile.LineProfilerModule',
    )

    DEVSERVER_IGNORED_PREFIXES = ['/__debug__']
    INSTALLED_APPS = tuple(list(INSTALLED_APPS) + [
        'devserver'
    ])
    MIDDLEWARE_CLASSES = tuple(list(MIDDLEWARE_CLASSES) + [
        'devserver.middleware.DevServerMiddleware'
    ])
except:
    pass

try:
    import debug_toolbar

    MIDDLEWARE_CLASSES = tuple(list(MIDDLEWARE_CLASSES) + [
        'debug_toolbar.middleware.DebugToolbarMiddleware',
    ])
    INSTALLED_APPS = tuple(list(INSTALLED_APPS) + [
        'debug_toolbar',
    ])
    INTERNAL_IPS = ('127.0.0.1',)
    DEBUG_TOOLBAR_CONFIG = {
        'INTERCEPT_REDIRECTS': False,
        'SHOW_TOOLBAR_CALLBACK': lambda request: False,
    }
except ImportError:
    pass

local_settings = os.path.join(os.path.dirname(__file__), 'local.py')
if os.path.isfile(local_settings):
    from local import *

PIPELINE = not DEBUG

JSCONF_DEVELOPMENT_MODE = True
