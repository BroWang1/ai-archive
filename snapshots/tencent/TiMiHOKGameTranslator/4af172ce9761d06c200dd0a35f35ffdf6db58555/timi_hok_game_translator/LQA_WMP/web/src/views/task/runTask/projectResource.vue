<!--
 * @Description: 项目资源
-->
<template>
  <el-form class="bg-gray-1 py-3 px-6" ref="form" :model="form" label-width="auto" status-icon>
    <!-- 来源 -->
    <el-form-item class="!mb-[10px]" label="来源" prop="proj_res_type">
      <el-radio-group v-model="form.proj_res_type">
        <el-radio value="git">Git</el-radio>
        <el-radio value="svn">SVN</el-radio>
        <el-radio value="p4">P4</el-radio>
      </el-radio-group>
    </el-form-item>

    <!-- 仓库 -->
    <el-form-item class="!mb-[12px]" label="仓库" prop="proj_res_repo">
      <el-input v-model.trim="form.proj_res_repo" placeholder="请填写仓库" :validate-event="false" />
    </el-form-item>

    <!-- 分支 -->
    <el-form-item class="!mb-[12px]" label="分支">
      <el-input v-model.trim="form.proj_res_br" placeholder="分支" />
    </el-form-item>

    <!-- 版本 -->
    <el-form-item class="!mb-[9px]" label="版本" prop="proj_res_ver">
      <el-input v-model.trim="form.proj_res_ver" placeholder="请填写版本" :validate-event="false" />
    </el-form-item>
  </el-form>
</template>

<script>
import { debounce } from 'lodash-es';

let that;

export default {
  name: 'ProjectResource',
  props: {
    modelValue: { type: String, default: '' },
  },
  emits: ['update:modelValue'],
  data() {
    return {
      form: {
        proj_res_type: '', // 来源
        proj_res_repo: '', // 仓库
        proj_res_br: '', // 分支
        proj_res_ver: '', // 版本
      },
    };
  },
  created() {
    // eslint-disable-next-line @typescript-eslint/no-this-alias
    that = this;
    try {
      this.form = { ...this.form, ...JSON.parse(this.modelValue || '{}') };
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
      handler: debounce(async () => {
        await that.validate();
      }, 500),
      deep: true,
    },
  },
  methods: {
    async validate() {
      if (Object.values(this.form).filter(v => v).length > 1) {
        await this.$refs.form.validate((valid) => {
          if (valid) {
            this.$emit('update:modelValue', JSON.stringify(this.form));
          } else {
            this.$emit('update:modelValue', '');
          }
        });
      } else {
        this.$emit('update:modelValue', '');
      }
    },
  },
};
</script>
