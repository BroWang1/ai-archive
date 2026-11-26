import datetime
import os
import time
import logging
import threading
import itertools
from typing import List, Union

import orjson
from munch import Munch as AttrDict
from django.db import transaction, DatabaseError
from django.db.models import Count, Q

from apps.project import service as proj_svr
from apps.project.models import Project
from apps.data.models import Data
from apps.job.models import Job, JobExtra
from apps.image.models import Image
from apps.bug.models import Bug
from libs import defs, cache, lodash, util, storage
from libs.decorators import test_project_user_role_by_project_id

logger = logging.getLogger('job_svr')


def _query_image_data_ids(param_, language_=None, module_ids_=(), counter_=False, seq_=None, iteration=0):
    """如果查询没有指定language_ 可能会出现重复data_id 这是预期之中"""
    logger.info(f'_query_image_data_ids seq:{seq_} p:{param_} lan:{language_} m:{module_ids_} c:{counter_} '
                f'i:{iteration}')
    if iteration > 0 and 'is_latest' in param_:
        del param_['is_latest']
    qs_ = Image.objects.filter(**param_)
    if iteration:
        qs_ = qs_.filter(iteration=iteration)
    if language_:
        qs_ = qs_.filter(language=language_)
    if len(module_ids_) > 0:
        qs_ = qs_.filter(data_id__in=Data.objects.filter(module__in=module_ids_))
    return qs_.count() if counter_ else list(qs_.values_list('data_id', flat=True))


def job_of_data_ids(job_dict_or_id, action, language=None, module_ids=(), counter=False, seq=None,
                    iteration=0) -> Union[List, int]:
    """
    获取任务的data id  !!!如果 job_dict_or_id 是dict 检查是否包含  id,data_ids,parent_id
    action = 1  # 获取任务所有的data_id，当是回归任务时不查Data表，因为不跟job_id绑定
    action = 2  # 场景 已经还原的data id
    action = 3  # 场景 编辑器获取未还原的data id
    action = 4  # 场景 任务详情计算任务进度时获取已经还原成功的 data id
    """
    if seq is None:
        seq = next(util.seq_generator)

    if isinstance(job_dict_or_id, int):
        job_dict = None
        job_id = job_dict_or_id
    else:
        job_dict = job_dict_or_id
        job_id = job_dict['id']

    logger.info(f'job_of_data_ids seq:{seq} act:{action} job:{job_id} lan:{language} m:{module_ids} c:{counter} '
                f'i:{iteration}')

    if action == 1:  # all
        if not job_dict:
            job_dict = Job.objects.filter(pk=job_id).values('data_ids', 'parent_id').first()     # 补充数据id
        data_ids = job_dict['data_ids']
        if job_dict['parent_id'] != 0:  # 回归任务，不需要跑跟job_id绑定的data
            if len(data_ids) > 0 and len(module_ids) > 0:
                # 这里的data_ids可能不是同一job下的
                qs = Data.objects.filter(pk__in=data_ids, module__in=module_ids)
                return qs.count() if counter else list(qs.values_list('id', flat=True))
            return len(data_ids) if counter else data_ids
        else:  # 非回归任务
            param = Q(job_id=job_id)
            if len(data_ids) > 0:
                param |= Q(pk__in=data_ids)
            qs = Data.objects.filter(param)
            if len(module_ids) > 0:
                qs = qs.filter(module__in=module_ids)
            return qs.count() if counter else list(qs.values_list('id', flat=True))
    elif action == 2:   # imaged
        param = {'job_id': job_id, 'is_latest': defs.SwitchEnum.ON}
        return _query_image_data_ids(param, language, module_ids, counter, seq, iteration)
    elif action == 3:   # unimaged
        all_data_ids = job_of_data_ids(job_dict_or_id, 1, language, module_ids, counter, seq, iteration)
        imaged_data_ids = job_of_data_ids(job_dict_or_id, 2, language, module_ids, counter, seq, iteration)
        if counter:
            return all_data_ids - imaged_data_ids
        return list(set(all_data_ids) - set(imaged_data_ids))
    elif action == 4:   # imaged and ai_sign
        param = {'job_id': job_id, 'is_latest': defs.SwitchEnum.ON, 'ai_sign_suc__gt': 0}
        return _query_image_data_ids(param, language, module_ids, counter, seq, iteration)


