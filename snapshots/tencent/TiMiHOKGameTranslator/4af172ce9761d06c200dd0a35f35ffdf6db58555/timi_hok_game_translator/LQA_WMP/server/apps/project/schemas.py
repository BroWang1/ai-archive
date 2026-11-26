import datetime
from typing import List, Optional, Union, Any, Annotated, Literal

import orjson
from pydantic import BaseModel, Field, BeforeValidator, field_validator, AfterValidator

from libs import util
from libs.defs import ProjectTypeEnum, ProjectPhaseEnum, GameTypeEnum, SwitchEnum, BugTrackerTypeEnum
from apps.project import service as proj_svr


def make_game_type_validator():
    """游戏类型（多选）统一校验：接受数组 / 逗号字符串 / 单个值，输出逗号分隔字符串（如 '1,3'）"""

    def _validate(value):
        if value is None or value == '':
            return ''
        items = value if isinstance(value, (list, tuple, set)) else str(value).split(',')
        result = []
        for item in items:
            if item is None or item == '':
                continue
            try:
                num = int(item)
            except (TypeError, ValueError):
                raise ValueError(f'非法的游戏类型: {item}')
            if num not in GameTypeEnum.values:
                raise ValueError(f'非法的游戏类型: {num}')
            if str(num) not in result:
                result.append(str(num))
        return ','.join(result)

    return _validate


def split_game_type(value):
    """把库中逗号分隔的游戏类型转成 int 数组，供接口返回（如 '1,3' -> [1, 3]）"""
    if not value:
        return []
    return [int(v) for v in str(value).split(',') if v != '']


def make_game_type_search_validator():
    """搜索参数：接受数组 / 逗号串 / 单值，统一输出逗号分隔字符串（如 '1,2'），非法项直接忽略"""

    def _validate(value):
        if value is None or value == '':
            return None
        items = value if isinstance(value, (list, tuple, set)) else str(value).split(',')
        result = []
        for item in items:
            if item is None or item == '':
                continue
            try:
                num = int(item)
            except (TypeError, ValueError):
                continue
            if num not in GameTypeEnum.values:
                continue
            if str(num) not in result:
                result.append(str(num))
        return ','.join(result) if result else None

    return _validate


class ProjectSchema(BaseModel):
    project_id: int = Field(default=0)
    code: str = Field(min_length=2, max_length=100, pattern=r'^[A-Za-z0-9_\-]+$')
    name: str = Field(min_length=1, max_length=100)
    img: str = Field(default='')
    project_type: ProjectTypeEnum
    project_phase: ProjectPhaseEnum
    game_type: Annotated[str, BeforeValidator(make_game_type_validator())] = Field(default='')
    team: str = Field(default='', max_length=100)
    cvtest_project: str = Field(default='', max_length=32)
    test_manager: str = Field(default='')


class ProjectListSchema(BaseModel):
    project_id: int = Field(default=None)
    team__icontains: str = Field(default=None, alias='team')
    name__icontains: str = Field(default=None, alias='name')
    project_type: int = Field(default=None)
    game_type: Annotated[str, BeforeValidator(make_game_type_search_validator())] = Field(
        default=None, alias='game_type')
    project_phase: int = Field(default=None)
    cur_id: int = Field(default=None)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=2)


class ProjectModuleCreateSchema(BaseModel):
    id: int = 0
    project_id: int
    name: str = Field(min_length=2)
    show_name: str = Field(min_length=2)
    sub_module: str = Field(default='')


class ProjectModuleListSchema(BaseModel):
    project_id: int
    all: SwitchEnum = Field(default=SwitchEnum.OFF)
    name__icontains: str = Field(default=None, alias='name')
    show_name__icontains: str = Field(default=None, alias='show_name')
    cur_id: int = Field(default=None)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=2)


class ProjectConfigBugTypeSchema(BaseModel):
    id: int = Field(default=0)
    project_id: int = Field(ge=0)
    name: str = Field(min_length=2)
    label: str = Field(min_length=2)
    value: int = Field(gt=0)
    enable: int = Literal[0, 1]
    trans_marks: Annotated[List, BeforeValidator(util.make_json_validator()), AfterValidator(lambda v: orjson.dumps(v).decode())] = Field(default_factory=lambda: [])


