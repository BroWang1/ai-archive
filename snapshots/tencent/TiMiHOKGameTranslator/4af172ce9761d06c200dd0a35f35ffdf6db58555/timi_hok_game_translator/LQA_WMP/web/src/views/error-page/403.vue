<script lang="ts" setup>
import { useRouter } from 'vue-router';
import ErrorPageLayout from './components/ErrorPageLayout.vue';
import Svg403 from '@/assets/error-page/403.svg?component'; // vite-svg-loader 插件的功能
import { useUserStore } from '@/store/modules/user';

const router = useRouter();
const userStore = useUserStore();
const contact = import.meta.env.VITE_ADMIN_CONTACT;

const logout = async () => {
  await userStore.logout();
  router.replace('/login');
};
</script>

<template>
  <ErrorPageLayout>
    <Svg403 />
    <div class="tip">
      <p>当前账号（{{ userStore.name || '-' }}）尚未加入任何项目，请联系管理员分配项目角色</p>
      <p v-if="contact" class="contact">管理员联系方式：{{ contact }}</p>
      <el-button link type="primary" @click="logout">切换账号</el-button>
    </div>
  </ErrorPageLayout>
</template>

<style lang="scss" scoped>
.tip {
  text-align: center;
  .contact {
    color: var(--el-text-color-secondary);
  }
}
</style>
