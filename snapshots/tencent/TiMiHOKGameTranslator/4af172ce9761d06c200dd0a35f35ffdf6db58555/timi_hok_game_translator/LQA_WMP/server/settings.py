"""
lqa 后端项目的 Django 配置文件

本文件最初由 'django-admin startproject' 基于 Django 5.1 自动生成,
现已扩展为实际项目配置, 涵盖: 环境变量加载 (config/env.{APP_ENV}/.env)、
应用 (INSTALLED_APPS) 与中间件 (MIDDLEWARE) 注册、数据库 (MySQL) 与缓存 (Redis)、
Session、Celery 异步任务队列、日志 (LOGGING) 等核心配置

更多关于本文件的说明, 参见:
https://docs.djangoproject.com/en/5.1/topics/settings/

完整的配置项列表及取值说明, 参见:
https://docs.djangoproject.com/en/5.1/ref/settings/
"""
import os
import sys
import re
import environ
from pathlib import Path


# 项目内部路径均基于 BASE_DIR 构建, 例如 BASE_DIR / 'subdir';
# 同时写入环境变量供其他模块读取, 并将 BASE_DIR 及其下的 apps 目录加入模块搜索路径 (sys.path)
BASE_DIR = Path(__file__).resolve().parent
os.environ.setdefault('BASE_DIR', str(BASE_DIR))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, 'apps'))


APP_ENV = os.environ.get('APP_ENV', 'dev')
env = environ.Env(
    APP_ENV=(str, 'dev'),
    APP_NAME=(str, 'LQA'),
    DEBUG=(bool, False),
    APP_DATA_ROOT=(str, os.path.join(BASE_DIR, 'data', 'n0')),
    APP_MEDIA_ROOT=(str, os.path.join(BASE_DIR, 'data', 'media_root')),
    NODE_NAME=(str, 'n0'),  # 当前节点名称 (响应头 Lqa-Node)
    COMPRESS=(bool, False),
    ALLOW_REGISTER=(bool, True),    # 是否开放自助注册
    PUBLIC_URL=(str, ''),           # 平台对外访问地址, 如 https://lqa.example.com (用于缺陷中的截图链接、Webhook 变量)
    MEDIA_PUBLIC=(bool, False),     # /media/ 截图是否允许匿名访问 (禅道内嵌截图时需要开启)
    AI_BASE_URL=(str, ''),          # AI 识别服务地址
    SESSION_COOKIE_SECURE=(bool, False),
)
# 配置读取顺序: 系统环境变量 > config/env.{APP_ENV} > .env
for env_file in (os.path.join(BASE_DIR, 'config', f'env.{APP_ENV}'), os.path.join(BASE_DIR, '.env')):
    if os.path.exists(env_file):
        environ.Env.read_env(env_file)
        print(f'READ ENV FILE: {env_file}')

# 安全警告: 生产环境务必关闭 DEBUG 模式! 开启 DEBUG 会暴露详细的报错堆栈、
# 源码片段及配置信息等敏感内容, 存在严重安全风险
DEBUG = env('DEBUG')
APP_NAME = env('APP_NAME')
def _abs_path(path):
    """相对路径以 server 目录为基准; 统一使用 / 分隔 (libs.storage 依赖路径前缀替换)"""
    return os.path.abspath(os.path.join(BASE_DIR, path)).replace('\\', '/')


APP_DATA_ROOT = _abs_path(env('APP_DATA_ROOT'))
APP_MEDIA_ROOT = _abs_path(env('APP_MEDIA_ROOT'))
ALLOW_REGISTER = env('ALLOW_REGISTER')
PUBLIC_URL = env('PUBLIC_URL').rstrip('/')
MEDIA_PUBLIC = env('MEDIA_PUBLIC')

