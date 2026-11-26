import { dict, useCompute } from '@fast-crud/fast-crud';
import { ElMessage } from 'element-plus';
import { customRequest } from '@/utils/service.ts';
// import { cloneDeep, pick } from 'lodash-es';
import { getBugTypeDict, getLanguageDict } from '@/utils/dict.js';
import { dateRangeBind } from '@/utils/bind/date.js';
import dayjs from 'dayjs';
import createCrudOptions from '@/views/task/runTask/data/crud.jsx';
import { ref } from 'vue';

const basicColumns = ['discern', 'name', 'plan_time', 'languages', 'sign_bug_types', 'ocr_detect'];
const testDataColumn = ['data_ids'];
// 注：当前后端未消费资源配置相关字段（test_app_file_path / test_case_file_path / proj_res_* / trans_res_*），
// 暂时整个「资源配置」分组隐藏。字段定义保留以便后续恢复或兼容老任务数据回显。
const resourceColumns = [];
const bugColumns = [
  'bill_bug_types', 'priority', 'severity', 'version_report', 'version_fix', 'release_id', 'current_owner',
];

export default function ({
  route, trackerMeta, bugOptions, doRefresh, projectSourceRef, translateResourceRef,
}) {
  const { compute } = useCompute();
  const tracker = trackerMeta?.value || { type: 'none' };
  const trackerTitle = tracker.type === 'none' ? '平台内记录' : tracker.label;

  const languageDict = ref(getLanguageDict(route.meta.value));
  const languageDictNoDisable = ref(getLanguageDict(route.meta.value, true));
  // 此处编辑 crudOptions 配置
  return {
    pagination: {
      show: false,
    },
    table: {
      border: false,
      // defaultSort: {prop: 'create_time', order: 'descending'}
    },
    form: {
      labelWidth: '110px',
      wrapper: {
        title: '创建任务',
        onOpened(e) {
          setTimeout(() => {
            e.formRef.formRef.clearValidate();
          }, 500);
        },
      },
      beforeValidate: () => {
        // 「资源配置」分组已隐藏，对应 ref 可能未挂载，需做空值防御
        // 项目资源校验
        projectSourceRef.value?.validate?.();
        // 译文资源校验
        translateResourceRef.value?.$refs?.form?.validate?.();
      },
      doSubmit: async ({ form }) => {
        console.log('=>(crud.jsx:44) formatForm', form);
        // 生成参数
        const params = {
          project_id: route.meta.value, ...form,
        };
        // FIXME
        // if (form.dataSource === 'filter') {
        //   // 条件筛选
        //   params = { ...params, ...pick(form, dataSourceColumns) };
        // } else {
        //   // 选中数据
        //   params.data_ids = selectedIds.value;
        // }
        // if (form.bug_types.length) {
        //   // 有缺陷类型则有提单配置
        //   params = { ...params, ...pick(form, bugColumns) };
        // }
        // 执行请求
        const res = await customRequest({
          url: '/api/job/entity',
          method: params.id ? 'patch' : 'post',
          data: params,
        });
        if (res.code === 0) {
          ElMessage.success(res.msg || '创建成功');
          languageDict.value = await getLanguageDict(route.meta.value).reloadDict();
          languageDictNoDisable.value = await getLanguageDict(route.meta.value, true);
          doRefresh();
          return true;
        }
        ElMessage.error(res.msg);
        return false;
      },
      group: {
        groupType: 'collapse', // collapse， tabs
        accordion: false,
        groups: {
          basic: {
            title: '基础配置',
            columns: basicColumns,
          },
          test_data: {
            title: '测试数据',
            columns: testDataColumn,
          },
          resource: {
            title: '资源配置',
            columns: resourceColumns,
          },
          submitBugs: {
            title: `提单配置（${trackerTitle}${tracker.error ? '，配置有误' : ''}）`,
            columns: bugColumns,
          },
        },
      },
    },
    columns: {
      /** 基础配置 */
      // 任务类型
      discern: {
        title: '任务类型',
        type: 'dict-radio',
        form: {
          col: { span: 24 },
          value: 1,
        },
        dict: dict({
          data: [
            { value: 1, label: '差异识别' },
            { value: 0, label: '全量识别' },
          ],
        }),
      },
      // 名称
      name: {
        title: '名称',
        type: 'text',
        form: {
          component: { placeholder: '请填写任务名' },
          rules: [{ required: true, message: '请填写任务名' }],
        },
      },
      // 预约测试时间
      plan_time: {
        title: '预约测试时间',
        type: 'daterange',
        form: {
          component: {
            ...dateRangeBind,
            shortcuts: undefined,
            disabledDate(time) {
              return dayjs(time).startOf('day') < dayjs().startOf('day');
            },
            clearable: true,
          },
          rules: [{ required: true, message: '请选择预约测试时间' }],
          valueBuilder(context) {
            // 构建时
            if (context.form.plan_start_at && context.form.plan_end_at) {
              context.form[context.key] = [context.form.plan_start_at, context.form.plan_end_at];
            }
          },
          valueResolve(context) {
            // 提交时
            context.form.plan_start_at = context.form[context.key][0];
            context.form.plan_end_at = context.form[context.key][1];
          },
        },
      },
      // 语言
      languages: {
        title: '区域语言',
        type: 'dict-select',
        // dict: getLanguageDict(route.meta.value),
        dict: languageDict.value,
        form: {
          col: { span: 24 },
          component: {
            // dict: getLanguageDict(route.meta.value, true),
            dict: languageDictNoDisable.value,
            multiple: true, placeholder: '请选择区域语言',
          },
          rules: [{ required: true, message: '请选择区域语言' }],
        },
      },
      // 识别缺陷类型
      sign_bug_types: {
        title: '识别缺陷类型',
        type: 'dict-select',
        dict: getBugTypeDict(route.meta.value),
        form: {
          col: { span: 24 },
          component: {
            multiple: true,
            placeholder: '请选择识别缺陷类型',
          },
          rules: [{ required: true, message: '请选择识别缺陷类型' }],
        },
      },
      // OCR 检测文本位置
      ocr_detect: {
        title: '检测文本位置',
        type: 'dict-switch',
        form: {
          value: 0,
          helper: '是否需要 OCR 检测文本在文本框内的实际位置',
        },
      },

      /** 测试数据 */
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
            createCrudOptions: () => createCrudOptions(route.meta.value),
          },
        },
      },

      /** 资源配置 */
      // 测试应用
      test_app_file_path: {
        title: '测试应用',
        type: 'file-uploader',
        form: {
          // 「资源配置」整组暂未被后端消费，表单隐藏
          show: false,
          component: {
            limit: 1,
            accept: '.apk,.ipa,.hap,.zip',
          },
          valueBuilder(context) {
            // 构建时
            if (context.form[context.key]) {
              context.form[context.key] = `${import.meta.env.VITE_RESOURCE_API}${context.form[context.key]}`;
            }
          },
          valueResolve(context) {
            // 提交时
            if (context.form[context.key]) {
              const regex = new RegExp(`^${import.meta.env.VITE_RESOURCE_API}`);  // 创建一个正则表达式，匹配开头的 "hello"
              context.form[context.key] = context.form[context.key].replace(regex, '');
            } else {
              // 移除文件后值可能为 null/undefined，归一化为空串避免后端 schema 报错
              context.form[context.key] = '';
            }
          },
        },
      },
      // 测试用例
      test_case_file_path: {
        title: '测试用例',
        type: 'file-uploader',
        form: {
          // 「资源配置」整组暂未被后端消费，表单隐藏
          show: false,
          component: {
            limit: 1,
            accept: '.xlsx',
          },
          valueBuilder(context) {
            // 构建时
            if (context.form[context.key]) {
              context.form[context.key] = `${import.meta.env.VITE_RESOURCE_API}${context.form[context.key]}`;
            }
          },
          valueResolve(context) {
            // 提交时
            if (context.form[context.key]) {
              const regex = new RegExp(`^${import.meta.env.VITE_RESOURCE_API}`);  // 创建一个正则表达式，匹配开头的 "hello"
              context.form[context.key] = context.form[context.key].replace(regex, '');
            } else {
              // 移除文件后值可能为 null/undefined，归一化为空串避免后端 schema 报错
              context.form[context.key] = '';
            }
          },
        },
      },
      // 项目资源
      project_resource: {
        title: '项目资源',
        form: {
          // 「资源配置」整组暂未被后端消费，表单隐藏
          show: false,
          col: { span: 24 },
          valueBuilder(context) {
            // 构建时
            const keys = ['proj_res_type', 'proj_res_repo', 'proj_res_br', 'proj_res_ver'];
            const temp = {};
            keys.forEach((key) => {
              if (context.form[key]) {
                temp[key] = context.form[key];
              }
            });
            context.form[context.key] = JSON.stringify(temp);
          },
          valueResolve(context) {
            // 提交时
            const temp = JSON.parse(context.form[context.key] || '{}');
            Object.entries(temp).forEach(([key, value]) => {
              context.form[key] = value;
            });
          },
        },
      },
      // 译文资源
      translate_resource: {
        title: '译文资源',
        form: {
          // 「资源配置」整组暂未被后端消费，表单隐藏；同时移除必填校验避免按「确定」时被卡住
          show: false,
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

      /** 提单配置 */
      // 缺陷类型
      bill_bug_types: {
        title: '缺陷类型',
        type: 'dict-select',
        dict: getBugTypeDict(route.meta.value),
        form: {
          component: {
            multiple: true,
            placeholder: '识别出这些缺陷类型时自动提单，不选则不提单',
          },
        },
      },
      // 优先级
      priority: {
        title: '优先级',
        type: 'dict-select',
        dict: dict({
          url: '/api/system/enums/bug_priority',
        }),
        form: {
          show: compute(({ form }) => !!form.bill_bug_types.length),
          component: { placeholder: '优先级' },
        },
      },
      // 严重程度
      severity: {
        title: '严重程度',
        type: 'dict-select',
        dict: dict({
          url: '/api/system/enums/bug_severity',
        }),
        form: {
          show: compute(({ form }) => !!form.bill_bug_types.length),
          component: { placeholder: '严重程度' },
        },
      },
      // 发现版本
      version_report: {
        title: '发现版本',
        type: 'dict-select',
        dict: dict({
          data: bugOptions.value.version_report || [],
        }),
        form: {
          show: compute(({ form }) => !!form.bill_bug_types.length),
          component: { placeholder: '发现版本' },
        },
      },
      // 合入版本
      version_fix: {
        title: '修复版本',
        type: 'dict-select',
        dict: dict({
          data: bugOptions.value.version_fix || [],
        }),
        form: {
          show: compute(({ form }) => !!form.bill_bug_types.length),
          component: { placeholder: '修复版本' },
        },
      },
      // 发布计划
      // release_id_value: {
      release_id: {
        title: '发布计划',
        type: 'dict-select',
        dict: dict({
          data: bugOptions.value.release_id || [],
        }),
        form: {
          show: compute(({ form }) => !!form.bill_bug_types.length),
          component: { placeholder: '发布计划' },
        },
      },
      // 处理人
      current_owner: {
        title: '处理人',
        type: 'text',
        form: {
          show: compute(({ form }) => !!form.bill_bug_types.length),
          component: {
            name: <div class="opacity-75">根据配置自动生成</div>,
          },
        },
      },
    },
  };
}
