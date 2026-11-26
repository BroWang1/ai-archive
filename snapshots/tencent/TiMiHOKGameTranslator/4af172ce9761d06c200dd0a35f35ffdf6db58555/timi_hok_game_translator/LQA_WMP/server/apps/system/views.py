from django.views.generic import View

from libs.util import choices_to_python
from libs import ApiResponse, defs, lodash
from apps.project import service as proj_svr

class EnumsView(View):
    CATE_MAP = {
        'role': choices_to_python(defs.RoleEnum),
        'project_type': choices_to_python(defs.ProjectTypeEnum),
        'game_type': choices_to_python(defs.GameTypeEnum),
        'user_status': choices_to_python(defs.UserStatusEnum),
        'bug_tracker': choices_to_python(defs.BugTrackerTypeEnum),
        'project_phase': choices_to_python(defs.ProjectPhaseEnum),
        'job_status': choices_to_python(defs.JobStatusEnum),
        'bug_priority': choices_to_python(defs.BugPriorityEnum),
        'bug_severity': choices_to_python(defs.BugSeverityEnum),
        'bug_status': choices_to_python(defs.BugRegressStatusEnum)
    }

    Field1 = ('id', 'name', 'label', 'value', 'enable')
    Field2 = ('id', 'name', 'label', 'value', 'trans_marks')

    def get(self, request, cate):
        cate = cate.strip()
        if cate == 'language':
            arrs = [lodash.pick(obj, self.Field1) for obj in proj_svr.ProjCfgService.get_sys_language()]
        elif cate == 'bug_type':
            arrs = [lodash.pick(obj, self.Field2) for obj in proj_svr.ProjCfgService.get_sys_bugtype()]
            arrs = sorted(arrs, key=lambda obj_: obj_['value'])
        else:
            arrs = self.CATE_MAP.get(cate, None)
        if arrs is None:
            return ApiResponse(defs.ApiErrorEnum.NOT_EXIST)
        return ApiResponse(data={'list': arrs})
