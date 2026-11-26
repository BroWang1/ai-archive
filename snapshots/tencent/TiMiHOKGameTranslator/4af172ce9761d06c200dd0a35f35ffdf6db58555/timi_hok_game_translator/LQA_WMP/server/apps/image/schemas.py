from typing import List, Annotated, Literal
import datetime

from pydantic import BaseModel, Field, field_validator, BeforeValidator, AfterValidator, AliasChoices

from libs import defs, lodash, util
from apps.project import service as proj_svr


class ImageListSchema(BaseModel):
    job_id: int = Field(default=None, gt=0)
    id: int = Field(default=None, gt=0)
    pk__gte: int = Field(default=None, ge=0)
    pk__lte: int = Field(default=None, ge=0)
    data_id: int = Field(default=None, gt=0)
    module_ids: Annotated[List[int], BeforeValidator(util.make_item_array_validator())] = Field(default=None, min_length=1)
    file_name__contains: str = Field(default=None, alias='file_name')
    err_type: int = Field(default=None)
    will_review: int = Field(default=None)
    languages: Annotated[List[int], BeforeValidator(util.make_item_array_validator())] = Field(default=None, min_length=1)
    is_latest: int = Field(default=1)
    ai_bug_types: Annotated[List[int], BeforeValidator(util.make_item_array_validator()), AfterValidator(proj_svr.BugTypeValidator())] = Field(default=None, alias='ai_bug_types')
    reviewed: int = Field(default=None)
    rect_location__contains: str = Field(default=None, min_length=1, alias='rect_location')
    info_type: int = Field(default=0)  # 0:简略信息 1:详细信息
    created_begin_at: datetime.datetime = Field(default=None)
    created_end_at: datetime.datetime = Field(default=None)
    updated_begin_at: datetime.datetime = Field(default=None)
    updated_end_at: datetime.datetime = Field(default=None)
    cur_id: int = Field(default=None)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=2, le=100)


    # @field_validator('languages', mode='before')  # 指定解析的模型属性
    # @classmethod
    # def valid_languages(cls, v: str):  # 通过自定义类方法解析获取模型属性
    #     if v.strip() == '':
    #         return []
    #     return lodash.split(v, func=lambda i: int(i))

class ImageListUpdateSchema(BaseModel):
    ids: List[int] = Field(min_length=1)
    reviewed: Literal[0, 1]

class ImageCreateSchema(BaseModel):
    project_id: int
    job_id: int
    data_id: int
    language: Annotated[int, BeforeValidator(proj_svr.LanguageValidator())]    # 创建时验证语言有效性
    rect_locations: str
    ai_sign: defs.SwitchEnum = Field(default=defs.SwitchEnum.OFF)
    regression: defs.JobRegressionEnum = Field(default=defs.JobRegressionEnum.NORMAL)
    bug_ids: Annotated[List[int], BeforeValidator(util.make_item_array_validator())] = Field(default=[])
    # 识别后是否自动提单（兼容旧版编辑器插件的参数名 create_bug_tapd）
    create_bug: defs.SwitchEnum = Field(default=defs.SwitchEnum.OFF,
                                        validation_alias=AliasChoices('create_bug', 'create_bug_tapd'))
    discern: defs.JobDiscernEnum = Field(default=defs.JobDiscernEnum.FULL)


class ImageAiSignRequestSchema(BaseModel):
    image_id: int = Field(default=None)
    job_id: int = Field(default=None)
    languages: Annotated[List[int], BeforeValidator(proj_svr.LanguageValidator())] = Field(default=None)
    discern: defs.JobDiscernEnum = Field(default=defs.JobDiscernEnum.FULL)


class DataReviewPatchSchema(BaseModel):
    id: int = Field(default=None, description="DataReview id")
    check_rect_location: str = Field('{}', description="审核后的文本框,图像框集合 json")
    dirty_rect_location: str = Field('{}', description="删除的文本框,图像框集合 json")