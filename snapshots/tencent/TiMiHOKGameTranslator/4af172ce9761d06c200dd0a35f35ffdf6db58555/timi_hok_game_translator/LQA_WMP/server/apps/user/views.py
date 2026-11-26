from typing import List, Tuple
import logging

from django.views.generic import View
from django.db import transaction
from django.utils.decorators import method_decorator
import orjson

import settings
from apps.project.models import Project
from apps.project import service as proj_svr
from apps.user import service as user_svr
from apps.user.models import User, UserProjectRelationship
from libs.decorators import *
from libs import ApiResponse, PageView, lodash
from libs.defs import ApiErrorEnum, RoleEnum, UserStatusEnum, SwitchEnum
from .schemas import *

logger = logging.getLogger('user_view')

# 管理员添加用户时，若未指定密码则使用该默认密码（需符合 Password 规则：8~64位、字母+数字）
DEFAULT_NEW_USER_PASSWORD = 'Lqa@123456'


def view_auth_config(request):
    """登录页需要的公开配置（免登录） GET /api/user/auth_config"""
    return ApiResponse(data={'allow_register': settings.ALLOW_REGISTER, 'app_name': settings.APP_NAME})


class UserLoginView(View):
    """账号密码登录（免登录） POST /api/user/login {username, password}"""

    def post(self, request):
        vmi = LoginSchema.model_validate(orjson.loads(request.body or b'{}'))
        username, ip = vmi.username.strip(), getattr(request, 'client_ip', '')
        if user_svr.login_locked(username, ip):
            return ApiResponse(ApiErrorEnum.ERROR_AUTH,
                               msg=f'登录失败次数过多，请 {user_svr.LOGIN_LOCK_SECONDS // 60} 分钟后再试')
        user = User.objects.filter(name=username).first()
        if not user or not user.check_password(vmi.password):
            left = user_svr.login_failed(username, ip)
            logger.warning(f'[event.user.login_fail] name:{username} ip:{ip}')
            return ApiResponse(ApiErrorEnum.ERROR_AUTH, msg=f'用户名或密码错误{f"，还可尝试 {left} 次" if left > 0 else ""}')
        if user.status != UserStatusEnum.ACTIVE:
            return ApiResponse(ApiErrorEnum.ERROR_AUTH, msg='账号已被禁用，请联系管理员')
        user_svr.login_succeeded(request, user)
        logger.info(f'[event.user.login] uid:{user.id} name:{user.name} ip:{ip}')
        return ApiResponse(data={'user': {'id': user.id, 'name': user.name, 'name_zh': user.name_zh,
                                          'is_admin': user.is_admin}})


class UserRegisterView(View):
    """自助注册（免登录） POST /api/user/register；注册后需由管理员分配项目角色才能使用业务功能"""

    def post(self, request):
        if not settings.ALLOW_REGISTER:
            return ApiResponse(ApiErrorEnum.ERROR_PERMISSION, msg='系统未开放注册，请联系管理员创建账号')
        vmi = RegisterSchema.model_validate(orjson.loads(request.body or b'{}'))
        if User.objects2.filter(name=vmi.username).exists():
            return ApiResponse(ApiErrorEnum.ERROR, msg='用户名已存在')
        user = User(name=vmi.username, name_zh=vmi.name_zh or vmi.username, email=vmi.email)
        user.set_password(vmi.password)
        user.save()
        logger.info(f'[event.user.register] uid:{user.id} name:{user.name} ip:{getattr(request, "client_ip", "")}')
        return ApiResponse(msg='注册成功，请登录')


class UserLogoutView(View):
    def post(self, request):
        request.session.flush()
        return ApiResponse(msg='已退出登录')

    get = post


