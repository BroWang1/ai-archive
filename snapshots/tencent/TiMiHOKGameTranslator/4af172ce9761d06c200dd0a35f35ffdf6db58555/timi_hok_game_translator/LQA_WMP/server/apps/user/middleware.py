import time
import re
import logging

from django.utils.deprecation import MiddlewareMixin

import settings
from apps.user.models import User
from libs.util import decode_jwt
from libs import ApiResponse
from libs.defs import ApiErrorEnum, UserStatusEnum

logger = logging.getLogger('user_ware')

# 免登录接口
_exclude_paths = (
    r'^/api/user/(login|register|auth_config)$',
    r'^/api/health$',
)
if settings.MEDIA_PUBLIC:   # 截图允许匿名访问（禅道内嵌截图需要）
    _exclude_paths += (r'^/media/', )
_re_exclude_paths = list(map(lambda p: re.compile(p), _exclude_paths))

# request.user 中不携带的字段
_user_fields = [f.name for f in User._meta.concrete_fields if f.name != 'password']


class AuthRequiredMiddleware(MiddlewareMixin):
    """
    检查用户登录
      - 浏览器：Session（/api/user/login 登录后写入 login_uid）
      - API 调用：请求头 LQA-Authorization: <access_token>，通过 /api/user/access_token 获取
    """
    def process_request(self, request):
        if any(map(lambda reg: reg.match(request.path), _re_exclude_paths)):
            return

        uid = None
        access_token = request.headers.get('LQA-Authorization', 'web')
        if access_token in ('web', ''):
            access_token = None
        if access_token is not None:
            code, body = decode_jwt(access_token, settings.SECRET_KEY)
            if code != 0:
                logger.error(f'decode_jwt code:{code} err:{body}')
                return ApiResponse(ApiErrorEnum.ERROR_AUTH, msg=f'认证失败，access_token验证失败:{code}')
            if time.time() - int(body['exp']) > 0:
                logger.error(f' access_token expire uid:{body["uid"]}')
                return ApiResponse(ApiErrorEnum.ERROR_AUTH, msg=f'认证失败，access_token已过期')
            uid = body['uid']

        if not uid:
            uid = request.session.get('login_uid', None)

        if not uid:
            return ApiResponse(ApiErrorEnum.ERROR_AUTH, msg='未登录或登录已过期')

        user = User.objects.filter(pk=int(uid)).values(*_user_fields).first()
        if not user:
            request.session.flush()
            return ApiResponse(ApiErrorEnum.ERROR_AUTH, msg='认证失败，用户不存在')
        if user['status'] != UserStatusEnum.ACTIVE:
            request.session.flush()
            return ApiResponse(ApiErrorEnum.ERROR_AUTH, msg='账号已被禁用，请联系管理员')

        if access_token is not None and access_token != user['access_token']:
            return ApiResponse(ApiErrorEnum.ERROR_AUTH, msg='认证失败，非法的access_token')

        request.user = user
