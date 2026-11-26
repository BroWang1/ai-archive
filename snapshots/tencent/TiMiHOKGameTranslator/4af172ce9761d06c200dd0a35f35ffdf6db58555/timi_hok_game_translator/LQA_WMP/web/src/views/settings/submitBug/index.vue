<!--
 * @Description: 提单配置
-->
<template>
  <div style="height: calc(100vh - 200px); overflow-y: auto; padding-right: 10px;">
    <!-- 缺陷描述模板 -->
    <el-descriptions title="缺陷描述模板" />
    <div class="template-section">
      <p style="color: #909399; font-size: 13px; margin-bottom: 8px;">
        提单时缺陷描述将使用此模板自动填充。支持变量：
        <code>{image_id}</code> 图片ID、
        <code>{image_name}</code> 图片名称、
        <code>{job_id}</code> 任务ID
      </p>
      <scEditor v-model="descriptionTemplate" />
      <el-button type="primary" style="margin-top: 10px;" @click="saveTemplate">保存模板</el-button>
    </div>

    <!-- 自定义提单字段配置 -->
    <el-divider />
    <el-descriptions title="自定义提单字段" />
    <div class="custom-fields-section">
      <div v-for="(field, index) in customFields" :key="field.id || index" class="custom-field-item">
        <el-card shadow="hover" style="margin-bottom: 12px;">
          <el-form :inline="true" :model="field">
            <el-form-item label="缺陷系统字段">
              <el-select v-model="field.field_key" placeholder="选择或输入字段名" filterable allow-create default-first-option style="width: 200px;" @change="onTrackerFieldChange(field)">
                <el-option
                  v-for="item in trackerFields"
                  :key="item.key"
                  :label="item.label"
                  :value="item.key"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="下拉选项">
              <el-input v-model="field.optionsText" placeholder="逗号分隔（选择字段后自动填充）" style="width: 280px;" @blur="parseOptions(field)" />
            </el-form-item>
            <el-form-item label="启用">
              <el-switch :active-value="1" :inactive-value="0" v-model="field.enable" />
            </el-form-item>
            <el-form-item>
              <el-button type="danger" size="small" @click="removeCustomField(index)">删除</el-button>
              <el-button type="primary" size="small" @click="saveCustomField(field)">保存</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </div>
      <el-button type="primary" plain @click="addCustomField">+ 添加自定义字段</el-button>
    </div>

    <!-- 处理人分配方式 -->
    <el-divider />
    <el-descriptions title="处理人分配方式" />
    <el-form :model="form" :inline="true">
      <el-form-item label="缺陷类型">
        <el-switch :active-value="1" :inactive-value="0" v-model="form.bug_type_enable" @change="dataUpdate" />
      </el-form-item>
      <el-form-item label="区域语言">
        <el-switch :active-value="1" :inactive-value="0" v-model="form.language_enable" @change="dataUpdate" />
      </el-form-item>
      <el-form-item label="模块">
        <el-switch :active-value="1" :inactive-value="0" v-model="form.module_enable" @change="dataUpdate" />
      </el-form-item>
    </el-form>

    <!-- 处理人配置 -->
    <el-descriptions title="处理人配置" />
    <confTable
      v-if="isShow"
      :form="form" :data="tableData"
      @refresh="getData"
    />
  </div>
</template>

<script>
import { customRequest } from '@/utils/service.ts';
import confTable from './table.vue';
import scEditor from '@/components/scEditor/index.vue';
import { pick } from 'lodash-es';

