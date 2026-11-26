<script lang="ts" setup>
import { reactive, ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, type FormInstance, type FormRules } from 'element-plus';
import { User, Lock, Message, Avatar } from '@element-plus/icons-vue';
import ThemeSwitch from '@/components/ThemeSwitch/index.vue';
import { useUserStore } from '@/store/modules/user';
import { customRequest } from '@/utils/service';
import { USERNAME_RULE, passwordRules } from './rules';

const router = useRouter();
const formRef = ref<FormInstance | null>(null);
const loading = ref(false);
const errorMsg = ref('');
const allowRegister = ref(true);
const form = reactive({
  username: '',
  name_zh: '',
  email: '',
  password: '',
  confirm: '',
});

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }, USERNAME_RULE],
  email: [{ type: 'email', message: '邮箱格式不正确', trigger: 'blur' }],
  password: passwordRules(),
  confirm: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_r, value, cb) => (value === form.password ? cb() : cb(new Error('两次输入的密码不一致'))),
      trigger: 'blur',
    },
  ],
};

onMounted(async () => {
  try {
    const res = await customRequest({ url: '/api/user/auth_config', method: 'get', silent: true });
    allowRegister.value = !!res.data.allow_register;
  } catch {
    allowRegister.value = false;
  }
});

const handleRegister = () => {
  formRef.value?.validate((valid: boolean) => {
    if (!valid) return;
    loading.value = true;
    errorMsg.value = '';
    useUserStore()
      .register({ username: form.username, password: form.password, name_zh: form.name_zh, email: form.email })
      .then(() => {
        ElMessage.success('注册成功，请登录。登录后需等待管理员为你分配项目权限');
        router.replace('/login');
      })
      .catch((err) => {
        errorMsg.value = err?.response?.data?.msg || err?.message || '注册失败';
      })
      .finally(() => {
        loading.value = false;
      });
  });
};
</script>

<template>
  <div class="register-container">
    <ThemeSwitch class="theme-switch" />
    <div class="register-card">
      <div class="title">
        <img src="@/assets/layouts/logo-text-2.png" />
      </div>
      <div class="content">
        <el-result v-if="!allowRegister" icon="info" title="系统未开放注册" sub-title="请联系管理员创建账号">
          <template #extra>
            <router-link to="/login"><el-button type="primary">返回登录</el-button></router-link>
          </template>
        </el-result>
        <el-form v-else ref="formRef" :model="form" :rules="rules" @keyup.enter="handleRegister">
          <el-form-item prop="username">
            <el-input v-model.trim="form.username" placeholder="用户名（登录使用）" :prefix-icon="User" size="large"
                      autocomplete="username" />
          </el-form-item>
          <el-form-item prop="name_zh">
            <el-input v-model.trim="form.name_zh" placeholder="显示名称（选填）" :prefix-icon="Avatar" size="large" />
          </el-form-item>
          <el-form-item prop="email">
            <el-input v-model.trim="form.email" placeholder="邮箱（选填，Bugzilla 指派人使用）" :prefix-icon="Message"
                      size="large" />
          </el-form-item>
          <el-form-item prop="password">
            <el-input v-model="form.password" placeholder="密码（至少8位，包含字母和数字）" type="password"
                      :prefix-icon="Lock" size="large" show-password autocomplete="new-password" />
          </el-form-item>
          <el-form-item prop="confirm">
            <el-input v-model="form.confirm" placeholder="确认密码" type="password" :prefix-icon="Lock" size="large"
                      show-password autocomplete="new-password" />
          </el-form-item>
          <el-alert v-if="errorMsg" :title="errorMsg" type="error" show-icon :closable="false" class="mb-3" />
          <el-button :loading="loading" type="primary" size="large" @click.prevent="handleRegister">注 册</el-button>
          <div class="footer-links">
            <span class="tip">注册后需管理员分配项目权限</span>
            <router-link to="/login">已有账号，去登录</router-link>
          </div>
        </el-form>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.register-container {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  width: 100%;
  min-height: 100%;
  .theme-switch {
    position: fixed;
    top: 5%;
    right: 5%;
    cursor: pointer;
  }
  .register-card {
    width: 480px;
    max-width: 90%;
    border-radius: 20px;
    box-shadow: 0 0 10px #dcdfe6;
    background-color: var(--el-bg-color);
    overflow: hidden;
    .title {
      display: flex;
      justify-content: center;
      align-items: center;
      height: 120px;
      img {
        height: 100%;
      }
    }
    .content {
      padding: 10px 50px 40px 50px;
      // 禁止点击眼睛图标切换密码可见性时，校验错误文字 / 后缀图标 / label 等被浏览器误选中
      :deep(.el-input__suffix),
      :deep(.el-input__suffix-inner),
      :deep(.el-input__password),
      :deep(.el-input__prefix),
      :deep(.el-input__prefix-inner),
      :deep(.el-form-item__label),
      :deep(.el-form-item__error),
      :deep(.el-alert) {
        user-select: none;
        -webkit-user-select: none;
        -moz-user-select: none;
        -ms-user-select: none;
      }
      // 输入框内容保持可选中（允许复制粘贴）
      :deep(.el-input__inner) {
        user-select: text;
        -webkit-user-select: text;
      }
      .el-button {
        width: 100%;
        margin-top: 10px;
      }
      .footer-links {
        display: flex;
        justify-content: space-between;
        margin-top: 16px;
        font-size: 13px;
        .tip {
          color: var(--el-text-color-secondary);
        }
        a {
          color: var(--el-color-primary);
          text-decoration: none;
        }
      }
    }
  }
}
</style>
