"""
初始化系统数据（可重复执行）:
  - 系统模板项目（id=0），存放系统级的缺陷类型、区域语言，新建项目时会复制这些配置
  - 默认缺陷类型、区域语言

python manage.py init_data
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.project.models import Project, ProjectConfigBugType, ProjectConfigLanguage
from apps.system.models import SystemLanguage
from libs.defs import QCC_PROJECT_ID, ProjectTypeEnum, ProjectPhaseEnum, GameTypeEnum

# (value, name, label) value 与 AI 识别服务约定的缺陷类型编号一致
DEFAULT_BUG_TYPES = (
    (1, 'MISS_TRANS', '漏译'),
    (2, 'OVERFLOW', '超框'),
    (3, 'MISS_KEY', '漏key'),
    (4, 'OVERLAP', '标准框重叠'),
    (5, 'ERR_TRANS', '错译'),
    (7, 'NON_STANDARD_FRAME', '非标准框'),
    (8, 'ERR_TRANS_RULE', '错译(规则)'),
    (9, 'LINE_HEIGHT', '行高百分比'),
    (10, 'FONT_TOO_SMALL', '字体太小'),
)

# (value, code, label) 其中 2/4/5/6/8/10 与 AI 识别服务的语言编码映射一致（见 apps/image/service.py）
DEFAULT_LANGUAGES = (
    (2, 'LAN_EN_US', '英语'),
    (3, 'LAN_KO_KR', '韩语'),
    (4, 'LAN_TH_TH', '泰语'),
    (5, 'LAN_VI_VN', '越南语'),
    (6, 'LAN_JA_JP', '日语'),
    (7, 'LAN_RU_RU', '俄语'),
    (8, 'LAN_ZH_TW', '繁体中文'),
    (9, 'LAN_FR_FR', '法语'),
    (10, 'LAN_ZH_CN', '简体中文'),
    (11, 'LAN_TR_TR', '土耳其语'),
    (12, 'LAN_DE_DE', '德语'),
    (13, 'LAN_ES_ES', '西班牙语'),
    (14, 'LAN_PT_BR', '葡萄牙语'),
    (15, 'LAN_ID_ID', '印尼语'),
    (16, 'LAN_AR_SA', '阿拉伯语'),
)


class Command(BaseCommand):
    help = '初始化系统模板项目、默认缺陷类型和区域语言'

    def _ensure_template_project(self):
        if Project.objects2.filter(pk=QCC_PROJECT_ID).exists():
            return False
        # 需要 libs.db_mysql 后端（允许 id=0 且启用 NO_AUTO_VALUE_ON_ZERO）
        Project.objects.create(id=QCC_PROJECT_ID, code='__system__', name='系统模板',
                               project_type=ProjectTypeEnum.PLATFORM, project_phase=ProjectPhaseEnum.ONLINE,
                               game_type=str(GameTypeEnum.MOBILE_GAME.value))
        if not Project.objects2.filter(pk=QCC_PROJECT_ID).exists():
            raise RuntimeError('系统模板项目 id=0 创建失败，请确认使用的是 libs.db_mysql 数据库后端')
        return True

    @transaction.atomic
    def handle(self, *args, **options):
        created = self._ensure_template_project()
        self.stdout.write(f'系统模板项目(id={QCC_PROJECT_ID}): {"已创建" if created else "已存在"}')

        n = 0
        for value, name, label in DEFAULT_BUG_TYPES:
            _, c = ProjectConfigBugType.objects.get_or_create(
                project_id=QCC_PROJECT_ID, value=value, defaults={'name': name, 'label': label, 'trans_marks': '[]'})
            n += int(c)
        self.stdout.write(f'缺陷类型: 新增 {n} 条')

        n = 0
        for value, code, label in DEFAULT_LANGUAGES:
            _, c = ProjectConfigLanguage.objects.get_or_create(
                project_id=QCC_PROJECT_ID, value=value, defaults={'name': code, 'label': label})
            SystemLanguage.objects.get_or_create(id=value, defaults={'language': label, 'language_code': code})
            n += int(c)
        self.stdout.write(f'区域语言: 新增 {n} 条')
        self.stdout.write(self.style.SUCCESS('初始化完成'))