export default {
  name: 'submitBug',
  components: { confTable, scEditor },
  data() {
    return {
      form: {
        bug_type_enable: 0,
        language_enable: 0,
        module_enable: 0,
      },
      tableData: [],
      customFields: [],
      trackerFields: [],
      descriptionTemplate: '',
      defaultTemplate: '<p><strong style="color:#2b79c2">[测试环境]（Version &amp; Test environment）</strong></p>'
        + '<p>测试包(Installation package)：</p>'
        + '<p>服务器名(Server name)：</p>'
        + '<p>测试机型(Device)：</p>'
        + '<p>图片ID：{image_id}</p>'
        + '<p>图片名称：{image_name}</p>'
        + '<p>任务ID：{job_id}</p>'
        + '<p>发生时间：{create_time}</p>'
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
        + '<p><strong style="color:#2b79c2">[备注]（Notes）</strong></p>',
    };
  },
  computed: {
    isShow() {
      return this.form.bug_type_enable || this.form.language_enable || this.form.module_enable;
    },
  },
  async created() {
    await this.getData();
    await this.getCustomFields();
    await this.getTrackerFields();
  },
  methods: {
    /** 获取数据 */
    async getData() {
      const { data } = await customRequest({
        url: '/api/project/config',
        method: 'get',
        params: { project_id: this.$route.meta.value, cate: 'BugBillMethod' },
      });
      this.setData(data.list[0]);
    },
    /** 设置数据 */
    async setData(data) {
      this.form = pick(data, ['bug_type_enable', 'language_enable', 'module_enable', 'id']);
      this.descriptionTemplate = data.description_template || this.defaultTemplate;
      await this.getTableData();
    },
    /** 数据更新 */
    async dataUpdate() {
      const { data } = await customRequest({
        url: '/api/project/config?cate=BugBillMethod',
        method: 'patch',
        data: {
          ...this.form,
          project_id: this.$route.meta.value,
        },
      });
      this.setData(data.config);
    },
    async getTableData() {
      const { data } = await customRequest({
        url: '/api/project/config',
        method: 'get',
        params: { project_id: this.$route.meta.value, cate: 'BugBillUser' },
      });
      this.tableData = data.list.map(item => ({
        ...item,
        bug_type: item.bug_type ? item.bug_type : '',
        language: item.language ? item.language : '',
        module: item.module ? item.module : '',
      }));
    },
    /** 获取自定义字段列表 */
    async getCustomFields() {
      const { data } = await customRequest({
        url: '/api/project/config',
        method: 'get',
        params: { project_id: this.$route.meta.value, cate: 'CustomField' },
      });
      this.customFields = (data.list || []).map(item => ({
        ...item,
        optionsText: (item.options || []).join(','),
      }));
    },
    /** 获取缺陷系统中可配置的字段（平台内记录模式下为空，可手动输入字段名） */
    async getTrackerFields() {
      try {
        const res = await customRequest({
          url: '/api/bug/tracker_fields',
          method: 'get',
          params: { project_id: this.$route.meta.value },
          silent: true,
        });
        this.trackerFields = res.data.fields || [];
      } catch (e) {
        console.warn('获取缺陷系统字段失败，可手动输入字段名', e);
        this.trackerFields = [];
      }
    },
    /**
     * 字段变更时，自动填充下拉选项和字段名称。
     * 选项存储格式："中文|英文"（有 label 且 label != value 时）或 "英文"（无中文 label 时）。
     * - "英文"部分是最终提交给缺陷系统的真实值（如禅道的 codeerror/config/...）
     * - "中文"部分仅用于前端展示，让提单下拉显示人类可读的中文（如 代码错误/配置相关/...）
     * 使用 "|" 分隔是因为缺陷系统的 value 通常是英文字母/数字，不会包含竖线，解析简单可靠。
     */
    onTrackerFieldChange(field) {
      const trackerField = this.trackerFields.find(f => f.key === field.field_key);
      if (trackerField) {
        field.field_name = trackerField.label || field.field_key;
        if (trackerField.options && trackerField.options.length > 0) {
          field.options = trackerField.options.map((o) => {
            const value = o.value || o.label;
            const label = o.label || o.value;
            // label 与 value 相同（如用户手输场景），只存一份英文；
            // label 与 value 不同（如禅道返回的中英对照），用 "中文|英文" 存储
            return label && label !== value ? `${label}|${value}` : value;
          });
          field.optionsText = field.options.join(',');
        } else {
          field.options = [];
          field.optionsText = '';
        }
      } else {
        field.field_name = field.field_key;
        field.options = [];
        field.optionsText = '';
      }
    },
    /** 添加自定义字段 */
    addCustomField() {
      this.customFields.push({
        project_id: this.$route.meta.value,
        field_name: '',
        field_key: '',
        options: [],
        optionsText: '',
        enable: 1,
        sort_order: this.customFields.length,
      });
    },
    /** 解析选项文本为数组 */
    parseOptions(field) {
      field.options = field.optionsText
        .split(',')
        .map(s => s.trim())
        .filter(s => s.length > 0);
    },
    /** 保存自定义字段 */
    async saveCustomField(field) {
      if (!field.field_key) {
        this.$message.warning('请选择或输入缺陷系统字段');
        return;
      }
      if (!field.field_name) {
        field.field_name = field.field_key;
      }
      this.parseOptions(field);
      const method = field.id ? 'patch' : 'post';
      const res = await customRequest({
        url: '/api/project/config?cate=CustomField',
        method,
        data: {
          ...field,
          project_id: this.$route.meta.value,
        },
      });
      this.$message.success('保存成功');
      // 修复：保存后不再全量 getCustomFields()，否则会把其他尚未保存的"新增态草稿行"覆盖掉导致消失。
      // 只把后端返回的最新对象（含生成的 id）合并回当前行，保留页面上其他草稿。
      const latest = res && res.data && res.data.config;
      if (latest) {
        Object.assign(field, latest, {
          optionsText: (latest.options || []).join(','),
        });
      }
    },
    /** 删除自定义字段 */
    async removeCustomField(index) {
      const field = this.customFields[index];
      if (field.id) {
        await customRequest({
          url: '/api/project/config?cate=CustomField',
          method: 'delete',
          data: { project_id: this.$route.meta.value, ids: [field.id] },
        });
        this.$message.success('删除成功');
      }
      this.customFields.splice(index, 1);
    },
    /** 保存描述模板 */
    async saveTemplate() {
      const res = await customRequest({
        url: '/api/project/config?cate=BugBillMethod',
        method: 'patch',
        data: {
          id: this.form.id || 0,
          bug_type_enable: this.form.bug_type_enable || 0,
          language_enable: this.form.language_enable || 0,
          module_enable: this.form.module_enable || 0,
          description_template: this.descriptionTemplate,
          project_id: this.$route.meta.value,
        },
      });
      if (res.code === 0) {
        this.$message.success('模板保存成功');
      } else {
        this.$message.error(res.msg || '保存失败');
      }
    },
  },
};
</script>

<style scoped>
.custom-fields-section {
  padding: 12px 0;
}
.custom-field-item .el-card {
  border-left: 3px solid #409eff;
}
</style>
