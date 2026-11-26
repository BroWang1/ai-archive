from typing import List, Optional, Annotated, Literal
import datetime

from pydantic import BaseModel, Field, BeforeValidator

from libs import defs, util
from apps.project import service as proj_svr


class JobListSchema(BaseModel):
    project_id: int
    id: int = Field(default=None, ge=0)
    name__icontains: str = Field(default=None, alias='name')
    module_id: int = Field(default=None)
    language: Annotated[int, BeforeValidator(proj_svr.LanguageValidator())] = Field(default=None)
    status: defs.JobStatusEnum = Field(default=None)
    is_parent: int = Field(default=None)
    creator_id: int = Field(default=None)
    created_begin_at: datetime.datetime = Field(default=None, alias='begin_at')
    created_end_at: datetime.datetime = Field(default=None, alias='end_at')
    children: int = Field(default=0)    # 是否查询子任务
    info_type: int = Field(default=0)  # 0:简略信息 1:详细信息
    cur_id: int = Field(default=None)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=2, le=100)


class JobSchema(BaseModel):
    id: int = Field(default=None)
    project_id: int
    discern: defs.JobDiscernEnum
    ocr_detect: defs.SwitchEnum = Field(default=defs.SwitchEnum.OFF)
    name: str = Field(min_length=2)
    languages: Annotated[List[int], BeforeValidator(proj_svr.LanguageValidator())] = Field(min_length=1)
    plan_start_at: datetime.datetime
    plan_end_at: datetime.datetime
    data_ids: List[int] = Field(default_factory=list)
    sign_bug_types: Annotated[List[int], BeforeValidator(proj_svr.BugTypeValidator())] = Field(default=None)
    bill_bug_types: Annotated[List[int], BeforeValidator(proj_svr.BugTypeValidator())] = Field(default=None)
    priority: defs.BugPriorityEnum = Field(default=None)
    severity: defs.BugSeverityEnum = Field(default=None)
    version_report: str = Field(default=None)
    version_fix: str = Field(default=None)
    release_id: str = Field(default=None)
    svn_url: str = Field(default='')
    svn_version: str = Field(default='')


class JobExtraSchema(BaseModel):
    test_app_file_path: Annotated[str, BeforeValidator(lambda v: v or '')] = Field(default='')
    test_case_file_path: Annotated[str, BeforeValidator(lambda v: v or '')] = Field(default='')
    proj_res_type: defs.JobResTypeEnum = Field(default=defs.JobResTypeEnum.GIT)
    proj_res_repo: str = Field(default='')
    proj_res_br: str = Field(default='')
    proj_res_ver: str = Field(default='')
    proj_res_file_path: Annotated[str, BeforeValidator(lambda v: v or '')] = Field(default='')
    trans_res_type: defs.JobResTypeEnum = Field(default=defs.JobResTypeEnum.GIT)
    trans_res_repo: str = Field(default='')
    trans_res_br: str = Field(default='')
    trans_res_ver: str = Field(default='')
    trans_res_file_path: Annotated[str, BeforeValidator(lambda v: v or '')] = Field(default='')


class JobGetSchema(BaseModel):
    job_id: int = Field(gt=0)
    progress: defs.SwitchEnum = Field(default=defs.SwitchEnum.OFF)
    fields: Annotated[List[str], BeforeValidator(util.make_item_array_validator(item_class=str))] = Field(default_factory=lambda: [])
    mappings: Literal['0', '1'] = Field(default='0')


class JobBugRegressSchema(BaseModel):
    bug_ids: List[int] = Field(min_length=1)
    discern: defs.JobDiscernEnum


class JobDatasSchema(BaseModel):
    job_id: int
    regression: defs.JobRegressionEnum = Field(default=defs.JobRegressionEnum.NORMAL)
    language: Annotated[int, BeforeValidator(proj_svr.LanguageValidator())] = Field(default=None)
    count: int = Field(default=10, gt=0)    # 一次获取个数
    minID: int = Field(default=0, ge=0)     # 最小id
    module_ids: Annotated[List[int], BeforeValidator(util.make_item_array_validator())] = (
        Field(default_factory=lambda: [], min_length=1))
    iteration: int = Field(default=1, ge=0)     # 迭代次数
    use_cache: int = Field(default=1, ge=0)


class JobDeviceCreateSchema(BaseModel):
    job_id: int = Field(ge=1)
    execute_pc: str = Field(min_length=1)
    language: Annotated[int, BeforeValidator(proj_svr.LanguageValidator())] = Field(gt=0)
    status: str = Field(min_length=1)
    editor_nums: int = Field(ge=0)


class JobActionSchema(BaseModel):
    action: Literal['start', 'stop', 'retry', 'started']
    job_id: int = Field(gt=0)
    # 以下仅 action=started 时使用
    regression: defs.JobRegressionEnum = Field(default=defs.JobRegressionEnum.NORMAL)
    build_id: str = Field(default='', description='Webhook 返回的外部构建ID/链接')
