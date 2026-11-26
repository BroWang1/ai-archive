import time

import settings
from libs import cache
from libs.util import encode_jwt, datetime_ms
from apps.user.models import User

LOGIN_MAX_FAILS = 5             # 连续失败次数上限
LOGIN_LOCK_SECONDS = 15 * 60    # 达到上限后锁定时长


def update_user_access_token(uid, exp=86400 * 30):
    """更新用户access_token"""
    payload = {
        'uid': uid,
        'exp': int(time.time()) + exp
    }
    jwt_str = encode_jwt(payload, settings.SECRET_KEY)
    num = User.update_db(uid, {'access_token': jwt_str})
    if num == 0:
        raise Exception(f'update_user_access_token uid: {uid}  invalidate')
    return jwt_str


def _fail_key(username, ip):
    return f'{cache.BASE_KEY}login_fail:{username.lower()}:{ip}'


def login_locked(username, ip) -> bool:
    count = cache.get_redis_client().get(_fail_key(username, ip))
    return int(count or 0) >= LOGIN_MAX_FAILS


def login_failed(username, ip):
    client = cache.get_redis_client()
    key = _fail_key(username, ip)
    count = client.incr(key)
    if count == 1:
        client.expire(key, LOGIN_LOCK_SECONDS)
    return LOGIN_MAX_FAILS - int(count)


def login_succeeded(request, user: User):
    cache.get_redis_client().delete(_fail_key(user.name, getattr(request, 'client_ip', '')))
    request.session.cycle_key()     # 防止会话固定攻击
    request.session['login_uid'] = user.id
    request.session['login_at'] = int(time.time())
    User.update_db(user.id, {'last_login_at': datetime_ms()}, auto_updated_at=False)
