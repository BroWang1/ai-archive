<script lang="ts" setup>
import { reactive, ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useUserStore } from '@/store/modules/user';
import { type FormInstance, type FormRules } from 'element-plus';
import { User, Lock } from '@element-plus/icons-vue';
import ThemeSwitch from '@/components/ThemeSwitch/index.vue';
import { customRequest } from '@/utils/service';
import Owl from './components/Owl.vue';
import { useFocus } from './hooks/useFocus';

const router = useRouter();
const route = useRoute();
const { isFocus, handleBlur, handleFocus } = useFocus();

const loginFormRef = ref<FormInstance | null>(null);
const loading = ref(false);
const errorMsg = ref('');
const allowRegister = ref(false);
const loginFormData = reactive({
  username: '',
  password: '',
});
const loginFormRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
};

onMounted(async () => {
  try {
    const res = await customRequest({ url: '/api/user/auth_config', method: 'get', silent: true });
    allowRegister.value = !!res.data.allow_register;
  } catch {
    allowRegister.value = false;
  }
});

/** 只允许站内跳转，防止开放重定向 */
const redirectTarget = () => {
  const redirect = String(route.query.redirect || '/');
  return redirect.startsWith('/') && !redirect.startsWith('//') ? redirect : '/';
};

const handleLogin = () => {
  loginFormRef.value?.validate((valid: boolean) => {
    if (!valid) return;
    loading.value = true;
    errorMsg.value = '';
    useUserStore()
      .login(loginFormData)
      .then(() => router.replace(redirectTarget()))
      .catch((err) => {
        errorMsg.value = err?.response?.data?.msg || err?.message || '登录失败';
        loginFormData.password = '';
      })
      .finally(() => {
        loading.value = false;
      });
  });
};
</script>

<template>
  <div class="login-container">
    <ThemeSwitch class="theme-switch" />
    <Owl :close-eyes="isFocus" />
    <div class="login-card">
      <div class="title">
        <img src="@/assets/layouts/logo-text-2.png" />
      </div>
      <div class="content">
        <el-form ref="loginFormRef" :model="loginFormData" :rules="loginFormRules" @keyup.enter="handleLogin">
          <el-form-item prop="username">
            <el-input
              v-model.trim="loginFormData.username"
              placeholder="用户名"
              type="text"
              tabindex="1"
              autocomplete="username"
              :prefix-icon="User"
              size="large"
            />
          </el-form-item>
          <el-form-item prop="password">
            <el-input
              v-model="loginFormData.password"
              placeholder="密码"
              type="password"
              tabindex="2"
              autocomplete="current-password"
              :prefix-icon="Lock"
              size="large"
              show-password
              @blur="handleBlur"
              @focus="handleFocus"
            />
          </el-form-item>
          <el-alert v-if="errorMsg" :title="errorMsg" type="error" show-icon :closable="false" class="mb-3" />
          <el-button :loading="loading" type="primary" size="large" @click.prevent="handleLogin">登 录</el-button>
          <div class="footer-links">
            <span class="tip">忘记密码请联系管理员重置</span>
            <router-link v-if="allowRegister" to="/register">注册账号</router-link>
          </div>
        </el-form>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.login-container {
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
  .login-card {
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
      height: 150px;
      img {
        height: 100%;
      }
    }
    .content {
      padding: 20px 50px 40px 50px;
      // 禁止点击眼睛图标切换密码可见性时，错误提示 / 后缀图标等被浏览器误选中
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
