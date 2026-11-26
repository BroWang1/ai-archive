from celery.utils.log import get_task_logger
from celery_app import app as celery_app

from .service import AiImageSignTask, SubmitAiImageSignTask

logger = get_task_logger(__name__)


@celery_app.task(bind=True, ignore_result=True, queue='lqa_queue_ai_sign')
def run_ai_sign(self, ctx):
    """启动任务"""
    logger.info(f'run_ai_sign start')
    svr = AiImageSignTask(ctx, self.request, logger)
    svr.run()
    logger.info(f'run_ai_sign end')


@celery_app.task(bind=True, ignore_result=True, queue='lqa_queue_submit_ai_sign')
def run_submit_ai_sign(self, ctx):
    logger.info(f'run_submit_ai_sign start')
    svr = SubmitAiImageSignTask(ctx, self.request, logger)
    svr.run()
    logger.info(f'run_submit_ai_sign end')
