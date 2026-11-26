import logging

from django.db import transaction
from django.db.models import Q
from django.views.generic import View
from django.forms.models import model_to_dict
from django.utils.decorators import method_decorator
import orjson

from apps.project.models import *
from apps.project import service as proj_svr
from libs.util import choices_to_python
from libs.decorators import require_super_admin, require_project_perm, test_project_user_role_by_project_id
from libs import ApiResponse, PageView, lodash
from libs.defs import ApiErrorEnum, RoleEnum, QCC_PROJECT_ID
from .schemas import *

logger = logging.getLogger('proj_view')


def _project_dict(project):
    """项目信息序列化：游戏类型统一转成数组返回（多选）"""
    data_ = model_to_dict(project)
    data_['game_type'] = split_game_type(data_.get('game_type'))
    return data_


class ProjectView(View):
    def get(self, request):
        """获取项目信息"""
        project_id = int(request.GET.get('project_id', 0))
        if not project_id:
            return ApiResponse(ApiErrorEnum.ERROR_PARAM, msg='非法的project_id')
        project_info = Project.objects.filter(pk=project_id).values().first()
        if not project_info:
            return ApiResponse(ApiErrorEnum.NOT_EXIST)
        project_info['game_type'] = split_game_type(project_info.get('game_type'))
        return ApiResponse(data={'project': project_info})

    @method_decorator(require_super_admin)
    def post(self, request, *args, **kwargs):
        """创建项目"""
        vmi = ProjectSchema.model_validate(orjson.loads(request.body))

        if Project.objects.filter(code=vmi.code).exists():
            return ApiResponse(ApiErrorEnum.ERROR, msg=f'项目名"{vmi.code}"已存在，请换一个项目名')

        fields1 = ('name', 'label', 'value', 'enable', 'trans_marks')
        proj_cfg_bugtypes = list(ProjectConfigBugType.objects.filter(project_id=QCC_PROJECT_ID).values(*fields1))
        fields2 = ('name', 'label', 'custom_label', 'value', 'enable')
        proj_cfg_languages = list(ProjectConfigLanguage.objects.filter(project_id=QCC_PROJECT_ID).values(*fields2))
        proj_cfg_bugtypes_, proj_cfg_languages_ = [], []

        project = Project(**vmi.model_dump(exclude={'project_id'}, exclude_unset=True))
        with transaction.atomic():
            project.save()
            # 初始化项目配置
            for proj_cfg_bugtype in proj_cfg_bugtypes:
                proj_cfg_bugtype['project_id'] = project.id
                proj_cfg_bugtype['trans_marks'] = '[]'
                proj_cfg_bugtypes_.append(ProjectConfigBugType(**proj_cfg_bugtype))
            for proj_cfg_language in proj_cfg_languages:
                proj_cfg_language['project_id'] = project.id
                proj_cfg_languages_.append(ProjectConfigLanguage(**proj_cfg_language))
            ProjectConfigBugType.objects.bulk_create(proj_cfg_bugtypes_)
            ProjectConfigLanguage.objects.bulk_create(proj_cfg_languages_)
            ProjectConfigOther.objects.get_or_create(project_id=project.id)
            ProjectConfigBugTracker.objects.get_or_create(project_id=project.id)
            ProjectConfigBugBillMethod.objects.get_or_create(project_id=project.id)
        logger.info(f'[event.project.add] user:{request.user["name"]} id:{project.id}')
        return ApiResponse(data={'project': _project_dict(project)})

    @method_decorator(require_super_admin)
    def patch(self, request, *args, **kwargs):
        """修改项目信息"""
        vmi = ProjectSchema.model_validate(orjson.loads(request.body))

        project_id = vmi.project_id
        project = Project.objects.filter(pk=project_id).first()
        if not project:
            return ApiResponse(ApiErrorEnum.NOT_EXIST)

        mapping = vmi.model_dump(exclude={'project_id', 'code'}, exclude_unset=True)
        for k, v in mapping.items():
            setattr(project, k, v)
        project.save(update_fields=list(mapping.keys()))

        logger.info(f'[event.project.update] user:{request.user["name"]} body:{orjson.dumps(mapping).decode()}')
        return ApiResponse(data={'project': _project_dict(project)})