# 用户上传文件的存储目录 (绝对路径)
MEDIA_ROOT = os.path.join(APP_DATA_ROOT, 'media')
# 静态文件 (CSS/JS/Images等) 收集汇总后存放的目录 (绝对路径),
# 通常由 collectstatic 命令在部署时写入该目录
STATIC_ROOT = os.path.join(APP_DATA_ROOT, 'static')
LOG_ROOT = os.path.join(APP_DATA_ROOT, 'logs')
LOG_FILE_PATH = os.path.join(LOG_ROOT, 'app.log')
TEMP_ROOT = os.path.join(APP_DATA_ROOT, 'temp')

NODE_NAME = env('NODE_NAME')
COMPRESS = env('COMPRESS')

print(f'PID: {os.getpid()} \nDEBUG: {DEBUG} \nLOG_FILE_PATH: {LOG_FILE_PATH}\nAPP_MEDIA_ROOT:{APP_MEDIA_ROOT}')


must_dirs = (TEMP_ROOT, STATIC_ROOT, MEDIA_ROOT, LOG_ROOT, APP_MEDIA_ROOT)
for root_path in must_dirs:
    os.makedirs(root_path, exist_ok=True)



# 以下为快速启动的开发环境配置, 不适合直接用于生产环境
# 详见部署检查清单: https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# 安全警告: 生产环境使用的 SECRET_KEY 必须妥善保密, 不可泄露或提交到代码仓库!
SECRET_KEY = env('SECRET_KEY', default='')
if not SECRET_KEY or SECRET_KEY.startswith('change-me'):
    if not DEBUG:
        raise RuntimeError('请在环境变量或 .env 中设置随机的 SECRET_KEY (生产环境必须)')
    SECRET_KEY = 'django-insecure-dev-only-do-not-use-in-production'  # nosemgrep: rule-id-here -- 仅用于本地开发默认值, 生产环境强制要求配置

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['*'])


# 应用定义: 已注册的 Django App (包括业务应用 image/bug/data/job/project/system/user/lqa
# 及部分 Django 内置应用)

INSTALLED_APPS = [
    'image',
    'bug',
    'data',
    'job',
    'project',
    'system',
    'user',
    'lqa',
    # 'django.contrib.admin',
    # 'django.contrib.auth',
    # 'django.contrib.contenttypes',
    'django.contrib.sessions',
    # 'django.contrib.messages',
    'django.contrib.staticfiles',
    # 'user.apps.UserConfig',
]

MIDDLEWARE = [
    'apps.lqa.middleware.AccessLogMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    # 'django.middleware.csrf.CsrfViewMiddleware',
    # 'django.contrib.auth.middleware.AuthenticationMiddleware',
    # 'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.lqa.middleware.ExceptionMiddleware',
    # 'lqa.middleware.DistinctBodyMiddleware',
    'apps.user.middleware.AuthRequiredMiddleware'
]

