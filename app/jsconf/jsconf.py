import json
import time

from django.conf import settings


def get_config():

    if getattr(settings, 'JSCONF_DEVELOPMENT_MODE', False):
        timestamp = ""
    else:
        timestamp = int(time.time())   # POSIX timestamp

    js_configuration = {
        'debug': settings.JS_DEBUG,
        'timestamp': timestamp,
        'static_url': settings.STATIC_URL,
    }

    return 'window.jsconf = %s;' % json.dumps(js_configuration)
