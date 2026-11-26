from typing import List, Annotated, Optional, Dict

import orjson
from pydantic import BaseModel, Field, AliasChoices, BeforeValidator, AfterValidator

from libs.defs import BugSeverityEnum, BugPriorityEnum, BugRegressStatusEnum, BugTrackerTypeEnum
from libs import util
from apps.project import service as proj_svr


class BugBuildInfoSchema(BaseModel):
    image_id: int = Field(gt=0)
    project_id: int = Field(gt=0)
    bug_types: Annotated[List[int], BeforeValidator(util.make_item_array_validator()), AfterValidator(proj_svr.BugTypeValidator())] = Field(default_factory=list)


class BugListSchema(BaseModel):
    job_id: int = Field(ge=1)
    image_id: int = Field(default=None, ge=1)
    title__contains: str = Field(default=None, alias='title')
    info_type: int = Field(default=0)  # 0:同步缺陷系统中的最新状态  1:只取平台数据库中的数据
    cur_id: int = Field(default=None)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=2, le=100)


class BugCreateSchema(BaseModel):
    project_id: int
    image_id: int
    job_id: int
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=3)
    version_report: str = Field(default='')
    release_id: str = Field(default='')
    version_fix: str = Field(default='')
    severity: BugSeverityEnum = Field(default=BugSeverityEnum.EMPTY)
    priority: BugPriorityEnum = Field(default=BugPriorityEnum.EMPTY)
    reporter: str = Field(min_length=1)
    current_owner: str = Field(default='')
    raw_image_path: Annotated[str, BeforeValidator(util.make_img_url_validator())] = Field(min_length=3)
    ai_image_path: Annotated[str, BeforeValidator(util.make_img_url_validator())] = Field(min_length=3)
    key_in_bug: str = Field(default='{}')
    # 自定义提单字段 {field_key: 选中的值}，会原样附加到缺陷系统的创建请求中
    custom_fields: Optional[Dict[str, str]] = Field(default=None, description="自定义字段 {field_key: value}")


class BugBatchCreateSchema(BaseModel):
    project_id: int = Field(gt=0)
    job_id: int = Field(gt=0)
    image_ids: List[int] = Field(min_length=1)
    bug_types: Annotated[List[int], AfterValidator(proj_svr.BugTypeValidator())]
    version_report: str = Field(default='', description="发现版本")
    version_fix: str = Field(default='',  description="修复版本")
    release_id: str = Field(default='',  description="发布计划")
    severity: BugSeverityEnum = Field(default=BugSeverityEnum.EMPTY)
    priority: BugPriorityEnum = Field(default=BugPriorityEnum.EMPTY)
    reporter: str = Field(default='')


class BugTrackerTestSchema(BaseModel):
    """测试缺陷系统连接（使用表单中尚未保存的配置）"""
    project_id: int = Field(gt=0)
    tracker_type: str = Field(default='none')
    base_url: str = Field(default='')
    username: str = Field(default='')
    api_key: str = Field(default='')
    product: str = Field(default='')
    component: str = Field(default='')
    extra: Annotated[dict, BeforeValidator(lambda v: orjson.loads(v) if isinstance(v, str) and v.strip() else (v or {}))] = Field(default_factory=dict)


class BugBatchUpdateSchema(BaseModel):
    bug_ids: List[int] = Field(min_length=1)
    regress_status: BugRegressStatusEnum = Field(validation_alias=AliasChoices('regress_status', 'status'))


class BugExportSchema(BaseModel):
    """导出当前任务下的缺陷单为 Excel"""
    job_id: int = Field(gt=0)
    image_id: int = Field(default=0, ge=0)

