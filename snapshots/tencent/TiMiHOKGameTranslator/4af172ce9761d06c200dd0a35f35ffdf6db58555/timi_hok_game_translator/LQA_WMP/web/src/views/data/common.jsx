import AutoPopover from '@/components/autoPopover.vue';
import { customRequest } from '@/utils/service.ts';
import { dateRangeBind } from '@/utils/bind/date.js';
import { dict } from '@fast-crud/fast-crud';
import { timeCols } from '@/fast-crud/common.ts';
import dayjs from 'dayjs';

export function getCommonCols(projectId, versionDict) {
  return {
    // 任务 ID
    job_id: {
      title: '任务 ID',
      type: 'number',
      column: { width: 100, align: 'right' },
      form: {
        component: { placeholder: '任务 ID' },
      },
      search: {
        show: true,
        component: {
          name: 'fs-dict-select',
          filterable: true,
          allowCreate: true,
          clearable: true,
          defaultFirstOption: true,
          renderLabel(e) {
            return <div>
              <span class="font-bold">{e.id}</span> -
              <span> {e.name}</span>
              <span>（{dayjs(e.created_at).format('YYYY-MM-DD HH:mm:ss')}）</span>
            </div>;
          },
          dict: dict({
            url: '/api/job/list',
            async getData({ url }) {
              const res = await customRequest({
                url,
                method: 'get',
                params: {
                  project_id: projectId,
                  page_size: 10,
                },
              });
              if (res.code === 0) {
                return res.data.list.map(item => ({
                  value: `${item.id}`,
                  // label: `${item.id} - ${item.name}1（${dayjs(item.created_at).format('YYYY-MM-DD HH:mm:ss')}）`,
                  ...item,
                }));
              }
              return [];
            },
          }),
        },
      },
    },

    // 名称
    name: {
      title: '名称',
      type: 'text',
      column: {
        component: {
          name: AutoPopover,
          vModel: 'value',
        },
        showOverflowTooltip: false,
      },
      search: {
        show: true,
        component: {
          placeholder: '模糊搜索',
        },
      },
    },

    // 采集图片
    shot_img_path: {
      title: '采集图片',
      type: 'image-uploader',
      column: {
        width: 300,
        align: 'center',
        component: {
          buildUrl(val) {
            return `${import.meta.env.VITE_RESOURCE_API}${val}`;
          },
        },
      },
    },

    // 还原图片
    revert_img_path: {
      title: '还原图片',
      type: 'image-uploader',
      column: {
        width: 300,
        align: 'center',
        component: {
          buildUrl(val) {
            return `${import.meta.env.VITE_RESOURCE_API}${val}`;
          },
        },
      },
    },

    // 资源版本
    resource_version: {
      title: '资源版本',
      type: 'dict-select',
      column: { width: 150 },
      form: {
        component: {
          placeholder: '资源版本',
        },
      },
      search: {
        show: true,
        component: {
          dict: versionDict,
        },
      },
    },
    // 模块
    module_id: {
      title: '模块',
      type: 'dict-select',
      dict: dict({
        url: `/api/project/module/list?project_id=${projectId}&all=1`,
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
        width: 200,
        align: 'center',
      },
      form: {
        component: { placeholder: '模块' },
      },
      search: { show: true },
    },
    // 数据审核状态（这条数据的原始标注框是否已被人工 review 过；注意：这不是用来手动添加 bug 的入口）
    reviewed: {
      title: '数据审核状态',
      type: 'dict-select',
      dict: dict({
        data: [
          { value: 0, label: '未审核' },
          { value: 1, label: '已审核' },
        ],
      }),
      column: { show: false },
      form: {
        component: { placeholder: '数据审核状态' },
      },
      search: { show: true },
    },
    // 机器型号
    'device.phone_type': {
      title: '机器型号',
      type: 'text',
      column: { width: 300 },
    },
    ...timeCols,
    // 创建时间
    time: {
      title: '创建时间',
      type: 'datetimerange',
      column: { show: false },
      form: { show: false },
      search: {
        show: true,
        // value: [
        //   dayjs().subtract(3, isDevMode() ? 'year' : 'month')
        //     .format('YYYY-MM-DD'),
        //   dayjs().format('YYYY-MM-DD'),
        // ],
        component: {
          ...dateRangeBind,
          clearable: true,
        },
        valueResolve({ value, form }) {  //  <------注意这里是form，不是row
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
  };
}
