"""
本地调试 Celery worker (便于在 IDE 中断点调试):
    python celery_worker_debug.py -A celery_app worker -l INFO --pool threads -c 2
"""
from celery.__main__ import main

main()
