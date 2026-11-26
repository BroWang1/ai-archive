#!/bin/sh
# 用法: docker-entrypoint.sh web | worker | <任意命令>
set -e

case "$1" in
  web)
    python manage.py migrate --noinput
    python manage.py init_data
    if [ -n "$LQA_ADMIN_PASSWORD" ]; then
      python manage.py init_admin --if-not-exists
    fi
    exec gunicorn wsgi:application \
      --bind 0.0.0.0:8000 \
      --workers "${GUNICORN_WORKERS:-4}" \
      --timeout "${GUNICORN_TIMEOUT:-120}" \
      --access-logfile -
    ;;
  worker)
    exec celery -A celery_app worker -l info \
      --concurrency "${CELERY_CONCURRENCY:-4}" \
      -Q "${CELERY_QUEUES:-celery,lqa_queue_ai_sign,lqa_queue_submit_ai_sign,lqa_queue_bug}"
    ;;
  *)
    exec "$@"
    ;;
esac
