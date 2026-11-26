import os
import base64
import time
import logging
from collections import defaultdict
from zlib import adler32
import cv2
import numpy as np
import copy

import requests
import orjson
from munch import Munch as AttrDict
from django.db.models import Count

import settings
from libs import TaskBase, util, lodash, storage
from libs.defs import ImageTaskErrorEnum, JobRegressionEnum, ImageAiSignErrorEnum, BugBillStatusEnum, JobDiscernEnum
from apps.job.models import Job
from apps.project.models import Project
from apps.project import service as proj_svr
from apps.image.models import Image, DataReview
from apps.bug import service as bug_svr
from apps.bug.models import Bug

logger = logging.getLogger('img_svr')


def _size_to_wh(size):
    if isinstance(size, str):
        size = size.split(',')
    return int(size[0]), int(size[1])


class DataReviewService(object):
    """利用DataReview清洗rect_location数据"""

    @classmethod
    def rect_location_to_corners(cls, rect_location, size):
        """
        将文本框、图像框集合转换为前端需要的坐标格式
        :param rect_location: 文本框、图像框集合
        :param size: 图片尺寸
        :return:
        """
        res = defaultdict(list)
        if not rect_location:
            return res
        width, height = _size_to_wh(size)
        rect_location_dict = orjson.loads(rect_location) if isinstance(rect_location, str) else rect_location
        for k, v in rect_location_dict.items():
            for span in v:
                corners = span["corners"]
                if not util.judge_rectangle(corners):   # 过滤掉非矩形
                    continue
                x1 = int(corners[1]["x"])
                y1 = int(height) - int(corners[1]["y"])
                x2 = int(corners[3]["x"])
                y2 = int(height) - int(corners[3]["y"])
                w = x2 - x1
                h = y2 - y1
                temp = {"key": str(adler32(orjson.dumps(corners))), "corners": [x1, y1, w, h]}
                res[k].append(temp)
        return res

    @classmethod
    def data_clean(cls, rect_location, db_dirty):
        """
        数据清洗
        :param rect_location: 文本框，图像框集合
        :param db_dirty: 排除的文本框，图像框集合
        :return:
        """
        cleaned = False
        if not rect_location:
            return rect_location, cleaned
        db_dirty = orjson.loads(db_dirty) if isinstance(db_dirty, str) else db_dirty
        clean_rect_location = defaultdict(list)
        dirty_rect_location = defaultdict(list)
        dirty_rect_location.update(db_dirty)
        dirty_key = defaultdict(list)
        for k, v in dirty_rect_location.items():
            for span in v:
                dirty_key[k].append(span["key"])
        rect_location_dict = orjson.loads(rect_location) if isinstance(rect_location, str) else rect_location
        for k, v in rect_location_dict.items():
            for span1 in v:
                key = str(adler32(orjson.dumps(span1["corners"])))
                if key not in dirty_key[k]:
                    clean_rect_location[k].append(span1)
                else:
                    cleaned = True
        return orjson.dumps(clean_rect_location).decode(), cleaned

    @classmethod
    def auto_review(cls, rect_location, size):
        """
        自动审核
        :param rect_location: 文本框，图像框集合
        :param size: 图片尺寸
        :return:
        """
        if not rect_location:
            return "{}", "{}", "{}"
        clean_rect_location = defaultdict(list)
        check_rect_location = defaultdict(list)
        dirty_rect_location = defaultdict(list)
        width, height = _size_to_wh(size)
        rect_location_dict = orjson.loads(rect_location) if isinstance(rect_location, str) else rect_location
        for k, v in rect_location_dict.items():
            for span_corners in v:
                corners = span_corners["corners"]
                x1 = int(corners[1]["x"])
                y1 = height - int(corners[1]["y"])
                x2 = int(corners[3]["x"])
                y2 = height - int(corners[3]["y"])
                w = x2 - x1
                h = y2 - y1
                span_rect = {"key": str(adler32(orjson.dumps(corners))), "corners": [x1, y1, w, h], "tag": "system"}
                if min([x1, y1, x2, y2, w, h]) < 0 or max([x1, x2]) > width or max([y1, y2]) > height:
                    dirty_rect_location[k].append(span_rect)
                    continue
                check_rect_location[k].append(span_rect)
                clean_rect_location[k].append(span_corners)
        return (orjson.dumps(clean_rect_location).decode(),
                orjson.dumps(check_rect_location).decode(),
                orjson.dumps(dirty_rect_location).decode())


