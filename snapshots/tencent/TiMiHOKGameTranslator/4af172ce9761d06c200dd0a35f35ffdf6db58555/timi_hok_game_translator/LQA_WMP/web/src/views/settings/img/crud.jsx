import { customRequest } from '@/utils/service';
import { useRoute } from 'vue-router';
import { isValidPath } from '@/utils/validate';
import langPathTable from './langPathTable.vue';
import { shallowRef } from 'vue';

export default function ({ crudExpose, context }) {
  const route = useRoute();

  const addRequest = async ({ form }) => {
    await customRequest({
      url: '/api/project/config?cate=ImgRevert',
      method: 'post',
      data: {
        ...form,
        lang_path: JSON.stringify(form.lang_path),
        project_id: context.project_id,
      },
    }).finally(() => {
      crudExpose.doRefresh();
    });
  };
  const editRequest = async ({ form }) => {
    await customRequest({
      url: '/api/project/config?cate=ImgRevert',
      method: 'patch',
      data: {
        ...form,
        lang_path: JSON.stringify(form.lang_path),
      },
    }).finally(() => {
      crudExpose.doRefresh();
    });
  };
  const delRequest = async ({ row }) => {
    await customRequest({
      url: '/api/project/config?cate=ImgRevert',
      method: 'delete',
      data: {
        ids: [row.id],
        project_id: context.project_id,
      },
    }).finally(() => {
      crudExpose.doRefresh();
    });
  };

  /** 文件根路径校验 */
  const validateRootPath = (rule, value, callback) => {
    if (!value) {
      callback(new Error('请填写文件根路径'));
      return;
    }
    if (!isValidPath(value)) {
      callback(new Error('路径格式不合法'));
      return;
    }
    callback();
  };

  /** 自定义校验 */
  const validateLangPath = (rule, value, callback) => {
    for (let i = 0; i < value.length; i++) {
      const allHasValue = Object.values(value[i]).every(item => !!item);
      if (!allHasValue) {
        callback(new Error('请填写必填字段'));
        return;
      }
      // 校验每行的 配置路径(filePath) 格式
      if (!isValidPath(value[i].filePath)) {
        callback(new Error(' '));
        return;
      }
    }
    callback();
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
      editable: {
        enabled: false,
        mode: 'row',
        activeTrigger: false,
      },
      table: {
        border: false,
        // defaultSort: {prop: 'create_time', order: 'descending'}
      },
      form: {
        group: {
          groupType: 'collapse', // collapse， tabs
          accordion: false,
          groups: {
            img: {
              title: '图片还原',
              columns: ['root_path', 'key', 'text', 'no_trans_text'],
            },
            info: {
              title: '翻译配置',
              columns: ['lang_path'],
            },
            // custom: {
            //   title: "自定义",
            //   collapsed: false,
            //   show(context) {
            //     console.log("custom context", context);
            //     return context.mode === "view";
            //   },
            //   disabled: false,
            //   icon: "el-icon-warning-outline",
            //   columns: ["custom", "custom2"]
            // }
          },
        },
      },
      search: {
        show: false,
      },
      columns: {
        $expand: {
          title: '',
          form: { show: false },
          column: {
            type: 'expand',
            align: 'center',
            width: '55px',
            columnSetDisabled: true, // 禁止在列设置中选择
            exportable: false, // 不能导出
          },
        },
        // ID
        // id: {
        //   title: 'ID',
        //   type: 'number',
        //   column: { width: 64, align: 'center' },
        //   form: { show: false },
        // },
        // 根路径
        root_path: {
          title: '文件根路径',
          type: 'text',
          form: {
            component: { placeholder: '请填写文件根路径' },
            rules: [
              { required: true, message: '请填写文件根路径' },
              { validator: validateRootPath, trigger: 'blur' },
            ],
          },
        },
        // key 列
        key: {
          title: 'key 列',
          type: 'text',
          form: {
            component: { placeholder: '请填写 key 列' },
            rules: [{ required: true, message: '请填写 key 列' }],
          },
        },
        // 描述列
        text: {
          title: '描述列',
          type: 'text',
          form: {
            component: { placeholder: '请填写描述列' },
            rules: [{ required: true, message: '请填写描述列' }],
          },
        },
        // 排除标识
        no_trans_text: {
          title: '排除标识',
          type: 'text',
          form: {
            component: { placeholder: '排除标识' },
          },
        },
        lang_path: {
          title: '',
          column: { show: false },
          form: {
            col: { span: 24 },
            // labelWidth: '0px',
            component: {
              name: shallowRef(langPathTable),
              projectId: route.meta.value,
              vModel: 'modelValue',
              addTemplate: { code_raw: '', code: '', filePath: ''  },
              dragSort: true,
              // slots: {
              //   default: () => (
              //     [
              //       // 语言
              //       <el-table-column prop={'code_raw'} label={'语言'}>
              //         {scope => <el-select
              //             modelValue={scope.row.code_raw} onUpdate:modelValue={val => scope.row.code_raw = val}
              //             placeholder="请选择语言"
              //           >
              // eslint-disable-next-line
              //           {langCodeOptions.value.map(item => <el-option label={item.code_raw} value={item.language_code} />)}
              //           </el-select>
              //         }
              //       </el-table-column>,
              //       // 列名
              //       <el-table-column prop={'code'} label={'列名'}>
              //         {scope => <el-input
              //             modelValue={scope.row.code} onUpdate:modelValue={val => scope.row.code = val}
              //             placeholder="请输入列名"
              //           />
              //         }
              //       </el-table-column>,
              //       // 配置路径
              //       <el-table-column prop={'filePath'} label={'配置路径'}>
              //         {scope => <el-input
              //             modelValue={scope.row.filePath} onUpdate:modelValue={val => scope.row.filePath = val}
              //             placeholder="请输入配置路径"
              //           />
              //         }
              //       </el-table-column>,
              //     ]
              //   ),
              // },
            },
            rules: [
              { type: 'array', min: 1, required: true, message: '请添加翻译配置' },
              { validator: validateLangPath, trigger: 'blur' },
            ],
          },
        },
      },
    },
  };
}
