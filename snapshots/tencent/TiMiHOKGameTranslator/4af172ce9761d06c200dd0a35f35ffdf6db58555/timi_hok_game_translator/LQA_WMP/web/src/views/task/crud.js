import { dict, useCompute } from '@fast-crud/fast-crud';
import { customRequest } from '@/utils/service.ts';
import { useRoute, useRouter } from 'vue-router';
import { getLanguageDict, getUserDict } from '@/utils/dict.js';
import { dateRangeBind } from '@/utils/bind/date.js';
import dayjs from 'dayjs';
import { isDevMode } from '@/utils/env.ts';
import { computed, ref, nextTick } from 'vue';
import { ElMessageBox, ElMessage } from 'element-plus';
import { timeCols } from '@/fast-crud/common.ts';
import { runJob } from '@/utils/runner.js';

export default function ({ expose, context }) {
  const route = useRoute();
  const router = useRouter();
  const dataLen = ref(0);
  const expandSingleKey = ref();
  const { compute } = useCompute();
  // @ts-ignore
  const pageRequest = async params => await customRequest({
    url: '/api/job/list',
    method: 'get',
    params: {
      project_id: route.meta.value,
      ...params,
      id: route.query.id || params.id || undefined,
      module_id: params.module_ids || undefined,
    },
  }).then((res) => {
    dataLen.value = res.data.list.length;
    if (dataLen.value > 1) {
      res.data.list.forEach(item => item.hasChildren = !!item.regress_num);
    }
    nextTick(() => {
      if (dataLen.value === 1 && res.data.list[0].regress_num) {
        expandSingleKey.value = res.data.list[0].id;
      } else {
        expandSingleKey.value = undefined;
      }
    });
    return res;
  });

  // 此处编辑 crudOptions 配置
  return {
    crudOptions: {
      request: {
        pageRequest,
      },
      actionbar: {
        buttons: {
          add: {
            show: false,
          },
        },
      },
      rowHandle: {
        buttons: {
          // 查看
          view: {
            show: true,
            link: true,
            // text: '查看',
            style: { height: '30px', width: 'auto' },
            // tooltip: null,
            // style: {
            //   scale: 0.75,
            // },
            click: context.openViewTask,
          },
          // 编辑
          edit: {
            link: true,
            style: { height: '30px', width: 'auto' },
            click: context.openEditTask,
            order: 1,
            // 1 - 未执行 - 编辑
            // 2 - 执行中 - 追加
            disabled: compute(({ row }) => ![1, 2].includes(row.status)),
            tooltip: compute(({ row }) => (
              [1, 2].includes(row.status) ? { content: '编辑', enterable: false } : null
            )),
          },
          // 执行进度
          progress: {
            size: 'small',
            title: '',
            type: 'primary',
            plain: true,
            link: true,
            icon: 'uil:process',
            text: '',
            style: { height: '30px' },
            tooltip: { content: '执行进度', enterable: false },
            click: context.openProgress,
          },
          // 删除隐藏
          remove: { show: false },
          // 开始
          start: {
            size: 'small',
            title: '',
            type: 'primary',
            plain: true,
            link: true,
            icon: 'akar-icons:play',
            text: '',
            style: { height: '30px' },
            tooltip: compute(({ row }) => (
              row.status === 1 ? { content: '开始', enterable: false } : null
            )),
            loading: compute(({ row }) => row.loading),
            // 未执行展示
            show: compute(({ row }) => row.status === 1),
            order: 1,
            click: (scope) => {
              scope.row.loading = true;
              runJob(scope.row.id, 'start')
                .then((msg) => {
                  ElMessage.success(msg);
                  expose.doRefresh();
                })
                .catch((err) => {
                  // 后端业务错误已由请求拦截器提示，这里只提示 Webhook 调用失败
                  if (!err?.response) ElMessageBox.alert(err.message, '启动失败', { type: 'error' });
                  console.log(`任务开始调用失败: ${err}`);
                })
                .finally(() => {
                  scope.row.loading = false;
                });
            },
          },
          // 结束
          stop: {
            size: 'small',
            title: '',
            type: 'danger',
            plain: true,
            link: true,
            icon: 'ph:stop-circle-bold',
            text: '',
            style: { height: '30px' },
            tooltip: { content: '结束', enterable: false },
            loading: compute(({ row }) => row.loading),
            // 仅执行中展示
            show: compute(({ row }) => row.status === 2),
            order: 1,
            click: (scope) => {
              scope.row.loading = true;
              customRequest({
                url: '/api/job/action',
                method: 'post',
                data: {
                  action: 'stop',
                  job_id: scope.row.id,
                },
              })
                .then((res) => {
                  if (res.code === 0) {
                    ElMessage.success(res.msg || '操作成功');
                    expose.doRefresh();
                  } else {
                    ElMessage.warning(res.msg);
                  }
                })
                .catch((err) => {
                  console.log(`任务结束调用失败: ${err}`);
                })
                .finally(() => {
                  scope.row.loading = false;
                });
            },
          },
          // 重试
          retry: {
            size: 'small',
            title: '',
            type: 'primary',
            plain: true,
            link: true,
            icon: 'mdi:reload',
            text: '',
            style: { height: '30px' },
            tooltip: { content: '重试', enterable: false },
            loading: compute(({ row }) => row.loading),
            show: true,
            order: 1,
            click: (scope) => {
              ElMessageBox.confirm(
                `${scope.row.status === 2 ? '任务运行中,是否需要重试?' : '任务重试,未生成图片的数据继续生成,是否需要执行?'}`,
                '提示',
                {
                  confirmButtonText: '确定',
                  cancelButtonText: '取消',
                  type: 'warning',
                },
              ).then(() => {
                scope.row.loading = true;
                runJob(scope.row.id, 'retry')
                  .then((msg) => {
                    ElMessage.success(msg);
                    expose.doRefresh();
                  })
                  .catch((err) => {
                    if (!err?.response) ElMessageBox.alert(err.message, '重试失败', { type: 'error' });
                    console.log(`任务重试调用失败: ${err}`);
                  })
                  .finally(() => {
                    scope.row.loading = false;
                  });
              });
            },
          },
          // 结果审核
          audit: {
            size: 'small',
            title: '',
            // type: 'success',
            type: 'primary',
            link: true,
            plain: true,
            icon: 'icon-park-outline:audit',
            text: '审核',
            style: { height: '30px' },
            // tooltip: { content: '结果审核', enterable: false },
            show: true,
            order: 1,
            click: ({ row }) => {
              const currentRouteArr = route.path.split('/').slice(0, -1);
              currentRouteArr.push(`image-results?job_id=${row.id}`);
              router.push(currentRouteArr.join('/'));
            },
          },
          // 缺陷单
          bugs: {
            size: 'small',
            title: '',
            type: 'danger',
            plain: true,
            link: true,
            icon: 'cil:bug',
            text: '缺陷',
            style: { height: '30px' },
            show: true,
            order: 1,
            click: ({ row }) => {
              const currentRouteArr = route.path.split('/').slice(0, -1);
              currentRouteArr.push(`bugs?job_id=${row.id}`);
              router.push(currentRouteArr.join('/'));
            },
          },
        },
        align: 'center',
        width: 260,
      },
      table: {
        border: false,
        lazy: computed(() => dataLen.value > 1),
        load: (row, treeNode, resolve) => {
          customRequest({
            url: '/api/job/list',
            method: 'get',
            params: {
              project_id: route.meta.value,
              id: row.id,
            },
          }).then((res) => {
            resolve(res.data.list[0].children);
          });
        },
        defaultExpandAll: computed(() => dataLen.value === 1),
        expandRowKeys: computed(() => (expandSingleKey.value ? [expandSingleKey.value] : undefined)),
        // defaultExpandAll: true454
        // defaultSort: {prop: 'create_time', order: 'descending'}
      },
      form: {
        // 具体可配置请参考 grid 布局： http://www.ruanyifeng.com/blog/2019/03/grid-layout-tutorial.html
        // display: 'grid',
        labelWidth: '100px',
      },
      columns: {
        // 时间范围
        times: {
          title: '时间',
          type: 'daterange',
          column: {
            show: false,
          },
          form: {
            component: {
              ...dateRangeBind,
              clearable: true,
            },
            show: false,
          },
          search: {
            show: computed(() => !route.query.id),
            value: [
              dayjs()
                .subtract(3, isDevMode() ? 'year' : 'month')
                .format('YYYY-MM-DD'),
              dayjs().format('YYYY-MM-DD'),
            ],
            valueResolve({ value, form }) {
              //  <------注意这里是form，不是row
              if (value && value.length === 2) {
                form.begin_at = dayjs(value[0]).startOf('day')
                  .format('YYYY-MM-DD HH:mm:ss');
                form.end_at = dayjs(value[1]).endOf('day')
                  .format('YYYY-MM-DD HH:mm:ss');
              }
            },
            // style: { width: '288px' },
          },
        },

        // ID
        id: {
          title: 'ID',
          type: 'number',
          column: { width: 100, align: 'center' },
          form: {
            component: { placeholder: 'ID' },
          },
          search: {
            show: computed(() => !route.query.id),
            component: {
              name: 'el-input',
              type: 'number',
            },
          },
        },

        // 名称
        name: {
          title: '名称',
          type: 'text',
          column: {
            width: 180,
          },
          search: {
            show: true,
            component: { placeholder: '模糊搜索' },
          },
        },
        // 模块（任务管理页暂未落地任务-模块关联，先隐藏列表列与顶部筛选，仅此页面隐藏，不影响其他页面）
        module_ids: {
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
          column: { show: false, align: 'center' },
          form: {
            component: {
              multiple: true,
              placeholder: '模块',
            },
          },
          search: {
            show: false,
            component: {
              multiple: false,
            },
          },
        },
        // 区域语言
        languages: {
          title: '区域语言',
          type: 'dict-select',
          dict: getLanguageDict(route.meta.value),
          column: {
            align: 'center',
            width: '200px',
            showOverflowTooltip: false,
          },
          form: {
            component: {
              dict: getLanguageDict(route.meta.value, true),
              placeholder: '区域语言',
            },
          },
          search: {
            show: true,
            valueResolve(e) {
              e.form.language = e.form[e.key];
            },
          },
        },
        // 状态
        status: {
          title: '状态',
          type: 'dict-select',
          search: { show: true },
          dict: context.statusDict,
          column: { align: 'center' },
          form: {
            component: { placeholder: '状态' },
          },
        },

        // 进度
        progress_rate: {
          title: '进度',
          type: 'text',
          column: { show: false },
        },
        // 缺陷数
        bug_num: {
          title: '缺陷数',
          type: 'text',
          column: { align: 'right' },
        },
        // 是否回归
        is_parent: {
          title: '回归',
          type: 'dict-select',
          dict: dict({
            data: [
              { label: '否', value: 0 },
              { label: '是', value: 1 },
            ],
          }),
          column: { show: false },
          search: {
            show: true,
            value: 0,
            component: {
              clearable: false,
            },
          },
        },
        // 回归任务数
        regress_num: {
          title: '回归任务数',
          type: 'number',
          column: { align: 'right' },
          valueBuilder({ row }) {
            // value构建，就是把后台传过来的值转化为前端组件所需要的值
            // 在pageRequest之后执行转化，然后将转化后的数据放到table里面显示
            row.regress_num = row.regress_num || 0;
          },
        },
        // 创建人
        creator_id: {
          title: '创建人',
          type: 'dict-select',
          dict: getUserDict(),
          column: {
            component: {
              type: 'text',
            },
          },
          search: {
            show: true,
            component: {
              allowCreate: true,
              defaultFirstOption: true,
              placeholder: '创建人',
            },
          },
        },

        ...timeCols,

        // 版本号
        resource_version: {
          title: '版本号',
          type: 'text',
          column: { show: false },
        },
        // 外部构建（Webhook 返回）
        build_id: {
          title: '外部构建',
          type: 'text',
          column: { show: false },
        },
        // 选取的数据 id
        data_ids: {
          title: '选取的数据 id',
          type: 'text',
          column: { show: false },
          form: { col: { span: 24 } },
          valueBuilder({ row }) {
            // value构建，就是把后台传过来的值转化为前端组件所需要的值
            // 在pageRequest之后执行转化，然后将转化后的数据放到table里面显示
            if (row.type === 'GeneratePictureByVersion') {
              row.data_ids = [];
            }
          },
        },
        // SVN 地址
        svn_url: {
          title: 'SVN 地址',
          type: 'text',
          column: { show: false },
          form: { col: { span: 24 } },
        },
        // SVN 版本号
        svn_version: {
          title: 'SVN 版本号',
          type: 'text',
          column: { show: false },
          form: { col: { span: 24 } },
        },

        /** 执行信息 */
        infoTable: {
          title: '',
          form: {
            labelWidth: '0px',
            col: { span: 24 },
          },
        },
      },
    },
  };
}
