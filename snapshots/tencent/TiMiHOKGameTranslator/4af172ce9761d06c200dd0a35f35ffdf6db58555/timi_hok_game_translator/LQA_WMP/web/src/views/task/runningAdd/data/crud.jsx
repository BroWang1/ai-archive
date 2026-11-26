import { dict } from '@fast-crud/fast-crud';
import { customRequest } from '@/utils/service.ts';
import { getCommonCols } from '@/views/data/common.jsx';
import { shallowRef } from 'vue';
import numberRange from '@/components/numberRange.vue';

export default function (projectId, selectedIds) {
  // @ts-ignore
  const pageRequest = async params => await customRequest({
    url: '/api/data/list',
    method: 'get',
    params: {
      project_id: projectId,
      ...params,
      id: params.id || undefined,
      job_id: params.job_id || undefined,
    },
  });

  // 此处编辑 crudOptions 配置
  return {
    crudOptions: {
      request: {
        pageRequest,
      },
      pagination: {
        pageSize: 10, // 默认pageSize
      },
      actionbar: {
        buttons: {
          add: {
            show: false,
          },
        },
      },
      table: {
        showOverflowTooltip: false,
        border: false,
      },
      form: {
        // 具体可配置请参考 grid 布局： http://www.ruanyifeng.com/blog/2019/03/grid-layout-tutorial.html
        // display: 'grid',
        labelWidth: '100px',
      },
      rowHandle: {
        show: false,
      },
      columns: {
        $checked: {
          column: {
            selectable: row => !(selectedIds || []).includes(row.id),
          },
        },
        // ID
        id: {
          title: 'ID',
          type: 'number',
          column: { width: 100, align: 'right' },
          form: {
            component: { placeholder: 'ID' },
          },
          search: {
            show: true,
            value: ['', ''],
            component: {
              name: shallowRef(numberRange),
            },
            valueResolve(e) {
              e.form.pk__gte = (e.form[e.key] || [])[0] ? e.form[e.key][0] : undefined;
              e.form.pk__lte = (e.form[e.key] || [])[1] ? e.form[e.key][1] : undefined;
              e.form[e.key] = undefined;
            },
          },
        },

        ...getCommonCols(
          projectId,
          dict({
            url: '/api/data/resource_version/list',
            cache: false,
            async getData({ url }) {
            // 获取字典请求
            // @ts-ignore
              const { data } = await customRequest({ url, method: 'get', params: { project_id: projectId } });
              return data.list.map(item => ({ label: item, value: item }));
            },
          }),
        ),
      },
    },
  };
}
