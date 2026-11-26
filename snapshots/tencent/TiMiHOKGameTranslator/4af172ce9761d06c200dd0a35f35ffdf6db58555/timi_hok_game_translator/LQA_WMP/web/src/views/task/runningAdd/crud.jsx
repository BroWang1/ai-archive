import { dict } from '@fast-crud/fast-crud';
import { ElMessage } from 'element-plus';
import { customRequest } from '@/utils/service.ts';
import createCrudOptions from './data/crud.jsx';
import { ref } from 'vue';
import { getLanguageDict } from '@/utils/dict.js';

export default function ({
  route, selectedLanguages, selectedDataIds, doRefresh,
}) {
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
        submitDisabled.value = !Object.values(form).some(item => item.length);
      },
      wrapper: {
        buttons: {
          ok: {
            disabled: submitDisabled,
          },
        },
      },
      doSubmit: async ({ form }) => {
        const res = await customRequest({
          url: '/api/job/entity',
          method: 'patch',
          data: {
            ...form,
            languages: [...form.languages, ...selectedLanguages],
            data_ids: [...form.data_ids, ...selectedDataIds],
          },
        });
        if (res.code === 0) {
          ElMessage.success(res.msg || '追加成功');
          doRefresh();
          return true;
        }
        ElMessage.error(res.msg);
        return false;
      },
    },
    columns: {
      // 语言
      languages: {
        title: '区域语言',
        type: 'dict-select',
        dict: getLanguageDict(route.meta.value, true),
        form: {
          col: { span: 24 },
          component: {
            multiple: true,
            onDictChange: ({ dict }) => {
              (dict.data || []).forEach((item) => {
                if (selectedLanguages.includes(item.value)) {
                  item.disabled = true;
                }
              });
            },
            placeholder: '区域语言',
          },
        },
      },
      // 测试数据
      data_ids: {
        title: '数据添加',
        search: { show: true },
        type: 'table-select',
        dict: dict({
          value: 'id',
          label: 'id',
          // getNodesByValues: async (values: any[]) => await textTableApi.GetByIds(values),
        }),
        form: {
          col: { span: 24 },
          component: {
            select: {
              placeholder: '数据添加',
            },
            multiple: true,
            crossPage: true,
            showCurrent: false, // 回显 tag 点击删除有问题，先屏蔽掉
            createCrudOptions: () => createCrudOptions(route.meta.value, selectedDataIds),
          },
        },
      },
    },
  };
}