class SubmitAiImageSignTask(TaskBase):
    """
    场景：批量ai识别和重试时 可能会瞬间大量提交AiImageSignTask(预估10w级)。
    在dev测试时100个提交差不多要800ms左右，所以这里将大批量提交做成异步任务
    """
    def __init__(self, ctx, request=None, logger=None):
        super(SubmitAiImageSignTask, self).__init__(ctx, request, logger)

    def _run(self):
        self.logger.info(f'AiImageSignSubmitTask.run ctx:{orjson.dumps(self.ctx).decode()}')
        # 防止互相import冲突，放这里延迟import
        from apps.image.tasks import run_ai_sign
        param = self.ctx['param']  # 查询条件
        discern = self.ctx['discern']
        current_user = self.ctx['current_user']

        stat = {'total': 0, 'success': 0}
        fields = ['id', 'job_id', 'data_id', 'rect_location']
        size = 1000
        pk__gt = 0
        while True:
            param['pk__gt'] = pk__gt
            images = list(Image.objects.filter(**param).order_by('pk')[:size].values(*fields))  # QuerySet to list

            use_images = []
            for image in images:
                stat['total'] += 1
                if image['rect_location'] == '':
                    continue
                use_images.append(image)

            code, ctx_list = prepare_ai_sign_task_ctx_with_images(use_images, discern, current_user)
            if code == 0:
                self.logger.info(f'prepare_ai_sign_task_ctx_with_images code:{code} ctx_list_len:{len(ctx_list)}')
                event = 'event.run_ai_sign_3'
                for ctx in ctx_list:
                    ctx['_event'] = event
                    task = run_ai_sign.apply_async((ctx,))  # 接口图片识别
                    self.logger.info(f'[{event}] user:{current_user["name"]} '
                                f'task_id:{task.task_id} image_id:{ctx["image_id"]} discern:{discern}')
                    stat['success'] += 1
            else:
                self.logger.warning(f'prepare_ai_sign_task_ctx_with_images code:{code}')

            # 控制循环变量
            if len(images) < size:
                break
            pk__gt = images[-1]['id']
        self.logger.info(f'stat: {stat}')

    def run(self):
        try:
            self._run()
        except Exception as err:
            self.logger.error(f'AiImageSignSubmitTask ctx:{self.ctx} run err:', exc_info=err)