class JobOfDataIdsQuery(object):
    """查询任务相关的data ids，利用缓存"""

    def __init__(self, job_id):
        self.job_id = job_id
        """
            cache_datas
            {
                id: {id: id, module_id: module_id},
            }
        """
        self._cache_datas = {}
        self._cache_bd_datas = {}
        """cache_of_images
            {image_id: {
                        id: id,
                        is_latest: is_latest,
                        ai_sign_suc: ai_sign_suc,
                        language: language,
                        module: module,
                        iteration: iteration
                    }
            }
        """
        self._cache_of_images = {}

        self._updated_at = 0
        self.EXPIRE = 60
        self.DELTA_CNT = self.EXPIRE * 8

        self.lock = threading.Lock()

    def _update_cache_data(self, job_id):
        """查询全量数据"""
        now = time.time()
        if now - self._updated_at < self.EXPIRE:
            return

        job_dict = Job.objects.filter(pk=job_id).values('data_ids', 'parent_id').first()
        _cache_bd_datas = dict()
        if len(job_dict['data_ids']) > 0:
            datas_ = Data.objects.filter(id__in=job_dict['data_ids']).values('id', 'module_id')
            _cache_bd_datas = {data_['id']: data_ for data_ in datas_}

        datas_ = Data.objects.filter(job_id=job_id).values('id', 'module_id')
        _cache_datas = {data_['id']: data_ for data_ in datas_}

        images_ = Image.objects.filter(job_id=job_id).values('id', 'is_latest', 'ai_sign_suc', 'language', 'iteration',
                                                             'data_id')
        _cache_of_images = {image_['id']: image_ for image_ in images_}

        self._cache_bd_datas = _cache_bd_datas
        self._cache_datas = _cache_datas
        self._cache_of_images = _cache_of_images

        self._updated_at = now

        logger.info(f'_update_cache_data job_id: {job_id} datas:{len(_cache_datas)} bd_datas:{len(_cache_bd_datas)} '
                    f'images:{len(_cache_of_images)}')

    def get_cache_data(self):
        """获取全量数据"""
        if time.time() - self._updated_at > self.EXPIRE:
            with self.lock:
                self._update_cache_data(self.job_id)
        return self._cache_datas, self._cache_bd_datas, self._cache_of_images

    def query_delta_data(self, job_id):
        """查询增量数据"""
        datas_ = Data.objects.filter(job_id=job_id).values('id', 'module_id').order_by('-id')[:self.DELTA_CNT]
        images_ = Image.objects.filter(job_id=job_id).values('id', 'is_latest', 'ai_sign_suc', 'language', 'data_id',
                                                             'iteration').order_by('-id')[:self.DELTA_CNT]
        return datas_, images_

    def _image_of_data_ids(self, data_tpl, where, counter=False, seq=None):
        """如果查询没有指定language_ 可能会出现重复data_id 这是预期之中"""
        is_latest = where['is_latest']
        ai_sign_suc__gt = where.get('ai_sign_suc__gt', None)
        language = where['language']
        module_ids = where['module_ids']
        iteration = where['iteration']
        images, delta_images = data_tpl[3].values(), data_tpl[4]

        logger.info(f'_image_of_data_ids seq:{seq} counter:{counter} where:{where}')

        data_ids_set = set()
        for image_ in itertools.chain(images, delta_images):
            if ai_sign_suc__gt is not None and image_['ai_sign_suc'] <= ai_sign_suc__gt:
                continue
            if language and language != image_['language']:
                continue
            if iteration and iteration != image_['iteration']:
                continue
            if iteration == 0 and is_latest != image_['is_latest']:
                continue
            data_ids_set.add(image_['data_id'])

        if len(data_ids_set) > 0 and len(module_ids) > 0:
            data_ids_set1 = set(Data.objects.filter(job_id=self.job_id, module__in=module_ids)
                                .values_list('id', flat=True))
            return len(data_ids_set & data_ids_set1) if counter else (data_ids_set & data_ids_set1)

        return len(data_ids_set) if counter else data_ids_set

    def _job_of_data_ids(self, data_tpl, job_dict, action, language=None, module_ids=(), counter=False,
                         seq=None, iteration=0) -> Union[set, int]:
        job_id = job_dict['id']

        if seq is None:
            seq = next(util.seq_generator)

        logger.info(f'_job_of_data_ids seq:{seq} act:{action} job:{job_id} lan:{language} m:{module_ids} c:{counter} '
                    f'i:{iteration}')

        if action == 1:  # all
            datas, bd_datas, delta_datas = data_tpl[0].values(), data_tpl[1].values(), data_tpl[2]
            if job_dict['parent_id'] != 0:  # 回归任务，不需要跑跟job_id绑定的data
                if len(module_ids) > 0:
                    module_ids_set = set(module_ids)
                    data_ids_set = {data_['id'] for data_ in bd_datas if data_['module_id'] in module_ids_set}
                else:
                    data_ids_set = {data_['id'] for data_ in bd_datas}
                return len(data_ids_set) if counter else data_ids_set
            else:  # 非回归任务
                if len(module_ids) > 0:
                    module_ids_set = set(module_ids)
                    data_ids_set = {data_['id'] for data_ in
                                    itertools.chain(datas, bd_datas, delta_datas)
                                    if data_['module_id'] in module_ids_set}
                else:
                    data_ids_set = {data_['id'] for data_ in itertools.chain(datas, bd_datas, delta_datas)}
                return len(data_ids_set) if counter else data_ids_set

        elif action == 2:  # imaged
            where = {
                'is_latest': defs.SwitchEnum.ON,
                'language': language,
                'module_ids': module_ids,
                'iteration': iteration
            }
            return self._image_of_data_ids(data_tpl, where, counter, seq)

        elif action == 3:  # unimaged
            all_data_ids_set = self._job_of_data_ids(data_tpl, job_dict, 1, language, module_ids, counter, seq,
                                                 iteration)
            imaged_data_ids_set = self._job_of_data_ids(data_tpl, job_dict, 2, language, module_ids, counter, seq,
                                                    iteration)
            if counter:
                return all_data_ids_set - imaged_data_ids_set
            return all_data_ids_set - imaged_data_ids_set

        elif action == 4:  # imaged and ai_sign
            where = {
                'is_latest': defs.SwitchEnum.ON,
                'ai_sign_suc__gt': 0,
                'language': language,
                'module_ids': module_ids,
                'iteration': iteration
            }
            return self._image_of_data_ids(data_tpl, where, counter, seq)

    def job_of_data_ids(self, job_dict_or_id, action, language=None, module_ids=(), counter=False,
                        seq=None, iteration=0) -> Union[List, int]:
        """获取任务的data ids"""
        job_dict, job_id = (None, job_dict_or_id) if isinstance(job_dict_or_id, int) \
            else (job_dict_or_id, job_dict_or_id['id'])

        if not job_dict:
            job_dict = Job.objects.filter(pk=job_id).values('data_ids', 'parent_id').first()  # 补充数据id

        datas, bd_datas, images = self.get_cache_data()

        delta_datas, delta_images = self.query_delta_data(job_id)

        data_tpl = (datas, bd_datas, delta_datas, images, delta_images)

        return self._job_of_data_ids(data_tpl, job_dict, action, language, module_ids, counter, seq, iteration)


