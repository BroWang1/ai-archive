from typing import List, Optional
import datetime

from pydantic import BaseModel, Field, AliasPath
from libs.defs import ReviewedEnum


class DataListSchema(BaseModel):
    project_id: int
    id: int = Field(default=None, ge=0)
    pk__gte: int = Field(default=None, ge=0)
    pk__lte: int = Field(default=None, ge=0)
    job_id: int = Field(default=None, ge=0)
    name__contains: str = Field(default=None, alias='name')
    reviewed: ReviewedEnum = Field(default=None)
    resource_version: str = Field(default=None)
    module_id: int = Field(default=None)
    created_begin_at: datetime.datetime = Field(default=None, alias='begin_at')
    created_end_at: datetime.datetime = Field(default=None, alias='end_at')
    info_type: int = Field(default=0)  # 0:简略信息 1:详细信息
    cur_id: int = Field(default=None)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=2, le=100)


class DatasUpdateSchema(BaseModel):
    ids: List[int] = Field(min_length=1)
    resource_version: str = Field(default=None, min_length=2)
    module_id: int = Field(default=None)


class DatasDeleteSchema(BaseModel):
    ids: List[int] = Field(min_length=1)


class DataUpdateSchema(BaseModel):
    id: int = Field(gt=0)
    shot_img_path: str = Field(min_length=2, default=None)
    resource_version: str = Field(default=None)
    module_id: int = Field(default=None)


class ImageResCreateSchema(BaseModel):
    project_id: int
    name: str = Field(min_length=5)
    resource_version: str = Field(description="资源版本")
    resources_path: str = Field(default=None, description="资源路径")
    upload_data: bytes = Field(default=None, description="图片文件base64数据")
    # by_res_path: int = Field(default=0, description="是否通过资源路径处理, 0:否, 1:是")


class ImageResQuerySchema(BaseModel):
    project_id: int
    name: str
    resource_version: str