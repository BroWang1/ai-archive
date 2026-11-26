<!--
 * @Description: 项目配置 - 还原执行（Webhook）
 *   点击“开始任务”时，浏览器按此配置直接请求 Webhook（Jenkins / GitLab CI / 自建服务等）触发还原
-->
<template>
  <div class="app-container !pt-4.25 bg-white runner-config" v-loading="loading">
    <el-alert type="info" :closable="false" show-icon class="mb-4">
      <template #title>
        开始/重试任务时，由<b>浏览器</b>直接请求该 Webhook，目标服务需允许平台域名跨域（CORS）。
        地址、请求头、请求体中可使用 <code v-pre>{{变量名}}</code> 占位符；请求体中某个值恰好为
        <code v-pre>"{{变量名}}"</code> 时保留原始类型（数字/数组）。请求体留空时发送全部变量。
      </template>
    </el-alert>
    <el-form ref="formRef" :model="form" :rules="rules" label-width="110px" style="max-width: 900px">
      <el-form-item label="Webhook 地址" prop="webhook_url">
        <el-input v-model.trim="form.webhook_url"
                  placeholder="如 https://jenkins.example.com/job/lqa/buildWithParameters?token=xxx&JOB_ID={{job_id}}" />
      </el-form-item>
      <el-form-item label="请求方法" prop="webhook_method">
        <el-radio-group v-model="form.webhook_method">
          <el-radio-button value="POST">POST</el-radio-button>
          <el-radio-button value="PUT">PUT</el-radio-button>
          <el-radio-button value="GET">GET</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="请求头(JSON)" prop="webhook_headers">
        <el-input v-model="form.webhook_headers" type="textarea" :rows="3"
                  placeholder='{"Authorization": "Bearer xxx"}' class="mono" />
      </el-form-item>
      <el-form-item v-if="form.webhook_method !== 'GET'" label="请求体(JSON)" prop="webhook_body">
        <el-input v-model="form.webhook_body" type="textarea" :rows="6" class="mono"
                  placeholder='{"job_id": "{{job_id}}", "languages": "{{languages}}", "regression": "{{regression}}"}' />
      </el-form-item>
      <el-form-item label="编辑器路径" prop="editor_path">
        <el-input v-model.trim="form.editor_path" placeholder="还原端编辑器路径，编辑器拉取还原配置时返回，也可作为变量 {{editor_path}}" />
      </el-form-item>
      <el-form-item label="编辑器版本" prop="editor_version">
        <el-input v-model.trim="form.editor_version" placeholder="可作为变量 {{editor_version}}" />
      </el-form-item>
      <el-form-item>
        <el-button @click="getData">重置</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </el-form-item>
    </el-form>

    <el-divider content-position="left">可用变量</el-divider>
    <el-table :data="variables" size="small" border style="max-width: 900px">
      <el-table-column prop="name" label="变量" width="200">
        <template #default="{ row }"><code v-text="placeholder(row.name)" /></template>
      </el-table-column>
      <el-table-column prop="desc" label="说明" />
    </el-table>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue';
import { useRoute } from 'vue-router';
import { ElMessage } from 'element-plus';
import { customRequest } from '@/utils/service';

const route = useRoute();
const formRef = ref();
const loading = ref(false);
const saving = ref(false);
const form = reactive({
  webhook_url: '',
  webhook_method: 'POST',
  webhook_headers: '{}',
  webhook_body: '',
  editor_path: '',
  editor_version: '',
});

const jsonValidator = (allowEmpty, expectArray) => (_r, value, cb) => {
  if (!value || !value.trim()) return allowEmpty ? cb() : cb(new Error('请填写 JSON'));
  try {
    const v = JSON.parse(value);
    if (v === null || typeof v !== 'object' || (!expectArray && Array.isArray(v))) {
      return cb(new Error(expectArray ? '必须是 JSON 对象或数组' : '必须是 JSON 对象'));
    }
    return cb();
  } catch {
    return cb(new Error('不是合法的 JSON'));
  }
};
const rules = {
  webhook_url: [{ pattern: /^https?:\/\/.+/, message: '请填写 http(s):// 开头的地址', trigger: 'blur' }],
  webhook_headers: [{ validator: jsonValidator(true, false), trigger: 'blur' }],
  webhook_body: [{ validator: jsonValidator(true, true), trigger: 'blur' }],
};

const placeholder = name => `{{${name}}}`;
const variables = [
  { name: 'job_id', desc: '任务ID' },
  { name: 'job_name', desc: '任务名称' },
  { name: 'parent_job_id', desc: '父任务ID（回归任务时有值，否则为 0）' },
  { name: 'project_id', desc: '项目ID' },
  { name: 'project_code', desc: '项目代号' },
  { name: 'project_name', desc: '项目名称' },
  { name: 'languages', desc: '还原语言编码，逗号分隔，如 LAN_EN_US,LAN_JA_JP' },
  { name: 'language_values', desc: '还原语言值数组，如 [2, 6]' },
  { name: 'ue_languages', desc: 'UE 还原插件专用语言编码（逗号分隔），如 LAN_EU_EN,LAN_JP_JP；UE 命令行 -Language= 应传此值' },
  { name: 'ue_language_values', desc: 'UE 还原插件专用语言编码数组，如 ["LAN_EU_EN","LAN_JP_JP"]' },
  { name: 'regression', desc: '执行类型：0 普通 / 1 回归 / 2 重试' },
  { name: 'discern', desc: '识别方式：0 全量识别 / 1 差异识别' },
  { name: 'create_bug', desc: '识别后是否自动提单：0/1' },
  { name: 'svn_url', desc: '任务配置的资源仓库地址' },
  { name: 'svn_version', desc: '任务配置的资源版本' },
  { name: 'language_path', desc: '图片还原配置中的语言根目录' },
  { name: 'editor_path', desc: '编辑器路径（本页配置）' },
  { name: 'editor_version', desc: '编辑器版本（本页配置）' },
  { name: 'lqa_server', desc: '平台对外地址（后端 PUBLIC_URL）' },
];

const getData = async () => {
  loading.value = true;
  try {
    const res = await customRequest({
      url: '/api/project/config',
      method: 'get',
      params: { project_id: route.meta.value, cate: 'Other' },
    });
    const cfg = res.data.list[0] || {};
    Object.keys(form).forEach((k) => {
      if (cfg[k] !== undefined && cfg[k] !== null) form[k] = cfg[k];
    });
    formRef.value?.clearValidate();
  } finally {
    loading.value = false;
  }
};

const submit = () => {
  formRef.value.validate(async (valid) => {
    if (!valid) return;
    saving.value = true;
    try {
      await customRequest({
        url: '/api/project/config?cate=Other',
        method: 'patch',
        data: { ...form, project_id: route.meta.value },
      });
      ElMessage.success('已保存');
      await getData();
    } finally {
      saving.value = false;
    }
  });
};

onMounted(getData);
</script>

<style scoped lang="scss">
.runner-config {
  code {
    padding: 0 4px;
    border-radius: 3px;
    background: var(--el-fill-color-light);
  }
  :deep(.mono textarea) {
    font-family: Consolas, Menlo, monospace;
  }
}
</style>
