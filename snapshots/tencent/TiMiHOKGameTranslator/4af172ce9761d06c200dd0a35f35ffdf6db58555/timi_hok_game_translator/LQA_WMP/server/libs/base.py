from typing import Tuple, List, Set
from abc import ABC, abstractmethod
import logging
import datetime

from django.db import models, transaction
from django.views.generic import View

from libs.defs import SwitchEnum
from libs.util import time_ms, datetime_ms

logger = logging.getLogger('base')

class BaseManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_delete=SwitchEnum.OFF)


class BaseModel(models.Model):
    @classmethod
    def query_batch(cls, params, exclude_params=None, fields=None, size=600, asc=True, loop=1000):
        """大批量查询"""
        if exclude_params is None:
            exclude_params = {}
        if fields is None:
            fields = ['id']
        rows = []
        cur_id = 0 if asc else 100000000
        order_key = 'id'
        for _ in range(loop):
            if asc:  # 升序
                params['id__gt'] = cur_id
            else:
                params['id__lt'] = cur_id
                order_key = '-d'
            query_set = cls.objects.filter(**params).exclude(**exclude_params)
            rows_ = query_set.order_by(order_key)[:size].values(*fields)
            rows.extend(rows_)
            if len(rows_) < size:
                return rows
            cur_id = rows[-1]['id']
        return rows

    @classmethod
    def query_batch_by_pks(cls, pks, fields=None, step=500, reverse=False):
        """
        当 pks 数量比较多的场景
        reverse False 升序 True 降序
        """
        if not fields:
            fields = []
        cur = 0
        order_pks = sorted(pks, reverse=reverse)
        pks_ = order_pks[cur: cur + step]
        datas = []
        while len(pks_) > 0:
            rows = cls.objects.filter(pk__in=pks_).values(*fields)
            datas.extend(list(rows))
            cur += step
            pks_ = order_pks[cur: cur + step]
        return datas

    @classmethod
    def update_db_and_cache(cls, pks, mapping=None, cache_update=None, atomic=False, auto_updated_at=True):
        """更新数据库同时删除缓存"""
        if not pks or mapping is None or len(mapping) == 0:
            return 0, []
        if not (isinstance(pks, Tuple) or isinstance(pks, List) or isinstance(pks, Set)):
            pks = (pks,)
        if auto_updated_at and 'updated_at' not in mapping:
            mapping['updated_at'] = datetime_ms()

        def _update_db_and_cache():
            num = cls.objects.filter(pk__in=pks).update(**mapping)
            ret = []
            if cache_update:
                # 在事务内应该更新缓存, 而不是删除缓存
                if callable(cache_update):
                    cache_func_name = cache_update.__name__
                    ret = cache_update(pks)
                else:
                    cache_func_name = cache_update.hmget.__name__
                    ret = cache_update.hmget(pks, refresh=True)
                logger.info(f'update_query_and_cache model:{cls._meta.model_name} {cache_func_name}:{pks} rows:{num}')
            else:
                logger.info(f'update_query model:{cls._meta.model_name} rows:{num}')
            return num, ret

        if atomic:
            with transaction.atomic():
                return _update_db_and_cache()
        else:
            return _update_db_and_cache()

    @classmethod
    def update_db(cls, pks, mapping=None, auto_updated_at=True):
        """
        cls.objects.filter(pk__in=pks).update(**mapping) 方法是直接转为 SQL 语句的, 这是一种用于直接更新的批量操作,
        它并不会调用模型的 save() 方法, 或发射 pre_save 或 post_save 信号 (调用 save() 会触发信号), 或使用 auto_now 字段选项
        若想保存 QuerySet 中的每项, 并确保调用了每个实例的 save() 方法, 你并不需要任何特殊的函数来处理此问题, 迭代它们,
        并调用它们的 save() 方法
        所以再这里 统一更新 updated_at
        """
        if not pks or mapping is None or len(mapping) == 0:
            return 0
        if not (isinstance(pks, Tuple) or isinstance(pks, List) or isinstance(pks, Set)):
            pks = (pks,)
        if auto_updated_at and 'updated_at' not in mapping:
            mapping['updated_at'] = datetime_ms()
        return cls.objects.filter(pk__in=pks).update(**mapping)

    class Meta:
        abstract = True


class BaseAttrModel(BaseModel):
    is_delete = models.IntegerField(choices=SwitchEnum, default=SwitchEnum.OFF, verbose_name='逻辑删除')
    created_at = models.DateTimeField(default=datetime_ms)
    updated_at = models.DateTimeField(default=datetime_ms)

    objects = BaseManager()
    objects2 = models.Manager()

    class Meta:
        abstract = True


class PageView(View):

    BEGIN_AT = '_begin_at'
    END_AT = '_end_at'
    Pk_Conditions = {'pk__lt': 1, 'pk__lte': 1, 'pk__gt': 1, 'pk__gte': 1}

    Query_Fields = None

    def make_query_params(self, vmi, query_fields=None):
        if not query_fields:
            query_fields = self.Query_Fields
        if not query_fields:
            raise Exception('need query fields')
        has_pk_condition = False
        params = {}
        for field in query_fields:
            val = getattr(vmi, field)
            if val is not None:
                if field.endswith('contains') and len(val) == 0:
                    continue
                if field in self.Pk_Conditions:     # 防止和本身的 pk 查询冲突
                    has_pk_condition = True
                    if 'pk_lt' in params:
                        del params['pk_lt']
                if field == 'cur_id' and not has_pk_condition:  # 防止和本身的 pk 查询冲突
                    params['pk__lt'] = vmi.cur_id
                elif field.endswith(self.BEGIN_AT):
                    params[f'{field[:len(field) - len(self.BEGIN_AT)]}_at__gte'] = val
                elif field.endswith(self.END_AT):
                    params[f'{field[:len(field) - len(self.END_AT)]}_at__lt'] = val
                else:
                    params[field] = val
        logger.debug(f'make_query_params: {params}')
        return params

    def page_query(self, module, param, page=1, page_size=20, order_key='-id', return_id=False, fields=(),
                   page_by_where=None):
        """
        param dict or Q()
        """
        if isinstance(param, dict):
            total = module.objects.filter(**param).count()
        else:
            total = module.objects.filter(param).count()

        if total == 0:
            return 0, []

        if page_by_where is None:
            page_by_where = self.page_by_where(param)

        def _db_query(only_id_):
            if isinstance(param, dict):
                qs = module.objects.filter(**param).order_by(order_key)
            else:
                qs = module.objects.filter(param).order_by(order_key)
            qs = qs.values_list('id', flat=True) if only_id_ else qs.values(*fields)
            if page_by_where:  # 用 where + id 分页
                return qs[:page_size]
            else:   # 用 offset + limit 分页
                return qs[(page - 1) * page_size:page * page_size]

        return total, list(_db_query(return_id))

    @classmethod
    def page_by_where(cls, param: dict):
        return False  # 强制使用 page 分页
        if param is None:
            return False
        return True if any([k_ in param for k_ in cls.Pk_Conditions]) else False


class TaskBase(ABC):
    def __init__(self, ctx, request= None, logger=None):
        self.ctx = ctx
        self.request = request
        self.logger = logger

    @abstractmethod
    def run(self):
        pass


class ExpireData(ABC):
    def __init__(self, default_data=None, expire_time=60):
        self.expire_time = expire_time * 1000
        self.expire_at = 0
        self._data = default_data or {}

    @abstractmethod
    def query_db(self):
        pass

    @property
    def data(self):
        if time_ms() > self.expire_at:
            self._data = self.query_db()
            self.expire_at = time_ms() + self.expire_time
        return self._data
