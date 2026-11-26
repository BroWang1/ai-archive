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
        buttons: {
          ok: {
            disabled: submitDisabled,
          },
        },
      },
      doSubmit: async ({ form }) => {
        const res = await customRequest({
          url: '/api/data/list',
          method: 'patch',
          data: { ...form, ids: selectedIds.value },
        })
          .catch((err) => {
            ElMessage.error('操作失败');
            console.log(`/data/project/${route.meta.value}/data 接口调用失败: ${err}`);
            throw err;
          });
        if (res.code === 0) {
          ElMessage.success(res.msg);
          clearRefresh();
          return true;
        }
        ElMessage.warning('操作失败');
        return false;
      },
    },
    columns: {
      // 资源版本
      resource_version: {
        title: '资源版本',
        type: 'text',
        form: {
          component: {
            placeholder: '资源版本',
          },
        },
      },
      // 模块
      module_id: {
        title: '模块',
        type: 'dict-select',
        dict: dict({
          url: `/api/project/module/list?project_id=${route.meta.value}&all=1`,
          value: 'id',
          label: 'show_name',
          async getData({ url }) {
            // 获取字典请求
            // @ts-ignore
            const { data } = await customRequest({ url, method: 'get' });
            return data.modules;
          },
        }),
        column: { align: 'center' },
        form: {
          component: { placeholder: '模块' },
        },
      },
    },
  };
}