class UserPasswordView(View):
    """修改自己的密码 POST /api/user/password {old_password, new_password}"""

    def post(self, request):
        vmi = PasswordChangeSchema.model_validate(orjson.loads(request.body))
        user = User.objects.filter(pk=request.user['id']).first()
        if not user.check_password(vmi.old_password):
            return ApiResponse(ApiErrorEnum.ERROR, msg='原密码错误')
        user.set_password(vmi.new_password)
        user.save(update_fields=['password', 'updated_at'])
        request.session.cycle_key()     # 更换当前会话ID，保留登录态
        logger.info(f'[event.user.password] uid:{user.id}')
        return ApiResponse(msg='密码已修改')


@require_super_admin
def view_reset_password(request):
    """超级管理员重置用户密码 POST /api/user/reset_password {id, new_password}"""
    vmi = PasswordResetSchema.model_validate(orjson.loads(request.body))
    user = User.objects.filter(pk=vmi.id).first()
    if not user:
        return ApiResponse(ApiErrorEnum.NOT_EXIST, msg='用户不存在')
    user.set_password(vmi.new_password)
    user.save(update_fields=['password', 'updated_at'])
    logger.info(f'[event.user.reset_password] by:{request.user["name"]} uid:{user.id}')
    return ApiResponse(msg='密码已重置')


class UserProfileView(View):
    """修改自己的资料 PATCH /api/user/profile"""

    def patch(self, request):
        vmi = ProfilePatchSchema.model_validate(orjson.loads(request.body))
        mapping = vmi.model_dump(exclude_unset=True, exclude_none=True)
        if mapping:
            User.update_db(request.user['id'], mapping)
        return ApiResponse(msg='已保存')


def _patch_user_infos(user_infos, include=None, exclude=None):
    if exclude is None:
        exclude = User.SENSITIVE_FIELDS
    if isinstance(user_infos, List) or isinstance(user_infos, Tuple):
        ret = []
        for user_info_ in user_infos:
            if include:
                user_info_ = lodash.pick(user_info_, include)
            user_info_ = lodash.omit(user_info_, exclude, False)
            ret.append(user_info_)
        return ret
    else:
        user_info_ = lodash.omit(user_infos, exclude, False)
        if include:
            user_info_ = lodash.pick(user_infos, include)
        return user_info_


def _patch_user_project_roles(user_infos, user_of_project_roles, project_dict):
    for user_info in user_infos:
        user_info['projects'] = []
        user_info['roles'] = []
        uid = user_info['id']
        project_roles = user_of_project_roles.get(uid, {})
        for project_id, roles in project_roles.items():
            project_info = project_dict.get(project_id)
            if project_info:
                user_info['roles'].extend(list(map(lambda role: f'{project_info["id"]}_{role}', roles)))
                user_info['projects'].append({'id': project_info['id'], 'code': project_info['code'],
                                              'name': project_info['name'], 'roles': roles})


def _query_user_of_project_roles(ship_param_):
    """{user_id1: {project_id1: [role1, role2]} }"""
    ships = UserProjectRelationship.objects.filter(**ship_param_).values()
    user_of_project_roles_ = {}
    project_ids_set_ = set()
    for ship in ships:
        projects_dict = user_of_project_roles_.get(ship['user_id'], {})
        roles = projects_dict.get(ship['project_id'], [])
        roles.append(ship['role'])
        projects_dict[ship['project_id']] = roles
        user_of_project_roles_[ship['user_id']] = projects_dict
        project_ids_set_.add(ship['project_id'])
    return user_of_project_roles_, project_ids_set_


