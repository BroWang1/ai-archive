import { dict, FastCrud, useTypes, setLogger } from '@fast-crud/fast-crud';
import '@fast-crud/fast-crud/dist/style.css';
import { FsExtendsEditor, FsExtendsJson, FsExtendsCopyable, FsExtendsTime, FsExtendsUploader } from '@fast-crud/fast-extends';
import '@fast-crud/fast-extends/dist/style.css';
import UiElement from '@fast-crud/ui-element';
// import API from '@/api';
// import tool from '@/utils/tool';
// import sysConfig from '@/config';
import './style.scss';
import { customRequest } from '@/utils/service';
import { App } from 'vue';

function install(app: App,  options: any = {}) {
  app.use(UiElement);
  setLogger({ level: 'error' });
  // @ts-ignore
  app.use(FastCrud, {
    i18n: options.i18n,
    async dictRequest({ url }) {
      // 获取字典请求
      // @ts-ignore
      const { data } = await customRequest({ url, method: 'get' });
      return data.list;
    },
    /**
     * useCrud时会被执行
     */
    commonOptions() {
      return {
        search: {
          autoSearch: false,
          container: {
            col: { span: 6 }, // 默认列宽度配置
          },
        },
        /** 表格上方 */
        // 「右上」工具栏
        toolbar: {
          compact: false,
          // 导出
          export: {
            onlyShow: true,
            columnBuilder: ({ col }) => {
              col.title = col.title.replace('\n', '');
            // 列构建器，调整列宽
            // col.width = '200px';
            },
          },
          buttons: {
            search: { show: false },
            // compact: { show: false },
            columns: { show: false },
            refresh: { type: '' },
          },
        },
        // 「左上」动作条
        actionbar: {
          buttons: {
            add: {
              title: '',
            },
          },
        },

        // 操作列
        rowHandle: {
          buttons: {
            // 查看
            view: {
              size: 'small',
              title: '',
              icon: 'View',
              text: null,
              style: { height: '30px', width: '32px' },
              tooltip: { content: '查看', enterable: false },
              show: false,
              order: 1,
            },
            // 编辑
            edit: {
              size: 'small',
              title: '',
              icon: 'EditPen',
              text: null,
              style: { height: '30px', width: '32px' },
              tooltip: { content: '编辑', enterable: false },
              order: 2,
            },
            // 删除
            remove: {
              size: 'small',
              title: '',
              icon: 'Delete',
              // class: 'fs-button is-thin',
              text: null,
              style: { height: '30px', width: '32px' },
              // style: { height: "34px" },
              tooltip: { content: '删除', enterable: false },
              order: 3,
            },
            // dropdown: {
            // 	more: {
            // 		size: "default"
            // 	}
            // }
          },
          fixed: 'right',
          align: 'center',
          width: 110,
        },

        table: {
          size: 'default',
          rowKey: 'id',
          showOverflowTooltip: true,
          headerCellStyle: {
            background: '#f5f7fa',
          },
          cellClassName: ({ column }: { column: any }) => {
            if (!column.showOverflowTooltip) {
              return 'no-table-cell-text-ellipsis';
            }
          },
        },

        request: {
          transformQuery: ({ page, form, sort }) => {
            // @ts-ignore
            const order = sort === null ? {} : { orderProp: sort.prop, orderAsc: sort.asc };
            // @ts-ignore
            return { page: page.currentPage, page_size: page.pageSize, ...form, ...order };
          },
          // @ts-ignore
          transformRes: ({ res }) => ({
            currentPage: res.data.page || 1, pageSize: res.data.page_size || res.data?.list?.length || 20,
            total: res.data.total || res.data?.list?.length || 0, records: res.data.list, ...res,
          }),
        },
        // 表单
        form: {
          display: 'flex',
          labelWidth: '94px',
          wrapper: {
            // width: '1000px',
            // 	draggable: true,
          },
        },
      };
    },
  });

  // fast-extends里面的扩展组件均为异步组件，只有在使用时才会被加载，并不会影响首页加载速度
  // 安装editor
  // @ts-ignore
  app.use(FsExtendsEditor, {
    // 编辑器的公共配置
    wangEditor: {},
    quillEditor: {},
  });
  app.use(FsExtendsCopyable);
  app.use(FsExtendsJson);
  app.use(FsExtendsTime);

  // 安装uploader 公共参数
  app.use(FsExtendsUploader, {
    defaultType: 'form',
    form: {
      name: 'file',
      withCredentials: false,
      uploadRequest: async ({ file }) => {
        const data = new FormData();
  			// const token = tool.cookie.get('TOKEN');
        data.append('file', file);
        // data.append('file_type_id', action);
        return await customRequest({
          url: '/api/upload_file',
          method: 'post',
          data,
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        });
      },
      successHandle(ret) {
        return Promise.resolve({ url: `${import.meta.env.VITE_RESOURCE_API}${ret.data.file_path}` });
      },
    },
  });

  // 修改官方字段类型
  // 不要写在页面里，这个是全局的，要写在vue.use(FastCrud)之后
  const { getType } = useTypes();

  /** dict-select */
  const selectType = getType('dict-select');
  // 下拉框
  selectType.form.component.filterable = true; // 可过滤
  selectType.form.component.style = { width: '100%' }; // 宽度 100%
  // values-format
  selectType.column.component.color = 'auto'; // 修改官方的字段类型，设置为支持自动染色
  // selectType.column.component.effect = 'plain';
  selectType.column.component.autoEffects = ['plain'];
  selectType.column.showOverflowTooltip = false;
  selectType.search.component = { collapseTags: true, maxCollapseTags: 3, collapseTagsTooltip: true };

  /** dict-cascader */
  const cascaderType = getType('dict-cascader');
  cascaderType.column.component = {
    name: 'fs-values-format',
    color: 'auto',
    autoEffects: ['plain'],
  };

  /** number */
  // const numberType = getType('number');
  // numberType.form.component['controls-position'] = 'right';

  /** text */
  // const textType = getType('text');
  // textType.search.autoSearchTrigger = true;  // 修改官方的字段类型，设置为文本变化就触发查询

  /** dict-switch */
  const switchType = getType('dict-switch');
  switchType.column.align = 'center';
  const switchOptions = [
    { value: 1, label: '是', color: 'success' },
    { value: 0, label: '否', color: 'error' },
  ];
  switchType.dict = dict({ data: switchOptions });
  switchType.form.component.dict = dict({
    data: switchOptions.map(item => ({ ...item, label: '' })),
  });
  switchType.search.component.dict = dict({ data: switchOptions });

  // image-uploader
  const imageUploaderType = getType('image-uploader');
  imageUploaderType.column.component.style = { height: '100%' };
}

export default {
  install,
};
