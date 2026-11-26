import datetime
import decimal
import uuid
import json

from django.utils.timezone import is_aware
from django.utils.duration import duration_iso_string
from django.utils.functional import Promise
from django.http.response import JsonResponse, HttpResponse
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models.query import QuerySet
from django.db.models import Choices
import orjson


def _default_api_data(code, data, msg, api_err: Choices = None):
    if data is None:
        data = {}
    if api_err:
        resp = {'code': api_err.value, 'data': data, 'msg': api_err.label }
        if code:
            resp['code'] = code
        if msg:
            resp['msg'] = msg
        return resp
    return {'code': code, 'data': data, 'msg': msg}


class ApiResponseBase(HttpResponse):
    def __init__(self, api_err: Choices = None, data=None, code=0, msg='', dump=True, **kwargs):
        self.data = _default_api_data(code, data, msg, api_err)
        kwargs.setdefault("content_type", "application/json")
        # 业务错误统一返回 HTTP 500; 认证失败 (1003) 返回 401, 前端据此跳转登录页
        kwargs.setdefault("status", 200 if self.data['code'] == 0 else (401 if self.data['code'] == 1003 else 500))
        data_s = self.json() if dump else ''
        self._dumped = dump
        super().__init__(data_s, **kwargs)

    def dump(self, force=False):
        """dump content"""
        if self._dumped and not force:
            return self
        self.content = self.json()
        self._dumped = True
        return self

    def raw(self):
        """raw data"""
        return self.data

    def __str__(self):
        return f"code:{self.data['code']}, msg:{self.data['msg']}"


class ApiJsonResponse(ApiResponseBase):
    def __init__(self, api_err: Choices = None, data=None, code=0, msg='', dump=True,
                 encoder=None, json_dumps_params=None, **kwargs):
        self.encoder = encoder
        self.json_dumps_params = json_dumps_params
        super().__init__(api_err, data, code, msg, dump, **kwargs)

    def json(self, encoder=DjangoJSONEncoder, json_dumps_params=None):
        """
        :param encoder:
        :param json_dumps_params:
        :return: str
        """
        json_dumps_params_ = json_dumps_params or self.json_dumps_params or {}
        encoder_ = encoder or self.encoder
        return json.dumps(self.data, cls=encoder_, **json_dumps_params_)


class ApiOrjsonResponse(ApiResponseBase):
    def __init__(self, api_err: Choices = None, data=None, code=0, msg='', dump=True, json_dumps_params=None, **kwargs):
        self.json_dumps_params = json_dumps_params or {}
        super().__init__(api_err, data, code, msg, dump, **kwargs)

    def json(self, json_dumps_params=None):
        """
        :param json_dumps_params:
        :return:  bytes
        """
        json_dumps_params_ = json_dumps_params or self.json_dumps_params or {}
        return orjson.dumps(self.data, default=self._encode_default, option=orjson.OPT_PASSTHROUGH_DATETIME,
                            **json_dumps_params_)

    @classmethod
    def _encode_default(cls, o):
        if isinstance(o, QuerySet):
            return tuple(o)
        elif isinstance(o, datetime.datetime):
            r = o.isoformat()
            if o.microsecond:
                r = r[:23] + r[26:]
            if r.endswith("+00:00"):
                r = r.removesuffix("+00:00") + "Z"
            return r
        elif isinstance(o, datetime.date):
            return o.isoformat()
        elif isinstance(o, datetime.time):
            if is_aware(o):
                raise ValueError("JSON can't represent timezone-aware times.")
            r = o.isoformat()
            if o.microsecond:
                r = r[:12]
            return r
        elif isinstance(o, datetime.timedelta):
            return duration_iso_string(o)
        elif isinstance(o, (decimal.Decimal, uuid.UUID, Promise)):
            return str(o)
        elif hasattr(o, '__iter__'):
            return tuple(item for item in o)
        raise TypeError


ApiResponse = ApiOrjsonResponse
