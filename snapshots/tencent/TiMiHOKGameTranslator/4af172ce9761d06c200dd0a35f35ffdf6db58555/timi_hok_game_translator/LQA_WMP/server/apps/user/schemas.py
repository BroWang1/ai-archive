import re
from typing import List, Annotated

from pydantic import BaseModel, Field, BeforeValidator, AfterValidator

from libs.defs import SwitchEnum, RoleEnum, UserStatusEnum

USERNAME_PATTERN = r'^[A-Za-z][A-Za-z0-9_.\-]{2,31}$'
USERNAME_HELP = '用户名需以字母开头，3~32位，只能包含字母、数字、下划线、点、中划线'


def validate_password(v: str) -> str:
    if not (8 <= len(v) <= 64):
        raise ValueError('密码长度需为 8~64 位')
    if not (re.search(r'[A-Za-z]', v) and re.search(r'\d', v)):
        raise ValueError('密码需同时包含字母和数字')
    return v


Password = Annotated[str, AfterValidator(validate_password)]
Username = Annotated[str, BeforeValidator(lambda v: v.strip() if isinstance(v, str) else v),
                     Field(pattern=USERNAME_PATTERN, description=USERNAME_HELP)]


class UserListSchema(BaseModel):
    name__icontains: str = Field(default="", alias="name")
    name_zh__icontains: str = Field(default="", alias="name_zh")
    department__icontains: str = Field(default="", alias="department")
    status: UserStatusEnum = Field(default=None)
    project_id: int = Field(default=None)
    is_admin: SwitchEnum = Field(default=None)
    info_type: int = Field(default=0)   # 0:用户简略信息; 1:用户详细信息; 2:用户详细信息（带项目角色信息）
    cur_id: int = Field(default=None)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=2)


def make_project_roles_validator():
    def validator(project_roles, info):
        if project_roles is None:
            return project_roles
        arr = []
        for project_role in project_roles:
            project_id, role = project_role.split('_')
            arr.append((int(project_id), int(role)))
        return arr
    return validator


class LoginSchema(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=128)


class RegisterSchema(BaseModel):
    username: Username
    password: Password
    name_zh: str = Field(default='', max_length=100)
    email: str = Field(default='', max_length=128, pattern=r'^([^@\s]+@[^@\s]+\.[^@\s]+)?$')


class PasswordChangeSchema(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: Password


class PasswordResetSchema(BaseModel):
    id: int = Field(gt=0)
    new_password: Password


class UserCreateSchema(BaseModel):
    name: Username
    # 管理员添加用户时允许不传密码；view 层会使用系统默认密码（见 DEFAULT_NEW_USER_PASSWORD）
    password: Password = None
    name_zh: str = Field(default='', max_length=100)
    email: str = Field(default='', max_length=128, pattern=r'^([^@\s]+@[^@\s]+\.[^@\s]+)?$')
    department: str = Field(default='', max_length=100)
    project_id: int = Field(default=None)  # 非super admin需要，要不然可能越权操作其他项目
    roles: Annotated[List[tuple[int, RoleEnum]], BeforeValidator(make_project_roles_validator())] = Field(default_factory=list)


class UserPatchSchema(BaseModel):
    id: int
    is_admin: SwitchEnum = Field(default=None)
    status: UserStatusEnum = Field(default=None)
    name_zh: str = Field(default=None, max_length=100)
    email: str = Field(default=None, max_length=128, pattern=r'^([^@\s]+@[^@\s]+\.[^@\s]+)?$')
    department: str = Field(default=None, max_length=100)
    project_id: int = Field(default=None)  # 非super admin需要，要不然可能越权操作其他项目
    roles: Annotated[List[tuple[int, RoleEnum]], BeforeValidator(make_project_roles_validator())] = Field(default=None)


class ProfilePatchSchema(BaseModel):
    """用户修改自己的资料"""
    name_zh: str = Field(default=None, max_length=100)
    email: str = Field(default=None, max_length=128, pattern=r'^([^@\s]+@[^@\s]+\.[^@\s]+)?$')
    department: str = Field(default=None, max_length=100)
