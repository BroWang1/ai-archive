import random
import time
import logging
import traceback
from typing import List
from zlib import compress as zcompress, decompress as zdecompress, error as ZLIB_ERROR

import orjson
from orjson import loads as json_loads, dumps as json_dumps, JSONDecodeError
from django.core.cache import cache
from django.db.models import Count, Max
from munch import Munch as AttrDict

from settings import COMPRESS
from apps.bug.models import Bug
from apps.project.models import Project, Module
from apps.data.models import Data
from apps.user.models import User, UserProjectRelationship
from apps.job.models import Job, JobExtra
from apps.image.models import Image
from libs.defs import Minute_5, BugBillStatusEnum

logger = logging.getLogger('cache')


def _json_loads_zlib(bjson, compress):
    if compress and COMPRESS:  # 可能旧缓存还是 json 的
        try:
            return json_loads(zdecompress(bjson))
        except ZLIB_ERROR:
            return json_loads(bjson)
    else:
        try:
            return json_loads(bjson)
        except JSONDecodeError:
            return json_loads(zdecompress(bjson))


def _json_dumps_zlib(obj, compress):
    return zcompress(json_dumps(obj)) if compress and COMPRESS else json_dumps(obj)


def get_redis_client():
    return cache._cache.get_client()


BASE_KEY = "lqa_"


class ConnectBase(object):
    @property
    def client(self):
        return cache._cache.get_client()


class TableBase(ConnectBase):
    def __init__(self, modal, name, expire=Minute_5, compress=False ):
        self.name = name
        self.modal = modal
        self.expire = expire
        self.compress = compress

        self.db_name = f'{BASE_KEY}{self.name}'

    def _field(self, obj):
        return obj['id']
    def _index_pk(self, pk_):
        return f'{self.db_name}:{pk_}'
    def _index_obj(self, obj):
        return f'{self.db_name}:{self._field(obj)}'

    def _query_db(self, pks, **kwargs):
        if len(pks) == 0:
            return []
        return list(self.modal.objects.filter(pk__in=pks).values())

    def mset(self, objs, expire=None):
        if len(objs) == 0:
            return
        client = self.client
        mapping = {self._index_obj(o): _json_dumps_zlib(o, self.compress) for o in objs}
        client.mset(mapping)

        expire_ = expire if expire else self.expire
        pipe = client.pipeline()
        for key in mapping.keys():
            pipe.expire(key, expire_ + random.randint(1, 10))
        pipe.execute()

    def hget(self, pk, default=None, refresh=False, attrify=False, **kwargs):
        objs = self.hmget([pk], refresh=refresh, attrify=attrify, **kwargs)
        return default if len(objs) == 0 else objs[0]

    def hmget(self, pks: List = None, refresh=False, mapping=False, attrify=False, ** kwargs):
        if len(pks) == 0:
            return {} if mapping else []
        pks = list(pks) if isinstance(pks, set) else list(set(pks))
        if refresh:
            objs = self._query_db(pks, **kwargs)
            self.mset(objs)
        else:
            b_jsons = self.client.mget(map(self._index_pk, pks))
            quey_db_pks = []
            objs = []
            for idx, bjson in enumerate(b_jsons):
                if bjson is None:
                    quey_db_pks.append(pks[idx])
                    continue
                objs.append(_json_loads_zlib(bjson, self.compress and COMPRESS))
            objs_delt = self._query_db(quey_db_pks, **kwargs)
            for obj in objs_delt:
                objs.append(obj)
            self.mset(objs_delt)
        if attrify:
            objs = list(map(lambda o: AttrDict(o), objs))
        if mapping:
            return {self._field(obj): obj for obj in objs}
        return objs

    def hdel(self, *pks):
        self.client.delete(*list(map(self._index_pk, pks)))



class CommBase(ConnectBase):
    def __init__(self, name='comm'):
        self.prefix = f'{BASE_KEY}{name}'

    def key(self, name):
        return f'{self.prefix}:{name}'

    def set(self, name, val, json=False, timeout=Minute_5):
        if json:
            val = orjson.dumps(val)
        self.client.set(self.key(name), val, ex=timeout)

    def get(self, name, default=None, json=False):
        val = self.client.get(self.key(name))
        if val is None:
            return default
        return orjson.loads(val) if json else val

    def delete(self, name):
        self.client.delete(self.key(name))


class UserHash(TableBase): pass
class ProjectHash(TableBase): pass
class DataHash(TableBase): pass
class JobHash(TableBase): pass
class JobExtraHash(TableBase): pass
class ImageHash(TableBase): pass
class BugHash(TableBase): pass


