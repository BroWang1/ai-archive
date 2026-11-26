<!--
 * @Description: 项目配置
-->
<style scoped lang="scss">

</style>

<template>
  <div class="app-container !pt-4.25 bg-white">
    <el-tabs v-model="activeTab" class="demo-tabs">
      <el-tab-pane
        v-if="checkPermission([ `${$route.meta.value}:admin`, `${$route.meta.value}:develop` ])"
        label="缺陷类型" name="bug_type"
        style="height: calc(100vh - 240px)"
      >
        <bug-type />
      </el-tab-pane>
      <el-tab-pane
        v-if="checkPermission([ `${$route.meta.value}:admin`, `${$route.meta.value}:develop` ])"
        label="区域语言" name="language"
        style="height: calc(100vh - 240px)"
      >
        <language />
      </el-tab-pane>
      <el-tab-pane
        v-if="checkPermission([ `${$route.meta.value}:admin`, `${$route.meta.value}:develop` ])"
        label="图片还原" name="img"
        style="height: calc(100vh - 240px)"
      >
        <img-conf />
      </el-tab-pane>
      <el-tab-pane label="模块" name="module" style="height: calc(100vh - 240px)">
        <module-conf />
      </el-tab-pane>
      <el-tab-pane
        v-if="checkPermission([ `${$route.meta.value}:admin`, `${$route.meta.value}:develop` ])"
        label="还原执行" name="other"
        style="height: calc(100vh - 240px); overflow: auto"
      >
        <other-conf />
      </el-tab-pane>
      <el-tab-pane
        v-if="checkPermission([ `${$route.meta.value}:admin` ])"
        label="缺陷系统" name="tracker"
        style="height: calc(100vh - 240px); overflow: auto"
      >
        <tracker-conf />
      </el-tab-pane>
      <el-tab-pane label="提单" name="submitBug" style="height: calc(100vh - 240px)">
        <submit-bug />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script>
import bugType from './bugType.vue';
import language from './language.vue';
import imgConf from './img/index.vue';
import moduleConf from './module/index.vue';
import otherConf from './other/index.vue';
import trackerConf from './tracker/index.vue';
import submitBug from './submitBug/index.vue';
import { checkPermission } from '@/utils/permission.ts';
export default {
  name: 'settings',
  components: {
    bugType, language, imgConf, moduleConf, otherConf, trackerConf, submitBug,
  },
  data() {
    return {
      activeTab: 'submitBug',
    };
  },
  methods: {
    checkPermission,
  },
};
</script>