class AiImageSignTask(TaskBase):
    """识别任务分为3个阶段：1.识别阶段 2.自动提bug阶段 3.更新bug阶段"""

    Project_Methods = {}

    Language_Code_Dict = {
        10: 0,    # 中文
        8: 1,     # 中文 (台湾)
        2: 2,     # 英文
        6: 3,     # 日文
        4: 4,     # 泰文
        5: 5,     # 越南
        3: 6,     # 韩文
        7: 7,     # 俄文
        9: 8,     # 法文
        11: 9,    # 土耳其文
        12: 10,   # 德文
        13: 11,   # 西班牙文
        14: 12,   # 葡萄牙文(巴西)
        15: 13,   # 印尼文
        16: 14,   # 阿拉伯文
    }

    def __init__(self, ctx, request=None, logger=None):
        super(AiImageSignTask, self).__init__(ctx, request, logger)

        self.url = f"{settings.env('AI_BASE_URL')}/image/lqa_check/"
        self.image = None
        self.job = None

        self._check_type = None

    @property
    def project_method(self):
        project_id = self.image.project_id
        val = self.Project_Methods.get(project_id, None)
        if not val:
            p = Project.objects.filter(pk=project_id).values('id', 'cvtest_project').first()
            cvtest_project = p['cvtest_project'].strip()
            if not cvtest_project:
                raise Exception(f'project:{project_id} "cvtest_project" invalidate')
            val = f"{cvtest_project}_lqa"
            self.Project_Methods[project_id] = val  # 运行时缓存
        return val

    @property
    def check_type(self):
        if self._check_type is None:
            check_type_ = []
            sign_bug_types = self.job['sign_bug_types']
            if len(sign_bug_types) > 0:
                for bug_type_ in sign_bug_types:
                    if bug_type_ == 2:
                        check_type_.extend(['2-0', '2-1'])
                    else:
                        check_type_.append(str(bug_type_))
            self._check_type = check_type_
        return self._check_type

    @property
    def language_id(self):
        return self.Language_Code_Dict.get(self.image.language, None)

    @classmethod
    def _trans_marks(cls, project_id, sign_bug_types):
        bug_type_dict = {}
        sys_bug_type_dict = {}

        def _trans_marks(bug_type_):
            nonlocal bug_type_dict
            nonlocal sys_bug_type_dict
            if bug_type_ not in sign_bug_types:
                return '[]'
            if len(sys_bug_type_dict) == 0:
                sys_bug_type_dict = proj_svr.ProjCfgService.get_sys_bugtype(True)
            if len(bug_type_dict) == 0:
                bug_type_dict = proj_svr.ProjCfgService.get_bug_type(project_id, True)
            trans_marks_ = bug_type_dict[bug_type_]['trans_marks']
            if len(orjson.loads(trans_marks_)) == 0:    # 使用系统的
                trans_marks_ = sys_bug_type_dict[bug_type_]['trans_marks']
            return trans_marks_
        return _trans_marks(1), _trans_marks(5)

    @classmethod
    def _base64_to_mat(cls, image_base64, gray=False):
        """
        base64转ndarray
        Args:
            base64_img (str):
            gray (bool):
        Returns:
            img (ndarray)
        """
        if not image_base64:
            return None
        img_b64decode = base64.b64decode(image_base64)
        img_array = np.frombuffer(img_b64decode, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE if gray else cv2.COLOR_BGR2RGB)
        return img

    def _request_ai(self, rect_locations, file_path, old_file_path=None, image_check_detail=None,
                    discern=JobDiscernEnum.FULL):
        """调用 AI 识别服务 POST {AI_BASE_URL}/image/lqa_check/，接口约定见 README「AI 识别服务」"""
        # try:
        #     file_name_full = file_path.split("-")[2]
        #     language_code = file_name_full.split(".")[0]
        # except Exception as e:
        #     language_code = '获取失败'
        # language_id = self.language_code_dict.get(language_code, None)
        # if language_id == 1:
        #     check_type = ['1', '2-0', '2-1', '4', '5', '6']
        # else:
        #     check_type = None

        file_path_abs = storage.get_abs_path(file_path)
        self.logger.info(f'_request_ai file_path_abs:{file_path_abs} check_type:{self.check_type} language_id:{self.language_id}')
        img_base64 = ''.join([part for part in util.base64_encode_file_iter(file_path_abs)])

        img_base64_old = None
        if discern:
            if old_file_path:
                abs_old_file_path = storage.get_abs_path(old_file_path)
                if abs_old_file_path and os.path.exists(abs_old_file_path):
                    img_base64_old = ''.join([part for part in util.base64_encode_file_iter(abs_old_file_path)])
                else:
                    logger.warning(f'_request_ai old_file_path:{old_file_path} not exist')
            if image_check_detail:
                image_check_detail = orjson.loads(image_check_detail)

        rect_locations = orjson.loads(rect_locations) if isinstance(rect_locations, str) else rect_locations
        no_trans_marks, err_trans_marks = self._trans_marks(self.image.project_id, self.job['sign_bug_types'])
        body = {
            "img_base64": img_base64,
            "history_img_base64": img_base64_old,
            "rect_locations": rect_locations,
            "language": self.language_id,
            "history_result": image_check_detail,
            "check_type": self.check_type,
            "no_trans_marks": no_trans_marks,
            # 字段名须与 lqa_service handles/handle_lqa.py 读取的保持一致，
            # 历史上误写为 err_trans_marks，导致项目自定义错译标记不生效
            "error_trans_marks": err_trans_marks,
            "ocr_detect": self.job['ocr_detect']
        }

        self.logger.info(f'request_ai_server body: {self.language_id} {self.check_type} '
                         f'{no_trans_marks} {err_trans_marks} {self.job["ocr_detect"]}')

        resp_obj = None
        t1 = int(time.time() * 1000)
        headers = {"project-method": self.project_method}
        for idx in range(3):
            try:
                with requests.post(self.url, json=body, headers=headers, timeout=100) as resp:
                    resp.raise_for_status()
                    resp_obj = resp.json()
                    if resp_obj['err_msg'] != '':
                        break
            except Exception as err:
                if idx == 2:
                    raise err
        t2 = int(time.time() * 1000)
        self.logger.info(f'request_ai_server cost: {t2 - t1}ms')
        mark_img_abs = ''
        rect_img_abs = ''
        # 保存识别后的图片
        if resp_obj:
            if not resp_obj['success']:
                raise Exception(f'request_ai_err: {orjson.dumps(resp_obj).decode()}')
            mark_img = self._base64_to_mat(resp_obj['result']["mark_img"], False)
            rect_img = self._base64_to_mat(resp_obj['result']["rect_img"], False)
            # cv2.imwrite 不支持中文路径，这里使用 imencode + tofile，找不到路径会抛出异常FileNotFoundError
            name_path, ext = os.path.splitext(file_path_abs)  # /a/b/c/d.txt => ('/a/b/c/d', '.txt')
            # file_ext = ".jpg"
            mark_img_abs = fr"{name_path}-mark_img{ext}"
            rect_img_abs = fr"{name_path}-rect_img{ext}"
            os.remove(mark_img_abs) if os.path.exists(mark_img_abs) else 1
            os.remove(rect_img_abs) if os.path.exists(rect_img_abs) else 1
            cv2.imencode(ext, mark_img)[1].tofile(mark_img_abs)
            self.logger.info(f'save mark_img_abs:{mark_img_abs}')
            cv2.imencode(ext, rect_img)[1].tofile(rect_img_abs)
            self.logger.info(f'save rect_img_abs:{rect_img_abs}')
        return mark_img_abs, rect_img_abs, resp_obj

    def _get_last_ai_image(self, image):
        """获取最近一次识别成功的结果"""
        param = {'data_id': image.data_id, 'language': image.language, 'ai_sign_suc': ImageAiSignErrorEnum.ERR_SUC}
        image_qs = Image.objects.filter(**param).order_by('-id').values('file_path', 'ai_mark_img_path', 'ai_check_detail')
        for image_q in image_qs:
            if image_q['ai_mark_img_path']:
                return image_q['file_path'], image_q['ai_check_detail']
        return None, None

    def _run(self):
        ctx_bak = copy.deepcopy(self.ctx)
        if 'clean_rect_location' in ctx_bak:
            del ctx_bak['clean_rect_location']
        self.logger.info(f'AiImageSignTask.run ctx_bak:{orjson.dumps(ctx_bak).decode()}')
        image_id = self.ctx['image_id']
        clean_rect_location = self.ctx.get('clean_rect_location', None)  # 没有说明没有dirty_rect_location,直接用image原始数据
        regression = self.ctx['regression']
        discern = self.ctx['discern']
        # 方案 B：以后端 job.bill_bug_types 为准，不信任编辑器插件/调用方传的 create_bug。
        # 规则：job 配了 bill_bug_types 且非回归 => 自动提单；否则不提。
        # 保留一个显式关闭的后门：ctx 显式传 create_bug=-1 时强制不提单（兼容特殊调试场景）。
        _ctx_create_bug = self.ctx.get('create_bug', self.ctx.get('create_bug_tapd', None))
        bug_ids = self.ctx.get('bug_ids', [])

        image = Image.objects.filter(pk=image_id).first()
        if not image:
            self.logger.error(f'image:{image_id} not exist')
            return
        self.image = image
        job = Job.objects.filter(pk=image.job_id).values(
            'id', 'sign_bug_types', 'bill_bug_types', 'discern', 'ocr_detect').first()
        if not job:
            self.logger.error(f'job:{image.job_id} not exist')
            return
        self.job = job
        if _ctx_create_bug == -1:
            create_bug = 0
            self.logger.info(f'create_bug forced OFF by ctx(-1)')
        else:
            create_bug = 1 if job.get('bill_bug_types') and regression != JobRegressionEnum.REGRESSION else 0
            self.logger.info(
                f'create_bug by job: ctx={_ctx_create_bug} bill_bug_types={job.get("bill_bug_types")} '
                f'regression={regression} -> create_bug={create_bug}')
        if clean_rect_location is None:
            clean_rect_location = image.rect_location
        old_image_path, image_check_detail = None, None
        if discern == JobDiscernEnum.DIFF:   # 1.差异识别就需要传回旧信息
            old_image_path, image_check_detail = self._get_last_ai_image(image)
            self.logger.info(f'discern:{discern} old_image_path:{old_image_path}')

        ai_rec_err = ''
        try:
            mark_img_abs, rect_img_abs, resp = self._request_ai(clean_rect_location, image.file_path,
                                                                old_file_path=old_image_path,
                                                                image_check_detail=image_check_detail,
                                                                discern=discern)
        except Exception as err:
            self.logger.error(f'_request_ai wrap err:', exc_info=err)
            ai_rec_err = f'{str(err)} resp:{util.err_response_text(err)}'
            mark_img_abs, rect_img_abs, resp = '', '', None

        if mark_img_abs and rect_img_abs:
            ai_check_detail = resp['result']['check_detail']
            # check_detail 的键可能是带子类型的 "2-0"/"2-1"，取主类型后去重
            _raw_types = []
            for bug_id in ai_check_detail.keys():
                try:
                    _raw_types.append(int(str(bug_id).split("-")[0]))
                except (ValueError, TypeError):
                    continue
            ai_bug_types = sorted(set(_raw_types))
            ai_overframe = int(resp["result"]["overframe"])
            will_review = 1 if ai_check_detail.get("4") else 0  # 当有“标准框重叠”时，需要人工审核
            Image.update_db(image_id, {
                'ai_mark_img_path': storage.get_url_path(mark_img_abs),
                'ai_rect_img_path': storage.get_url_path(rect_img_abs),
                'ai_check_detail': orjson.dumps(ai_check_detail).decode(),
                'ai_bug_types': ai_bug_types,
                'ai_overframe': ai_overframe,
                'will_review': will_review,
                'ai_sign_suc': ImageAiSignErrorEnum.ERR_SUC,
                'err_msg': '',
                'err_type': ImageTaskErrorEnum.ERR_NO
            })

            self.logger.info(f'create_bug:{create_bug}')
            if create_bug:
                self.create_bug(image_id)

            will_update_bug = True if regression == JobRegressionEnum.REGRESSION and len(bug_ids) > 0 else False
            self.logger.warning(f'will_update_bug:{will_update_bug} regression:{regression} bug_ids_len:{len(bug_ids)}')
            if will_update_bug :
                self.update_bug(image_id, bug_ids)
        else:
            self.update_image_err_info(image_id, resp['err_msg'] if resp else ai_rec_err,
                                       ImageTaskErrorEnum.ERR_AI_REC, ImageAiSignErrorEnum.ERR_FAIL)

    def run(self):
        try:
            self._run()
        except Exception as err:
            self.logger.error(f'run err:', exc_info=err)
            self.update_image_err_info(self.ctx['image_id'], str(err), ImageTaskErrorEnum.ERR_AI_REC,
                                       ImageAiSignErrorEnum.ERR_FAIL)

    def create_bug(self, image_id):
        """自动提bug"""
        self.logger.info(f'create_bug image_id:{image_id}')
        try:
            err_msg, ctx = bug_svr.prepare_create_bug_task_ctx_by_ai_sign(image_id)
            if err_msg:
                self.logger.error(f'create_bug build err:{err_msg}')
                self.update_image_err_info(image_id, f'prepare_bug err: {err_msg}', ImageTaskErrorEnum.ERR_BUG_BILL)
            else:
                event = 'event.run_bug_create_2'
                ctx['_event'] = event
                self.logger.info(f'[{event}] image_id:{image_id}')
                task = bug_svr.CreateBugTask(ctx, None, self.logger) # 图片识别后，自动提bug。因为图片识别任务本来就是后台任务，这里不用异步跑
                err, bug = task.run()
                if err:
                    self.update_image_err_info(image_id, f'create_bug task err: {err}', ImageTaskErrorEnum.ERR_BUG_BILL)
        except Exception as err:
            self.logger.error(f'create_bug err:', exc_info=err)
            self.update_image_err_info(image_id, f'create_bug err: {err}', ImageTaskErrorEnum.ERR_BUG_BILL)

    def update_bug(self, image_id, bug_ids):
        """回归任务场景下，图片识别后处理：关闭或重新打开缺陷"""
        self.logger.info(f'[event.run_update_bug] image_id:{image_id} bug_ids:{bug_ids}')
        try:
            svr = bug_svr.UpdateBugByRegressedImageService({'image_id': image_id, 'bug_ids': bug_ids}, self.request, self.logger)
            code, err_msg, stats = svr.run()
            self.logger.info(f'run_update_bug.return image_id:{image_id} bug_ids:{bug_ids} code:{code} msg:{err_msg} stats:{stats}')
            if code != 0:
                self.update_image_err_info(image_id, err_msg, ImageTaskErrorEnum.ERR_REGRESSION)
            self.logger.info(f'update_bug image_id:{image_id} bug_ids:{bug_ids} finish')
        except Exception as err:
            self.logger.error(f'update_bug err:', exc_info=err)
            self.update_image_err_info(image_id, f'update_bug err: {err}', ImageTaskErrorEnum.ERR_REGRESSION)

    def update_image_err_info(self, image_id, err_msg, err_type, ai_sign_suc=None):
        mapping = {'err_msg': err_msg, 'err_type': err_type}
        if ai_sign_suc is not None:
            mapping['ai_sign_suc'] = ai_sign_suc
        Image.update_db(image_id, mapping)