class JobRegressNumHash(TableBase):
    def _query_db(self, pks, **kwargs):
        if len(pks) == 0:
            return []
        param = {'parent_id__in': pks}
        if 'project_id' in kwargs:
            param['project_id'] = kwargs['project_id']
        rows = self.modal.objects.filter(**param).values('id', 'parent_id')
        stat = {}
        for row in rows:
            job = stat.get(row['parent_id'], {'id': row['parent_id'], 'children': []})
            job['children'].append(row['id'])
            stat[row['parent_id']] = job
        if len(pks) != len(rows):  # 防止频繁查询 Job 表, 场景: 查询不到时, 补充默认值
            delt_pk_set = set(pks) - set(stat.keys())
            for pk in delt_pk_set:
                stat[pk] = {'id': pk, 'children': []}
        return list(stat.values())


class JobBugNumHash(TableBase):
    def _gen(self, pk):
        return {'job_id': pk, 'bug_num': 0}

    def _query_db(self, pks, **kwargs):
        param = {'job_id__in': pks}
        if 'project_id' in kwargs:
            param['project_id'] = kwargs['project_id']
        stats = list(self.modal.objects.filter(**param).values('job_id').annotate(bug_num=Count('job_id')))
        if len(stats) == len(pks):
            return stats
        # 防止频繁查询 Bug 表, 场景: 有些 job 没有产生 bug
        delt_pks_set = set(pks) - set(map(lambda stat: stat['job_id'], stats))
        for pk_ in delt_pks_set:
            stats.append(self._gen(pk_))
        return stats


    def _field(self, obj):
        return obj['job_id']

class ImageBugNumHash(TableBase):
    def _gen(self, pk):
        return {'image_id': pk, 'bug_num': 0}

    def _query_db(self, pks, **kwargs):
        param = {'image_id__in': pks, 'bill_status': BugBillStatusEnum.SUCCESS}
        if 'job_id' in kwargs:
            param['job_id'] = kwargs['job_id']
        stats = list(self.modal.objects.filter(**param).values('image_id').annotate(bug_num=Count('image_id')))
        if len(stats) == len(pks):
            return stats
        # 防止频繁查询 Bug 表, 场景: 有些 image 没有产生 bug
        delt_pks_set = set(pks) - set(map(lambda stat: stat['image_id'], stats))
        for pk_ in delt_pks_set:
            stats.append(self._gen(pk_))
        return stats

    def _field(self, obj):
        return obj['image_id']


class ProjectUserHash(TableBase):
    """
    {
        "project_id": project_id,
        "members": [
            user_id_str: [1, 2, 3]
        ]
    }
    """
    def _query_db(self, project_ids):
        if len(project_ids) == 0:
            return []
        projects = {}
        for ship_row in self.modal.objects.filter(project_id__in=project_ids).values():
            project_id = ship_row['project_id']
            user_id = ship_row['user_id']
            user_id_str = str(user_id)
            role = ship_row['role']
            project = projects.get(project_id, {'project_id': project_id, 'members': {}})
            roles = project['members'].get(user_id_str, [])
            roles.append(role)
            project['members'][user_id_str] = roles
            projects[project_id] = project
        return list(projects.values())

    def _field(self, obj):
        return obj['project_id']


class ModuleHash(TableBase):

    wrap_id = '_projectid_'
    def _field(self, obj):
        return obj[self.wrap_id]

    def _query_db(self, project_ids, **kwargs):
        rows = self.modal.objects.filter(project_id__in=project_ids).values()
        wrap_rows = {}
        for row in rows:
            wrap_row = wrap_rows.get(row['project_id'], {self.wrap_id: row['project_id']})
            wrap_row[str(row['id'])] = row
            wrap_rows[row['project_id']] = wrap_row
        return wrap_rows.values()

    def hget(self, pk, default=None, refresh=False, attrify=False, **kwargs):
        val = super().hget(pk, default=default, refresh=refresh, attrify=attrify, **kwargs)
        if val:
            del val[self.wrap_id]
        return val


user_cache = UserHash(User, 'users')
project_cache = ProjectHash(Project, 'projects')
project_module_cache = ModuleHash(Module, 'project_module', compress=True)
project_user_cache = ProjectUserHash(UserProjectRelationship, 'project_users')
data_cache = DataHash(Data, 'datas', Minute_5 * 2, compress=True)
job_cache = JobHash(Job, 'jobs')
job_ext_cache = JobExtraHash(JobExtra, 'job_extra')
job_regress_num_cache = JobRegressNumHash(Job, 'job_regress_num')
job_bug_num_cache = JobBugNumHash(Bug, 'bug_num')
image_cache = ImageHash(Image, 'images', compress=True)
image_bug_num_cache = ImageBugNumHash(Bug, 'image_bug_num')
bug_cache = BugHash(Bug, 'bugs')


