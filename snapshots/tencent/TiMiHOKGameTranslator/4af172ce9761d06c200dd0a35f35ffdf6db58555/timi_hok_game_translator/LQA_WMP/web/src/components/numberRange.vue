<!--
 * @Description: 数字范围（只允许正整数输入，极简版 - 保证输入流畅）
-->
<template>
  <div class="flex w-full">
    <el-input
      v-model="modelValue[0]"
      type="text"
      inputmode="numeric"
      clearable
      placeholder="最小值"
      maxlength="10"
      :onkeydown="blockInvalidKey"
      :onpaste="onPaste"
      :oninput="onNativeInput"
      :oncompositionend="onCompositionEnd"
      @blur="onBlur(0)"
    />
    <span class="mx-2"> - </span>
    <el-input
      v-model="modelValue[1]"
      type="text"
      inputmode="numeric"
      clearable
      placeholder="最大值"
      maxlength="10"
      :onkeydown="blockInvalidKey"
      :onpaste="onPaste"
      :oninput="onNativeInput"
      :oncompositionend="onCompositionEnd"
      @blur="onBlur(1)"
    />
  </div>
</template>

<script>
export default {
  name: 'numberRange',
  props: {
    modelValue: { type: Array, default: () => ['', ''] },
  },
  methods: {
    // 原生 DOM 层拦截非法键：所有非数字键（允许控制键）
    // 不触发 Vue 响应式，保证输入流畅
    blockInvalidKey(e) {
      // 允许常用控制键（删除、方向键、Tab、Home/End、Enter）
      const allowCtrl = ['Backspace', 'Delete', 'ArrowLeft', 'ArrowRight',
        'ArrowUp', 'ArrowDown', 'Home', 'End', 'Tab', 'Enter'];
      if (allowCtrl.includes(e.key)) return;
      // 允许 Ctrl+C / V / A / X 等组合键
      if (e.ctrlKey || e.metaKey) return;
      // 仅允许 0-9，其他一律拦截（包括 e / + / - / . / 字母等）
      if (!/^\d$/.test(e.key)) {
        e.preventDefault();
      }
    },
    // 原生 DOM 层拦截粘贴非法内容：如果有非数字字符，就阻止粘贴
    onPaste(e) {
      const text = (e.clipboardData || window.clipboardData).getData('text');
      if (!/^\d*$/.test(text)) {
        e.preventDefault();
      }
    },
    // 共用的 DOM 层清洗：若 input.value 含非数字字符，就地改为纯数字且不超过 10 位，
    // 并手动 dispatch 一次 input，让 el-input 的 v-model 同步到清洗后的值
    sanitizeDomValue(el) {
      if (!el) return;
      const raw = el.value;
      if (raw === '') return;
      const clean = String(raw).replace(/\D/g, '').slice(0, 10);
      if (clean !== raw) {
        el.value = clean;
        el.dispatchEvent(new Event('input', { bubbles: true }));
      }
    },
    // 原生 input 事件兜底：中文输入法切英文、候选词注入等场景
    onNativeInput(e) {
      // 输入法合成过程中不处理，等 compositionend 再统一清洗
      if (e.isComposing || e.inputType === 'insertCompositionText') return;
      this.sanitizeDomValue(e.target);
    },
    // 输入法合成结束（例如中文切英文塞进 e、中文候选词确认等）兜底清洗
    onCompositionEnd(e) {
      this.sanitizeDomValue(e.target);
    },
    // 失焦时兜底清洗：确保最终值合法
    onBlur(idx) {
      const raw = this.modelValue[idx];
      if (raw === '' || raw == null) return;
      // 保留数字字符
      const digits = String(raw).replace(/\D/g, '');
      if (digits === '') {
        this.modelValue[idx] = '';
        return;
      }
      // 限制在 10 位以内
      const clean = digits.slice(0, 10);
      if (clean !== String(raw)) {
        this.modelValue[idx] = clean;
      }
    },
  },
};
</script>
