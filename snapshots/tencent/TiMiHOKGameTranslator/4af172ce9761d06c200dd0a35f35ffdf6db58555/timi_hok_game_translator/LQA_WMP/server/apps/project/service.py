from functools import partialmethod
from typing import Union

from django.db.models import Q, QuerySet

from apps.user.models import UserProjectRelationship
from apps.project.models import *
from libs.base import ExpireData
from libs.defs import QCC_PROJECT_ID


Project_Config_Model_Map = {
    'BugType': ProjectConfigBugType,
    'Language': ProjectConfigLanguage,
    'ImgRevert': ProjectConfigImgRevert,
    'BugBillMethod': ProjectConfigBugBillMethod,
    'BugBillUser': ProjectConfigBugBillUser,
    'Other': ProjectConfigOther,              # 还原执行（Webhook）
    'BugTracker': ProjectConfigBugTracker,    # 缺陷系统
    'CustomField': ProjectConfigCustomField,  # 自定义提单字段
}

# 每个项目只有一条记录的配置
Project_Single_Config_Models = (ProjectConfigBugBillMethod, ProjectConfigOther, ProjectConfigBugTracker)


class _SysLanguage(ExpireData):
    def query_db(self):
        return list(ProjCfgService.get_language(QCC_PROJECT_ID))


class _SysBugType(ExpireData):
    def query_db(self):
        return list(ProjCfgService.get_bug_type(QCC_PROJECT_ID))


class ProjCfgService(object):
    _sys_language = _SysLanguage()
    _sys_bugtype = _SysBugType()

    @classmethod
    def get_config(cls, cate, project_id) -> QuerySet:
        model = Project_Config_Model_Map[cate]
        return model.objects.filter(project_id=project_id).values()

    @classmethod
    def get_bill(cls, project_id) -> Union[dict, None]:
        cfg = cls.get_bill_method(project_id).first()
        if not cfg:
            return None
        cfg['rows'] = list(cls.get_bill_user(project_id))
        return cfg

    @classmethod
    def get_runner(cls, project_id, validate=True) -> Union[dict, None]:
        """还原执行（Webhook）配置；validate=True 时未配置 webhook_url 返回 None"""
        cfg = cls.get_config('Other', project_id).first()
        if not cfg:
            return None
        if validate and not cfg['webhook_url'].strip():
            return None
        return cfg

    @classmethod
    def get_bug_tracker(cls, project_id) -> Union[dict, None]:
        """缺陷系统配置，未配置时返回 None（等同于平台内记录）"""
        return cls.get_config('BugTracker', project_id).first()

    @classmethod
    def get_sys_language(cls, mapping=False) -> Union[dict, list]:
        return {o['value']: o for o in cls._sys_language.data} if mapping else cls._sys_language.data

    @classmethod
    def get_sys_bugtype(cls, mapping=False) -> Union[dict, list]:
        return {o['value']: o for o in cls._sys_bugtype.data} if mapping else cls._sys_bugtype.data

    @classmethod
    def get_bug_type(cls, project_id, mapping=False) -> Union[dict, list]:
        rows = list(cls.get_config('BugType', project_id))
        if mapping:
            return {r_['value']: r_ for r_ in rows}
        return rows

    @classmethod
    def get_language(cls, project_id, mapping=False) -> Union[dict, list]:
        rows = list(cls.get_config('Language', project_id))
        if mapping:
            return {r_['value']: r_ for r_ in rows}
        return rows

    get_img_revert = partialmethod(get_config, 'ImgRevert')
    get_bill_user = partialmethod(get_config, 'BugBillUser')
    get_bill_method = partialmethod(get_config, 'BugBillMethod')


def update_user_project_roles(uid, project_id, project_roles):
    """更新用户项目的角色信息 增删改 """
    param = {'user_id': uid}
    if project_id:
        param['project_id'] = project_id
    ships = UserProjectRelationship.objects.filter(**param)
    req_ships_set = set(map(lambda pr_: (pr_[0], uid, pr_[1]), project_roles))
    all_ships_set = set(map(lambda ship_: (ship_.project_id, ship_.user_id, ship_.role), ships))
    del_ships_set = all_ships_set - req_ships_set
    add_ships_set = req_ships_set - all_ships_set
    updated_project_ids = set()
    if len(del_ships_set):  # 删除的角色
        qs = Q()
        for ship in del_ships_set:
            qs |= Q(project_id=ship[0], user_id=ship[1], role=ship[2])
            updated_project_ids.add(ship[0])
        UserProjectRelationship.objects.filter(qs).delete()
    if len(add_ships_set):  # 新增的角色
        add_ships = []
        for ship in add_ships_set:
            add_ships.append(UserProjectRelationship(project_id=ship[0], user_id=ship[1], role=ship[2]))
            updated_project_ids.add(ship[0])
        UserProjectRelationship.objects.bulk_create(add_ships)
    return updated_project_ids


