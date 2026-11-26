import { dict } from '@fast-crud/fast-crud';
import { ElMessage } from 'element-plus';
import { customRequest } from '@/utils/service.ts';

export default function (route, bugIdList, clearRefresh) {
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
      labelWidth: '100px',
      wrapper: {
        title: '回归',
      },
      doSubmit: async ({ form }) => {
        const res = await customRequest({
          url: '/api/job/bug_regress',
          method: 'post',
          data: {
            bug_ids: bugIdList,
            ...form,
          },
        }).catch((err) => {
          console.error(`regressionBug 接口调用失败:${err}`);
          return;
        });
        if (!res) {
          return false;
        }
        if (res.code === 0) {
          ElMessage.success('提交成功');
          clearRefresh();
          return true;
        }
        ElMessage.warning(res.data.msg);
        return true;
      },
    },
    columns: {
      // 任务类型
      discern: {
        title: '任务类型',
        type: 'dict-radio',
        form: {
          value: 0,
        },
        dict: dict({
          data: [
            { value: 1, label: '差异识别' },
            { value: 0, label: '全量识别' },
          ],
        }),
      },
      // 译文资源
      translate_resource: {
        title: '译文资源',
        form: {
          col: { span: 24 },
          valueBuilder(context) {
            // 构建时
            const keys = [
              'trans_res_type', 'trans_res_repo', 'trans_res_br', 'trans_res_ver', 'trans_res_file_path',
            ];
            const temp = {};
            keys.forEach((key) => {
              if (context.form[key]) {
                if (key === 'trans_res_file_path') {
                  // 文件数据组装
                  temp[key] = [
                    {
                      url: context.form[key],
                      name: context.form[key].split('/').pop(),
                    },
                  ];
                } else {
                  temp[key] = context.form[key];
                }
              }
            });
            context.form[context.key] = JSON.stringify(temp);
          },
          valueResolve(context) {
            // 提交时
            const temp = JSON.parse(context.form[context.key]);
            Object.entries(temp).forEach(([key, value]) => {
              context.form[key] = value;
            });
          },
        },
      },
      // 说明信息
      helper: {
        title: '',
        form: {
          col: { span: 24 },
          component: {
            name: 'div',
          },
          helper: '回归时间受配置更新时间影响，配置更新内容多，回归时间就会较长',
        },
      },
    },
  };
}