class ProjectListView(PageView):
    Query_Fields = ('cur_id', 'team__icontains', 'name__icontains', 'project_type',
                    'project_phase')

    def get(self, request):
        """查询项目列表"""
        vmi = ProjectListSchema.model_validate(request.GET.dict())

        param = {}
        if vmi.project_id is not None and vmi.project_id > 0:
            param['id'] = vmi.project_id
        else:
            param = self.make_query_params(vmi)
            param['pk__gt'] = QCC_PROJECT_ID     # 不展示系统模板项目
            # 游戏类型多选：数据库里以逗号分隔存储（如 "1,3"），用正则精确匹配每个值，再 OR 合并
            if vmi.game_type:
                q_game = Q()
                for item in vmi.game_type.split(','):
                    item = item.strip()
                    if not item:
                        continue
                    # (^|,) 和 (,|$) 保证匹配的是完整值而不是子串，避免 "1" 命中 "10,20"
                    q_game |= Q(game_type__regex=rf'(^|,){item}(,|$)')
                if q_game.children:
                    # param 是 dict：合并时转成 Q(**param) & q_game
                    param = Q(**param) & q_game

        total, datas = self.page_query(Project, param, vmi.page, vmi.page_size)

        # 游戏类型以数组返回（多选），便于前端直接绑定多选组件
        for data_ in datas:
            data_['game_type'] = split_game_type(data_.get('game_type'))

        return ApiResponse(data={'list': datas, 'total': total, 'page': vmi.page, 'page_size': vmi.page_size})


class ProjectRolesView(View):
    def get(self, request):
        """获取项目角色信息"""
        project_id = int(request.GET.get('project_id', 0))
        qs = Project.objects.exclude(pk=QCC_PROJECT_ID) if project_id == 0 else Project.objects.filter(pk=project_id)
        project_infos = {p_['id']: p_ for p_ in qs.values('id', 'name')}
        data_list = []
        roles_arr = choices_to_python(RoleEnum)
        for project_id_, project_info in project_infos.items():
            children = list(map(lambda role: ({
                'label': role['label'],
                'value': f'{project_id_}_{role["value"]}',
                'cell_roles': f'{project_info["name"]}/{role["label"]}'
            }), roles_arr))
            data_list.append({
                'project_id': project_id_,
                'label': project_info['name'],
                'value': project_info['name'],
                'children': children
            })
        return ApiResponse(data={'list': data_list})


