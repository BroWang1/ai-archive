import { customRequest } from '@/utils/service';
import { useRoute } from 'vue-router';

export default function () {
  const route = useRoute();
  // @ts-ignore
  const pageRequest = async params => await customRequest({
    url: '/system/setting/announcement',
    method: 'get',
    params: { project_id: route.meta.value, ...params },
  }).then(res => ({ ...res, page: 1, size: res.data.length, total: res.data.length }));
  // @ts-ignore
  const addRequest = async ({ form }) => await customRequest({
    url: `/system/setting/announcement?project_id=${route.meta.value}`,
    method: 'post',
    data: form,
  });
  // @ts-ignore
  const editRequest = async ({ form, row }) => await customRequest({
    url: `/system/setting/${row.id}/announcement?project_id=${route.meta.value}`,
    method: 'patch',
    data: form,
  });
  // @ts-ignore
  const delRequest = async ({ row }) => await customRequest({
    url: `/system/setting/${row.id}/announcement?project_id=${route.meta.value}`,
    method: 'delete',
  });
  // 此处编辑 crudOptions 配置
  return {
    crudOptions: {
      request: {
        pageRequest,
        addRequest,
        editRequest,
        delRequest,
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
        display: 'grid',
        labelWidth: '80px',
        col: { span: 24 },
      },
      columns: {
        // ID
        // id: {
        //   title: 'ID',
        //   type: 'number',
        //   column: { width: 64, align: 'center', sorter: true },
        //   form: { show: false },
        // },

        // 内容
        info: {
          title: '内容',
          type: 'text',
          addForm: {
            col: { span: 24 },
          },
          column: { minWidth: 300 },
          form: {
            order: 1,
            col: { span: 24 },
            component: { placeholder: '内容' },
            rules: [{ required: true, message: '请填写内容' }],
          },
        },

        // 创建人
        creator: {
          title: '创建人',
          type: 'text',
          column: { width: 100 },
          form: { show: false },
        },

        // 生效时间
        times: {
          title: '生效时间',
          type: 'datetimerange',
          column: {
            minWidth: 300,
            align: 'center',
            formatter({ value }) {
              if (value && value.length === 2) {
                return `${value[0]} ~ ${value[1]}`;
              }
              return '';
            },
          },
          valueBuilder({ row }) {
          // value构建，就是把后台传过来的值转化为前端组件所需要的值
          // 在pageRequest之后执行转化，然后将转化后的数据放到table里面显示
            if (row.start_time && row.end_time) {
              row.times = [row.start_time.replace('T', ' '), row.end_time.replace('T', ' ')];
            }
          },
          valueResolve(context) {
          // value解析，就是把组件的值转化为后台所需要的值
          // 在form表单点击保存按钮后，提交到后台之前执行转化
            if (context.form.times) {
              const [startTime, endTime] = context.form.times;
              context.form.start_time = startTime;
              context.form.end_time = endTime;
              context.form.times = [];
            }
          },
          form: {
            component: {
              format: 'YYYY-MM-DD HH:mm:ss',
              valueFormat: 'YYYY-MM-DD HH:mm:ss',
            },
          // component: dateRangeBind,
          },
        },
      },
    },
  };
}
