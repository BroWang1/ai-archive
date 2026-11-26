import { dict, useCompute } from '@fast-crud/fast-crud';
import { ElMessage } from 'element-plus';
import { useUserStoreHook } from '@/store/modules/user';
import { customRequest } from '@/utils/service.ts';
import { cloneDeep, debounce } from 'lodash-es';
import { getBasicInfo } from '@/views/task/audit/common.js';
import { shallowRef } from 'vue';
import scEditor from '@/components/scEditor/index.vue';

export default function (route, params, parentCrudExpose, bugTypes) {
  const { compute } = useCompute();

  // [新增] 根据配置动态构建自定义字段的 columns
  // params.customFields 来自基础配置页面的 ProjectConfigCustomField 表
  // 每个启用的自定义字段会在提单表单中渲染为一个可搜索的下拉选择框
  //
  // options 元素约定两种格式（在设置页写入）：
  //   1) "中文|英文"  —— 用户看到"中文"，选中后提交"英文"（如禅道的 "代码错误|codeerror"）
  //   2) "值"         —— label 与 value 相同（用户手输场景或缺陷系统本就无中文映射）
  // 这里统一拆成 { value, label } 对象供 dict-select 渲染
  const parseOption = (opt) => {
    if (typeof opt !== 'string') {
      return { value: String(opt), label: String(opt) };
    }
    const idx = opt.indexOf('|');
    if (idx > 0) {
      return { label: opt.slice(0, idx), value: opt.slice(idx + 1) };
    }
    return { value: opt, label: opt };
  };
  const customFieldColumns = {};
  if (params.customFields && params.customFields.length) {
    params.customFields.forEach((field) => {
      if (field.enable) {
        // fieldKey 加 custom_ 前缀避免与内置字段冲突
        const fieldKey = `custom_${field.field_key}`;
        customFieldColumns[fieldKey] = {
          title: field.field_name,  // 显示的标题
          type: 'dict-select',
          dict: dict({
            data: (field.options || []).map(parseOption),
          }),
          form: {
            component: {
              placeholder: '搜索',
              filterable: true,       // 支持搜索过滤
              allowCreate: true,      // 允许手动输入新值
              defaultFirstOption: true,
              clearable: true,
            },
          },
        };
      }
    });
  }

  return {
    table: {
      border: false,
    },
    search: {
      show: false,
    },
    form: {
      wrapper: {
        title: `${params.image_name} 提单${params.tracker_label ? `（${params.tracker_label}）` : ''}`,
        zIndex: 1003,
        top: '5vh',
        width: '70%',
        draggable: true,
        customClass: 'bug-submit-dialog',
      },
      doSubmit: async ({ form }) => {
        console.log('form submit:', form);
        const data = {
          project_id: route.meta.value,
          title: params.fix_title + form.title,
          description: form.description,
          version_report: form.version_report_value !== undefined ? form.version_report_value : undefined,
          release_id: form.release_id_label !== undefined ? form.release_id_label : undefined,
          version_fix: form.version_fix_value !== undefined ? form.version_fix_value : undefined,
          severity: form.severity !== undefined ? form.severity : undefined,
          priority: form.priority !== undefined ? form.priority : undefined,
          reporter: useUserStoreHook().name,
          current_owner: form.current_owner,
          raw_image_path: params.raw_image_path,
          image_id: params.image_id,
          job_id: params.job_id,
          ai_image_path: params.AI_image_path,
          key_in_bug: params.Key_in_bug,
        };
        // 收集自定义字段值，组装为 {field_key: 选中的值} 格式
        // 后端会将这些字段原样附加到缺陷系统创建 Bug 的请求体中
        const customFieldValues = {};
        if (params.customFields && params.customFields.length) {
          params.customFields.forEach((field) => {
            if (field.enable) {
              const fieldKey = `custom_${field.field_key}`;
              // 修复：使用 !== undefined 判断，避免将 0、false、空字符串等合法值错误排除
              if (form[fieldKey] !== undefined) {
                customFieldValues[field.field_key] = form[fieldKey];
              }
            }
          });
        }
        if (Object.keys(customFieldValues).length > 0) {
          data.custom_fields = customFieldValues;
        }

        const res = await customRequest({
          url: '/api/bug/entity',
          method: 'post',
          data,
        })
          .catch((err) => {
            ElMessage.error('创建 bug 失败,请确认图片正常显示');
            console.log(`/bug/project/${route.meta.value}/create 接口调用失败: ${err}`);
            throw err;
          });
        if (res.code === 0) {
          ElMessage.success(res.msg || '创建成功');
          parentCrudExpose.doRefresh();
          return true;
        }
        ElMessage.warning('创建bug失败');
        return false;
      },
    },
    columns: {
      // 缺陷类型
      bug_types: {
        title: '缺陷类型',
        type: 'dict-select',
        dict: dict({
          url: `/api/project/config?_=${Math.random()}`,
          async getData() {
            const res = await customRequest({
              url: '/api/project/config',
              method: 'get',
              params: { project_id: route.meta.value, cate: 'BugType' },
            });
            return res.data.list.filter(item => cloneDeep(bugTypes).includes(item.value)).map(item => ({
              ...item, label: item.enable ? item.label : `${item.label}（未启用）`,
              color: item.enable ? undefined : 'info',
              effect: item.enable ? undefined : 'light',
              disabled: !item.enable,
            }));
          },
        }),
        form: {
          col: { span: 24 },
          helper: '用于生成基础信息',
          component: {
            multiple: true,
            placeholder: '请选择缺陷类型',
          },
          valueChange: debounce(async ({ form }) => {
            await getBasicInfo(route.meta.value, params.image_id, form);
          }, 1000),
        },
      },
      // 名称
      title: {
        title: '名称',
        type: 'text',
        form: {
          col: { span: 24 },
          component: {
            placeholder: '请填写名称',
            slots: {
              prepend: compute(e => e.form.fix_title),
            },
          },
          rules: [{ required: true, message: '请填写名称' }],
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
          component: { placeholder: '严重程度' },
        },
      },
      // 发现版本
      version_report_value: {
        title: '发现版本',
        type: 'dict-select',
        dict: dict({
          data: params.version_report_options,
        }),
        form: {
          component: {
            allowCreate: true,
            defaultFirstOption: true,
            placeholder: '发现版本',
          },
        },
      },
      // 修复版本
      version_fix_value: {
        title: '修复版本',
        type: 'dict-select',
        dict: dict({
          data: params.version_fix_options,
        }),
        form: {
          component: {
            allowCreate: true,
            defaultFirstOption: true,
            placeholder: '修复版本',
          },
        },
      },
      // 发布计划
      release_id_label: {
        title: '发布计划',
        type: 'dict-select',
        dict: dict({
          data: params.release_id_options,
        }),
        form: {
          component: {
            allowCreate: true,
            defaultFirstOption: true,
            placeholder: '发布计划',
          },
        },
      },
      // 动态自定义字段（插入在发布计划和处理人之间）
      ...customFieldColumns,
      // 处理人
      current_owner: {
        title: '处理人',
        type: 'text',
        form: {
          component: {
            placeholder: '缺陷系统中的账号（Bugzilla 为邮箱），多个用逗号分隔',
          },
          rules: [{ required: true, message: '请填写处理人' }],
        },
      },
      // 缺陷描述
      description: {
        title: '缺陷描述',
        type: 'textarea',
        form: {
          col: { span: 24 },
          component: {
            name: shallowRef(scEditor),
            placeholder: '请填写缺陷描述',
            maxlength: 5000,
            showWordLimit: true,
            autosize: {
              minRows: 20,
            },
          },
          rules: [{ required: true, message: '请填写缺陷描述' }],
        },
      },
    },
  };
}