class UserListView(PageView):
    Query_Fields = ('cur_id', 'name__icontains', 'name_zh__icontains', 'department__icontains', 'status')

    def get(self, request):
        vmi = UserListSchema.model_validate(request.GET.dict())
        page, page_size, project_id, is_admin, info_type = vmi.page, vmi.page_size, vmi.project_id, vmi.is_admin, vmi.info_type

        user_param = self.make_query_params(vmi)

        ship_param = {}
        if project_id is not None:
            ship_param['project_id'] = project_id

        # is_admin 筛选：以"该用户在筛选范围内是否担任过 ADMIN"做二分，避免同一用户同时命中"是/否"
        # 先按 project_id 过滤查到范围内担任 ADMIN 的 user_id 集合
        admin_user_ids = None
        if is_admin is not None:
            admin_ship_param = dict(ship_param)
            admin_ship_param['role'] = RoleEnum.ADMIN
            admin_user_ids = set(
                UserProjectRelationship.objects.filter(**admin_ship_param).values_list('user_id', flat=True)
            )
            if is_admin == 1 and not admin_user_ids:
                return ApiResponse(data={'list': [], 'total': 0, 'page': page, 'page_size': page_size}, msg='empty')

        # 按 project_id 查该项目下的所有相关用户关系（用于后续 role 展示 & 范围限制）
        user_of_project_roles = {}
        project_ids_set = set()
        if len(ship_param) > 0:
            user_of_project_roles, project_ids_set = _query_user_of_project_roles(ship_param)
            if len(user_of_project_roles) == 0:
                return ApiResponse(data={'list': [], 'total': 0, 'page': page, 'page_size': page_size}, msg='empty')

        # 组装 user_param['id__in']：按 project_id 范围 ∩ is_admin 二分规则
        if is_admin == 1:
            # 查管理员：必须在 admin_user_ids 内；若还有 project 范围，则取交集
            allowed_ids = admin_user_ids
            if user_of_project_roles:
                allowed_ids = allowed_ids & set(user_of_project_roles.keys())
            if not allowed_ids:
                return ApiResponse(data={'list': [], 'total': 0, 'page': page, 'page_size': page_size}, msg='empty')
            user_param['id__in'] = list(allowed_ids)
        elif is_admin == 0:
            # 查非管理员：从"候选集合"中排除 admin_user_ids
            if user_of_project_roles:
                allowed_ids = set(user_of_project_roles.keys()) - admin_user_ids
            else:
                # 未指定项目：从全站用户中排除 admin_user_ids
                allowed_ids = set(User.objects.values_list('id', flat=True)) - admin_user_ids
            if not allowed_ids:
                return ApiResponse(data={'list': [], 'total': 0, 'page': page, 'page_size': page_size}, msg='empty')
            user_param['id__in'] = list(allowed_ids)
        elif user_of_project_roles:
            # 没有 is_admin 筛选但有 project 范围
            user_param['id__in'] = list(user_of_project_roles.keys())

        total, user_infos = self.page_query(User, user_param, page, page_size)
        if len(user_infos) == 0:
            return ApiResponse(data={'list': [], 'total': total, 'page': page, 'page_size': page_size})

        if info_type == 0:  # info
            user_infos = _patch_user_infos(user_infos)
            return ApiResponse(data={'list': user_infos, 'total': total, 'page': page, 'page_size': page_size})
        elif info_type == 1: # simple info
            user_infos = _patch_user_infos(user_infos, include=('id', 'name', 'name_zh'))
            return ApiResponse(data={'list': user_infos, 'total': total, 'page': page, 'page_size': page_size})
        else:
            if len(ship_param) == 0:
                ship_param['user_id__in'] = list(map(lambda user_info_: user_info_['id'],user_infos))
                user_of_project_roles, project_ids_set = _query_user_of_project_roles(ship_param)
            user_infos = _patch_user_infos(user_infos)
            project_dict = {p_['id']: p_ for p_ in Project.objects.filter(pk__in=project_ids_set).values()}
            _patch_user_project_roles(user_infos, user_of_project_roles, project_dict)

            return ApiResponse(data={'list': user_infos, 'total': total, 'page': page, 'page_size': page_size})


