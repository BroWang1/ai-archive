import { dict } from '@fast-crud/fast-crud';
import { ElMessage } from 'element-plus';
import { useUserStoreHook } from '@/store/modules/user';
import { customRequest } from '@/utils/service.ts';
import { getBugTypeDict } from '@/utils/dict.js';

export default function (route, params, clearRefresh) {
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
      wrapper: {
        title: `批量提单${params.tracker_label ? `（${params.tracker_label}）` : ''}`,
      },
      doSubmit: async ({ form }) => {
        console.log('form submit:', form);
        const data = {
          project_id: route.meta.value,
          image_ids: form.image_ids,
          version_report: form.version_report_value, // 发现版本
          release_id: form.release_id_label, // 发布计划
          version_fix: form.version_fix_value, // 修复版本
          severity: form.severity, // 严重程度
          priority: form.priority, // 优先级
          reporter: useUserStoreHook().name, // 提单人
          bug_types: form.bug_type,
          job_id: params.job_id,
        };
        const res = await customRequest({
          url: '/api/bug/list',
          method: 'post',
          data,
        })
          .catch((err) => {
            ElMessage.error('请求失败,请联系管理员');
            // this.$loading.hide();
            console.log(`batch_create_bug 接口调用失败:${err}`);
            throw err;
          });
        if (res.code === 0) {
          ElMessage.success(res.msg || '操作成功');
          clearRefresh();
          return true;
        }
        ElMessage.warning(res.msg);
        return false;
      },
    },
    columns: {
      // 缺陷类型
      bug_type: {
        title: '缺陷类型',
        type: 'dict-select',
        dict: getBugTypeDict(route.meta.value),
        form: {
          component: {
            multiple: true,
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
          component: { placeholder: '发现版本' },
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
          component: { placeholder: '修复版本' },
        },
      },
      // 发布计划
      // release_id_value: {
      release_id_label: {
        title: '发布计划',
        type: 'dict-select',
        dict: dict({
          data: params.release_id_options,
        }),
        form: {
          component: { placeholder: '发布计划' },
        },
      },
      // 处理人
      current_owner: {
        title: '处理人',
        type: 'text',
        form: {
          component: {
            name: <div class="opacity-75">根据配置自动生成</div>,
          },
        },
      },
    },
  };
}