class ProjectConfigLanguageSchema(BaseModel):
    id: int = Field(default=0)
    project_id: int = Field(ge=0)
    name: str = Field(min_length=2)
    label: str = Field(min_length=2)
    custom_label: str = Field(default='')
    value: int = Field(gt=0)
    enable: int = Literal[0, 1]


class ProjectConfigImgRevertSchema(BaseModel):
    """项目配置：图片还原"""
    id: int = Field(default=0)
    project_id: int = Field(ge=0)
    root_path: str = Field(default='')
    key: str = Field(default='')
    text: str = Field(default='')
    lang_path: str = Field(default='')
    no_trans_text: str = Field(default='')


class ProjectConfigBugBillMethodSchema(BaseModel):
    """项目配置：提单"""
    id: int = Field(default=0)
    project_id: int = Field(ge=0)
    bug_type_enable: int = Literal[0, 1]
    language_enable: int = Literal[0, 1]
    module_enable: int = Literal[0, 1]
    description_template: str = Field(default='')


class ProjectConfigBugBillUserSchema(BaseModel):
    """项目配置：提单"""
    id: int = Field(default=0)
    project_id: int = Field(ge=0)
    enable: int = Literal[0, 1]
    bug_type: Annotated[int, BeforeValidator(proj_svr.BugTypeValidator(True))]
    language: Annotated[int, BeforeValidator(proj_svr.LanguageValidator(True))]
    module: int = Field(ge=0)
    user_names: List[str]


def _json_text_validator(expect_type, allow_empty=False):
    def validator(v):
        if v is None:
            return '' if allow_empty else orjson.dumps(expect_type()).decode()
        if isinstance(v, (dict, list)):
            v = orjson.dumps(v).decode()
        v = v.strip()
        if allow_empty and v == '':
            return v
        try:
            parsed = orjson.loads(v)
        except orjson.JSONDecodeError:
            raise ValueError('不是合法的 JSON')
        if not isinstance(parsed, expect_type):
            raise ValueError(f'必须是 JSON {"对象" if expect_type is dict else "数组"}')
        return v
    return validator


class ProjectConfigOtherSchema(BaseModel):
    """项目配置：还原执行（Webhook）"""
    id: int = Field(default=0)
    project_id: int = Field(gt=0)
    webhook_url: str = Field(default='', max_length=512, pattern=r'^(https?://.*)?$')
    webhook_method: Literal['POST', 'GET', 'PUT'] = Field(default='POST')
    webhook_headers: Annotated[str, BeforeValidator(_json_text_validator(dict))] = Field(default='{}')
    webhook_body: Annotated[str, BeforeValidator(_json_text_validator((dict, list), True))] = Field(default='')
    editor_path: str = Field(default='', max_length=128)
    editor_version: str = Field(default='', max_length=32)


class ProjectConfigBugTrackerSchema(BaseModel):
    """项目配置：缺陷系统"""
    id: int = Field(default=0)
    project_id: int = Field(gt=0)
    tracker_type: BugTrackerTypeEnum = Field(default=BugTrackerTypeEnum.NONE)
    base_url: str = Field(default='', max_length=255, pattern=r'^(https?://.*)?$')
    username: str = Field(default='', max_length=128)
    api_key: str = Field(default='', max_length=255)
    product: str = Field(default='', max_length=128)
    component: str = Field(default='', max_length=128)
    extra: Annotated[dict, BeforeValidator(lambda v: orjson.loads(v) if isinstance(v, str) and v.strip() else (v or {}))] = Field(default_factory=dict)


class ProjectConfigDelSchema(BaseModel):
    project_id: int = Field(gt=0)
    ids: List[int] = Field(min_length=1)


class ProjectConfigCustomFieldSchema(BaseModel):
    """项目配置：自定义提单字段"""
    id: int = Field(default=0)
    project_id: int = Field(ge=0)
    field_name: str = Field(min_length=1)
    field_key: str = Field(min_length=1)
    options: List[str] = Field(default_factory=list)
    enable: int = Literal[0, 1]
    sort_order: int = Field(default=0)