class ProjectConfigView(View):

    Project_Config_Schema_Map = {
        'BugType': ProjectConfigBugTypeSchema,
        'Language': ProjectConfigLanguageSchema,
        'ImgRevert': ProjectConfigImgRevertSchema,
        'BugBillMethod': ProjectConfigBugBillMethodSchema,
        'BugBillUser': ProjectConfigBugBillUserSchema,
        'Other': ProjectConfigOtherSchema,
        'BugTracker': ProjectConfigBugTrackerSchema,
        'CustomField': ProjectConfigCustomFieldSchema,
    }

    # 返回给前端时需要隐藏的敏感字段 {cate: (fields)}
    Secret_Fields = {'BugTracker': ('api_key',)}
    SECRET_MASK = '******'

    def get(self, request):
        project_id = int(request.GET.get('project_id', 0))
        cate = request.GET.get('cate', '').strip()
        is_editor = int(request.GET.get('editor', 0))

        model = proj_svr.Project_Config_Model_Map.get(cate, None)
        if not model:
            return ApiResponse(ApiErrorEnum.NOT_EXIST, msg=f'非法的cate:{cate}')
        # 系统模板(project_id=0)的语言/缺陷类型对所有登录用户可读，其它项目配置需要项目成员权限
        if project_id != QCC_PROJECT_ID and not test_project_user_role_by_project_id(request.user, project_id):
            return ApiResponse(ApiErrorEnum.ERROR_PERMISSION, msg='没有该项目的权限')

        if cate == 'ImgRevert' and is_editor:   # 编辑器 获取还原配置
            return self.get_img_revert_cfg_by_editor(request, project_id)

        datas = list(model.objects.filter(project_id=project_id).order_by('-pk').values())
        if cate == 'ImgRevert':
            for data in datas:
                data['lang_path'] = orjson.loads(data['lang_path'])
        if cate == 'BugType':
            datas = sorted(datas, key=lambda obj_: obj_['value'])
        for field in self.Secret_Fields.get(cate, ()):
            for data in datas:
                data[field] = self.SECRET_MASK if data.get(field) else ''
        return ApiResponse(data={'list': datas})

    def get_img_revert_cfg_by_editor(self, request, project_id):
        """编辑器 获取还原配置
        # class ImageRSBase(BaseModel):
        #     项目图像还原配置信息
        #     id: int = Field(Required, description="项目id")
        #     name: str = Field(Required, description="项目名", alias="project_name")
        #     root_path: str = Field(None, description="根文件夹路径")
        #     text: str = Field(None, description="描述文本的标题")
        #     key: str = Field(None, description="唯一id名称")
        #     DN_translation: str = Field(None, description="不需要翻译的标识标题")
        #     unity_path: str = Field(None, description="不需要翻译的标识标题")
        """
        project = Project.objects.filter(pk=project_id).values().first()
        if not project:
            return ApiResponse(ApiErrorEnum.ERROR, msg='项目信息不存在')
        img_revert_cfg = proj_svr.ProjCfgService.get_img_revert(project_id).first()
        if not img_revert_cfg:
            return ApiResponse(ApiErrorEnum.ERROR, msg='图片还原配置不存在，请先配置再使用')
        runner_cfg = proj_svr.ProjCfgService.get_runner(project_id, validate=False) or {}
        data = {
            'project_id': project['id'],
            'name': project['code'],
            'text': img_revert_cfg['text'],
            'key': img_revert_cfg['key'],
            'root_path': img_revert_cfg['root_path'],
            'DN_translation': img_revert_cfg['no_trans_text'],
            'unity_path': runner_cfg.get('editor_path', ''),
        }
        for row in orjson.loads(img_revert_cfg['lang_path']):
            data[row['code_raw']] = row
        return ApiResponse(data=data)

    def _check_param(self, request):
        cate = request.GET.get('cate', '').strip()
        schema = self.Project_Config_Schema_Map.get(cate, None)
        model = proj_svr.Project_Config_Model_Map.get(cate, None)
        if not (schema and model):
            return ApiResponse(ApiErrorEnum.NOT_EXIST, msg=f'非法的cate:{cate}'), None, None
        vmi = schema.model_validate(getattr(request, 'body_json', None) or orjson.loads(request.body))
        return None, vmi, model

    def _drop_masked_secrets(self, cate, param):
        """前端回传的掩码表示“未修改”，不覆盖数据库中的密钥"""
        for field in self.Secret_Fields.get(cate, ()):
            if param.get(field) == self.SECRET_MASK:
                del param[field]
        return param

    @method_decorator(require_project_perm(RoleEnum.ADMIN))
    def post(self, request):
        response, vmi, model = self._check_param(request)
        if response:
            return response
        cate = request.GET.get('cate', '').strip()
        param = self._drop_masked_secrets(cate, vmi.model_dump(exclude_unset=True, exclude={'id'}))
        if model in proj_svr.Project_Single_Config_Models:
            obj, created = model.objects.get_or_create(project_id=param['project_id'], defaults=param)
            if not created:
                model.update_db(obj.id, mapping=lodash.omit(param, ('project_id',), False))
        else:
            obj = model.objects.create(**param)
        # 返回新建/更新后的完整对象（含 id），便于前端把草稿行转为已持久化状态，避免因全量刷新丢失其他草稿
        config = model.objects.filter(pk=obj.id).values().first()
        for field in self.Secret_Fields.get(cate, ()):
            if config:
                config[field] = self.SECRET_MASK if config.get(field) else ''
        return ApiResponse(msg='创建成功', data={'config': config})

    @method_decorator(require_project_perm(RoleEnum.ADMIN))
    def patch(self, request):
        response, vmi, model = self._check_param(request)
        if response:
            return response
        cate = request.GET.get('cate', '').strip()
        pk = vmi.id
        param = self._drop_masked_secrets(cate, vmi.model_dump(exclude_unset=True, exclude={'id', 'project_id'}))
        # 单条配置用 project_id 定位
        if model in proj_svr.Project_Single_Config_Models:
            obj, _ = model.objects.get_or_create(project_id=vmi.project_id)
            pk = obj.id
        elif not model.objects.filter(pk=pk, project_id=vmi.project_id).exists():
            return ApiResponse(ApiErrorEnum.NOT_EXIST, msg=f'配置不存在 id:{pk}')
        model.update_db(pk, mapping=param)
        config = model.objects.filter(pk=pk).values().first()
        for field in self.Secret_Fields.get(cate, ()):
            config[field] = self.SECRET_MASK if config.get(field) else ''
        return ApiResponse(msg='更新成功', data={'config': config})

    @method_decorator(require_project_perm(RoleEnum.ADMIN))
    def delete(self, request):
        cate = request.GET.get('cate', '').strip()
        model = proj_svr.Project_Config_Model_Map.get(cate, None)
        if not model:
            return ApiResponse(ApiErrorEnum.NOT_EXIST, msg=f'非法的cate:{cate}')
        vmi = ProjectConfigDelSchema.model_validate(getattr(request, 'body_json', None) or orjson.loads(request.body))
        model.objects.filter(pk__in=vmi.ids, project_id=vmi.project_id).delete()
        return ApiResponse(msg='删除成功')


