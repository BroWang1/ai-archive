import { ref } from 'vue';
import { dict } from '@fast-crud/fast-crud';
// import api from '@/api';
import { useRoute } from 'vue-router';
import { ElMessage } from 'element-plus';
import { customRequest } from '@/utils/service';
import { checkPermission } from '@/utils/permission';
import { SUPER_ADMIN_PROJECT_ID } from '@/constants/app-key.ts';
import { timeCols } from '@/fast-crud/common.ts';

// eslint-disable-next-line no-unused-vars
export default function ({ crudExpose } = {}) {
  const route = useRoute();
  const projectID = ref(route.meta.value);

  // const userAdminMap = {};
  const pageRequest = async params => await customRequest({
    url: '/api/user/list',
    method: 'get',
    params: { info_type: 2, ...params },
  });
  const addRequest = async ({ form }) => await customRequest({
    url: '/api/user/entity',
    method: 'post',
    data: { ...form, project_id: projectID.value },
  });
  const editRequest = async ({ form }) =>
    // const userIsAdmin = userAdminMap[form.id] || false;
    // form.roles = form.roles || [];
    // if (userIsAdmin) {
    //   if (!form.roles.includes('3')) {
    //     form.roles.push('3');
    //   }
    // }
    await customRequest({
      url: '/api/user/entity',
      method: 'patch',
      data: { ...form, id: form.id, roles: form.roles, project_id: projectID.value },
    })
  ;
  const delRequest = async ({ row }) => await customRequest({
    url: '/api/user/entity',
    method: 'delete',
    data: { id: row.id },
  });

  const rolesDict = dict({
    isTree: true,
    cache: true,
    prototype: true,
    label: 'cell_roles',
    url: '/api/project/roles?project_id=0',
  });

  return {
    projectID,
    rolesDict,
    crudOptions: {
      request: {
        pageRequest,
        addRequest,
        editRequest,
        delRequest,
      },
      // 右上「导出」按钮：默认实现直接把 roles 数组用 '|' join，导致导出结果是 1_2|1_3 这种原始编码；
      // 这里覆盖 click 走自定义 CSV 导出：请求角色字典做翻译，输出 "演示项目/项目管理员|演示项目/测试人员" 的人类可读文本。
      toolbar: {
        buttons: {
          export: {
            click: async () => {
              try {
                // 1) 取字典：project_id_role_id -> 'xx项目/xx角色'
                const { data: rolesData } = await customRequest({
                  url: '/api/project/roles?project_id=0',
                  method: 'get',
                });
                const rolesMap = {};
                (rolesData?.list || []).forEach((proj) => {
                  (proj.children || []).forEach((role) => {
                    rolesMap[role.value] = role.cell_roles;
                  });
                });

                // 2) 取当前表格的数据（已经按用户筛选过的列表）
                const rows = crudExpose?.getTableData?.() || [];
                if (rows.length === 0) {
                  ElMessage.warning('没有可导出的数据');
                  return;
                }

                // 3) 组装 CSV（UTF-8 BOM + 用 Excel 友好的 \r\n 换行，字段按需转义）
                const headers = ['英文名', '中文名', '所属部门', '角色', '创建时间', '更新时间'];
                const esc = (val) => {
                  const s = val === null || val === undefined ? '' : String(val);
                  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
                };
                const lines = [headers.join(',')];
                rows.forEach((row) => {
                  const rolesText = (row.roles || [])
                    .map(code => rolesMap[code] || code)
                    .join('|');
                  lines.push([
                    esc(row.name),
                    esc(row.name_zh),
                    esc(row.department),
                    esc(rolesText),
                    esc(row.created_at),
                    esc(row.updated_at),
                  ].join(','));
                });
                const csv = '\uFEFF' + lines.join('\r\n');

                // 4) 触发浏览器下载
                const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
                const url = URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = `用户列表_${new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '')}.csv`;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                URL.revokeObjectURL(url);
              } catch (err) {
                ElMessage.error('导出失败');
                throw err;
              }
            },
          },
        },
      },
      rowHandle: {
        buttons: {
          // 刷新
          // refresh: {
          //   size: 'small',
          //   title: '',
          //   icon: 'Refresh',
          //   text: null,
          //   style: { height: '30px' },
          //   tooltip: { content: '刷新', enterable: false },
          //   click: async ({ row }) => {
          //     await customRequest({
          //       url: `/users/${row.id}?project_id=${projectID.value}`,
          //       method: 'patch',
          //     });
          //     ElMessage.success(`更新 ${row.user_name} 信息成功`);
          //   },
          //   // show: proxy.$hasPermissions('user:del'),
          //   order: 1,
          // },

          edit: {
            disabled: !checkPermission([`${projectID.value}:admin`]),
          },

          // 删除
          remove: {
            disabled: projectID.value !== 0,
          },
        },
        align: 'center',
        width: 150,
      },
      table: {
        border: false,
      },
      columns: {
        // ID
        id: {
          title: 'ID',
          type: 'number',
          column: { width: 64, align: 'center', sorter: true, show: false },
          form: { order: 0, show: false },
        },
        // 英文名
        name: {
          title: '英文名',
          type: 'text',
          column: { width: 150 },
          search: {
            show: true,
            component: {
              name: 'fs-dict-select',
              filterable: true,
              clearable: true,
              placeholder: '英文名',
              dict: dict({
                url: '/api/user/list',
                value: 'name',
                label: 'name',
                async getData({ url }) {
                  const { data } = await customRequest({ url, method: 'get', params: {
                    info_type: 0, // 简略信息
                    page_size: 1000000000000000,
                  } });
                  return data.list;
                },
              }),
            },
          },
          form: {
            component: {
              style: { width: '100%' },
              placeholder: '请填写英文名',
            },
            rules: [{ required: true, message: '请填写英文名' }],
          },
          addForm: { col: { span: 24 } },
          editForm: { component: { disabled: true } },
        },
        // 中文名
        name_zh: {
          title: '中文名',
          type: 'text',
          column: { width: 120 },
          search: {
            show: true,
            component: {
              name: 'fs-dict-select',
              filterable: true,
              clearable: true,
              placeholder: '中文名',
              dict: dict({
                url: '/api/user/list',
                value: 'name_zh',
                label: 'name_zh',
                async getData({ url }) {
                  const { data } = await customRequest({ url, method: 'get', params: {
                    info_type: 0, // 简略信息
                    page_size: 1000000000000000,
                  } });
                  return data.list;
                },
              }),
            },
          },
          addForm: { show: false },
          editForm: { component: { disabled: true } },
        },
        // 所属项目
        project_id: {
          title: '所属项目',
          type: 'text',
          column: { show: false },
          form: { show: false },
          search: {
            // 仅在"系统管理 → 用户管理"（超管全局视角）下显示；具体项目视角下该下拉只有一个选项，无筛选意义，隐藏
            show: projectID.value === SUPER_ADMIN_PROJECT_ID,
            component: {
              name: 'fs-dict-select',
              filterable: true,
              clearable: true,
              placeholder: '所属项目',
              dict: dict({
                url: '/api/project/list',
                value: 'id',
                label: 'name',
                async getData({ url }) {
                  const { data } = await customRequest({ url, method: 'get', params: {
                    page_size: 1000000000000000,
                  } });
                  return data.list;
                },
              }),
            },
          },
        },
        // 所属部门
        department: {
          title: '所属部门',
          type: 'text',
          column: { width: 550 },
          search: {
            show: true,
            component: {
              placeholder: '模糊搜索',
            },
          },
          form: {
            col: { span: 24 },
            component: {
              placeholder: '请填写所属部门',
            },
          },
          addForm: { show: false },
          editForm: { component: { disabled: true } },
        },
        // // 是否管理员
        // isAdmin: {
        //   title: '系统管理员',
        //   column: {
        //     width: 100,
        //     align: 'center',
        //     cellRender({ row }) {
        //       const isAdmin = row.roles.includes('3');
        //       return <el-tag size="small" type={isAdmin ? 'primary' : 'info'}>{isAdmin ? '是' : '否'}</el-tag>;
        //     },
        //   },
        //   form: { show: false },
        // },
        is_admin: {
          title: '管理员',
          type: 'dict-select',
          column: { show: false },
          form: { show: false },
          dict: dict({
            data: [
              { value: 1, label: '是' },
              { value: 0, label: '否' },
            ],
          }),
          search: {
            show: true,
            component: {
              placeholder: '是否管理员',
              clearable: true,
            },
          },
        },
        // 角色
        roles: {
          title: '角色',
          type: 'dict-cascader',
          search: {
            show: false,
          },
          column: {
            minWidth: 300,
            component: {
              dict: rolesDict,
            },
          },
          form: {
            col: { span: 24 },
            component: {
              dict: dict({
                isTree: true,
                label: 'cell_roles',
                prototype: true,
                url: '/api/project/roles?project_id=0',
                async getData({ url }) {
                  const { data } = await customRequest({ url, method: 'get' });
                  if (projectID.value !== SUPER_ADMIN_PROJECT_ID) {
                    return data.list.filter(item => item.project_id === projectID.value);
                  }
                  return data.list;
                },
              }),
              style: 'width: 100%',
              filterable: true,
              placeholder: '角色',
              // popperClass 作为 JS 事件代理（点击 label 文字也能勾选）的作用域锚点，见 index.vue
              popperClass: 'user-roles-cascader-popper',
              props: { props: { multiple: true, emitPath: false } },
            },
          },
        },
        ...timeCols,
      },
    },
  };
}
