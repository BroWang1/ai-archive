import { useCompute } from '@fast-crud/fast-crud';
import { customRequest } from '@/utils/service.ts';
import { useRoute } from 'vue-router';
import { computed, ref, shallowRef } from 'vue';
import { ElMessage } from 'element-plus';
import pako from 'pako';
import { pick } from 'lodash-es';
import { downloadByData } from '@/utils/download.ts';
import { getCommonCols } from '@/views/data/common.jsx';
import numberRange from '@/components/numberRange.vue';

export default function ({ context }) {
  const pageReviews = ref([]);
  const route = useRoute();
  const { compute } = useCompute();
  // @ts-ignore
  const pageRequest = async params => await customRequest({
    url: '/api/data/list',
    method: 'get',
    params: {
      project_id: route.meta.value,
      ...params,
      id: route.query.id || params.id || undefined,
      job_id: params.job_id || undefined,
    },
  }).then((res) => {
    pageReviews.value = res.data.list.filter(item => item.reviewed).map(item => pick(item, ['id', 'revert_img_path']));
    return res;
  });

  const selectedIds = ref([]);
  const onSelectionChange = (changed) => {
    selectedIds.value = changed.map(item => item.id);
  };

  // 此处编辑 crudOptions 配置
  return {
    selectedIds,
    pageReviews,
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
      toolbar: {
        buttons: {
          export: { show: false },
        },
      },
      // search: {
      //   container: {
      //     col: { span: 6 }, // 默认列宽度配置
      //   },
      // },
      table: {
        border: false,
        onSelectionChange,
        // defaultSort: {prop: 'create_time', order: 'descending'}
      },
      form: {
        // 具体可配置请参考 grid 布局： http://www.ruanyifeng.com/blog/2019/03/grid-layout-tutorial.html
        // display: 'grid',
        labelWidth: '100px',
      },
      rowHandle: {
        buttons: {
          edit: { show: false },
          remove: { show: false },
          // 数据
          data: {
            size: 'small',
            title: '',
            type: 'warning',
            plain: true,
            link: true,
            icon: 'tabler:cloud-download',
            text: '数据',
            style: { height: '30px' },
            disabled: compute(({ row }) => !row.file_path),
            show: true,
            order: 1,
            click: ({ row }) => {
              customRequest({
                url: row.file_path,
                method: 'get',
                responseType: row.file_path.endsWith('.gzip') ? 'arraybuffer' : undefined,  // 确保接收的是二进制数据
              }).then((res) => {
                /* eslint-disable */
                if (row.file_path.endsWith('.gzip')) {
                  // 解压缩 GZIP 数据
                  const compressedData = new Uint8Array(res);
                  const decompressedData = pako.inflate(compressedData, { to: 'string' });

                  // 解析后会丢失精度
                  context.jsonViewDialog.value = JSON.parse(decompressedData);
                } else {
                  // json 数据
                  context.jsonViewDialog.value = res;
                }

                // 直接下载
                downloadByData(JSON.stringify(context.jsonViewDialog.value, null, 2), `job-${row.job_id} data-${row.id} 数据.json`);

                // context.jsonViewDialog.title = `${row.id} 数据`;
                // context.jsonViewDialog.visible = true;
                /* eslint-enable */
              })
                .catch((err) => {
                  if (err.response?.status === 403) {
                    ElMessage.error('无权限查看，请联系管理员');
                  } else {
                    ElMessage.error('请求失败,请联系管理员');
                  }
                  console.error(`${row.id} 数据调用失败: ${err}`);
                });
            },
          },
          // 审核
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
            disabled: compute(({ row }) => !row.reviewed),
            order: 1,
            click: ({ row }) => {
              context.imgDrawRef.value.open(row.id, row.revert_img_path);
            },
          },
        },
        width: 140,
      },
      columns: {
        // 多选
        $checked: {
          // title: '选择',
          form: { show: false },
          column: {
            type: 'selection',
            align: 'center',
            width: '60px',
            reserveSelection: true, // 跨页选
            columnSetDisabled: true, // 禁止在列设置中选择
            showOverflowTooltip: false,
            // selectable(row, index) {
            //   return row.id !== 1; // 设置第一行不允许选择
            // },
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
            show: computed(() => !route.query.id),
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

        ...getCommonCols(route.meta.value, context.versionDict),
      },
    },
  };
}