class JobOfDataIdsQueryManager(object):
    """按job管理查询器"""
    def __init__(self):
        self.querys = {}
        self.lock = threading.Lock()

    def get_query(self, job_id) -> JobOfDataIdsQuery:
        """ get_query """
        if job_id in self.querys:
            return self.querys[job_id]

        with self.lock:
            if job_id not in self.querys:
                self.querys[job_id] = JobOfDataIdsQuery(job_id)

        return self.querys[job_id]


_job_of_data_ids_query_manager = JobOfDataIdsQueryManager()


def job_of_data_ids_query(job_id):
    """按job获取查询器"""
    return _job_of_data_ids_query_manager.get_query(job_id)


def update_job_extra_files(job_extra, job_extra_old=None):
    """处理文件更新"""
    file_cates = ('test_app', 'test_case', 'proj_res', 'trans_res')
    if job_extra_old is None:
        job_extra_old = AttrDict({f'{cate}_file_path': '' for cate in file_cates})
    project_id = job_extra.project_id
    job_id = job_extra.job_id
    update_fields = {}
    for cate in file_cates:
        field = f'{cate}_file_path'
        url_path_new = getattr(job_extra, field, '')
        url_path_old = getattr(job_extra_old, field, '')
        if url_path_new == '' or url_path_new == url_path_old:
            continue
        _, file_ext = os.path.splitext(url_path_new)
        file_name = f'{job_id}-{cate}{file_ext}' if file_ext else f'{job_id}-{cate}.zip'
        abs_path_new, url_path = storage.gen_job_file_path(project_id, job_id, 'comm', file_name)
        if url_path_old:
            abs_url_path_old = storage.get_abs_path(url_path_old)
            if os.path.exists(abs_url_path_old):
                storage.mv_to_temp(abs_url_path_old)
        tmp_abs_path_new = storage.get_abs_path(url_path_new)   # 如果有更新，url_path_new还是临时路径
        storage.mv_file(tmp_abs_path_new, abs_path_new)     # 将临时路径移到正式路径
        update_fields[field] = url_path
    if len(update_fields) > 0:
        JobExtra.update_db(job_id, update_fields)


