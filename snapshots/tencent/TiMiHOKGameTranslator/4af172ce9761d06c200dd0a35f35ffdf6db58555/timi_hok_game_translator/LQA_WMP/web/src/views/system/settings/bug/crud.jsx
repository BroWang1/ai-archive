import { customRequest } from '@/utils/service';

export default function () {
  // @ts-ignore
  const pageRequest = async () => await customRequest({
    url: '/api/system/enums/bug_type',
    method: 'get',
  });
  // const edit =  data => {
  //   customRequest({
  //     url: '/api/project/config?cate=BugType',
  //     method: 'patch',
  //     data: data
  //   }).finally(() => {
  //     crudExpose.doRefresh();
  //   })
  // }
  // const isJson = str => {
  //   if(!str) return true
  //   try {
  //     const arr = JSON.parse(str)
  //     return Array.isArray(arr)
  //   } catch (e) {
  //     return false
  //   }
  // }

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
        // trans_marks
        // trans_marks: {
        //   title: '匹配标识',
        //   addForm: {
        //     col: { span: 24 },
        //   },
        //   column: {
        //     minWidth: 300,
        //     component: {
        //       show: compute(({ row }) => [1, 5].includes(row.value)),
        //       name: 'el-input',
        //       props: {
        //         type: 'input',
        //         class: {
        //           'isError': compute(({ row }) => !isJson(row.trans_marks))
        //         }
        //       },
        //       vModle: "trans_marks",
        //       on: {
        //         onBlur: ({ form, row }) => {
        //           const { trans_marks } = row
        //           const flag = isJson(trans_marks);
        //           if(flag) {
        //             edit(row)
        //             ElMessage.success('更新成功');
        //           } else {
        //             ElMessage.error('匹配标识格式有误，请重新输入！');
        //           }
        //         }
        //       }
        //     }
        //   }
        // }
      },
    },
  };
}
