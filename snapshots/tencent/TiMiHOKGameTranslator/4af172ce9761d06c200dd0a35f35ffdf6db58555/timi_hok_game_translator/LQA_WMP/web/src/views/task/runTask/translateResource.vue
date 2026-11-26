<!--
 * @Description: 译文资源
-->
<template>
  <el-form class="bg-gray-1 py-3 px-6" ref="form" :model="form" label-width="auto" status-icon>
    <!-- 来源 -->
    <el-form-item
      class="!mb-[18px]" label="来源" prop="trans_res_type"
      :rules="[{ required: true, message: '请选择来源' }]"
    >
      <el-radio-group v-model="form.trans_res_type" @change="onTypeChange">
        <el-radio value="git">Git</el-radio>
        <el-radio value="svn">SVN</el-radio>
        <el-radio value="p4">P4</el-radio>
        <el-radio value="other">ZIP</el-radio>
      </el-radio-group>
    </el-form-item>

    <!-- 仓库 -->
    <el-form-item
      v-if="form.trans_res_type !== 'other'" class="!mb-[22px]" label="仓库" prop="trans_res_repo"
      :rules="[{ required: true, message: '请填写仓库', trigger: 'blur' }]"
    >
      <el-input v-model.trim="form.trans_res_repo" placeholder="请填写仓库" :validate-event="false" @blur="validateField('trans_res_repo')" />
    </el-form-item>

    <!-- 分支 -->
    <el-form-item v-if="form.trans_res_type !== 'other'" class="!mb-[18px]" label="分支">
      <el-input v-model.trim="form.trans_res_br" placeholder="分支" :validate-event="false" />
    </el-form-item>

    <!-- 版本 -->
    <el-form-item
      v-if="form.trans_res_type !== 'other'" class="!mb-[22px]" label="版本" prop="trans_res_ver"
      :rules="[{ required: true, message: '请填写版本', trigger: 'blur' }]"
    >
      <el-input v-model.trim="form.trans_res_ver" placeholder="请填写版本" :validate-event="false" @blur="validateField('trans_res_ver')" />
    </el-form-item>

    <!-- 文件上传 -->
    <el-form-item
      v-if="form.trans_res_type === 'other'" class="!mb-[18px]" label="文件" prop="trans_res_file_path"
      :rules="[{ required: true, message: '请上传文件' }]"
    >
      <el-upload
        v-model:file-list="form.trans_res_file_path"
        :http-request="handleUpload"
        :on-preview="onPreview"
        :on-success="onSuccess"
        multiple
        :limit="1"
        style="width: 100%"
        accept=".zip"
      >
        <el-button type="primary">上传</el-button>
      </el-upload>
    </el-form-item>
  </el-form>
</template>

<script>
import { cloneDeep, debounce } from 'lodash-es';
import { customRequest } from '@/utils/service.ts';

let that;

export default {
  name: 'TranslateResource',
  props: {
    modelValue: { type: String, default: '' },
  },
  emits: ['update:modelValue'],
  data() {
    return {
      form: {
        trans_res_type: '', // 来源
        trans_res_repo: '', // 仓库
        trans_res_br: '', // 分支
        trans_res_ver: '', // 版本
        trans_res_file_path: [], // 文件
      },
    };
  },
  created() {
    // eslint-disable-next-line @typescript-eslint/no-this-alias
    that = this;
    try {
      this.form = { ...this.form, ...JSON.parse(this.modelValue) };
    } catch (e) {
      console.warn(e);
    }
  },
  mounted() {
    setTimeout(() => {
      this.$refs.form.clearValidate();
    }, 500);
  },
  watch: {
    form: {
      handler: debounce((newValue) => {
        // 不在此处做整表校验（避免用户刚选来源就飘红）
        // 只负责向外同步数据，整表校验由父组件在提交前兜底
        const formatValue = {
          ...cloneDeep(newValue),
          trans_res_file_path: newValue.trans_res_file_path.length ? newValue.trans_res_file_path[0].url : '',
        };
        that.$emit('update:modelValue', JSON.stringify(formatValue));
      }, 300),
      deep: true,
    },
  },
  methods: {
    /** 切换来源时，清空其它字段的旧红字（避免 Git <-> ZIP 切换残留提示） */
    onTypeChange() {
      this.$nextTick(() => {
        ['trans_res_repo', 'trans_res_ver', 'trans_res_file_path'].forEach((field) => {
          this.$refs.form?.clearValidate(field);
        });
      });
    },
    /** 单字段校验：仅在用户 blur 时触发，不会牵连其它字段 */
    validateField(prop) {
      this.$refs.form?.validateField(prop, () => {});
    },
    /** 自定义上传 */
    handleUpload(e) {
      const data = new FormData();
      data.append('file', e.file);
      customRequest({
        url: '/api/upload_file',
        method: 'post',
        data,
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }).then((res) => {
        if (res.code === 0) {
          const data = {
            name: res.data.file_name,
            url: res.data.file_path,
          };
          e.onSuccess(data);
        }
      });
    },
    /** 成功后操作 */
    onSuccess(res, file) {
      file.name = res.name;
      file.url = res.url;
    },
    /** 预览 */
    onPreview(e) {
      window.open(`${import.meta.env.VITE_RESOURCE_API}${e.url}`, '_blank');
    },
  },
};
</script>

<style lang="scss" scoped>
/* 修正错误提示被压扁 / 被下一行覆盖的问题 */
:deep(.el-form-item__error) {
  padding-top: 2px;
  line-height: 1.2;
  white-space: nowrap;
}
</style>
