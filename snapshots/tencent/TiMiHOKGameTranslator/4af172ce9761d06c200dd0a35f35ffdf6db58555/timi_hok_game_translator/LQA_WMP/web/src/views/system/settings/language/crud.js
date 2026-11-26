import { customRequest } from '@/utils/service';
import { SUPER_ADMIN_PROJECT_ID } from '@/constants/app-key.ts';

export default function () {
  // @ts-ignore
  const pageRequest = async () => await customRequest({
    url: '/api/system/enums/language',
    method: 'get',
    params: { project_id: SUPER_ADMIN_PROJECT_ID },
  });

  // 此处编辑 crudOptions 配置
  return {
    crudOptions: {
      request: {
        pageRequest,
      },
      search: { show: false },
      pagination: {
        show: false,
      },
      table: {
        border: false,
        // defaultSort: {prop: 'create_time', order: 'descending'}
      },
      form: {
        // 具体可配置请参考 grid 布局： http://www.ruanyifeng.com/blog/2019/03/grid-layout-tutorial.html
        labelWidth: '80px',
      },
      actionbar: {
        show: false,
      },
      rowHandle: {
        show: false,
      },
      columns: {
        // ID
        value: {
          title: 'ID',
          type: 'text',
          addForm: {
            col: { span: 24 },
          },
          column: {
            align: 'right',
            width: 50,
          },
        },
        // 名称
        label: {
          title: '名称',
          type: 'text',
          addForm: {
            col: { span: 24 },
          },
          column: { minWidth: 300 },
          form: {
            order: 1,
            col: { span: 24 },
            component: { placeholder: '名称' },
            rules: [{ required: true, message: '请填写名称' }],
          },
        },
        // 编码
        name: {
          title: '编码',
          type: 'text',
          addForm: {
            col: { span: 24 },
          },
          column: { minWidth: 300 },
          form: {
            order: 1,
            col: { span: 24 },
            component: { placeholder: '编码' },
            rules: [{ required: true, message: '请填写编码' }],
          },
        },
      },
    },
  };
}
