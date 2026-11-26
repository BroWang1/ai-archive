import { dict } from '@fast-crud/fast-crud';
import { ElMessage } from 'element-plus';
import { customRequest } from '@/utils/service.ts';
import { ref } from 'vue';

export default function (route, selectedIds, clearRefresh) {
  const submitDisabled = ref(false);
  // 此处编辑 crudOptions 配置
  return {
    table: {
      border: false,
      // defaultSort: {prop: 'create_time', order: 'descending'}
    },
    search: {
      show: false,
    },
    form: {
      watch({ form }) {
        submitDisabled.value = Object.values(form).every(item => !item);
      },
      wrapper: {
        title: '批量编辑',
        style: {
          justifyContent: 'center',
          // height: '22vh', // 使容器高度占满整个视口
          weights: '3vh',
        },
        buttons: {
          ok: {
            disabled: submitDisabled,
          },
        },
      },
      doSubmit: async ({ form }) => {
        const res = await customRequest({
          url: '/api/bug/list',
          method: 'patch',
          data: { ...form, bug_ids: selectedIds.value },
        })
          .catch((err) => {
            ElMessage.error('操作失败');
            console.log(`/data/project/${route.meta.value}/data 接口调用失败: ${err}`);
            throw err;
          });

        if (res.code === 0) {
          ElMessage.success('操作成功');
          clearRefresh();
          return true;
        }
        ElMessage.warning('操作失败');
        return false;
      },
    },
    columns: {
      // 资源版本
      status: {
        columnStyle: {
          className: 'center',
        },
        title: '回归状态',
        type: 'dict-select',
        dict: dict({
          data: [
            { value: '1', label: '初始' },
            { value: '2', label: '回归中' },
            { value: '3', label: '回归成功' },
            { value: '4', label: '回归失败' },
          ],
        }),
      },
    },
  };
}


