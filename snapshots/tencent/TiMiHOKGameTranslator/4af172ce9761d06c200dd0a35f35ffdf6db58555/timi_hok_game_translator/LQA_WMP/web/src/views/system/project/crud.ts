import { dict, useCompute } from '@fast-crud/fast-crud';
import { customRequest } from '@/utils/service';
import { useRoute } from 'vue-router';
import { timeCols } from '@/fast-crud/common';

export default function () {
  const route = useRoute();
  const { compute } = useCompute();
  // @ts-ignore
  const pageRequest = async params => {
    // 游戏类型为多选，默认会以数组形式提交（axios 会序列化为 game_type[]=1&game_type[]=2），
    // 后端可能无法正确解析数组参数；此处统一拼成逗号串（game_type=1,2）发给后端。
    const finalParams: any = { project_id: route.meta.value, ...params };
    if (Array.isArray(finalParams.game_type)) {
      finalParams.game_type = finalParams.game_type.length ? finalParams.game_type.join(',') : undefined;
    }
    return await customRequest({
      url: '/api/project/list',
      method: 'get',
      params: finalParams,
    });
  };
  // @ts-ignore
  const addRequest = async ({ form }) => await customRequest({
    url: '/api/project/entity',
    method: 'post',
    data: form,
  });
  // @ts-ignore
  const editRequest = async ({ form, row }) => await customRequest({
    url: '/api/project/entity',
    method: 'patch',
    data: { ...form, project_id: row.id },
  });
  // 此处编辑 crudOptions 配置
  return {
    crudOptions: {
      request: {
        pageRequest,
        addRequest,
        editRequest,
      },
      rowHandle: {
        buttons: {
          // 查看
          view: { show: true },
          // 删除
          remove: { show: false },
        },
        align: 'center',
        width: 110,
      },
      table: {
        border: false,
        // defaultSort: {prop: 'create_time', order: 'descending'}
      },
      form: {
        // 具体可配置请参考 grid 布局： http://www.ruanyifeng.com/blog/2019/03/grid-layout-tutorial.html
        display: 'grid',
        labelWidth: '80px',
      },
      columns: {
        // ID
        // id: {
        //   title: 'ID',
        //   type: 'number',
        //   column: { width: 64, align: 'center' },
        //   form: { show: false },
        // },

        // 所属团队
        team: {
          title: '所属团队',
          type: 'text',
          search: {
            show: true,
            component: { placeholder: '模糊搜索' },
          },
          form: {
            order: 1,
            component: { placeholder: '所属团队/工作室（选填）' },
          },
        },

        // 名称
        name: {
          title: '名称',
          type: 'text',
          search: {
            show: true,
            component: { placeholder: '模糊搜索' },
          },
          form: {
            order: 1,
            component: { placeholder: '名称' },
            rules: [{ required: true, message: '请填写名称' }],
          },
        },
        // 项目代号
        code: {
          title: '项目代号',
          type: 'text',
          form: {
            component: { placeholder: '英文代号，如 game_a' },
            rules: [
              { required: true, message: '请填写项目代号' },
              { pattern: /^[A-Za-z0-9_-]{2,100}$/, message: '只能包含字母、数字、下划线、中划线' },
            ],
            helper: '创建后不可修改；提单模板目录 templates/spec2/<代号小写> 存在时使用自定义模板',
          },
          editForm: {
            show: false, // 编辑时隐藏
            component: { disabled: true },
          },
        },

        // AI 识别项目名
        cvtest_project: {
          title: 'AI识别项目名',
          type: 'text',
          column: { show: false },
          form: {
            component: { placeholder: 'AI 识别服务中的项目标识' },
            rules: [{ required: true, message: '请填写 AI 识别项目名' }],
            helper: '调用 AI 识别服务时以 "<项目名>_lqa" 作为 project-method，未填写时无法创建任务',
          },
        },

        // 项目图片
        // project_img: {
        //   title: '项目图片',
        //   type: 'cropper-uploader',
        //   form: {
        //     order: 0,
        //     col: {
        //       style: { gridRow: 'span 3' },
        //     },
        //     component: {
        //       limit: 1,
        //     },
        //     helper: '图片比例 1:1，推荐尺寸为 60*60',
        //   },
        // },

        // 项目类型
        project_type: {
          title: '项目类型',
          type: 'dict-select',
          search: { show: true },
          dict: dict({
            data: [
              { value: 1, label: '平台级', effect: 'light' },
              { value: 2, label: '项目级', effect: 'light' },
            ],
          }),
          addForm: { value: 2 },
          form: {
            component: { placeholder: '项目类型' },
            rules: [{ required: true, message: '请选择项目类型' }],
          },
        },

        // 游戏类型（可多选）
        game_type: {
          title: '游戏类型',
          type: 'dict-select',
          search: {
            show: true,
            component: { multiple: true, placeholder: '游戏类型（可多选）' },
          },
          dict: dict({
            data: [
              { value: 1, label: '手游', color: '', effect: 'light' }, // primary
              { value: 2, label: '端游', color: 'danger', effect: 'light' },
              { value: 3, label: '页游', color: 'success', effect: 'plain' },
              { value: 4, label: 'app', color: 'danger', effect: 'plain' },
              { value: 5, label: '小游戏', color: 'warning', effect: 'light' },
            ],
          }),
          column: { align: 'center', minWidth: 140 },
          form: {
            component: { multiple: true, placeholder: '游戏类型（可多选）' },
            rules: [{ required: true, message: '请选择游戏类型' }],
          },
        },

        // 研发阶段
        project_phase: {
          title: '研发阶段',
          type: 'dict-select',
          search: {
            show: true,
          },
          dict: dict({
            data: [
              { value: 1, label: '上线运营', color: 'success', effect: 'light' },
              { value: 2, label: '下线', color: 'info', effect: 'light' },
              { value: 3, label: '研发期', color: 'warning', effect: 'light' },
              { value: 4, label: '保密', color: 'danger', effect: 'light' },
            ],
          }),
          form: {
            component: { placeholder: '研发阶段' },
            rules: [{ required: true, message: '请选择研发阶段' }],
          },
        },

        // 测试经理
        test_manager: {
          title: '测试经理',
          type: 'text',
          column: {
            showOverflowTooltip: true,
          },
          form: {
            component: { placeholder: '测试经理' },
            rules: [{ required: true, message: '请填写项目测试经理' }],
          },
          addForm: {
            helper: '填写平台用户名，新增项目会为测试经理添加项目管理员角色，多名请用 ; 分割',
          },
        },

        ...timeCols,
      },
    },
  };
}
