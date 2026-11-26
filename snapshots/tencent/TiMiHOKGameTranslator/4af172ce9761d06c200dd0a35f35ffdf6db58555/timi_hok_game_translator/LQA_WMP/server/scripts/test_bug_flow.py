"""
提单 + 回归 全流程测试 (平台内记录模式 & Bugzilla 模拟服务)
    python scripts/test_bug_flow.py
"""
import datetime
import logging
import os
import sys
import threading
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
import django  # noqa: E402

django.setup()
import orjson  # noqa: E402

from apps.bug.models import Bug  # noqa: E402
from apps.bug import service as bug_svr  # noqa: E402
from apps.data.models import Data  # noqa: E402
from apps.image.models import Image  # noqa: E402
from apps.job.models import Job  # noqa: E402
from apps.project.models import Project, ProjectConfigBugTracker, ProjectConfigBugBillMethod  # noqa: E402
from apps.user.models import User  # noqa: E402
from libs import storage  # noqa: E402
from libs.defs import BugBillStatusEnum, BugRegressStatusEnum  # noqa: E402
from scripts.test_bugtracker import MockHandler  # noqa: E402

logger = logging.getLogger('test')
logger.setLevel(logging.WARNING)


def ok(cond, title):
    if not cond:
        print(f'[FAIL] {title}')
        sys.exit(1)
    print(f'[ OK ] {title}')


def make_fixture(tracker_cfg):
    now = datetime.datetime.now()
    code = f'flow_{now.strftime("%H%M%S%f")}'
    project = Project.objects.create(code=code, name='流程测试', project_type=2, project_phase=3, game_type=1)
    ProjectConfigBugTracker.objects.create(project=project, **tracker_cfg)
    ProjectConfigBugBillMethod.objects.create(project=project)
    user = User.objects.filter(is_admin=1).first()
    job = Job.objects.create(project=project, creator=user, name='parent', languages=[2], plan_start_at=now,
                             plan_end_at=now, bill_bug_types=[1, 3])
    regress_job = Job.objects.create(project=project, creator=user, name='parent-回归', languages=[2], parent_id=job.id,
                                     plan_start_at=now, plan_end_at=now)
    data = Data.objects.create(project=project, job_id=job.id, resource_version='1.0',
                               device={'phone_type': 'PC', 'screen_w': 1920, 'screen_h': 1080})
    img_abs, img_url = storage.gen_job_file_path(project.id, job.id, 'image', f'{job.id}-{data.id}-LAN_EN_US.png')
    os.makedirs(os.path.dirname(img_abs), exist_ok=True)
    with open(img_abs, 'wb') as fp:
        fp.write(b'\x89PNG\r\n\x1a\nfake')
    detail = {'1': [['KEY_HELLO', [1, 2, 3, 4]]], '3': [['KEY_MISS', [5, 6, 7, 8]]]}
    image = Image.objects.create(project=project, job_id=job.id, data_id=data.id, language=2,
                                 file_name=f'{job.id}-{data.id}-LAN_EN_US.png', file_path=img_url,
                                 ai_mark_img_path=img_url, size='1920,1080', rect_location='{"text":[]}',
                                 ai_check_detail=orjson.dumps(detail).decode(), ai_bug_types=[1, 3])
    return project, user, job, regress_job, data, image, img_abs, img_url


