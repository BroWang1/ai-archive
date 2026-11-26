from django.db import models
import datetime

Minute_5 = 60 * 5

MAX_ID = 900000000


class ProjectTypeEnum(models.IntegerChoices):
    PLATFORM = 1, '平台级'
    PROJECT = 2, '项目级'


class ProjectPhaseEnum(models.IntegerChoices):
    ONLINE = 1, '上线运营'
    OFFLINE = 2, '下线'
    DEV = 3, '研发期'
    SECRECY = 4, '保密'


class GameTypeEnum(models.IntegerChoices):
    MOBILE_GAME = 1, '手游'
    PC_GAME = 2, '端游'
    WEB_GAME = 3, '页游'
    APP = 4, 'app'
    MINI_GAME = 5, '小游戏'


class UserStatusEnum(models.IntegerChoices):
    DISABLED = 0, '禁用'
    ACTIVE = 1, '正常'


class BugTrackerTypeEnum(models.TextChoices):
    NONE = 'none', '平台内记录'
    BUGZILLA = 'bugzilla', 'Bugzilla'
    ZENTAO = 'zentao', '禅道'


class RoleEnum(models.IntegerChoices):
    ADMIN = 1, '项目管理员'
    TEST = 2, '测试人员'
    DEVELOP = 3, '开发人员'


# class BugTypeEnum(models.IntegerChoices):
#     MISS_TRANS = 1, "漏译"
#     OVERFLOW = 2, "超框"
#     MISS_KEY = 3, "漏Key"
#     OVERLAP = 4, "标准框重叠"
#     ERR_TRANS = 5, "错译"


class ProjectConfigCateEnum(models.IntegerChoices):
    BUG_TYPE = 1, "缺陷类型"
    LANGUAGE = 2, "区域语言"
    IMG_REVERT = 3, "图片还原"
    RUNNER = 4, "还原执行(Webhook)"
    BILL = 5, "提单"
    BUG_TRACKER = 6, "缺陷系统"


class SwitchEnum(models.IntegerChoices):
    OFF = 0, '关闭'
    ON = 1, '开启'


class JobRegressionEnum(models.IntegerChoices):
    """任务类型标识 0:正常生成图片,1:回归任务生成图片,2:正常生成图片重试任务"""
    NORMAL = 0, '正常生成图片'
    REGRESSION = 1, '回归任务生成图片'
    RETRY = 2, '正常生成图片重试任务'

class JobDiscernEnum(models.IntegerChoices):
    FULL = 0, '全量识别'
    DIFF = 1, '差异识别'

class JobStatusEnum(models.IntegerChoices):
    UN_RUNNING = 1, '未执行'
    RUNNING = 2, '执行中'
    FAILED = 3, '执行失败'
    SUCCESS = 4, '执行成功'
    COMPLETED = 5, '执行完'

class JobResTypeEnum(models.TextChoices):
    GIT = 'git'
    SVN = 'svn'
    P4 = 'p4'
    OTHER = 'other'

class BugPriorityEnum(models.IntegerChoices):
    """平台内的优先级, 提交到缺陷系统时由适配器映射为对应系统的取值"""
    EMPTY = 0, '空'
    URGENT = 1, '紧急'
    HIGH = 2, '高'
    MEDIUM = 3, '中'
    LOW = 4, '低'
    INSIGNIFICANT = 5, '无关紧要'


class BugSeverityEnum(models.IntegerChoices):
    """平台内的严重程度, 提交到缺陷系统时由适配器映射为对应系统的取值"""
    EMPTY = 0, '空'
    FATAL = 1, '致命'
    SERIOUS = 2, '严重'
    NORMAL = 3, '一般'
    PROMT = 4, '提示'
    ADVICE = 5, '建议'


class BugBillStatusEnum(models.IntegerChoices):
    INIT = 0, '初始'
    SUCCESS = 1, '提bug单成功'
    FAILED = 2, '提bug单失败'


class BugRegressStatusEnum(models.IntegerChoices):
    INIT = 1, '初始'
    RUNNING = 2, '回归中'
    SUCCESS = 3, '回归成功'
    FAILED = 4, '回归失败'


class ImageTaskErrorEnum(models.IntegerChoices):
    ERR_NO = 0, '没有失败'
    ERR_AI_REC = 1, '识别失败'
    ERR_BUG_BILL = 2, '提单失败'
    ERR_REGRESSION = 3, '回归失败'

class ImageAiSignErrorEnum(models.IntegerChoices):
    ERR_NO = 0, '初始值'
    ERR_SUC = 1, '识别成功'
    ERR_FAIL = 2, '识别失败'


class SystemCateEnum(models.IntegerChoices):
    ROLE = 1, 'roles'
    BUG_TYPE = 2, 'bugtypes'
    LANGUAGE = 3, 'languages'


class ReviewedEnum(models.IntegerChoices):
    EMPTY = 0, '未审核(无审核记录)'
    AUTO = 1, '系统自动审核'
    MANUAL = 2, '人工审核'


class ApiErrorEnum(models.IntegerChoices):
    ERROR = 1000, '接口错误'
    ERROR_PARAM = 1001, '参数错误'
    ERROR_AUTH = 1003, '认证失败'
    NOT_EXIST = 1004, '数据不存在'
    ERROR_NEED_UPDATE = 1005, '数据版本错误'
    ERROR_PERMISSION = 1006, '没有权限'


LO_TIME_DELTA = datetime.timedelta(hours=8)
LO_ZONE = datetime.timezone(LO_TIME_DELTA)

# 系统模板项目id: 存放系统级缺陷类型、语言配置, 新建项目时以此为模板复制
QCC_PROJECT_ID = 0
