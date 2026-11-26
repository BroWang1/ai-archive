from celery.utils.log import get_task_logger

from celery_app import app as celery_app
from .service import CreateBugTask

logger = get_task_logger(__name__)


@celery_app.task(bind=True, ignore_result=True, queue='lqa_queue_bug')
def run_bug_create(self, ctx):
    """启动任务"""
    logger.info(f'run_bug_create start')
    task = CreateBugTask(ctx, self, logger)
    task.run()
    logger.info(f'run_bug_create end')