class UserView(View):

    @classmethod
    def _check_permission(cls, current_user, project_id, roles, update_is_admin):
        ERROR_PERMISSION = ApiErrorEnum.ERROR_PERMISSION
        is_super = test_super_admin(current_user)
        if is_super:
            return True, None
        # 不是super_admin 不能修改用户的is_admin属性
        if update_is_admin:
            return False, ApiResponse(ERROR_PERMISSION, msg='update_is_admin, 需要超管权限')
        # 不是super_admin 需要 project_id
        if not project_id:
            return False, ApiResponse(ApiErrorEnum.ERROR_PARAM, msg='请指定项目')
        if not test_project_user_role_by_project_id(current_user, project_id, {RoleEnum.ADMIN}):
            return False, ApiResponse(ERROR_PERMISSION, msg='需要项目管理员权限')
        # 不是super_admin 只能同时操作project_id一个项目且是管理员
        project_ids_set = set(map(lambda role: role[0], roles or []))
        if len(project_ids_set) > 1:
            return False, ApiResponse(ERROR_PERMISSION, msg='多项目修改, 需要超管权限')
        elif len(project_ids_set) == 1 and project_id not in project_ids_set:
            return False, ApiResponse(ERROR_PERMISSION, msg='跨项目修改, 需要超管权限')
        return True, None

    def post(self, request):
        """管理员创建用户（超管，或项目管理员为本项目创建成员）"""
        vr = UserCreateSchema.model_validate(orjson.loads(request.body))
        name, roles, project_id = vr.name, vr.roles, vr.project_id
        current_user = request.user

        ok, api_response = self._check_permission(current_user, project_id, roles, False)
        if not ok:
            return api_response

        user = User.objects2.filter(name=name).first()  # 可能之前被删除了，重新加回来
        if user and user.is_delete == 0:
            return ApiResponse(ApiErrorEnum.ERROR, msg=f'用户 {name} 已存在')
        if not user:
            user = User(name=name)
        user.is_delete = 0
        user.status = UserStatusEnum.ACTIVE
        user.name_zh = vr.name_zh or name
        user.email = vr.email
        user.department = vr.department
        # 管理员添加用户时允许不传密码，此时使用系统默认密码
        user.set_password(vr.password or DEFAULT_NEW_USER_PASSWORD)
        try:
            with transaction.atomic():
                user.save()
                if roles:
                    proj_svr.update_user_project_roles(user.id, project_id, roles)
        except Exception as err:
            logger.error('UserProjectRelationship bulk_create err:', exc_info=err)
            return ApiResponse(ApiErrorEnum.ERROR, msg=f'创建失败 err:{err}')
        user_info = _patch_user_infos(User.objects.filter(pk=user.id).values().first())
        logger.info(f'[event.user.add] user:{current_user["name"]} name:{name} roles:{roles}')
        return ApiResponse(data={'user': user_info})

    def patch(self, request, *args, **kwargs):
        vr = UserPatchSchema.model_validate(orjson.loads(request.body))
        roles, is_admin, project_id = vr.roles, vr.is_admin, vr.project_id
        uid = vr.id
        current_user = request.user

        user_info = User.objects.filter(pk=uid).values().first()
        if not user_info:
            return ApiResponse(ApiErrorEnum.NOT_EXIST, msg='用户数据不存在')
        # 只保留真正发生变化的资料字段（前端编辑表单会把未修改的字段一并提交）
        profile = {k: v for k, v in vr.model_dump(include={'name_zh', 'email', 'department', 'status'},
                                                  exclude_none=True).items() if user_info.get(k) != v}
        if roles is None and is_admin is None and not profile:
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg='没有需要修改的内容')

        update_is_admin = True if is_admin is not None and is_admin != user_info['is_admin'] else False
        # 修改资料/禁用账号属于超管操作
        ok, api_response = self._check_permission(current_user, project_id, roles, update_is_admin or bool(profile))
        if not ok:
            return api_response
        if uid == current_user['id'] and (is_admin == SwitchEnum.OFF or profile.get('status') == UserStatusEnum.DISABLED):
            return ApiResponse(ApiErrorEnum.ERROR, msg='不能取消自己的超管权限或禁用自己')

        try:
            with transaction.atomic():
                mapping = dict(profile)
                if update_is_admin:
                    mapping['is_admin'] = is_admin
                if mapping:
                    User.update_db(uid, mapping)
                if roles is not None:
                    proj_svr.update_user_project_roles(uid, project_id, roles)
        except Exception as err:
            logger.error('UserProjectRelationship bulk_create err:', exc_info=err)
            return ApiResponse(ApiErrorEnum.ERROR, msg=f'修改失败 err:{err}')
        logger.info(f'[event.user.update] user:{request.user["name"]} body:{orjson.dumps(vr.model_dump()).decode()}')
        return ApiResponse()

    def get(self, request):
        uid = int(request.GET.get('id', request.user['id']))
        info_type = int(request.GET.get('info_type', 1))

        user_info = User.objects.filter(pk=uid).values().first()
        if not user_info:
            return ApiResponse(ApiErrorEnum.NOT_EXIST, msg='用户不存在')

        # 本人可以看到自己的 access_token，密码哈希任何情况下都不返回
        exclude = ('password',) if user_info['id'] == request.user['id'] else User.SENSITIVE_FIELDS
        user_info = _patch_user_infos(user_info, exclude=exclude)

        if info_type == 1:
            user_of_project_roles, project_ids_set = _query_user_of_project_roles({'user_id': uid})
            project_dict = {p_['id']: p_ for p_ in Project.objects.filter(pk__in=project_ids_set).values()}

            _patch_user_project_roles((user_info,), user_of_project_roles, project_dict)

        return ApiResponse(data={'user': user_info})

    @method_decorator(require_super_admin)
    def delete(self, request):
        body = orjson.loads(request.body) if request.content_type == 'application/json' else request.POST.dict()
        uid = int(body.get('id', 0))
        if not uid:
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg=f'非法用户id:{uid}')
        if uid == request.user['id']:
            return ApiResponse(ApiErrorEnum.ERROR, msg='不能删除自己')
        user = User.objects.filter(pk=uid).first()
        if not user:
            return ApiResponse(ApiErrorEnum.NOT_EXIST)
        try:
            with transaction.atomic():
                proj_svr.update_ship_and_project_cfg_by_delete_user(uid)
                user.is_delete = 1
                user.access_token = ''
                user.save(update_fields=['is_delete', 'access_token'])
        except Exception as err:
            logger.error('use delete err:', exc_info=err)
            return ApiResponse(ApiErrorEnum.ERROR, msg=f'删除失败 err:{err}')
        logger.info(f'[event.user.del] user:{request.user["name"]} body:{orjson.dumps(body).decode()}')
        return ApiResponse()


def user_permission_view(request):
    user = request.user
    projects = []
    project_ids_set = set()
    ships = UserProjectRelationship.objects.filter(user_id=user['id'])
    ships_dict = {}
    for ship in ships:
        roles = ships_dict.get(ship.project_id, [])
        roles.append(f'{ship.project_id}_{ship.role}')
        ships_dict[ship.project_id] = roles
        project_ids_set.add(ship.project_id)

    user = _patch_user_infos(user, include=('id', 'is_admin', 'name', 'name_zh'))

    qs = None
    if user['is_admin']:
        qs = Project.objects.all().exclude(pk=0)
    elif len(project_ids_set) > 0:
        qs = Project.objects.filter(id__in=project_ids_set).exclude(pk=0)
    if qs:
        projects = qs.values('id', 'code', 'name')
    for p in projects:
        p['roles'] = ships_dict.get(p['id'], [])
    return ApiResponse(data={'user': user, 'projects': projects})


class UserToken(View):

    @method_decorator(require_ticket)
    def post(self, request):
        uid = request.user['id']
        jwt_str = user_svr.update_user_access_token(uid)
        logger.info(f'[event.access_token] user:{request.user["name"]}')
        return ApiResponse(data={'access_token': jwt_str})