def update_ship_and_project_cfg_by_delete_user(uid):
    """
    删除用户时 角色和提单配置处理
    """
    ships = UserProjectRelationship.objects.filter(user_id=uid)
    project_ids = set()
    for ship in ships:
        project_ids.add(ship.project_id)
    ships.delete()
    return project_ids


def project_of_members(project_ids):
    """
     {
        "project_id": project_id,
        "members": [
            user_id_str: [1, 2, 3]
        ]
    }
    :param project_ids: project_id or project_ids
    :return: dict or list[dict]
    """

    is_int = isinstance(project_ids, int)
    project_ids_ = [project_ids] if is_int else project_ids
    projects = {}
    for ship_row in UserProjectRelationship.objects.filter(project_id__in=project_ids_).values():
        project_id = ship_row['project_id']
        user_id_str = str(ship_row['user_id'])
        role = ship_row['role']
        project = projects.get(project_id, {'project_id': project_id, 'members': {}})
        roles = project['members'].get(user_id_str, [])
        roles.append(role)
        project['members'][user_id_str] = roles
        projects[project_id] = project
    datas = list(projects.values())
    return (datas[0] if len(datas) > 0 else None) if is_int else datas


class BugTypeValidator(ExpireData):

    def __init__(self, allow_zero=False):
        super(BugTypeValidator, self).__init__()
        self.allow_zero = allow_zero

    def query_db(self):
        data = {}
        for row in ProjCfgService.get_sys_bugtype():
            data[row['value']] = row['value']
            data[row['name']] = row['value']
        return data

    def _validate_bug_type(self, v, allow_zero=True):
        """v bug_type_code or bug_type_value"""
        try:
            v = int(v)
        except:
            pass
        if allow_zero and v == 0:
            return 0

        v_ = self.data.get(v, None)
        if v_ is None:
            raise ValueError(f'Invalid value: {v}')
        return v_

    def __call__(self, v, info):
        """
        v is List[value or name] or value or name
        """
        if isinstance(v, list) or isinstance(v, tuple):
            return [self._validate_bug_type(v_, self.allow_zero) for v_ in v]
        else:
            return self._validate_bug_type(v, self.allow_zero)


class LanguageValidator(BugTypeValidator):
    # UE 编辑器侧使用的语言代码到 WMP 标准代码的别名映射
    # 当 UE 通过 /api/job/datas /api/image/entity 等接口传入 UE 侧命名
    # (见 UE_LQARestore_Plugin/Plugins/LQARestore/.../ConfigManager.cpp InitializeLanguageMap)
    # 时, 自动翻译为 lqa_system_language 表里的标准 code, 避免误报 "Invalid language"
    _UE_LANGUAGE_CODE_ALIASES = {
        'LAN_EU_EN':  'LAN_EN_US',  # 英语
        'LAN_EU_DE':  'LAN_DE_DE',  # 德语
        'LAN_FR_FR':  'LAN_FR_FR',  # 法语
        'LAN_RU_RU':  'LAN_RU_RU',  # 俄语
        'LAN_JP_JP':  'LAN_JA_JP',  # 日语
        'LAN_KO_KO':  'LAN_KO_KR',  # 韩语
        'LAN_CHT_CHT': 'LAN_ZH_TW', # 繁体中文
        'LAN_AR_AR':  'LAN_AR_SA',  # 阿拉伯语
        'LAN_ES_LT':  'LAN_ES_ES',  # 西班牙语
        'LAN_PT_BR':  'LAN_PT_BR',  # 巴西葡萄牙语
        'LAN_TR_TR':  'LAN_TR_TR',  # 土耳其语
        'LAN_TH_TH':  'LAN_TH_TH',  # 泰语
        'LAN_ID_ID':  'LAN_ID_ID',  # 印尼语
        'LAN_CHS_CHS': 'LAN_ZH_CN', # 简体中文
    }

    def __init__(self, allow_zero=False):
        super(LanguageValidator, self).__init__(allow_zero)

    def query_db(self):
        data = {}
        for row in ProjCfgService.get_sys_language():
            data[row['value']] = row['value']
            data[row['name']] = row['value']
        return data

    def _validate_bug_type(self, v, allow_zero=True):
        # 若传入的是 UE 侧别名, 先翻译为 WMP 标准代码再走原校验
        if isinstance(v, str) and v in self._UE_LANGUAGE_CODE_ALIASES:
            v = self._UE_LANGUAGE_CODE_ALIASES[v]
        return super(LanguageValidator, self)._validate_bug_type(v, allow_zero)


def patch_language_code(val: Union[int, list]):
    language_codes = ProjCfgService.get_sys_language(True)
    if isinstance(val, int):
        return language_codes[val]['name']
    else:
        for v_ in val:
            v_['language_code'] = language_codes[v_['language']]['name']
