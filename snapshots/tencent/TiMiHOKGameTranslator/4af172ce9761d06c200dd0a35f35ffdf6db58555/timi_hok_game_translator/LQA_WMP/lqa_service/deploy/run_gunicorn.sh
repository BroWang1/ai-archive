#!/usr/bin/env bash
export LANG="zh_CN.UTF-8"

#cd /data/lqa/
gunicorn -c config/gunicorn_config.py portal:app --preload
