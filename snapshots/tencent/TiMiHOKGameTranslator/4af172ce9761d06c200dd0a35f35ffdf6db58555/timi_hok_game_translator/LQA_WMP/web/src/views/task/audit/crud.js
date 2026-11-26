import { dict, useCompute, useColumns } from '@fast-crud/fast-crud';
import { customRequest } from '@/utils/service.ts';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { dateRangeBind } from '@/utils/bind/date.js';
import dayjs from 'dayjs';
import createBugCrudOptions from './submitBug/crud';
import createBatchBugCrudOptions from './submitBug/batchCrud.jsx';
import { cloneDeep, debounce } from 'lodash-es';
import { ref, computed, shallowRef } from 'vue';
import { getBugTypeDict, getLanguageDict } from '@/utils/dict.js';
import { useTagsViewStore } from '@/store/modules/tags-view.ts';
import { getBasicInfo } from '@/views/task/audit/common.js';
import numberRange from '@/components/numberRange.vue';
import { getTrackerMeta } from '@/utils/tracker.js';

export default function ({ crudExpose, context }) {
  const route = useRoute();
  const router = useRouter();
  const { compute } = useCompute();
  const tagsViewStore = useTagsViewStore();

  if (route.query.data_id) {
    tagsViewStore.setCurrentTabTitle(route, `${route.query.data_id}-多语言对比`);
  }

  const debounceDoSearch = debounce(form => crudExpose.doSearch({ form }), 250);

  let searchBugTypes = [];
  const pageData = ref([]);
  const previewImgs = ref([]);

  // @ts-ignore
  const pageRequest = async (params) => {
    searchBugTypes = cloneDeep(params.ai_bug_types || []);
    pageData.value = [];
    previewImgs.value = [];
    return await customRequest({
      url: '/api/image/list',
      // url: `/images/project/${route.meta.value}/get_images`,
      method: 'get',
      params: {
        job_id: route.query.job_id,
        ...params,
        id: params.id || route.query.id || undefined,
        data_id: route.query.data_id || undefined,
        rect_location: params.rect_location || undefined,
        ai_bug_types:
          (params.ai_bug_types && params.ai_bug_types.length) ? params.ai_bug_types.join(',') : undefined,
      },
    }).then((res) => {
      pageData.value = res.data.list;
      const tempPreviewImgs = [];
      res.data.list.forEach((item) => {
        context.imgKeys.forEach((key) => {
          tempPreviewImgs.push(`${context.imgPrefix}${item[key]}`);
        });
      });
      previewImgs.value = tempPreviewImgs;
      return res;
    });
  };

  const delRequest = async ({ row }) => await customRequest({
    url: '/api/image/entity',
    method: 'delete',
    data: { image_ids: [row.id], project_id: route.meta.value },
  });

  const selectedIds = ref([]);
  // 保存当前勾选的完整行数据，批量提单前要据此过滤未识别/已提单的图片
  const selectedRows = ref([]);
  const jobId = ref();
  const onSelectionChange = (changed) => {
    selectedIds.value = changed.map(item => item.id);
    selectedRows.value = changed;
    if (changed.length) {
      jobId.value = changed[0].job_id;
    }
  };

  const commonSubmitObj = {
    priority: 3, // 中 - 优先级
    severity: 3, // 一般 - 严重程度
    // 发现版本
    version_report_options: [],
    version_report_value: '',
    version_report: '',
    // 发布计划
    release_id_options: [],
    release_id_value: '',
    release_id_label: '',
    // 合入版本
    version_fix_options: [],
    version_fix_value: '',
  };
  const submitDataObj = {
    title: '',
    fix_title: '',
    image_name: '',
    current_owner: '',
    raw_image_path: '',
    AI_image_path: '',
    description: '',
    image_id: '',
    job_id: '',
    Key_in_bug: '',
  };
  const batchDataForm = {
    bug_type: [],
  };

  // 判断单行图片不能提单的原因；返回空串表示该图片可以提单
  // 共三种不可提单情形，前端据此给出针对性建议：
  //   1) '已提单'                  → bill_status === 0
  //   2) 'AI 识别失败'              → ai_sign_suc === 2（后端标记为识别失败）
  //   3) 'AI 识别未完成'            → ai_sign_suc === 0 且 ai_mark_img_path 为空（还没识别过）
  //   4) 'AI 未发现缺陷'            → ai_sign_suc === 1 但 ai_bug_types 为空（识别成功但没检出 bug）
  function getUnbillableReason(row) {
    if (row.bill_status === 0) return '已提单';
    if (row.ai_sign_suc === 2) return 'AI 识别失败';
    if (!row.ai_mark_img_path && (!row.ai_bug_types || !row.ai_bug_types.length)) return 'AI 识别未完成';
    if (!row.ai_bug_types || !row.ai_bug_types.length) return 'AI 未发现缺陷';
    return '';
  }

  // 不可提单原因 → 可读颜色（表格里着色，橙=提示类，红=错误类）
  function getReasonColor(reason) {
    if (reason === '已提单' || reason === 'AI 未发现缺陷') return '#E6A23C';
    return '#F56C6C';
  }

  // 根据实际出现过的原因，返回 HTML 建议段落
  function getActionAdviceHtml(invalidRows) {
    const reasons = new Set(invalidRows.map(getUnbillableReason));
    const lines = [];
    if (reasons.has('AI 识别未完成')) {
      lines.push('• <b style="color:#F56C6C;">AI 识别未完成</b>：请先点击该行的 <b>识别</b> 按钮完成识别，再提单。');
    }
    if (reasons.has('AI 识别失败')) {
      lines.push('• <b style="color:#F56C6C;">AI 识别失败</b>：请点击该行的 <b>识别</b> 按钮重新识别；若多次失败，可能是图片本身异常（如抽帧失败），建议删除或更换图片。');
    }
    if (reasons.has('AI 未发现缺陷')) {
      lines.push('• <b style="color:#E6A23C;">AI 未发现缺陷</b>：AI 识别已完成，但该图片未检出任何 bug，当前版本不支持为此类图片手动提单。');
    }
    if (reasons.has('已提单')) {
      lines.push('• <b style="color:#E6A23C;">已提单</b>：可从 <b>缺陷管理</b> 页面查看，无需重复提单。');
    }
    lines.push('• 或先取消勾选这些图片，再对其他可提单的图片进行批量提单。');
    return `<div style="margin-top:10px;color:#606266;line-height:1.8;">
        <b>建议：</b><br/>${lines.join('<br/>')}
      </div>`;
  }

  // 防止弹窗重复打开
  let unbillableBoxOpen = false;

  // HTML 转义，避免文件名里带 < > & 等字符破坏弹窗内容
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  // 构建“不可提单”明细表格 HTML
  function buildUnbillableTable(invalidRows) {
    const rows = invalidRows.map((r) => {
      const reason = getUnbillableReason(r);
      const reasonColor = getReasonColor(reason);
      return `<tr>
        <td style="padding:4px 8px;border:1px solid #EBEEF5;">${esc(r.id)}</td>
        <td style="padding:4px 8px;border:1px solid #EBEEF5;max-width:260px;word-break:break-all;">${esc(r.file_name || '-')}</td>
        <td style="padding:4px 8px;border:1px solid #EBEEF5;color:${reasonColor};">${esc(reason)}</td>
      </tr>`;
    }).join('');
    return `<div style="max-height:260px;overflow:auto;">
      <table style="border-collapse:collapse;font-size:13px;width:100%;">
        <thead>
          <tr style="background:#F5F7FA;">
            <th style="padding:6px 8px;border:1px solid #EBEEF5;text-align:left;">图片 ID</th>
            <th style="padding:6px 8px;border:1px solid #EBEEF5;text-align:left;">文件名</th>
            <th style="padding:6px 8px;border:1px solid #EBEEF5;text-align:left;">原因</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
  }

  async function batchBill() {
    // 过滤勾选行：未完成 AI 识别（ai_bug_types 为空）或已提单（bill_status === 0）的图片都无法提单，
    // 若直接把它们提交到 /api/bug/list，后端会把 ai_check_detail 当 JSON 解析而抛
    // "Input is a zero-length, empty document" 等错误，前端只能看到一串英文异常。
    const rows = selectedRows.value || [];
    const validRows = [];
    const invalidRows = [];
    rows.forEach((row) => {
      if (getUnbillableReason(row)) invalidRows.push(row);
      else validRows.push(row);
    });

    // 情况 1：全部不可提单——用 alert 弹窗列出明细 + 建议
    if (validRows.length === 0) {
      if (unbillableBoxOpen) return;
      unbillableBoxOpen = true;
      const tip = `<div style="margin-bottom:8px;">以下 <b>${invalidRows.length}</b> 张图片都无法提单：</div>`
        + buildUnbillableTable(invalidRows)
        + getActionAdviceHtml(invalidRows);
      try {
        await ElMessageBox.alert(tip, '无法批量提单', {
          dangerouslyUseHTMLString: true,
          confirmButtonText: '知道了',
          customClass: 'batch-bill-unbillable-dialog',
          type: 'warning',
        });
      } catch (e) { /* 用户关闭 */ } finally {
        unbillableBoxOpen = false;
      }
      return;
    }

    // 情况 2：部分不可提单——confirm 弹窗，列出明细，让用户决定是否跳过它们继续
    if (invalidRows.length > 0) {
      if (unbillableBoxOpen) return;
      unbillableBoxOpen = true;
      const tip = `<div style="margin-bottom:8px;">以下 <b>${invalidRows.length}</b> 张图片无法提单，将被自动跳过：</div>`
        + buildUnbillableTable(invalidRows)
        + `<div style="margin-top:10px;color:#606266;">是否继续对剩余 <b style="color:#67C23A;">${validRows.length}</b> 张图片提单？</div>`;
      try {
        await ElMessageBox.confirm(tip, '部分图片无法提单', {
          dangerouslyUseHTMLString: true,
          type: 'warning',
          confirmButtonText: `继续对剩余 ${validRows.length} 张提单`,
          cancelButtonText: '取消',
          customClass: 'batch-bill-unbillable-dialog',
        });
      } catch (e) {
        unbillableBoxOpen = false;
        return; // 用户取消
      } finally {
        unbillableBoxOpen = false;
      }
    }

    const useBatchDataForm = cloneDeep({
      image_ids: validRows.map(r => r.id),
      ...commonSubmitObj,
      ...batchDataForm,
      job_id: jobId.value,
    });

    await getExtraInfo(useBatchDataForm);

    // 自定义表单配置
    const { buildFormOptions } = useColumns();
    // 使用crudOptions结构来构建自定义表单配置
    const formOptions = (
      buildFormOptions(createBatchBugCrudOptions(route, useBatchDataForm, context.clearRefresh))
    );
    formOptions.initialForm = useBatchDataForm;
    context.formWrapperRef.value.open(formOptions);
  }

  /** 缺陷系统提单选项（发现版本/发布计划/修复版本） */
  async function getExtraInfo(obj) {
    const meta = await getTrackerMeta(route.meta.value);
    if (meta.error) {
      ElMessage.warning(`缺陷系统配置有误，提单可能失败：${meta.error}`);
    }
    obj.tracker_label = meta.type === 'none' ? '平台内记录' : meta.label;
    // 发现版本
    obj.version_report_options = meta.version_report_list;
    obj.version_report_value = '';
    // 发布计划
    obj.release_id_options = meta.release_id_list;
    obj.release_id_value = '';
    obj.release_id_label = '';
    // 修复版本
    obj.version_fix_options = meta.version_fix_list;
    obj.version_fix_value = '';
  }

  // 此处编辑 crudOptions 配置
  return {
    pageData,
    previewImgs,
    selectedIds,
    crudOptions: {
      request: {
        pageRequest,
        delRequest,
      },
      pagination: {
        pageSize: 10, // 默认pageSize
      },
      // pagination: {
      //   onChange() {
      //     console.log('page change');
      //   },
      // },
      // 屏蔽 fast-crud 右上角内置的"导出"按钮。
      // 该页面（结果审核 / 多语言对比，共用本 crud.js）内置导出按钮点击无响应，
      // 容易引起误解，这里统一关掉；其他页面不受影响。
      toolbar: {
        buttons: {
          export: { show: false },
        },
      },
      actionbar: {
        buttons: {
          add: { show: false },
          submitBugs: {
            // size: 'small',
            title: '',
            type: 'warning',
            // plain: true,
            text: '批量提单',
            show: true,
            // order: 0,
            disabled: computed(() => !selectedIds.value.length),
            click: batchBill,
          },
        },
      },
      rowHandle: {
        buttons: {
          edit: { show: false }, // 编辑隐藏
          remove: {
            plain: true,
            link: true,
            text: '删除',
            tooltip: null,
            click: async ({ row }) => {
              // 没查到，二次确认删除
              ElMessageBox.confirm('确认删除该数据吗？', '温馨提示', {
                type: 'warning',
              }).then(async () => {
                await delRequest({ row });
                ElMessage.success('操作成功');
                context.clearRefresh();
              });
            },
          },
          // 多语种
          languages: {
            size: 'small',
            title: '',
            type: 'warning',
            plain: true,
            link: true,
            icon: 'ci:image-01',
            text: '多语种',
            // style: { height: '30px', width: '32px' },
            // tooltip: { content: '提单', enterable: false },
            show: true,
            order: 1,
            click: async ({ row }) => {
              const url = router.resolve({
                path: route.path,
                query: {
                  job_id: route.query.job_id,
                  data_id: row.data_id,
                },
              }).href;
              router.push(url);
            },
          },
          // 提单
          submitBugs: {
            size: 'small',
            title: '',
            type: 'warning',
            plain: true,
            link: true,
            icon: compute(({ row }) => (row.bill_status === 0 ? '' : 'cil:bug')),
            text: compute(({ row }) => (row.bill_status === 0 ? '提单中' : '提单')),
            // style: { height: '30px', width: '32px' },
            // tooltip: { content: '提单', enterable: false },
            disabled: compute(({ row }) => !row.ai_bug_types.length || row.bill_status === 0),
            show: true,
            order: 1,
            click: async ({ row }) => {
              const useSubmitDataObj = cloneDeep({ ...commonSubmitObj, ...submitDataObj });
              useSubmitDataObj.bug_types = cloneDeep(searchBugTypes.length ? searchBugTypes : row.ai_bug_types || []);

              useSubmitDataObj.image_name = row.file_name;
              useSubmitDataObj.raw_image_path = row.file_path;
              useSubmitDataObj.AI_image_path = row.ai_mark_img_path;
              useSubmitDataObj.job_id = row.job_id;
              useSubmitDataObj.image_id = row.id;

              // 获取描述模板
              const billMethodRes = await customRequest({
                url: '/api/project/config',
                method: 'get',
                params: { project_id: route.meta.value, cate: 'BugBillMethod' },
              });
              let descTemplate = '';
              if (billMethodRes.code === 0 && billMethodRes.data.list.length) {
                descTemplate = billMethodRes.data.list[0].description_template || '';
              }

              if (descTemplate) {
                // 使用配置的模板，替换变量
                let rendered = descTemplate
                  .replace(/\{image_id\}/g, row.id)
                  .replace(/\{image_name\}/g, row.file_name)
                  .replace(/\{job_id\}/g, row.job_id)
                  .replace(/\{create_time\}/g, row.create_time || '');
                // 如果模板不包含HTML标签，按行转换为<p>
                if (!rendered.includes('<')) {
                  rendered = rendered.split('\n').map(line => `<p>${line}</p>`)
                    .join('');
                }
                useSubmitDataObj.description = rendered;
              } else {
                // 默认模板
                useSubmitDataObj.description = '<p><strong style="color:#2b79c2">[测试环境]（Version &amp; Test environment）</strong></p>'
                  + '<p>测试包(Installation package)：</p>'
                  + '<p>服务器名(Server name)：</p>'
                  + '<p>测试机型(Device)：</p>'
                  + '<p><strong style="color:#2b79c2">[操作步骤](Steps)</strong></p>'
                  + '<p>1.自动化LQA单中列出了缺陷所在的蓝图和控件信息,未列出步骤,如需要步骤,请联系提单人</p>'
                  + '<p><strong style="color:#2b79c2">[问题描述]（Current result）</strong></p>'
                  + '<p>1、</p>'
                  + '<p><strong style="color:#2b79c2">[文本信息]（Text information）</strong></p>'
                  + '<p><strong>翻译key (TextKey)：</strong></p>'
                  + '<p>1、</p>'
                  + '<p><strong>翻译原文 (SourceText)：</strong></p>'
                  + '<p>1、</p>'
                  + '<p><strong>翻译译文 (Translation in text file)：</strong></p>'
                  + '<p>1、</p>'
                  + '<p><strong>文本控件名(Widget Name)：</strong></p>'
                  + '<p>1、</p>'
                  + '<p><strong>文本父蓝图(Parent Widget)：</strong></p>'
                  + '<p>1、</p>'
                  + '<p><strong style="color:#2b79c2">[截图]（Screenshots）</strong></p>'
                  + '<p></p>'
                  + '<p><strong style="color:#2b79c2">[备注]（Notes）</strong></p>';
              }
              // 保护前端已渲染好的 description：仅当项目在"设置→提单"里配置了自定义模板时，
              // getBasicInfo 回来后把 description 还原为前端模板，否则 /api/bug/build_info 返回的
              // 后端默认模板（BugBuildComm.description_tpl）会把前端的渲染结果覆盖掉。
              const useCustomDescTpl = !!descTemplate;
              const preRenderedDesc = useSubmitDataObj.description;
              await getBasicInfo(route.meta.value, row.id, useSubmitDataObj);
              if (useCustomDescTpl) {
                useSubmitDataObj.description = preRenderedDesc;
              }

              await getExtraInfo(useSubmitDataObj);

              // 获取自定义提单字段配置
              const customFieldRes = await customRequest({
                url: '/api/project/config',
                method: 'get',
                params: { project_id: route.meta.value, cate: 'CustomField' },
              });
              useSubmitDataObj.customFields = customFieldRes.code === 0 ? (customFieldRes.data.list || []) : [];

              // 生成名称前缀
              if (!useSubmitDataObj.fix_title) {
                if (useSubmitDataObj.image_name.split('_').length === 3) {
                  const language = useSubmitDataObj.image_name.split('_')[1];
                  const language2 = useSubmitDataObj.image_name.split('_')[2].split('.')[0];
                  console.log(`language2====${language2}`);
                  useSubmitDataObj.fix_title = `【GRN-${language}-${language2}】【LQA-Tools】-`;
                  console.log(`language====${language}----language2====${language2}-----v====${useSubmitDataObj.fix_title}`);
                } else {
                  console.error('fix_title:image_name 命名不符合规范');
                  useSubmitDataObj.fix_title = '【LQA-Tools】-';
                }
              }
              // 自定义表单配置
              const { buildFormOptions } = useColumns();
              // 使用crudOptions结构来构建自定义表单配置
              const formOptions = buildFormOptions(createBugCrudOptions(route, useSubmitDataObj, crudExpose, useSubmitDataObj.bug_types));
              formOptions.initialForm = useSubmitDataObj;
              context.formWrapperRef.value.open(formOptions);
            },
          },
        },
        align: 'center',
        width: 166,
      },
      table: {
        // border: false,
        onSelectionChange,
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
            width: '60px',
            fixed: 'left',
            // reserveSelection: true, // 跨页选
            columnSetDisabled: true, // 禁止在列设置中选择
            showOverflowTooltip: false,
            selectable(row) {
              return row.bill_status !== 0;
            },
          },
        },
        // 图片 ID
        id: {
          title: '图片 ID',
          type: 'number',
          column: { width: 180, align: 'right' },
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
        // 模块
        module_id: {
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
              // 仅返回 el-option 需要的字段，避免把后端整条 module 记录（含 checked/
              // file_name/container 等字段）透传到 <el-option>，否则会触发
              // "[Vue warn]: Slot default invoked outside of the render function"
              return (data.modules || []).map(item => ({
                id: item.id,
                show_name: item.show_name,
              }));
            },
          }),
          column: { width: 200 },
          search: {
            show: true,
            component: {
              multiple: true,
            },
            valueResolve(e) {
              e.form.module_ids = (e.form[e.key] && e.form[e.key].length) ? e.form[e.key].join(',') : undefined;
              e.form[e.key] = undefined;
            },
          },
        },
        // 图片名称
        file_name: {
          title: '图片名称',
          type: 'text',
          column: { width: 240 },
          search: {
            show: true,
            component: { placeholder: '模糊搜索' },
          },
        },
        // 图片名称
        name: {
          title: '图片名称',
          type: 'text',
          column: { show: false },
        },
        // 采集图片
        shot_img_path: {
          title: '采集图片',
          type: 'image-uploader',
          column: {
            align: 'center',
            width: 300,
          },
        },
        // 还原图片
        file_path: {
          title: '还原图片',
          type: 'image-uploader',
          column: {
            align: 'center',
            width: 300,
          },
        },
        // 图像检测结果
        ai_mark_img_path: {
          title: '图像检测结果',
          type: 'image-uploader',
          column: {
            align: 'center',
            width: 300,
          },
        },
        // 图像检测 Debug
        ai_rect_img_path: {
          title: '图像检测 Debug',
          type: 'image-uploader',
          column: {
            align: 'center',
            width: 300,
          },
        },
        // 区域语言
        language: {
          title: '区域语言',
          type: 'dict-select',
          dict: getLanguageDict(route.meta.value),
          column: { width: 100 },
          form: {
            component: {
              dict: getLanguageDict(route.meta.value, true),
            },
          },
          search: {
            show: true,
            valueResolve(e) {
              e.form.languages = (e.form[e.key] && e.form[e.key].length) ? e.form[e.key].join(',') : undefined;
              e.form[e.key] = undefined;
            },
            component: {
              multiple: true,
              // 监听 dict-change事件
              // 默认选中第一个
              onDictChange({ dict, form, key }) {
                if (!route.query.data_id) {
                  if (dict.data !== null && !form[key]) {
                    if (dict.data[0].name === 'DEFAULT') {
                      if (dict.data.length > 1) {
                        form[key] = [dict.data[1].value];
                      }
                    } else {
                      form[key] = [dict.data[0].value];
                    }
                  }
                }
                debounceDoSearch(form);
              },
            },
          },
        },
        // 缺陷类型
        ai_bug_types: {
          title: '缺陷类型',
          type: 'dict-select',
          dict: getBugTypeDict(route.meta.value),
          column: { width: 120 },
          search: {
            show: true,
            component: {
              multiple: true,
            },
          },
        },
        // 人工审核
        // will_review: {
        //   title: '人工审核',
        //   type: 'dict-select',
        //   column: { width: 84 },
        //   dict: dict({
        //     data: [
        //       { value: 1, label: '需要', color: 'danger', effect: 'light' },
        //       { value: 0, label: '不需要', color: '', effect: 'light' },
        //     ],
        //   }),
        //   form: {
        //     component: { placeholder: '人工审核' },
        //   },
        //   search: { show: true },
        // },
        // 审核（这条图片的"数据审核"状态；非"手动打 bug 位置"）
        reviewed: {
          title: '审核',
          type: 'dict-select',
          column: { width: 84 },
          dict: dict({
            data: [
              { value: 1, label: '已审核', color: 'success', effect: 'light' },
              { value: 0, label: '未审核', color: 'danger', effect: 'light' },
            ],
          }),
          form: {
            component: { placeholder: '数据审核状态' },
          },
          search: { show: true },
        },
        // 缺陷单
        bug_num: {
          title: '缺陷单',
          column: {
            align: 'right',
            width: 70,
            component: {
              name: 'el-button',
              type: 'primary',
              link: true,
              slots: {
                default: compute(e => e.value),
              },
              on: {
                click(e) {
                  const currentRouteArr = route.path.split('/').slice(0, -1);
                  currentRouteArr.push(`bugs?job_id=${e.row.job_id}&image_id=${e.row.id}`);
                  router.push(currentRouteArr.join('/'));
                },
              },
              style: {
                marginBottom: '3px',
              },
            },
          },
        },
        // 错误类型
        err_type: {
          title: '错误类型',
          type: 'dict-select',
          dict: dict({
            data: [
              { value: 0, label: '没有失败', color: 'info' },
              { value: 1, label: '识别失败', color: 'error' },
              { value: 2, label: '提单失败', color: 'error' },
              { value: 3, label: '回归失败', color: 'error' },
            ],
          }),
          column: {
            width: 100,
            component: {
              class: 'only-text-tag',
            },
          },
          form: {
            component: { placeholder: '错误类型' },
          },
          search: { show: true },
        },
        // 检测文本
        rect_location: {
          title: '检测文本',
          type: 'text',
          column: { width: 84 },
          search: {
            show: true,
            component: {
              disabled: compute(({ form }) => !(form.language && form.language.length)),
              placeholder: '模糊搜索',
            },
          },
        },

        // 创建时间
        created_at: {
          title: '创建时间',
          type: 'datetimerange',
          column: {
            align: 'center',
            width: 158,
            component: { name: 'fs-date-format' },
          },
          form: {
            component: {
              ...dateRangeBind,
              clearable: true,
            },
            show: false,
          },
          search: {
            show: true,
            order: 0,
            // value: [
            //   dayjs().subtract(3, isDevMode() ? 'year' : 'month')
            //     .format('YYYY-MM-DD'),
            //   dayjs().format('YYYY-MM-DD'),
            // ],
            valueResolve({ value, form }) {  //  <------注意这里是form，不是row
              if (value && value.length === 2) {
                // eslint-disable-next-line no-param-reassign
                form.created_begin_at = dayjs(value[0]).startOf('day')
                  .format('YYYY-MM-DD HH:mm:ss');
                // eslint-disable-next-line no-param-reassign
                form.created_end_at = dayjs(value[1]).endOf('day')
                  .format('YYYY-MM-DD HH:mm:ss');
              }
            },
            // style: { width: '288px' },
          },
        },
        // 更新时间
        updated_at: {
          title: '更新时间',
          type: 'datetimerange',
          column: {
            align: 'center',
            width: 158,
            component: {
              name: 'fs-date-format',
              // formatter: datetimerangeFormatter,
            },
          },
          form: {
            component: {
              ...dateRangeBind,
              clearable: true,
            },
            show: false,
          },
          search: {
            show: true,
            order: 0,
            // value: [
            //   dayjs().subtract(3, isDevMode() ? 'year' : 'month')
            //     .format('YYYY-MM-DD'),
            //   dayjs().format('YYYY-MM-DD'),
            // ],
            valueResolve({ value, form }) {  //  <------注意这里是form，不是row
              if (value && value.length === 2) {
                form.updated_begin_at = dayjs(value[0]).startOf('day')
                  .format('YYYY-MM-DD HH:mm:ss');
                form.updated_end_at = dayjs(value[1]).endOf('day')
                  .format('YYYY-MM-DD HH:mm:ss');
              }
            },
            // style: { width: '288px' },
          },
        },
      },
    },
  };
}
