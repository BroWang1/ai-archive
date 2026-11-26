import logging

import orjson
from django.utils.deprecation import MiddlewareMixin
from pydantic import ValidationError

from libs.util import md5, time_ms, get_client_ip
from libs import ApiResponse, lodash, cache
from libs.defs import ApiErrorEnum, Minute_5
from settings import NODE_NAME

logger = logging.getLogger('lqa_ware')
logger_access = logging.getLogger('access')


# 参数校验错误中，字段英文名 -> 中文标签 的映射。
# 没有命中的字段会直接显示英文名（不会导致出错），后续按需补充即可。
FIELD_LABELS = {
    'name': '英文名',
    'name_zh': '中文名',
    'username': '用户名',
    'password': '密码',
    'old_password': '原密码',
    'new_password': '新密码',
    'email': '邮箱',
    'department': '部门',
    'roles': '角色',
    'role': '角色',
    'project_id': '项目',
    'status': '状态',
    'is_admin': '管理员',
    'id': 'ID',
    'code': '项目代号',
    'game_type': '游戏类型',
    'page': '页码',
    'page_size': '每页条数',
}


# 常见正则校验失败时的人类可读规则说明。key 是字段英文名（loc 最后一段），
# 命中后会替换掉通用的“格式不正确”提示。
# 说明文案需和 schemas 里的 Field.description / xxx_HELP 常量保持一致。
PATTERN_HELP = {
    'name': '需以字母开头，3~32 位，只能包含字母、数字、下划线、点、中划线',
    'username': '需以字母开头，3~32 位，只能包含字母、数字、下划线、点、中划线',
    'email': '邮箱格式不正确（例如：name@example.com）',
}


def _field_key(loc):
    """取 loc 路径的最后一段字段名，用于查 PATTERN_HELP。"""
    if not loc:
        return ''
    for item in reversed(loc):
        if not isinstance(item, int):
            return str(item)
    return ''


def _loc_to_label(loc):
    """把 pydantic 的 loc 路径（元组/列表）转成中文/英文字段标签。"""
    if not loc:
        return '参数'
    parts = []
    for item in loc:
        if isinstance(item, int):
            parts.append(f'[{item}]')
        else:
            parts.append(FIELD_LABELS.get(str(item), str(item)))
    return '.'.join(parts).replace('.[', '[')


def _format_validation_error(exc):
    """把 pydantic ValidationError 转成人类可读的中文清单。"""
    messages = []
    for err in exc.errors():
        err_type = err.get('type', '')
        loc = err.get('loc', ())
        msg = err.get('msg', '')
        ctx = err.get('ctx', {}) or {}
        label = _loc_to_label(loc)

        if err_type == 'missing':
            text = f'{label} 不能为空'
        elif err_type == 'string_too_short':
            min_len = ctx.get('min_length')
            text = f'{label} 长度不能少于 {min_len} 个字符' if min_len is not None else f'{label} 长度过短'
        elif err_type == 'string_too_long':
            max_len = ctx.get('max_length')
            text = f'{label} 长度不能超过 {max_len} 个字符' if max_len is not None else f'{label} 长度过长'
        elif err_type == 'string_pattern_mismatch':
            help_text = PATTERN_HELP.get(_field_key(loc))
            text = f'{label} 格式不正确，{help_text}' if help_text else f'{label} 格式不正确'
        elif err_type in ('int_parsing', 'float_parsing', 'int_type', 'float_type'):
            text = f'{label} 必须是数字'
        elif err_type in ('bool_parsing', 'bool_type'):
            text = f'{label} 必须是布尔值'
        elif err_type in ('greater_than', 'greater_than_equal'):
            limit = ctx.get('gt', ctx.get('ge'))
            text = f'{label} 必须大于 {limit}' if err_type == 'greater_than' else f'{label} 必须不小于 {limit}'
        elif err_type in ('less_than', 'less_than_equal'):
            limit = ctx.get('lt', ctx.get('le'))
            text = f'{label} 必须小于 {limit}' if err_type == 'less_than' else f'{label} 必须不大于 {limit}'
        elif err_type == 'enum':
            text = f'{label} 不在允许的取值范围内'
        elif err_type.startswith('value_error'):
            # 业务校验器自己 raise ValueError('xxx') 时，pydantic 会在 msg 前加 'Value error, '
            clean_msg = msg.replace('Value error, ', '') if msg else ''
            text = f'{label} {clean_msg}' if clean_msg else f'{label} 校验失败'
        elif err_type.startswith('type_error'):
            text = f'{label} 类型错误'
        else:
            # 兜底：显示原始英文 msg，避免丢失信息
            text = f'{label} {msg}' if msg else f'{label} 校验失败'
        messages.append(text)
    return '参数校验失败：' + '；'.join(messages)


class DistinctBodyMiddleware(MiddlewareMixin):

    def process_request(self, request):
        if request.method == 'POST':
            ens = md5(request.body)
            client = cache.get_redis_client()
            if not client.set(f'lqa:body:{ens}', time_ms(), nx=True, ex=Minute_5+10):
                return ApiResponse(ApiErrorEnum.ERROR, msg='可能短时间内重复提交')


class ExceptionMiddleware(MiddlewareMixin):

    def process_request(self, request):
        ip = getattr(request, 'client_ip', None)
        if not ip:
            err, ip = get_client_ip(request)
            if err:
                logger.error(f'get_client_ip err:{err}')
            request.client_ip = ip

    def process_exception(self, request, exception):
        logger.exception(f'request method:{request.method} path: {request.path}', exc_info=exception)

        if isinstance(exception, ValidationError):
            # 开发排查用：仍把完整的原始错误结构打到日志
            errs = list(map(lambda o: lodash.pick(o, ('type', 'loc', 'msg')), exception.errors()))
            logger.warning(f'ValidationError detail: {orjson.dumps(errs).decode("utf-8")}')
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg=_format_validation_error(exception))

        return ApiResponse(ApiErrorEnum.ERROR, msg=f'接口错误 {exception}')

    def process_response(self, request, response):
        if isinstance(response, ApiResponse) and response.data['code'] != 0:
            logger.warning(f'ApiError {request.client_ip} {request.method} {request.path} {response}')

        response['Lqa-Node'] = NODE_NAME

        headers = request.headers
        proxy_node = headers.get('proxy-node')
        if proxy_node:
            proxy_headers = {
                'proxy-node': proxy_node,
                'proxy-target-node': headers.get('proxy-target-node', ''),
                'proxy-node-trace': headers.get('proxy-node-trace', ''),
                'proxy-url': headers.get('proxy-url', '')
            }
            logger.info(f'[event.proxy_node.response] {orjson.dumps(proxy_headers).decode()}')

        return response


class AccessLogMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.__req_at = time_ms()
        ip = getattr(request, 'client_ip', None)
        if not ip:
            err, ip = get_client_ip(request)
            if err:
                logger.error(f'get_client_ip err:{err}')
            request.client_ip = ip

    def process_response(self, request, response):
        cost = time_ms() - request.__req_at
        content = getattr(response, 'content', None)
        size = '-' if content is None else len(content)
        logger_access.info(f'"{request.method} {request.get_full_path()}" {response.status_code} {size} {cost} "{request.client_ip}"')
        return response