ROOT_URLCONF = 'urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates']
        ,
        'APP_DIRS': True,
        'OPTIONS': {
            'string_if_invalid': '[undefined]',
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'wsgi.application'


# 数据库配置
# 详见: https://docs.djangoproject.com/en/5.1/ref/settings/#databases

DATABASES = {
    'default': env.db_url('MYSQL_URL')
}
if DATABASES['default']['ENGINE'] == 'django.db.backends.mysql':
    DATABASES['default']['ENGINE'] = 'libs.db_mysql'  # 允许系统模板项目 id=0, 见 libs/db_mysql/base.py
    DATABASES['default'].setdefault('OPTIONS', {}).setdefault('charset', 'utf8mb4')

CACHES = {
    "default": env.cache_url('REDIS_URL')
}

KEY_PREFIX = 'lqa'  # 设个设置不起作用, django代码写死了 (不重要)
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'  # 指定 session 存储后端, 默认用的 db
SESSION_COOKIE_AGE = 60 * 60 * 24 * 3  # session cookie 有效期默认两周, 改为3天
SESSION_COOKIE_NAME = 'lqa_sessionid'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = env('SESSION_COOKIE_SECURE')  # 使用 HTTPS 部署时建议开启

# 密码校验规则
# 详见: https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# 国际化配置 (语言、时区等)
# 详见: https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Shanghai'

USE_I18N = True

USE_TZ = False


# 静态文件配置 (CSS、JavaScript、图片等)
# 详见: https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = 'static/'

# POST 请求体最大允许大小 (字节), 当前限制为 100MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024 * 100


# Celery 异步任务队列配置, 详见: https://docs.celeryq.dev/en/stable/userguide/configuration.html#configuration
CELERY_BROKER_URL = env('CELERY_BROKER_URL')  # broker 地址
CELERY_RESULT_BACKEND = env('CELERY_BACKEND_URL')  # 任务结果存储地址

CELERY_ENABLE_UTC = False
CELERY_TIMEZONE = 'Asia/Shanghai'

# 在默认情况下, CELERY_TASK_TRACK_STARTED 的值为 False, 这意味着当一个任务开始执行时, Celery 不会在任务状态中记录 STARTED 状态
# 任务状态会直接从 PENDING 跳转到 SUCCESS 或 FAILURE
CELERY_TASK_TRACK_STARTED = True
# 用于设置 Celery 中任务的时间限制, 具体来说, 这个选项决定了任务在被强制终止之前可以运行的最长时间
CELERY_TASK_TIME_LIMIT = 30 * 60
# 用于控制 Celery 在启动时如何处理与消息代理 (broker) 的连接重试
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS = False
# 用于控制 Celery 工作者 (worker) 在重定向标准输出 (stdout) 和标准错误 (stderr) 时的日志级别
CELERY_WORKER_REDIRECT_STDOUTS_LEVEL = 'INFO'
# 这个参数如果设置为 True, 那么任务实例的执行会在任务实例执行完毕之后才会确认; 否则只要开始执行任务实例就确认了, 防止丢掉任务
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_ROUTES = {
    'lqa_queue_ai_sign': {'queue': 'lqa_queue_ai_sign'},
    'lqa_queue_bug': {'queue': 'lqa_queue_bug'},
    'lqa_queue_submit_ai_sign': {'queue': 'lqa_queue_submit_ai_sign'},
}
# Celery 工作进程会接管根日志记录器, 默认 True
# CELERY_WORKER_HIJACK_ROOT_LOGGER = False
if not DEBUG:
    # 设置 worker 日志文件的路径
    CELERY_WORKER_LOGFILE=os.path.join(LOG_ROOT, 'celery.log')
    print(f'CELERY_WORKER_LOGFILE: {CELERY_WORKER_LOGFILE}')
    # 启用标准输出和标准错误的重定向 重定向到文件中去
    CELERY_WORKER_REDIRECT_STDOUTS = True


# 默认主键字段类型
# 详见: https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGGING = {
    'version': 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime} {name} {levelname} {process:d} {thread:d}] {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            'maxBytes': 1024 * 1024 * 1024 * 2,
            "formatter": "verbose",
            "filename": LOG_FILE_PATH,
            # "when": "D",
            # "backupCount": 90,
        },
        # "celery": {
        #     "class": "logging.handlers.TimedRotatingFileHandler",
        #     "formatter": "verbose",
        #     "filename": env('LOG_FILE_PATH').replace('.log', '.celery.log'),
        #     "when": "D",
        #     "backupCount": 90,
        # }
    },
    # "root": {
    #     "handlers": ["console", "file"],
    #     "level": "INFO",
    # },
    "loggers": {
        "": {
            "handlers": ["console", "file"],
            'level': 'DEBUG' if DEBUG else 'INFO',
        },
        # 'django.db.backends': {  # 打开可以看sql
        #     # 'handlers': ['console'],
        #     'level': 'DEBUG' if DEBUG else 'INFO',
        # },
        # 'celery': {
        #     'handlers': ["celery"],
        #     # 'propagate': True,  # 如果属性设置为 True, 则该消息不仅会被当前记录器处理, 还会被传递给其所有祖先记录器
        #     'level': 'INFO',
        # },
    }
}
