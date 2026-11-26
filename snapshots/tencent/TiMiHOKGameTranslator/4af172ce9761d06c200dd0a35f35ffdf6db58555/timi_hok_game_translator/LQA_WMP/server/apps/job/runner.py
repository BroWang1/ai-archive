"""
还原任务执行：前端调用 Webhook 触发外部执行器（Jenkins / GitLab CI / 自建服务等）

流程:
  1. 前端点击“开始/重试” -> POST /api/job/action {action: start|retry}
     后端校验任务状态，按项目配置渲染出 Webhook 请求（url/method/headers/body）返回给前端
  2. 前端浏览器直接请求 Webhook（目标服务需允许 LQA 域名跨域）
  3. 请求成功后前端 -> POST /api/job/action {action: started, regression, build_id}
     后端把任务置为“执行中”
  4. 执行器（Unity 编辑器等）按原有接口拉取数据、上传截图：
     GET /api/job/datas、POST /api/image/entity、POST /api/job/device

模板变量: url / headers / body 中可以使用 {{变量名}}，见 runner_variables()
  body 中某个字符串值恰好等于 "{{变量名}}" 时，替换为变量的原始类型（数字/数组）
"""
import re
from urllib.parse import quote

import orjson

import settings
from apps.project import service as proj_svr
from apps.project.models import Project
from libs import defs

_VAR_PATTERN = re.compile(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}')

# 平台标准 code -> UE 还原插件 code 的反向映射
# 平台内部统一使用 ISO 国家码（如 LAN_KO_KR）, 但 UE 还原插件 ConfigManager.cpp
# 的 LanguageMap 认的是另一套命名（如 LAN_KO_KO）。
# 触发 Webhook 直接把平台 code 拼到 UE 命令行 -Language= 参数时, 需要先翻译一次。
# 该映射由 LanguageValidator._UE_LANGUAGE_CODE_ALIASES 反转而来, 两边保持同步。
_WMP_TO_UE_LANGUAGE_CODE = {
    v: k for k, v in proj_svr.LanguageValidator._UE_LANGUAGE_CODE_ALIASES.items()
}


class RunnerConfigError(Exception):
    pass


def _to_ue_lang(code):
    """平台 code -> UE 还原插件 code; 不在映射表的保持原值"""
    return _WMP_TO_UE_LANGUAGE_CODE.get(code, code)


def runner_variables(job, regression, runner_cfg) -> dict:
    """可在 Webhook 模板中使用的变量"""
    project = Project.objects.filter(pk=job.project_id).values('id', 'code', 'name').first() or {}
    img_revert_cfg = list(proj_svr.ProjCfgService.get_img_revert(job.project_id))
    language_path = img_revert_cfg[0].get('root_path', '') if img_revert_cfg else ''
    sys_languages = proj_svr.ProjCfgService.get_sys_language(True)
    language_names = [sys_languages[lan]['name'] for lan in job.languages if lan in sys_languages]
    create_bug = 1 if job.bill_bug_types and regression != defs.JobRegressionEnum.REGRESSION else 0
    # job.languages 存的是语言数字 ID (如 [6, 3, 2]), sys_languages[id]['name'] 是平台标准 code (如 'LAN_KO_KR'),
    # 再经 _to_ue_lang 反向翻译为 UE 还原插件认识的 code (如 'LAN_KO_KO')
    ue_language_values = [_to_ue_lang(name) for name in language_names]
    return {
        'job_id': job.id,
        'job_name': job.name,
        'parent_job_id': job.parent_id,
        'project_id': job.project_id,
        'project_code': project.get('code', ''),
        'project_name': project.get('name', ''),
        'languages': ','.join(language_names),
        'language_values': list(job.languages),
        # UE 还原插件专用的语言编码（已按 LanguageValidator._UE_LANGUAGE_CODE_ALIASES 反向翻译）
        # Webhook 直接拉起 UE 时, 命令行 -Language= 必须用这个值, 否则插件 ConfigManager 无法识别。
        'ue_language_values': ue_language_values,
        'ue_languages': ','.join(ue_language_values),
        'regression': int(regression),
        'discern': int(job.discern),
        'create_bug': create_bug,
        'svn_url': job.svn_url,
        'svn_version': job.svn_version,
        'language_path': language_path,
        'editor_path': runner_cfg.get('editor_path', ''),
        'editor_version': runner_cfg.get('editor_version', ''),
        'lqa_server': (getattr(settings, 'PUBLIC_URL', '') or '').rstrip('/'),
    }


def _render_str(text, variables, url_encode=False):
    def _sub(m):
        key = m.group(1)
        if key not in variables:
            return m.group(0)
        val = variables[key]
        val = ','.join(map(str, val)) if isinstance(val, (list, tuple)) else str(val)
        return quote(val, safe='') if url_encode else val
    return _VAR_PATTERN.sub(_sub, text)


def _render_obj(obj, variables):
    if isinstance(obj, dict):
        return {k: _render_obj(v, variables) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_render_obj(v, variables) for v in obj]
    if isinstance(obj, str):
        m = _VAR_PATTERN.fullmatch(obj.strip())
        if m and m.group(1) in variables:
            return variables[m.group(1)]
        return _render_str(obj, variables)
    return obj


def build_trigger(job, regression) -> dict:
    """渲染 Webhook 请求，供前端直接发起"""
    runner_cfg = proj_svr.ProjCfgService.get_runner(job.project_id)
    if not runner_cfg:
        raise RunnerConfigError('请先在“项目设置 > 基础配置 > 还原执行”中配置 Webhook 地址')
    variables = runner_variables(job, regression, runner_cfg)

    try:
        headers = orjson.loads(runner_cfg['webhook_headers'] or '{}')
    except orjson.JSONDecodeError:
        raise RunnerConfigError('Webhook 请求头不是合法的 JSON')
    headers = {str(k): _render_str(str(v), variables) for k, v in headers.items()}

    method = (runner_cfg['webhook_method'] or 'POST').upper()
    body = None
    if method != 'GET':
        tpl = (runner_cfg['webhook_body'] or '').strip()
        try:
            body = _render_obj(orjson.loads(tpl), variables) if tpl else variables
        except orjson.JSONDecodeError:
            raise RunnerConfigError('Webhook 请求体模板不是合法的 JSON')
        headers.setdefault('Content-Type', 'application/json')

    return {
        'url': _render_str(runner_cfg['webhook_url'].strip(), variables, url_encode=True),
        'method': method,
        'headers': headers,
        'body': body,
        'variables': variables,
    }