class ProjectModuleView(View):
    @method_decorator(require_project_perm())
    def post(self, request):
        """创建项目模块"""
        vmi = ProjectModuleCreateSchema.model_validate(getattr(request, 'body_json', None) or orjson.loads(request.body))
        obj_dict = vmi.model_dump(exclude={'id'}, exclude_unset=True)
        module = Module(**obj_dict)
        module.save()
        logger.info(f'[event.project_module.add] user:{request.user["name"]} module_id:{module.id}')
        return ApiResponse(data={'module': model_to_dict(module)})

    @method_decorator(require_project_perm())
    def patch(self, request, *args, **kwargs):
        """修改项目模块"""
        vmi = ProjectModuleCreateSchema.model_validate(getattr(request, 'body_json', None) or orjson.loads(request.body))
        obj_dict = vmi.model_dump(exclude={'id', 'project_id'}, exclude_unset=True)
        if len(obj_dict) == 0:
            return ApiResponse(ApiErrorEnum.ERROR, msg='无有效参数')

        module_id = vmi.id
        module = Module.objects.filter(pk=module_id).first()
        if not module:
            return ApiResponse(ApiErrorEnum.NOT_EXIST)
        for k, v in obj_dict.items():
            setattr(module, k, v)
        module.save()
        logger.info(f'[event.project_module.update] user:{request.user["name"]} body:{orjson.dumps(vmi.model_dump()).decode()}')
        return ApiResponse(data={'module': model_to_dict(module)})

    @method_decorator(require_project_perm())
    def delete(self, request, *args, **kwargs):
        """删除模块"""
        body = getattr(request, 'body_json', None) or orjson.loads(request.body)
        module_id = int(body.get('module_id', 0))
        project_id = int(body.get('project_id', 0))
        mapping = {'id': module_id, 'project_id': project_id, 'is_delete': 1}
        num = Module.update_db(module_id, mapping)
        logger.info(f'[event.project_module.del] user:{request.user["name"]} module_id:{module_id}')
        return ApiResponse(data={'num': num})


class ProjectModuleListView(PageView):
    Query_Fields = ('project_id', 'cur_id', 'name__icontains', 'show_name__icontains')

    def get(self, request):
        """获取模块列表"""
        vmi = ProjectModuleListSchema.model_validate(request.GET.dict())
        project_id, page, page_size = vmi.project_id, vmi.page, vmi.page_size

        if vmi.all:  # 返回所有模块
            modules_dict = {o_['id']: o_ for o_ in Module.objects.filter(project_id=project_id).values()}
            modules = sorted(modules_dict.values(), key=lambda obj: obj['id'], reverse=True)
            return ApiResponse(
                data={'modules': modules, 'total': len(modules), 'page': page, 'page_size': page_size})
        #  分页查询
        param = self.make_query_params(vmi)
        total, datas = self.page_query(Module, param,  page, page_size)
        return ApiResponse(data={'list': datas, 'total': total, 'page': page, 'page_size': page_size})
