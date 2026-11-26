import { customRequest } from '@/utils/service';
import { useRoute } from 'vue-router';

export default function () {
  const route = useRoute();
  // @ts-ignore
  const pageRequest = async params => await customRequest({
    url: '/api/project/module/list',
    method: 'get',
    params: { project_id: route.meta.value, ...params },
  });
  // @ts-ignore
  const addRequest = async ({ form }) => await customRequest({
    url: '/api/project/module',
    method: 'post',
    data: { project_id: route.meta.value, ...form },
  });
  // @ts-ignore
  const editRequest = async ({ form, row }) => await customRequest({
    url: '/api/project/module',
    method: 'patch',
    data: { ...form, id: row.id, project_id: route.meta.value },
  });
  const delRequest = async ({ row }) => await customRequest({
    url: '/api/project/module',
    method: 'delete',
    data: { project_id: route.meta.value, module_id: row.id },
  });

  function buildShowName(form) {
    if (form.name && form.sub_module) {
      form.show_name = `${form.name}-${form.sub_module}`;
    } else if (form.name) {
      form.show_name = form.name;
    }
  }

  // 此处编辑 crudOptions 配置
  return {
    crudOptions: {
      request: {
        pageRequest,
        addRequest,
        editRequest,
        delRequest,
      },
      table: {
        border: false,
        // defaultSort: {prop: 'create_time', order: 'descending'}
      },
      search: {
        show: false,
      },
      columns: {
        // ID
        id: {
          title: 'ID',
          type: 'number',
          column: { width: 60, align: 'right', showOverflowTooltip: false },
          form: { show: false },
        },
        // 名称
        name: {
          title: '名称',
          type: 'text',
          form: {
            component: { placeholder: '请填写名称' },
            valueChange({ form }) {
              buildShowName(form);
            },
            rules: [{ required: true, message: '请填写名称' }],
          },
        },
        // 子模块
        sub_module: {
          title: '子模块',
          type: 'text',
          form: {
            component: { placeholder: '子模块' },
            valueChange({ form }) {
              buildShowName(form);
            },
          },
        },
        // 显示名称
        show_name: {
          title: '显示名称',
          type: 'text',
          form: {
            component: { placeholder: '显示名称' },
          },
        },
      },
    },
  };
}
