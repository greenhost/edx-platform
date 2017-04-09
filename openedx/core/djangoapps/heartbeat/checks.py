from importlib import import_module

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .defaults import HEARTBEAT_DEFAULT_CHECKS,\
    HEARTBEAT_EXTENDED_DEFAULT_CHECKS,\
    HEARTBEAT_CELERY_TIMEOUT

def checks(request):
    """
    Iterates through a tuple of systems checks,
    then returns a key name for the check and the value
    for that check.
    """
    response_dict = {}

    #Taken straight from Django
    #If there is a better way, I don't know it
    list_of_checks = getattr(settings, 'HEARTBEAT_CHECKS', HEARTBEAT_DEFAULT_CHECKS)
    if('extended' in request.GET):
        list_of_checks += getattr(settings, 'HEARTBEAT_EXTENDED_CHECKS', HEARTBEAT_EXTENDED_DEFAULT_CHECKS)

    for path in list_of_checks:
            i = path.rfind('.')
            module, attr = path[:i], path[i+1:]
            try:
                if(module[0] == '.'): #Relative path, assume relative to this app
                    mod = import_module(module, __package__)
                else:
                    mod = import_module(module)
                func = getattr(mod, attr)

                check_name, is_ok, message = func(request)
                response_dict[check_name] =  {
                    'status': is_ok,
                    'message': message
                }
            except ImportError as e:
                raise ImproperlyConfigured('Error importing module %s: "%s"' % (module, e))
            except AttributeError:
                raise ImproperlyConfigured('Module "%s" does not define a "%s" callable' % (module, attr))

    return response_dict

#DEFAULT SYSTEM CHECKS

#Modulestore

def check_modulestore(request):
    from xmodule.modulestore.django import modulestore
    from xmodule.exceptions import HeartbeatFailure
    # This refactoring merely delegates to the default modulestore (which if it's mixed modulestore will
    # delegate to all configured modulestores) and a quick test of sql. A later refactoring may allow
    # any service to register itself as participating in the heartbeat. It's important that all implementation
    # do as little as possible but give a sound determination that they are ready.
    try:
        #@TODO Do we want to parse the output for split and mongo detail and return it?
        modulestore().heartbeat()
        return 'modulestore', True, "OK"
    except HeartbeatFailure as fail:
        return 'modulestore', False, unicode(fail)

def check_database(request):
    from django.db import connection
    from django.db.utils import DatabaseError
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT CURRENT_DATE")
        cursor.fetchone()
        return 'sql', True, "OK"
    except DatabaseError as fail:
        return 'sql', False, unicode(fail)


#Caching
CACHE_KEY = 'heartbeat-test'
CACHE_VALUE = 'abc123'

def check_cache_set(request):
    from django.core.cache import cache
    try:
        cache.set(CACHE_KEY, CACHE_VALUE, 30)
        return 'cache_set', True, "OK"
    except fail:
        return 'cache_set', False, unicode(fail)

def check_cache_get(request):
    from django.core.cache import cache
    try:
        data = cache.get(CACHE_KEY)
        if data == CACHE_VALUE:
            return 'cache_get', True, "OK"
        else:
            return 'cache_get', False, "value check failed"
    except fail:
        return 'cache_get', False, unicode(fail)


#User
def check_user_exists(request):
    from django.contrib.auth.models import User
    try:
        username = request.GET.get('username')
        User.objects.get(username=username)
        return 'user_exists', True, "OK"
    except fail:
        return 'user_exists', False, unicode(fail)


#Celery
def check_celery(request):
    from datetime import datetime, timedelta
    from time import sleep, time
    from .tasks import sample_task

    now = time()
    datetimenow = datetime.now()
    expires = datetimenow + timedelta(seconds=getattr(settings, 'HEARTBEAT_CELERY_TIMEOUT', HEARTBEAT_CELERY_TIMEOUT))

    try:
        task = sample_task.apply_async(expires=expires)
        while expires > datetime.now():
            if task.ready() and task.result == True:
                finished = str(time() - now)
                return 'celery', True, unicode({ 'time':finished })
            sleep(0.25)
        return 'celery', False, "expired"
    except Exception as fail:
        return 'celery', False, unicode(fail)
