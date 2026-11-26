<script lang="ts" setup>
import { reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { storeToRefs } from 'pinia';
import { ElMessage, type FormInstance, type FormRules } from 'element-plus';
import { passwordRules } from '@/views/login/rules';
import { useAppStore } from '@/store/modules/app';
import { useSettingsStore } from '@/store/modules/settings';
import { useUserStore } from '@/store/modules/user';
import { UserFilled } from '@element-plus/icons-vue';
import Hamburger from '../Hamburger/index.vue';
import Breadcrumb from '../Breadcrumb/index.vue';
import Sidebar from '../Sidebar/index.vue';
import Notify from '@/components/Notify/index.vue';
import ThemeSwitch from '@/components/ThemeSwitch/index.vue';
import Screenfull from '@/components/Screenfull/index.vue';
import SearchMenu from '@/components/SearchMenu/index.vue';
import { useDevice } from '@/hooks/useDevice';
import { useLayoutMode } from '@/hooks/useLayoutMode';

const { isMobile } = useDevice();
const { isTop } = useLayoutMode();
const router = useRouter();
const appStore = useAppStore();
const userStore = useUserStore();
const settingsStore = useSettingsStore();
const { showNotify, showThemeSwitch, showScreenfull, showSearchMenu } = storeToRefs(settingsStore);

/** 切换侧边栏 */
const toggleSidebar = () => {
  appStore.toggleSidebar(false);
};

/** 登出 */
const logout = async () => {
  await userStore.logout();
  router.replace('/login');
};

/** 修改密码 */
const pwdDialogVisible = ref(false);
const pwdFormRef = ref<FormInstance | null>(null);
const pwdSubmitting = ref(false);
const pwdForm = reactive({ old_password: '', new_password: '', confirm: '' });
const pwdRules: FormRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: passwordRules(),
  confirm: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (_r, value, cb) => (value === pwdForm.new_password ? cb() : cb(new Error('两次输入的密码不一致'))),
      trigger: 'blur',
    },
  ],
};
const openPwdDialog = () => {
  Object.assign(pwdForm, { old_password: '', new_password: '', confirm: '' });
  pwdDialogVisible.value = true;
};
const submitPwd = () => {
  pwdFormRef.value?.validate(async (valid: boolean) => {
    if (!valid) return;
    pwdSubmitting.value = true;
    try {
      await userStore.changePassword(pwdForm.old_password, pwdForm.new_password);
      ElMessage.success('密码已修改');
      pwdDialogVisible.value = false;
    } finally {
      pwdSubmitting.value = false;
    }
  });
};
</script>

<template>
  <div class="navigation-bar">
    <Hamburger
      v-if="!isTop || isMobile"
      :is-active="appStore.sidebar.opened"
      class="hamburger"
      @toggle-click="toggleSidebar"
    />
    <Breadcrumb v-if="!isTop || isMobile" class="breadcrumb" />
    <Sidebar v-if="isTop && !isMobile" class="sidebar" />
    <div class="right-menu">
      <SearchMenu v-if="showSearchMenu" class="right-menu-item" />
      <Screenfull v-if="showScreenfull" class="right-menu-item" />
      <ThemeSwitch v-if="showThemeSwitch" class="right-menu-item" />
      <Notify v-if="showNotify" class="right-menu-item" />
      <el-dropdown class="right-menu-item">
        <div class="right-menu-avatar">
          <el-avatar :icon="UserFilled" :size="30" />
          <span>{{ userStore.username }}</span>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item disabled>
              <span style="display: block">账号：{{ userStore.name }}</span>
            </el-dropdown-item>
            <el-dropdown-item divided @click="openPwdDialog">
              <span style="display: block">修改密码</span>
            </el-dropdown-item>
            <el-dropdown-item @click="logout">
              <span style="display: block">退出登录</span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <el-dialog v-model="pwdDialogVisible" title="修改密码" width="420px" append-to-body destroy-on-close class="change-pwd-dialog">
      <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="80px" @keyup.enter="submitPwd">
        <el-form-item label="原密码" prop="old_password">
          <el-input v-model="pwdForm.old_password" type="password" show-password autocomplete="current-password" />
        </el-form-item>
        <el-form-item label="新密码" prop="new_password">
          <el-input v-model="pwdForm.new_password" type="password" show-password autocomplete="new-password"
                    placeholder="至少8位，包含字母和数字" />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirm">
          <el-input v-model="pwdForm.confirm" type="password" show-password autocomplete="new-password" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwdDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="pwdSubmitting" @click="submitPwd">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style lang="scss" scoped>
.navigation-bar {
  height: var(--v3-navigationbar-height);
  overflow: hidden;
  color: var(--v3-navigationbar-text-color);
  display: flex;
  justify-content: space-between;
  .hamburger {
    display: flex;
    align-items: center;
    height: 100%;
    padding: 0 15px;
    cursor: pointer;
  }
  .breadcrumb {
    flex: 1;
    // 参考 Bootstrap 的响应式设计将宽度设置为 576
    @media screen and (max-width: 576px) {
      display: none;
    }
  }
  .sidebar {
    flex: 1;
    // 设置 min-width 是为了让 Sidebar 里的 el-menu 宽度自适应
    min-width: 0px;
    :deep(.el-menu) {
      background-color: transparent;
    }
    :deep(.el-sub-menu) {
      &.is-active {
        .el-sub-menu__title {
          color: var(--el-color-primary) !important;
        }
      }
    }
  }
  .right-menu {
    margin-right: 10px;
    height: 100%;
    display: flex;
    align-items: center;
    .right-menu-item {
      padding: 0 10px;
      cursor: pointer;
      .right-menu-avatar {
        display: flex;
        align-items: center;
        .el-avatar {
          margin-right: 10px;
        }
        span {
          font-size: 16px;
        }
      }
    }
  }
}
</style>

<!-- 修改密码弹窗样式（因 append-to-body 挂载到 body，使用非 scoped 全局样式） -->
<style lang="scss">
.change-pwd-dialog {
  // 禁止标题、label、后缀图标等非输入区域被意外选中（点击眼睛图标时 label 会被框选）
  .el-dialog__header,
  .el-dialog__title,
  .el-form-item__label,
  .el-input__suffix,
  .el-input__suffix-inner,
  .el-input__password {
    user-select: none;
    -webkit-user-select: none;
    -moz-user-select: none;
    -ms-user-select: none;
  }
  // 输入框内容保持可选中（允许复制粘贴）
  .el-input__inner {
    user-select: text;
    -webkit-user-select: text;
  }
}
</style>
