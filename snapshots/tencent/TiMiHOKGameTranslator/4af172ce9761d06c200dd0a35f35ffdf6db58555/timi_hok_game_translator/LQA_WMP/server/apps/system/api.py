from libs.util import time_ms
from apps.system.models import SystemLanguage


_system_languages_value_map = {}
_system_languages_code_map = {}
_expire_at = 0


def get_system_language_config():
    global _system_languages_value_map
    global _system_languages_code_map
    global _expire_at
    if time_ms() > _expire_at:
        query_info = SystemLanguage.objects.filter(is_delete=0).values()
        __system_languages_value_map = {item['id']: {'value': item['id'], 'name': item['language_code'], 'label': item['language']}
                                  for item in query_info}
        _system_languages_value_map = __system_languages_value_map
        __system_languages_code_map = {item['language_code']: {'value': item['id'], 'name': item['language_code'], 'label': item['language']}
                                  for item in query_info}
        _system_languages_code_map = __system_languages_code_map
        _expire_at = time_ms() + 120
    return _system_languages_value_map


def get_language_by_code(language_code):
    get_system_language_config()
    return _system_languages_code_map.get(language_code, None)


def get_language_by_value(language_value):
    get_system_language_config()
    return _system_languages_value_map.get(language_value, None)

