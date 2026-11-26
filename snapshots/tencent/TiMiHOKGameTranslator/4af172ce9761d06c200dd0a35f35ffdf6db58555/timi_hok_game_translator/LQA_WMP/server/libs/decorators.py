import time
import functools
import logging

import orjson

from apps.project import service as proj_svr
from libs import ApiResponse, cache
from libs.defs import ApiErrorEnum, RoleEnum

logger = logging.getLogger(__name__)

DEFAULT_CHECK_PROJECT_ROLES = (RoleEnum.ADMIN, RoleEnum.DEVELOP, RoleEnum.TEST)

def _validate_ticket(ticket):
    expire_at = cache.ticket_cache.get(ticket, 0)
    validate = int(time.time()) < int(expire_at)
    if validate:
        cache.ticket_cache.delete(ticket)
    return validate


def require_ticket(func):
    """验证 ticket"""
    @functools.wraps(func)
    def _inner(request, *args, **kwargs):
        ticket = request.headers.get('LQA-Ticket', None)
        if not ticket:
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg='ticket require')
        if not _validate_ticket(ticket):
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg='ticket invalidate')

        return func(request, *args, **kwargs)
    return _inner


def test_super_admin(user_info):
    return True if user_info['is_admin'] else False


def require_super_admin(func):
    """检查超级管理员 装饰器"""
    @functools.wraps(func)
    def _inner(request, *args, **kwargs):
        if test_super_admin(request.user):
            return func(request, *args, **kwargs)
        else:
            return ApiResponse(ApiErrorEnum.ERROR_PERMISSION, msg='需要超管权限')
    return _inner


def test_project_user_role(user_info, project_users, roles, allow_super=True):
    """
    :param user_info:
    :param project_users:
    :param roles:
    :param allow_super:
    :return: bool
    """
    if allow_super and test_super_admin(user_info):
        return True
    if isinstance(roles, set):
        roles_set = roles
    elif isinstance(roles, tuple) or isinstance(roles, list):
        roles_set = set(roles)
    else:
        roles_set = {roles}
    has_roles = project_users['members'].get(str(user_info['id']), [])
    return True if len(roles_set.intersection(set(has_roles))) > 0 else False


def test_project_user_role_by_project_id(user_info, project_id, roles=DEFAULT_CHECK_PROJECT_ROLES, allow_super=True):
    if allow_super and test_super_admin(user_info):
        return True
    project_users = proj_svr.project_of_members(project_id)
    if not project_users:
        logger.error(f'test_project_user_role_by_project_id invalidate project:{project_id}')
        return False
    return test_project_user_role(user_info, project_users, roles, allow_super)


def test_project_user_role_by_project_ids(user_info, project_ids, check_roles, allow_super=True):
    if allow_super and test_super_admin(user_info):
        return True
    project_ids_set = project_ids if isinstance(project_ids, set) else set(project_ids)
    project_users = proj_svr.project_of_members(project_ids_set)
    if len(project_ids_set) != len(project_users):
        logger.error(f'test_project_user_role_by_project_ids invalidate projects:{project_ids_set}')
        return False
    return all(map(lambda item: test_project_user_role(user_info, item, check_roles, allow_super), project_users))


def require_project_perm(roles=DEFAULT_CHECK_PROJECT_ROLES, allow_super=True):
    """装饰器: 检查用户在项目中的角色"""
    def decorator(func):
        @functools.wraps(func)
        def _inner(request, *args, **kwargs):
            key = 'project_id'
            project_id = int(request.GET.get(key, 0)) or int(request.POST.get(key, 0)) or int(request.headers.get(key, 0))
            if not project_id and request.method != 'GET' and request.content_type == 'application/json':
                try:
                    body_json = orjson.loads(request.body)
                    project_id = int(body_json.get(key, 0))
                    request.body_json = body_json  # 标记一下, 不用重复 json 解析了
                except Exception as err:
                    pass
            code = ''
            if allow_super and test_super_admin(request.user):
                return func(request, *args, **kwargs)
            if project_id:
                project_users = proj_svr.project_of_members(project_id)
                if project_users:
                    if test_project_user_role(request.user, project_users, roles, allow_super):
                        return func(request, *args, **kwargs)
                    else:
                        code = f'test_project_user_role failed, roles:{roles} allow_super:{allow_super}'
                else:
                    code = f'no project_of_members:{project_id}'
            else:
                code = 'no project id'
            err_msg = f'require_project_perm uid: {request.user["id"]} msg: {code}'
            return ApiResponse(ApiErrorEnum.ERROR_PERMISSION, msg=err_msg)
        return _inner
    return decorator