def run_flow(name, tracker_cfg, expect_tracker):
    print(f'\n==== {name}')
    project, user, job, regress_job, data, image, img_abs, img_url = make_fixture(tracker_cfg)

    # 1. AI 识别后自动提单 (与 AiImageSignTask.create_bug 同一路径)
    err, ctx = bug_svr.prepare_create_bug_task_ctx_by_ai_sign(image.id)
    ok(not err and ctx['title'].startswith('【EN】【LQA】') and '漏译' in ctx['title'] and '漏key' in ctx['title']
       and 'KEY_HELLO' in ctx['description'] and ctx['reporter'] == user.name, f'生成提单内容: {ctx.get("title")}')
    err, bug = bug_svr.CreateBugTask(ctx, None, logger).run()
    bug = Bug.objects.get(pk=bug.id)
    ok(not err and bug.bill_status == BugBillStatusEnum.SUCCESS and bug.tracker == expect_tracker
       and bug.external_id, f'提单成功 tracker={bug.tracker} external_id={bug.external_id} url={bug.external_url}')

    # 2. 回归：新截图中仍有漏译(1) -> 重新打开
    Bug.update_db(bug.id, {'regress_status': BugRegressStatusEnum.RUNNING})
    if expect_tracker == 'bugzilla':
        MockHandler.bugs[f'bz{bug.external_id}']['status'] = 'RESOLVED'   # 模拟开发已解决
    elif expect_tracker == 'none':
        Bug.update_db(bug.id, {'status': 'open'})
    new_img = Image.objects.create(project=project, job_id=regress_job.id, data_id=data.id, language=2,
                                   file_name=image.file_name, file_path=img_url, ai_mark_img_path=img_url,
                                   size='1920,1080', rect_location='{"text":[]}',
                                   ai_check_detail=orjson.dumps({'1': [['KEY_HELLO', [1, 2, 3, 4]]]}).decode(),
                                   ai_bug_types=[1])
    code, msg, stats = bug_svr.UpdateBugByRegressedImageService(
        {'image_id': new_img.id, 'bug_ids': [bug.id]}, None, logger).run()
    ok(code == 0 and stats and stats[0][0] == 'reopen' and stats[0][3] == 'suc', f'回归不通过 -> 重新打开 {stats}')

    # 3. 回归: 新截图已无问题 -> 关闭
    Bug.update_db(bug.id, {'regress_status': BugRegressStatusEnum.RUNNING})
    clean_img = Image.objects.create(project=project, job_id=regress_job.id, data_id=data.id, language=2,
                                     file_name=image.file_name, file_path=img_url, ai_mark_img_path=img_url,
                                     size='1920,1080', rect_location='{"text":[]}', ai_check_detail='{}',
                                     ai_bug_types=[])
    code, msg, stats = bug_svr.UpdateBugByRegressedImageService(
        {'image_id': clean_img.id, 'bug_ids': [bug.id]}, None, logger).run()
    bug = Bug.objects.get(pk=bug.id)
    ok(code == 0 and stats and stats[0][0] == 'close' and bug.regress_status == BugRegressStatusEnum.SUCCESS
       and bug.status == 'closed', f'回归通过 -> 关闭 {stats}')
    if expect_tracker == 'none':
        ok(len(bug.comments) == 2, f'平台内记录处理日志: {[c["text"][:20] for c in bug.comments]}')

    # 4. 缺陷系统配置错误时提单失败要有记录
    os.remove(img_abs)
    return project


def main():
    run_flow('平台内记录', {'tracker_type': 'none'}, 'none')

    server = ThreadingHTTPServer(('127.0.0.1', 0), MockHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    run_flow('Bugzilla (模拟服务)', {'tracker_type': 'bugzilla', 'base_url': base, 'api_key': 'bz-key',
                                    'product': 'Game', 'component': 'UI'}, 'bugzilla')

    print('\n==== 缺陷系统不可用')
    project, user, job, regress_job, data, image, img_abs, img_url = make_fixture(
        {'tracker_type': 'bugzilla', 'base_url': base, 'api_key': 'wrong', 'product': 'Game', 'component': 'UI'})
    err, ctx = bug_svr.prepare_create_bug_task_ctx_by_ai_sign(image.id)
    err, bug = bug_svr.CreateBugTask(ctx, None, logger).run()
    bug = Bug.objects.get(pk=bug.id)
    ok(err and bug.bill_status == BugBillStatusEnum.FAILED and 'HTTP 401' in bug.bill_text,
       f'提单失败记录原因: {bug.bill_text[:60]}')
    os.remove(img_abs)
    server.shutdown()
    print('\n提单/回归全流程测试通过')


if __name__ == '__main__':
    main()
