import { dict, useCompute, useColumns } from '@fast-crud/fast-crud';
import { customRequest } from '@/utils/service.ts';
import { useRoute, useRouter } from 'vue-router';
import { computed, ref } from 'vue';
import createRegressCrudOptions from './regress.jsx';
import { timeCols } from '@/fast-crud/common.ts';

export default function ({ context }) {
  const route = useRoute();
  const router = useRouter();
  const { compute } = useCompute();
  const delKey = 'is_delete';
  // @ts-ignore
  const pageRequest = async params => await customRequest({
    // url: `/bug/project/${route.meta.value}/get_bugs`,
    url: '/api/bug/list',
    method: 'get',
    params: {
      ...params,
      job_id: route.query.job_id,
      image_id: route.query.image_id,
    },
  });

  // 平台内记录 / Bugzilla / 禅道 的常见状态
  const statusLabels = {
    open: '打开',
    closed: '关闭',
    // Bugzilla
    UNCONFIRMED: '未确认',
    CONFIRMED: '已确认',
    IN_PROGRESS: '处理中',
    RESOLVED: '已解决',
    VERIFIED: '已验证',
    // 禅道
    active: '激活',
    resolved: '已解决',
  };
  const isClosed = row => row.tracker_open === false || row.status === 'closed';
  const trackerDict = dict({ url: '/api/system/enums/bug_tracker' });

  const selectedIds = ref([]);
  const onSelectionChange = (changed) => {
    selectedIds.value = changed.map(item => item.id);
  };

  // 自定义表单配置
  const { buildFormOptions } = useColumns();

  // 此处编辑 crudOptions 配置
  return {
    selectedIds,
    crudOptions: {
      request: {
        pageRequest,
      },
      // 仅在本页面屏蔽 fast-crud 右上角内置的"导出"按钮。
      // 本页面已经在左上角提供了自定义的"导出"按钮（后端生成 Excel，带超链接），
      // 内置的那个按钮点击无响应，容易引起误解，这里单独关掉。
      // 其他页面不受影响。
      toolbar: {
        buttons: {
          export: { show: false },
        },
      },
      actionbar: {
        buttons: {
          add: {
            show: false,
          },
          regress: {
            // size: 'small',
            title: '',
            type: 'warning',
            // plain: true,
            text: '批量回归',
            show: true,
            // order: 0,
            disabled: computed(() => !selectedIds.value.length),
            click: () => {
              const formOptions = buildFormOptions((
                createRegressCrudOptions(route, selectedIds.value, context.clearRefresh)
              ));
              context.formWrapperRef.value.open(formOptions);
            },
          },
        },
      },
      rowHandle: {
        buttons: {
          edit: { show: false }, // 编辑隐藏
          remove: { show: false }, // 删除隐藏
          // 任务详情
          task: {
            size: 'small',
            title: '',
            // type: 'success',
            type: 'primary',
            link: true,
            plain: true,
            icon: 'svg:icon-menu',
            text: '任务',
            style: { height: '30px' },
            // tooltip: { content: '结果审核', enterable: false },
            show: true,
            order: 1,
            click: ({ row }) => {
              const currentRouteArr = route.path.split('/').slice(0, -1);
              currentRouteArr.push(`task?id=${row.job_id}`);
              router.push(currentRouteArr.join('/'));
            },
          },
          // 结果审核
          audit: {
            size: 'small',
            title: '',
            // type: 'success',
            type: 'danger',
            plain: true,
            link: true,
            icon: 'icon-park-outline:audit',
            text: '审核',
            style: { height: '30px' },
            // tooltip: { content: '结果审核', enterable: false },
            show: true,
            order: 1,
            click: ({ row }) => {
              const currentRouteArr = route.path.split('/').slice(0, -1);
              currentRouteArr.push(`image-results?id=${row.image_id}`);
              router.push(currentRouteArr.join('/'));
            },
          },
          // 回归
          regress: {
            size: 'small',
            title: '',
            type: 'denger',
            plain: true,
            link: true,
            icon: 'line-md:backup-restore',
            text: '回归',
            style: { height: '30px' },
            show: true,
            disabled: compute(({ row }) => row[delKey]),
            click: ({ row }) => {
              const formOptions = buildFormOptions(createRegressCrudOptions(route, [row.id], context.clearRefresh));
              context.formWrapperRef.value.open(formOptions);
            },
          },
        },
        align: 'center',
        width: 190,
      },
      table: {
        border: false,
        onSelectionChange,
        // rowClassName: ({ row }) => 'decoration-line-through',
        rowStyle: ({ row }) => (row[delKey] ? { 'text-decoration': 'line-through', opacity: '.6' } : {}),
        // rowStyle: ({ row }) => (row[delKey] ? { opacity: '.5' } : {}),
        // defaultSort: {prop: 'create_time', order: 'descending'}
      },
      form: {
        // 具体可配置请参考 grid 布局： http://www.ruanyifeng.com/blog/2019/03/grid-layout-tutorial.html
        // display: 'grid',
        labelWidth: '90px',
      },
      columns: {
        // 多选
        $checked: {
          // title: '选择',
          form: { show: false },
          column: {
            type: 'selection',
            align: 'center',
            width: '54px',
            reserveSelection: true, // 跨页选
            columnSetDisabled: true, // 禁止在列设置中选择
            showOverflowTooltip: false,
            selectable(row) {
              return !row[delKey];
            },
          },
        },
        // ID
        // id: {
        //   title: 'ID',
        //   type: 'number',
        //   column: { width: 100, align: 'center' },
        //   form: {
        //     component: { placeholder: 'ID' },
        //   },
        //   search: {
        //     show: true,
        //     component: {
        //       name: 'el-input',
        //       type: 'number',
        //     },
        //   },
        // },

        // 标题
        title: {
          title: '标题',
          column: {
            minWidth: 360,
            component: {
              name: compute(({ row }) => (row[delKey] ? 'div' : 'el-link')),
              type: 'primary',
              // link: true,
              href: compute(e => e.row.external_url || undefined),
              target: '_blank',
              slots: {
                default: compute(e => e.row.title),
              },
              // style: {
              //   marginBottom: '3px',
              // },
            },
          },
          search: {
            show: true,
            component: { placeholder: '模糊搜索' },
          },
        },
        // 严重程度
        severity: {
          title: '严重程度',
          type: 'dict-select',
          dict: dict({
            url: '/api/system/enums/bug_severity',
          }),
          column: {
            align: 'center',
            component: {
              type: compute(({ row }) => (row[delKey] ? 'text' : 'tag')),
            },
          },
          form: {
            component: { placeholder: '严重程度' },
          },
          // search: {
          //   show: true,
          // },
        },
        // 缺陷系统
        tracker: {
          title: '缺陷系统',
          type: 'dict-select',
          dict: trackerDict,
          column: { align: 'center', width: 110 },
        },
        // 缺陷ID
        external_id: {
          title: '缺陷ID',
          type: 'text',
          column: { align: 'center', width: 90 },
        },
        // 缺陷状态（优先显示缺陷系统中的实时状态）
        status_text: {
          title: '缺陷状态',
          type: 'text',
          valueBuilder({ row }) {
            let text;
            if (row.bill_status === 2) {
              text = '提单失败';
            } else if (row.bill_status === 0) {
              text = '提单中';
            } else {
              const raw = row.tracker_status || row.status || '';
              text = statusLabels[raw] || raw;
            }
            // eslint-disable-next-line no-param-reassign
            row.status_text = text;
          },
          column: {
            align: 'center',
            sortable: true,
            showOverflowTooltip: true,
            component: {
              name: 'el-tooltip',
              content: compute(({ row }) => row.bill_text || row.status_text || ''),
              disabled: compute(({ row }) => !row.bill_text),
              slots: { default: compute(({ row }) => row.status_text) },
            },
          },
        },
        // 提单人
        reporter: {
          title: '提单人',
          type: 'text',
        },
        // 处理人
        current_owner: {
          title: '处理人',
          type: 'text',
        },
        // 发现版本
        version_report: {
          title: '发现版本',
          type: 'text',
        },
        // 合入版本
        version_fix: {
          title: '修复版本',
          type: 'text',
        },
        // 发布计划
        release_id: {
          title: '发布计划',
          type: 'text',
        },
        // 回归状态
        human_local_bug_status: {
          title: '回归状态',
          type: 'dict-select',
          dict: dict({
            data: [
              { value: '无需回归', label: '无需回归', color: 'info' },
              { value: '等待回归', label: '等待回归', color: '' },
              { value: '回归中', label: '回归中', color: 'warning' },
              { value: '回归成功', label: '回归成功', color: 'success' },
              { value: '回归失败', label: '回归失败', color: 'error' },
            ],
          }),
          valueBuilder({ row }) {
            let humanText = '';
            if (row.regress_status === 1 && isClosed(row)) {
              humanText = '无需回归';
            } else if (row.regress_status === 1 && !isClosed(row)) {
              humanText = '等待回归';
            } else if (row.regress_status === 2) {
              humanText = '回归中';
            } else if (row.regress_status === 3) {
              humanText = '回归成功';
            } else if (row.regress_status === 4) {
              humanText = '回归失败';
            }
            // eslint-disable-next-line no-param-reassign
            row.human_local_bug_status = humanText;
          },
          column: {
            sortable: true,
            component: {
              name: 'fs-values-format',
            },
          },
        },

        ...timeCols,

        // 回归任务
        regress_job_ids: {
          title: '回归任务',
          type: 'text',
          column: {
            width: 180,
            showOverflowTooltip: false,
          },
        },
      },
    },
  };
}
