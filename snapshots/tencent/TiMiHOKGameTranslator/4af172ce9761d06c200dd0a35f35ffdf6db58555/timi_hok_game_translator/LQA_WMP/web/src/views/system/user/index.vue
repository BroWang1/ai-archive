<!--
 * @Description: 用户管理
-->

<template>
  <div class="app-container !pt-4.25 bg-white">
    <fs-crud ref="crudRef" v-bind="crudBinding">
      <!-- 单元格插槽 自定义roles展示 -->
<!--      <template #cell_roles="scope">-->
<!--        <fs-values-format :model-value="rolesFilter(scope.row.roles)" :dict="rolesDict" color="auto" />-->
<!--      </template>-->
    </fs-crud>
  </div>
</template>

<script>
import { defineComponent, onBeforeUnmount, onMounted, ref } from 'vue';
import { useFs, dict } from '@fast-crud/fast-crud';
// import api from '@/api';
import createCrudOptions from './crud.jsx';

export default defineComponent({
  name: 'User',
  setup() {
    // fs-crud 初始化
    const { crudRef, crudBinding, crudExpose, projectID, rolesDict } = useFs({ createCrudOptions });

    const showLoading = ref(false);
    // const projectRoleList = ref([]);
    // const roleList = [];
    // 项目角色查询
    // const getProjectRole = () => api.basics.projectRoleTree.get({ pro_id: projectID.value }).then((res) => {
    //   showLoading.value = false;
    //   projectRoleList.value = res;
    //   // 保存项目角色列表
    //   res.forEach((item) => {
    //     if (item.children) {
    //       item.children.map((child) => {
    //         roleList.push(child.id);
    //       });
    //     }
    //   });
    //   return res;
    // });

    // const rolesFilter = roles => roles.filter(value => value !== '3');

    /**
     * 让"角色"级联多选面板里，点击叶子节点的文字 label 也能触发勾选。
     *
     * 背景：Element Plus 2.9.11 的 el-cascader-node 在 multiple 模式下，点击 <li> 整行
     *   走的是 handleExpand 而不是 handleCheck（源码可查），只有点击 checkbox 本身才会勾选，
     *   导致用户点"项目管理员/测试人员/开发人员"这几个字时毫无反应。
     *
     * 方案：在 document 的 capture 阶段挂一个事件委托，仅处理我们自定义 popperClass 下
     *   （user-roles-cascader-popper）叶子节点 label 的点击：阻止其默认行为，手动触发
     *   同一 <li> 内 checkbox 的 click，让勾选逻辑正常走通。影响面严格限定在该面板内。
     */
    const handleRolesCascaderLabelClick = (e) => {
      const target = e.target;
      if (!(target instanceof HTMLElement)) return;
      // 必须在我们的角色级联面板内
      const popper = target.closest('.user-roles-cascader-popper');
      if (!popper) return;
      // 必须点击在 label 文字上
      const label = target.closest('.el-cascader-node__label');
      if (!label) return;
      // 必须是叶子节点（非叶子节点有 aria-haspopup="true"，让它继续走默认 handleExpand）
      const node = label.closest('.el-cascader-node');
      if (!node || node.getAttribute('aria-haspopup') === 'true') return;
      // 禁用节点不处理
      if (node.classList.contains('is-disabled')) return;
      // 定位到同一 <li> 内的 checkbox 原生 input 并触发 click
      const checkbox = node.querySelector('.el-checkbox');
      if (!checkbox) return;
      e.stopPropagation();
      e.preventDefault();
      checkbox.click();
    };

    onMounted(() => {
      showLoading.value = true;
      // 加载侧栏选择器
      // getProjectRole();
      // 页面打开后立即加载列表数据
      crudExpose.doRefresh();
      document.addEventListener('click', handleRolesCascaderLabelClick, true);
    });

    onBeforeUnmount(() => {
      document.removeEventListener('click', handleRolesCascaderLabelClick, true);
    });

    return {
      // 给 template 使用
      projectID,
      crudBinding,
      crudRef,
      showLoading,
      // projectRoleList,
      rolesDict,
      dict,
      // rolesFilter,
    };
  },

});

</script>

<style scoped lang="scss">
.el-main {
  padding: 0;
}

.user-avatar-container {
  display: flex;
  align-items: center;
}

.user-avatar-image {
  height: 30px;
  line-height: 30px;
  padding-right: 8px;
}
</style>