def prepare_ai_sign_task_ctx(review, image, ctx=None, trace=''):
    """准备ai识别任务上下文参数"""
    ctx['image_id'] = image.id
    ctx['trace'] = trace

    if not ctx.get('clean_rect_location'):
        if review and review.dirty_rect_location:
            clean_rect_location, cleaned = DataReviewService.data_clean(image.rect_location, review.dirty_rect_location)
            if cleaned:     # 如果没有脏数据，不写入redis，减少内存消耗
                ctx['clean_rect_location'] = clean_rect_location
    return ctx


def prepare_ai_sign_task_ctx_with_images(images, discern, current_user):
    """
    准备ai_sign任务的ctx
    场景1：单个、批量识别接口
    场景2：重试job
    """
    ctx_list = []
    if len(images) == 0:
        return 1, ctx_list
    data_ids = list(set(map(lambda img: img['data_id'], images)))
    if len(data_ids) == 0:
        return 2, ctx_list
    # 查询 data_review
    data_reviews = DataReview.query_batch({'data_id__in': data_ids}, fields=['id', 'data_id', 'dirty_rect_location'])
    if len(data_reviews) == 0:
        return 3, ctx_list
    data_review_dict = lodash.key_by(data_reviews, 'data_id')

    for image_info in images:
        data_review_ = data_review_dict.get(image_info['data_id'])
        if not data_review_:
            continue
        ctx = prepare_ai_sign_task_ctx(AttrDict(data_review_), AttrDict(image_info), ctx={
            'regression': JobRegressionEnum.NORMAL,
            'bug_ids': [],
            'discern': discern,
            'create_bug': 0,
            'staff_name': current_user['name']
        }, trace=f'ai_sign image_id:{image_info["id"]} job_id:{image_info["job_id"]}')
        ctx_list.append(ctx)
    return 0, ctx_list


