<!--
 * @Description: $description$
-->
<template>
  <div class="app-container !pt-4 bg-white">
    <el-tabs class="setting-side-tab h-full" tab-position="left">
      <!-- 公告 -->
<!--      <el-tab-pane label="公告">-->
<!--        <announcement />-->
<!--      </el-tab-pane>-->

      <!-- 缺陷类型 -->
      <el-tab-pane label="缺陷类型">
        <bug-type />
      </el-tab-pane>

      <!-- 区域语言 -->
      <el-tab-pane label="区域语言">
        <language />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script>
import announcement from './announcement/index.vue';
import bugType from './bug/index.vue';
import language from './language/index.vue';

export default {
  name: 'settings',
  components: { announcement, bugType, language },
  data() {
    return {};
  },
  methods: {},
};
</script>

<style lang="scss" scoped>
.setting-side-tab:deep {
  .el-tabs__header {
    margin-top: 15px
  }
  .el-tabs__content {
    height: 100%;
    .el-tab-pane {
      height: 100%;
    }
  }
}
</style>