def create_job_by_custom(vmi, vmi_extra, user):
    """普通创建job"""
    project = Project.objects.filter(pk=vmi.project_id).values('id', 'cvtest_project').first()
    if not project or project['cvtest_project'].strip() == '':
        return '项目未配置“AI识别项目名”，请联系超级管理员在“项目管理”中完善', None

    if not proj_svr.ProjCfgService.get_runner(vmi.project_id):
        return '请先通过路径 “项目设置 > 基础配置 > 还原执行” 配置 Webhook', None

    job_body = vmi.model_dump(exclude={'id'}, exclude_unset=True)
    job_body['creator_id'] = user['id']
    job = Job(**job_body)

    job_extra_body = vmi_extra.model_dump(exclude_unset=True)
    job_extra_body['project_id'] = vmi.project_id
    job_extra = JobExtra(**job_extra_body)
    with transaction.atomic():
        job.save()
        job_extra.job_id = job.id
        job_extra.save()
    update_job_extra_files(job_extra, None)
    logger.info(f'[event.job.add] at:0 user:{user["name"]} job_id:{job.id}')
    return '', job


def create_job_by_regress_bugs(vmi, vmi_extra, user):
    """通过bug回归创建任务"""
    bug_ids = list(set(vmi.bug_ids))
    bugs = Bug.objects.filter(pk__in=bug_ids)
    if len(bugs) != len(bug_ids):
        return '存在无效 bug_ids', None

    project_id = bugs[0].project_id
    if not test_project_user_role_by_project_id(user, project_id):
        return f'没有项目权限 project_id:{project_id}', None

    if not proj_svr.ProjCfgService.get_runner(project_id):
        return '请先通过路径 “项目设置 > 基础配置 > 还原执行” 配置 Webhook', None

    image_ids_set = set()
    for bug_ in bugs:
        # 正在回归的bug不再回归
        if bug_.regress_status != defs.BugRegressStatusEnum.RUNNING:
            image_ids_set.add(bug_.image_id)

    if len(image_ids_set) == 0:
        return '无有效的image_ids', None

    images = Image.objects.filter(pk__in=image_ids_set).values('id', 'job_id', 'project_id', 'data_id')  # image 可能已经被删除

    job_ids_set = set()
    project_ids_set = set()
    use_image_ids_set = set()
    data_ids_set = set()
    for image_ in images:
        project_ids_set.add(image_['project_id'])
        job_ids_set.add(image_['job_id'])
        use_image_ids_set.add(image_['id'])
        data_ids_set.add(image_['data_id'])

    if len(job_ids_set) == 0:
        return '无满足条件的任务id', None
    if len(job_ids_set) != 1:
        return '回归的bug任务id必须相同', None
    if len(project_ids_set) != 1:
        return '回归的bug项目必须相同', None

    use_data_ids_set = set(Data.objects.filter(pk__in=data_ids_set).values_list('id', flat=True))

    use_bugs = []
    use_bug_ids = []
    for _bug in bugs:
        if _bug.image_id in use_image_ids_set:  # image 可能已经被删除所以要过滤一次
            use_bugs.append(_bug)
            use_bug_ids.append(_bug.id)
    if len(use_bugs) == 0:
        return '无满足条件的bug_ids', None

    job_id = job_ids_set.pop()
    job = Job.objects.filter(pk=job_id).first()
    if not job:
        return f'未找到原始任务,job_id:{job_id}', None
    if job.parent_id:
        return f'不允许在回归任务上再次回归，请在原始任务上回归,job_id:{job_id}', None

    fields = lodash.pick(job, ['project_id', 'languages', 'bill_bug_types',
                               'plan_start_at', 'plan_end_at',
                               'priority', 'severity', 'version_report', 'version_fix', 'release_id', 'config_path99'])
    fields.update({
        'discern': vmi.discern,
        'creator_id': user['id'],
        'name': job.name + "-回归",
        'parent_id': job_id,
        'regression_bug_ids': use_bug_ids,
        'data_ids': list(use_data_ids_set),
        'svn_url': '',
        'svn_version': '',
    })

    updated_at = util.datetime_ms()
    job_regress = Job(**fields)
    job_extra_body = vmi_extra.model_dump(exclude_unset=True)
    job_extra_body['project_id'] = project_id
    job_extra = JobExtra(**job_extra_body)
    with transaction.atomic():
        job_regress.save()
        job_extra.job_id = job_regress.id
        job_extra.save()
        bugs_ = []
        for bug_ in use_bugs:
            bug_.regress_status = defs.BugRegressStatusEnum.RUNNING
            bug_.regress_job_ids.append(job_regress.id)
            bug_.updated_at = updated_at
            bugs_.append(bug_)
        if len(bugs_) > 0:
            Bug.objects.bulk_update(bugs_, ('regress_status', 'regress_job_ids', 'updated_at'))
    update_job_extra_files(job_extra, None)
    logger.info(f'[event.job.add] at:1 user:{user["name"]} job_id:{job.id} job_regress:{job_regress.id}')
    return '', job_regress


def job_of_regress_num(job_ids, project_id):
    param = {'parent_id__in': job_ids, 'project_id': project_id}
    rows = Job.objects.filter(**param).values('id', 'parent_id')
    stat = {}
    for row in rows:
        job = stat.get(row['parent_id'], {'id': row['parent_id'], 'children': []})
        job['children'].append(row['id'])
        stat[row['parent_id']] = job
    if len(job_ids) != len(rows):
        delt_pk_set = set(job_ids) - set(stat.keys())
        for pk in delt_pk_set:
            stat[pk] = {'id': pk, 'children': []}
    return stat


def job_of_bug_num(job_ids, project_id):
    param = {'job_id__in': job_ids, 'project_id': project_id}
    stats = list(Bug.objects.filter(**param).values('job_id').annotate(bug_num=Count('job_id')))
    if len(stats) != len(job_ids):
        delt_pks_set = set(job_ids) - set(map(lambda stat: stat['job_id'], stats))
        for pk_ in delt_pks_set:
            stats.append({'job_id': pk_, 'bug_num': 0})
    return {st_['job_id']: st_ for st_ in stats}