def image_of_bug_num(pks, job_id):
    param = {'image_id__in': pks, 'job_id': job_id, 'bill_status': BugBillStatusEnum.SUCCESS}
    stats = list(Bug.objects.filter(**param).values('image_id').annotate(bug_num=Count('image_id')))
    if len(stats) < len(pks):
        # 防止频繁查询Bug表。场景：有些image没有产生bug
        delt_pks_set = set(pks) - set(map(lambda stat: stat['image_id'], stats))
        for pk_ in delt_pks_set:
            stats.append({'image_id': pk_, 'bug_num': 0})
    return {st_['image_id']: st_ for st_ in stats}


# if __name__ == '__main__':
#     rect_location1 = {"text":[{"corners":[{"x":949.7177124023438,"y":-89.23961639404297},{"x":915.7986450195313,"y":-56.17535400390625},{"x":1322.8271484375,"y":340.59588623046877},{"x":1356.74609375,"y":307.5316162109375}],"textStr":""},{"corners":[{"x":993.6756591796875,"y":161.15724182128907},{"x":959.756591796875,"y":194.22152709960938},{"x":1366.784912109375,"y":590.9927978515625},{"x":1400.7041015625,"y":557.928466796875}],"textStr":""},{"corners":[{"x":606.0126342773438,"y":-216.83648681640626},{"x":572.0936279296875,"y":-183.772216796875},{"x":979.1220092773438,"y":212.99900817871095},{"x":1013.0410766601563,"y":179.9347381591797}],"textStr":""},{"corners":[{"x":904.4332275390625,"y":173.6291046142578},{"x":870.51416015625,"y":206.6934051513672},{"x":1277.5426025390625,"y":603.464599609375},{"x":1311.46142578125,"y":570.400390625}],"textStr":""},{"corners":[{"x":512.9335327148438,"y":-207.24273681640626},{"x":479.0145263671875,"y":-174.178466796875},{"x":886.0428466796875,"y":222.59275817871095},{"x":919.9619140625,"y":189.5284881591797}],"textStr":""},{"corners":[{"x":653.3583984375,"y":23.007246017456056},{"x":619.4393310546875,"y":56.071510314941409},{"x":1026.4677734375,"y":452.8427429199219},{"x":1060.38671875,"y":419.7784423828125}],"textStr":""},{"corners":[{"x":748.9884033203125,"y":295.4697570800781},{"x":715.0694580078125,"y":328.53399658203127},{"x":1122.0977783203125,"y":725.3052978515625},{"x":1156.016845703125,"y":692.240966796875}],"textStr":""},{"corners":[{"x":342.121826171875,"y":-94.995849609375},{"x":308.2027893066406,"y":-61.93159103393555},{"x":715.231201171875,"y":334.8396301269531},{"x":749.1502685546875,"y":301.7753601074219}],"textStr":""},{"corners":[{"x":424.97674560546877,"y":65.21974182128906},{"x":391.0577087402344,"y":98.28400421142578},{"x":798.0860595703125,"y":495.0552673339844},{"x":832.005126953125,"y":461.990966796875}],"textStr":""},{"corners":[{"x":385.3042907714844,"y":323.2916259765625},{"x":351.38525390625,"y":356.35589599609377},{"x":758.4136352539063,"y":753.1270751953125},{"x":792.3327026367188,"y":720.0628051757813}],"textStr":""},{"corners":[{"x":20.6610107421875,"y":-30.717756271362306},{"x":-13.257980346679688,"y":2.346524238586426},{"x":393.7703857421875,"y":399.1177673339844},{"x":427.689453125,"y":366.053466796875}],"textStr":""},{"corners":[{"x":292.739501953125,"y":476.9834899902344},{"x":258.8204345703125,"y":510.0477600097656},{"x":665.848876953125,"y":906.8190307617188},{"x":699.767822265625,"y":873.7546997070313}],"textStr":""},{"corners":[{"x":-72.67318725585938,"y":121.05538177490235},{"x":-106.59217834472656,"y":154.11964416503907},{"x":300.43621826171877,"y":550.890869140625},{"x":334.355224609375,"y":517.8265991210938}],"textStr":""},{"corners":[{"x":-15.480880737304688,"y":274.3634948730469},{"x":-49.399871826171878,"y":307.427734375},{"x":357.62847900390627,"y":704.198974609375},{"x":391.54754638671877,"y":671.134765625}],"textStr":""},{"corners":[{"x":162.92251586914063,"y":-88.28025817871094},{"x":129.00347900390626,"y":-55.21599578857422},{"x":536.0318603515625,"y":341.5552673339844},{"x":569.950927734375,"y":308.490966796875}],"textStr":""},{"corners":[{"x":539.9736328125,"y":277.2416076660156},{"x":506.05462646484377,"y":310.305908203125},{"x":913.0829467773438,"y":707.0771484375},{"x":947.0020141601563,"y":674.0128784179688}],"textStr":""},{"corners":[{"x":845.1287231445313,"y":-89.23961639404297},{"x":811.209716796875,"y":-56.17535400390625},{"x":1218.238037109375,"y":340.59588623046877},{"x":1252.1571044921875,"y":307.5316162109375}],"textStr":""},{"corners":[{"x":418.9768981933594,"y":-118.980224609375},{"x":385.0578308105469,"y":-85.91596221923828},{"x":792.0862426757813,"y":310.8552551269531},{"x":826.0052490234375,"y":277.7909851074219}],"textStr":""},{"corners":[{"x":825.7823486328125,"y":273.40411376953127},{"x":791.86328125,"y":306.4683837890625},{"x":1198.8916015625,"y":703.2396240234375},{"x":1232.8106689453125,"y":670.17529296875}],"textStr":""},{"corners":[{"x":308.5308532714844,"y":160.1978759765625},{"x":274.61181640625,"y":193.26214599609376},{"x":681.64013671875,"y":590.0333862304688},{"x":715.5592041015625,"y":556.9691162109375}],"textStr":""},{"corners":[{"x":134.7803497314453,"y":192.8166046142578},{"x":100.86135864257813,"y":225.88088989257813},{"x":507.8897399902344,"y":622.6521606445313},{"x":541.8087768554688,"y":589.587890625}],"textStr":""},{"corners":[{"x":903.593017578125,"y":47.95001220703125},{"x":903.593017578125,"y":95.95623779296875},{"x":1109.4462890625,"y":95.95623779296875},{"x":1109.4462890625,"y":47.95001220703125}],"textStr":""},{"corners":[{"x":962.1188354492188,"y":99.42042541503906},{"x":962.1188354492188,"y":126.60833740234375},{"x":1051.41943359375,"y":126.60833740234375},{"x":1051.41943359375,"y":99.42042541503906}],"textStr":""},{"corners":[{"x":710.5418701171875,"y":48.42136764526367},{"x":710.5418701171875,"y":94.97811889648438},{"x":892.7023315429688,"y":94.97811889648438},{"x":892.7023315429688,"y":48.42136764526367}],"textStr":""},{"corners":[{"x":1031.261962890625,"y":560.4241943359375},{"x":1031.261962890625,"y":597.0425415039063},{"x":1158.2255859375,"y":597.0425415039063},{"x":1158.2255859375,"y":560.4241943359375}],"textStr":""},{"corners":[{"x":883.1456298828125,"y":559.56298828125},{"x":883.1456298828125,"y":595.8507080078125},{"x":1008.3408203125,"y":595.8507080078125},{"x":1008.3408203125,"y":559.56298828125}],"textStr":""},{"corners":[{"x":679.751220703125,"y":337.70001220703127},{"x":679.751220703125,"y":372.23748779296877},{"x":1170.5013427734375,"y":372.23748779296877},{"x":1170.5013427734375,"y":337.70001220703127}],"textStr":""},{"corners":[{"x":708.2402954101563,"y":387.07763671875},{"x":708.2402954101563,"y":425.74322509765627},{"x":1127.72021484375,"y":425.74322509765627},{"x":1127.72021484375,"y":387.07763671875}],"textStr":""},{"corners":[{"x":1012.8131103515625,"y":484.161865234375},{"x":1012.8131103515625,"y":507.6400146484375},{"x":1012.8131103515625,"y":507.6400146484375},{"x":1012.8131103515625,"y":484.161865234375}],"textStr":""},{"corners":[{"x":423.1435546875,"y":42.4984130859375},{"x":423.1435546875,"y":71.35640716552735},{"x":640.395263671875,"y":71.35640716552735},{"x":640.395263671875,"y":42.4984130859375}],"textStr":""},{"corners":[{"x":128.25592041015626,"y":47.820438385009769},{"x":128.25592041015626,"y":69.58753204345703},{"x":346.04364013671877,"y":69.58753204345703},{"x":346.04364013671877,"y":47.820438385009769}],"textStr":""}],"image":[{"corners":[{"x":623.9625244140625,"y":338.26190185546877},{"x":623.9625244140625,"y":589.2619018554688},{"x":1200.9625244140625,"y":589.2619018554688},{"x":1200.9625244140625,"y":338.26190185546877}],"textStr":""}]}
#     items = DataReviewService.auto_review(orjson.dumps(rect_location1).decode('utf8'), (1280, 614))
#     for item in items:
#         print(item)

