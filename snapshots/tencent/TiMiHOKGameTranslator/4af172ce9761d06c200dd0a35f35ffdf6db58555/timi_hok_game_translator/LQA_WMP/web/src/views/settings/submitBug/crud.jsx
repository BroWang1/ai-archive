import { customRequest } from '@/utils/service';
import { useRoute } from 'vue-router';
import { dict } from '@fast-crud/fast-crud';
import { getBugTypeDict, getLanguageDict } from '@/utils/dict.js';
import { computed } from 'vue';

export default function ({ context }) {
  const route = useRoute();

  const baseForm = {
    bug_type: 0, // 缺陷类型
    language: 0, // 区域语言
    module: 0, // 模块
  };
  const keys = Object.keys(baseForm);
  const addRequest = ({ form }) => {
    customRequest({
      url: '/api/project/config?cate=BugBillUser',
      method: 'post',
      data: {
        ...baseForm,
        ...form,
        project_id: context.project_id,
      },
    }).finally(() => {
      context.refresh();
    });
  };
  const editRequest = ({ form }) => {
    // 构造要发往后端的 payload：空值补 0（后端存储的是数值）
    // 注意：不要直接修改入参 form，因为它是 fast-crud 行数据的引用，
    //      修改会触发列重新渲染，让字典里不存在的 value=0 短暂显示为"0"，造成闪烁
    const payload = { ...form, project_id: context.project_id };
    keys.forEach((key) => {
      if (!payload[key]) {
        payload[key] = 0;
      }
    });
    customRequest({
      url: '/api/project/config?cate=BugBillUser',
      method: 'patch',
      data: payload,
    }).finally(() => {
      context.refresh();
    });
  };
  const delRequest = ({ row }) => {
    customRequest({
      url: '/api/project/config?cate=BugBillUser',
      method: 'delete',
      data: {
        ids: [row.id],
        project_id: context.project_id,
      },
    }).finally(() => {
      context.refresh();
    });
  };

  // 此处编辑 crudOptions 配置
  return {
    crudOptions: {
      request: {
        addRequest,
        editRequest,
        delRequest,
      },
      // mode: {
      //   name: 'local',
      //   isMergeWhenUpdate: true,
      //   isAppendWhenAdd: true,
      // },
      pagination: {
        show: false,
      },
      table: {
        border: false,
        // defaultSort: {prop: 'create_time', order: 'descending'}
      },
      editable: {
        enabled: false,
        mode: 'row',
        activeTrigger: false,
      },
      search: {
        show: false,
      },
      columns: {
        // ID
        // id: {
        //   title: 'ID',
        //   type: 'number',
        //   column: { width: 64, align: 'center' },
        //   form: { show: false },
        // },
        // "/setting/BugClass/project/" + "{{projectId}}" + "/get_BugClass"

        // 缺陷类型
        bug_type: {
          title: '缺陷类型',
          type: 'dict-select',
          dict: getBugTypeDict(route.meta.value),
          column: { show: computed(() => !!context.props.form.bug_type_enable) },
          form: {
            show: computed(() => !!context.props.form.bug_type_enable),
            component: { placeholder: '请选择缺陷类型' },
            rules: [{ required: true, message: '请选择缺陷类型' }],
            order: 1,
          },
        },
        // 区域语言
        language: {
          title: '区域语言',
          type: 'dict-select',
          dict: getLanguageDict(route.meta.value),
          column: {
            // show: !!context.props.form.language_enable
            show: computed(() => !!context.props.form.language_enable),
          },
          form: {
            show: computed(() => !!context.props.form.language_enable),
            component: {
              dict: getLanguageDict(route.meta.value, true),
              placeholder: '请选择区域语言',
            },
            rules: [{ required: true, message: '请选择区域语言' }],
            order: 2,
          },
        },
        // 模块
        module: {
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
          column: {
            show: computed(() => !!context.props.form.module_enable),
          },
          form: {
            show: computed(() => !!context.props.form.module_enable),
            component: { placeholder: '请选择模块' },
            rules: [{ required: true, message: '请选择模块' }],
            order: 3,
          },
        },
        // 处理人
        user_names: {
          title: '处理人',
          type: 'dict-select',
          dict: dict({
            url: '/api/user/list',
            value: 'name',
            label: 'format_name',
            async getData({ url }) {
              const { data } = await customRequest({ url, method: 'get', params: {
                info_type: 0, // 简略信息
                page_size: 1000000000000000,
              } });
              data.list.forEach((item) => {
                let formatName = item.name;
                if (item.name_zh) {
                  formatName = `${item.name}(${item.name_zh})`;
                }
                // eslint-disable-next-line no-param-reassign
                item.format_name = formatName;
              });
              return data.list;
            },
          }),
          form: {
            col: { span: 24 },
            component: {
              multiple: true,
              allowCreate: true,
              defaultFirstOption: true,
              reserveKeyword: false,
              placeholder: '请选择/填写处理人',
            },
            rules: [{ required: true, message: '请选择/填写处理人' }],
            order: 5,
          },
          addForm: { value: [] },
        },
        // 生效
        enable: {
          title: '生效',
          type: 'dict-switch',
          dict: dict({
            data: [
              { value: 1, label: '是', color: 'success' },
              { value: 0, label: '否', color: 'error' },
            ],
          }),
          column: {
            component: {
              name: 'fs-dict-switch',
              vModel: 'modelValue',
              on: {
                change: editRequest,
              },
              // on: {
              //   onChange: async (e) => {
              //     await customRequest({
              //       url: `/setting/project/${route.meta.value}/bill_info/${e.row.id}`,
              //       method: 'patch',
              //       data: e.form,
              //     });
              //     expose.doRefresh();
              //   },
              // },
            },
          },
          form: {
            order: 4,
          },
          addForm: {
            value: 1, // 	addForm默认值 是
          },
        },
      },
    },
  };
}
