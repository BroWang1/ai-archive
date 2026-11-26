<!--
 * @Description: 项目配置 - 缺陷系统（平台内记录 / Bugzilla / 禅道）
-->
<template>
  <div class="app-container !pt-4.25 bg-white" v-loading="loading">
    <el-form ref="formRef" :model="form" :rules="rules" label-width="120px" style="max-width: 820px">
      <el-form-item label="缺陷系统" prop="tracker_type">
        <el-radio-group v-model="form.tracker_type">
          <el-radio-button value="none">平台内记录</el-radio-button>
          <el-radio-button value="bugzilla">Bugzilla</el-radio-button>
          <el-radio-button value="zentao">禅道</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-alert v-if="form.tracker_type === 'none'" type="info" :closable="false" show-icon class="mb-4"
                title="缺陷只保存在本平台，回归验证时由平台自动关闭/重新打开，不对接外部系统。" />

      <template v-else>
        <el-form-item label="系统地址" prop="base_url">
          <el-input v-model.trim="form.base_url"
                    :placeholder="isBugzilla ? '如 https://bugzilla.example.com' : '如 https://zentao.example.com（不含 /api.php）'" />
        </el-form-item>
        <el-form-item v-if="!isBugzilla" label="账号" prop="username">
          <el-input v-model.trim="form.username" placeholder="用于调用禅道 API 的账号，需要有提 Bug 权限" />
        </el-form-item>
        <el-form-item :label="isBugzilla ? 'API Key' : '密码'" prop="api_key">
          <el-input v-model="form.api_key" type="password" show-password autocomplete="new-password"
                    :placeholder="isBugzilla ? 'Bugzilla 用户偏好设置 > API Keys 中生成' : '禅道账号密码'" />
          <div class="form-tip">已保存的密钥显示为 ******，不修改则保持原值</div>
        </el-form-item>
        <el-form-item :label="isBugzilla ? '产品名称' : '产品ID'" prop="product">
          <el-input v-model.trim="form.product"
                    :placeholder="isBugzilla ? 'Bugzilla 中的 Product 名称' : '禅道产品 ID（数字），在产品页 URL 中可以看到'" />
        </el-form-item>
        <el-form-item v-if="isBugzilla" label="组件" prop="component">
          <el-input v-model.trim="form.component" placeholder="Bugzilla 中的 Component 名称" />
        </el-form-item>
        <el-form-item label="高级配置(JSON)" prop="extraText">
          <el-input v-model="form.extraText" type="textarea" :rows="4" class="mono" :placeholder="extraPlaceholder" />
          <div class="form-tip">{{ extraTip }}</div>
        </el-form-item>
      </template>

      <el-form-item>
        <el-button @click="getData">重置</el-button>
        <el-button v-if="form.tracker_type !== 'none'" :loading="testing" @click="testConnection">测试连接</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { useRoute } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { customRequest } from '@/utils/service';

const route = useRoute();
const formRef = ref();
const loading = ref(false);
const saving = ref(false);
const testing = ref(false);
const form = reactive({
  tracker_type: 'none',
  base_url: '',
  username: '',
  api_key: '',
  product: '',
  component: '',
  extraText: '',
});
const isBugzilla = computed(() => form.tracker_type === 'bugzilla');
const extraPlaceholder = computed(() => (isBugzilla.value
  ? '{"assignee_field": "email", "reopen_status": "CONFIRMED", "default_version": "unspecified"}'
  : '{"project_id": 5, "bug_type": "others"}'));
const extraTip = computed(() => (isBugzilla.value
  ? 'assignee_field：指派人取用户的 email（默认）或 name；reopen_status：回归不通过时重新打开的状态；default_version：未选择发现版本时使用的版本'
  : 'project_id：禅道项目/执行 ID，用于拉取版本(Build)列表；bug_type：缺陷类型，默认 others'));

const required = msg => ({
  validator: (_r, v, cb) => (form.tracker_type === 'none' || (v && String(v).trim()) ? cb() : cb(new Error(msg))),
  trigger: 'blur',
});
const rules = {
  base_url: [required('请填写系统地址'), { pattern: /^https?:\/\/.+/, message: '请填写 http(s):// 开头的地址', trigger: 'blur' }],
  username: [{
    validator: (_r, v, cb) => (form.tracker_type !== 'zentao' || v ? cb() : cb(new Error('请填写账号'))), trigger: 'blur',
  }],
  api_key: [required('请填写 API Key / 密码')],
  product: [required('请填写产品')],
  extraText: [{
    validator: (_r, v, cb) => {
      if (!v || !v.trim()) return cb();
      try {
        const o = JSON.parse(v);
        return o && typeof o === 'object' && !Array.isArray(o) ? cb() : cb(new Error('必须是 JSON 对象'));
      } catch {
        return cb(new Error('不是合法的 JSON'));
      }
    },
    trigger: 'blur',
  }],
};

const payload = () => {
  const { extraText, ...rest } = form;
  return { ...rest, extra: extraText && extraText.trim() ? JSON.parse(extraText) : {}, project_id: route.meta.value };
};

const getData = async () => {
  loading.value = true;
  try {
    const res = await customRequest({
      url: '/api/project/config',
      method: 'get',
      params: { project_id: route.meta.value, cate: 'BugTracker' },
    });
    const cfg = res.data.list[0] || {};
    form.tracker_type = cfg.tracker_type || 'none';
    ['base_url', 'username', 'api_key', 'product', 'component'].forEach((k) => {
      form[k] = cfg[k] || '';
    });
    form.extraText = cfg.extra && Object.keys(cfg.extra).length ? JSON.stringify(cfg.extra, null, 2) : '';
    formRef.value?.clearValidate();
  } finally {
    loading.value = false;
  }
};

const testConnection = () => {
  formRef.value.validate(async (valid) => {
    if (!valid) return;
    testing.value = true;
    try {
      const res = await customRequest({ url: '/api/bug/tracker_test', method: 'post', data: payload(), silent: true });
      ElMessage.success(res.msg || '连接成功');
    } catch (err) {
      const raw = err?.response?.data?.msg || err.message || '未知错误';
      // 后端错误信息可能包含换行和编号列表(如 1)/2)/3))，这里用 <pre> 原样保留换行；
      // 内容来源不受信，所以先做 HTML 转义再塞进 message
      const escaped = String(raw)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
      ElMessageBox.alert(
        `<pre style="margin:0;white-space:pre-wrap;word-break:break-word;font-family:inherit;font-size:13px;line-height:1.6;">${escaped}</pre>`,
        '连接失败',
        { type: 'error', dangerouslyUseHTMLString: true, customClass: 'tracker-test-error' },
      );
    } finally {
      testing.value = false;
    }
  });
};

const submit = () => {
  formRef.value.validate(async (valid) => {
    if (!valid) return;
    saving.value = true;
    try {
      await customRequest({ url: '/api/project/config?cate=BugTracker', method: 'patch', data: payload() });
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
.form-tip {
  width: 100%;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
  // 避免双击 / 快速连点 el-input 右侧"显示密码"眼睛图标时，相邻的提示文字被浏览器
  // 默认行为选中成一片蓝底；提示本身是帮助文案，不需要被选中复制。
  user-select: none;
}
:deep(.mono textarea) {
  font-family: Consolas, Menlo, monospace;
}
</style>