class ResourceVersionZSet(ConnectBase):
    KEY_RESOURCE_VERSION = f'{BASE_KEY}resource_versions'

    def _index_pk(self, project_id):
        return f'{self.KEY_RESOURCE_VERSION}:{project_id}'

    def _query_db(self, project_id):
        # return Data.objects.filter(project_id=project_id).exclude(resource_version='')\
        #            .values_list('id', 'resource_version')[:1000]
        return Data.objects.filter(project_id=project_id).exclude(resource_version='')\
            .values('resource_version').annotate(id=Max('id')).values_list('id', 'resource_version')

    def reset(self, project_id):
        qset = self._query_db(project_id)
        mapping = {version: id_ for id_, version in qset}
        index_pk = self._index_pk(project_id)
        self.client.delete(index_pk)
        self._zadd(project_id, mapping)
        self.client.expire(index_pk, Minute_5 + 50)

    def _zadd(self, project_id, mapping):
        if len(mapping) == 0:
            return
        self.client.zadd(self._index_pk(project_id), mapping)

    def zadd(self, project_id, mapping):
        if self.client.exists(self._index_pk(project_id)):
            self._zadd(project_id, mapping)
        else:
            self.reset(project_id)

    def zrem(self, *value):
        self.client.zrem(*value)

    def zrevrange(self, project_id, start, end):
        items = self.client.zrevrange(self._index_pk(project_id), start, end)
        if len(items) == 0:
            if self.client.exists(self._index_pk(project_id)):
                return items
            self.reset(project_id)
            items = self.client.zrevrange(self._index_pk(project_id), start, end)
        return items

resource_version_cache = ResourceVersionZSet()

ticket_cache = CommBase('ticket')

comm_cahce = CommBase()

class Lock(ConnectBase):
    def __init__(self, key, flag='', timeout=Minute_5, raise_err=False):
        self.timeout = timeout
        self.flag = flag
        self._key = key
        self.refresh_at = 0
        self.raise_err = raise_err

        self.current_val_str = None
        self.pre_val_str = None

    def __str__(self):
        return f'<Lock key:{self.key} val:{self.current_val_str} pre_val:{self.pre_val_str}>'

    @property
    def key(self):
        return f'{BASE_KEY}lock:{self._key}'

    def _encode_val(self):
        validate_at = int(time.time()) + self.timeout
        return f'{validate_at}:{self.flag}'

    def _decode_val(self, val):
        idx = val.find(':')
        return int(val[:idx]), val[idx+1:]

    def _require(self, ex, nx=False, xx=False):
        val = self._encode_val()
        # NX: 仅在键不存在时设置; XX: 仅在键存在时设置; EX: 设置键的过期时间, 单位: 秒
        ok = self.client.set(self.key, val, nx=nx, xx=xx, ex=ex)
        if ok:
            self.current_val_str = val
        return ok

    def acquire(self, timeout=None):
        """
        获取锁: 场景 1.如果锁key不存在, 则占用; 场景2: 如果锁key存在但超时, 则占用
        :param timeout:
        :return:
        """
        _timeout = timeout if timeout else self.timeout
        by = 0
        ok = self._require(_timeout, nx=True)
        if not ok:
            r_val_b = self.client.get(self.key)
            if r_val_b:
                r_val_str = r_val_b.decode('utf-8')
                r_validate_at, flag = self._decode_val(r_val_str)
                if time.time() > r_validate_at:  # 锁超时 强行占用
                    self.client.delete(self.key)
                    by = 1
                    ok = self._require(_timeout, nx=True)
                    if ok:
                        self.pre_val_str = r_val_str
            else:
                by = 2
                ok = self._require(_timeout, nx=True)
        logger.warning(f'[lock_acquire] {self} by:{by} ok:{ok}')
        return ok

    def release(self):
        self.client.delete(self.key)
        logger.warning(f'[lock_release] {self}')

    def validate(self, val):
        r_validate_at, flag = self._decode_val(val)
        if self.flag != flag:
            return 1
        elif time.time() > r_validate_at:
            return 2
        return 0

    def refresh(self, timeout=None, interval=30):
        now_at = int(time.time())
        if now_at - self.refresh_at < interval:
            return True
        _timeout = timeout if timeout else self.timeout
        r_val_b = self.client.get(self.key)
        ok = False
        by = 0
        if r_val_b:
            r_val_str = r_val_b.decode('utf8')
            code = self.validate(r_val_str)
            if code == 0:
                ok = self._require(_timeout, xx=True)
                by = 1
            else:
                ok = False
                by = 2
                logger.warning(f'[lock_refresh] {self} validate:{code} reason:{r_val_str}')
        if ok:
            self.refresh_at = now_at
            logger.debug(f'[lock_refresh] {self} by:{by} ok:{ok}')
        else:
            logger.warning(f'[lock_refresh] {self} by:{by} ok:{ok}')
        return ok

    def __enter__(self):
        return self if self.acquire() else None

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            logger.error(f'[lock_error]: {exc_type} {exc_val} {"".join(traceback.format_tb(exc_tb))}')
        self.release()
        if exc_val and self.raise_err:
            return False
        else:
            return True


def try_lock(key, func, *args, flag='', timeout=15, raise_err=True, num=3, delay=0.1):
    """重试 lock"""
    for idx in range(num):
        with Lock(key, flag, timeout, raise_err) as lock:
            if not lock:
                if idx == num - 1:
                    return False, None
                logger.warning(f'try_lock {key} fail, idx:{idx}')
                time.sleep(delay)
                continue
            return True, func(lock, *args)
