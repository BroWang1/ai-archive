/* ============================================================================
 * TiMiHOKGameTranslator Web Console SPA
 * ----------------------------------------------------------------------------
 * 架构：
 *   - 工具层：api / utils / FieldInput（动态表单控件）/ FieldRow / FieldGroupedForm
 *   - 页面层：Dashboard / SetupWizard / GlobalConfigView / LlmView /
 *             LanguagesView / RunsView / RunDetailView / SchedulesView
 *   - 顶层 App：带侧边栏布局 + 基于 hash 的路由
 * ========================================================================== */

const { createApp, ref, reactive, computed, onMounted, onBeforeUnmount, watch, h, defineComponent, nextTick } = Vue;
const { ElMessage, ElMessageBox, ElNotification } = ElementPlus;

/* ========== API 封装 ========== */
const api = {
  async _req(method, url, body) {
    const opts = { method, headers: { "Content-Type": "application/json" } };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const resp = await fetch(url, opts);
    if (!resp.ok) {
      let msg = `${resp.status} ${resp.statusText}`;
      try {
 const data = await resp.json(); msg = data.detail || JSON.stringify(data); 
} catch (e) {}
      throw new Error(msg);
    }
    const ct = resp.headers.get("content-type") || "";
    if (ct.includes("application/json")) return await resp.json();
    return await resp.text();
  },
  get(u)        {
 return this._req("GET", u); 
},
  post(u, b)    {
 return this._req("POST", u, b); 
},
  put(u, b)     {
 return this._req("PUT", u, b); 
},
  del(u)        {
 return this._req("DELETE", u); 
},

  // setup
  setupStatus()               {
 return this.get("/api/setup/status"); 
},
  setupInit(payload)          {
 return this.post("/api/setup/init", payload); 
},
  getGlobalConfig()           {
 return this.get("/api/setup/global-config"); 
},
  putGlobalConfig(data)       {
 return this.put("/api/setup/global-config", data); 
},
  getLlm()                    {
 return this.get("/api/setup/llm"); 
},
  putLlm(data)                {
 return this.put("/api/setup/llm", data); 
},
  getSchema(kind)             {
 return this.get(`/api/setup/schema/${kind}`); 
},
  getPreferences()            {
 return this.get("/api/setup/preferences"); 
},
  putPreferences(data)        {
 return this.put("/api/setup/preferences", data); 
},

  // languages
  listLanguages()             {
 return this.get("/api/languages"); 
},
  getLanguage(id)             {
 return this.get(`/api/languages/${encodeURIComponent(id)}`); 
},
  saveLanguage(id, data)      {
 return this.put(`/api/languages/${encodeURIComponent(id)}`, data); 
},
  deleteLanguage(id)          {
 return this.del(`/api/languages/${encodeURIComponent(id)}`); 
},
  duplicateLanguage(src, dst) {
 return this.post(`/api/languages/${encodeURIComponent(src)}/duplicate`, { target_id: dst }); 
},

  // runs
  startRun(payload)           {
 return this.post("/api/runs", payload); 
},
  listRuns()                  {
 return this.get("/api/runs"); 
},
  getRun(id)                  {
 return this.get(`/api/runs/${encodeURIComponent(id)}`); 
},
  stopRun(id)                 {
 return this.post(`/api/runs/${encodeURIComponent(id)}/stop`, {}); 
},

  // schedules
  listSchedules()             {
 return this.get("/api/schedules"); 
},
  saveSchedule(id, body)      {
 return this.put(`/api/schedules/${encodeURIComponent(id)}`, body); 
},
  deleteSchedule(id)          {
 return this.del(`/api/schedules/${encodeURIComponent(id)}`); 
},
  toggleSchedule(id, enabled) {
 return this.post(`/api/schedules/${encodeURIComponent(id)}/toggle`, { enabled }); 
},

  // logs
  tailLog(runId, limit)       {
 return this.get(`/api/logs/${encodeURIComponent(runId)}?limit=${limit || 500}`); 
},

  // meta
  meta()                      {
 return this.get("/api/meta"); 
},
};

/* ========== 共享：LLM profiles 缓存 ==========
 * 用于 FieldInput 的 llm_profile_ref 下拉：避免每个实例独自 fetch，一次加载全局共享。
 * LlmView 新增/编辑/删除后应调用 refreshLlmProfiles() 失效缓存。
 */
const llmProfilesCache = ref([]);        // [{ name, provider, model }, ...]
const llmProfilesLoading = ref(false);
let _llmProfilesLoaded = false;
async function ensureLlmProfiles() {
  if (_llmProfilesLoaded || llmProfilesLoading.value) return;
  llmProfilesLoading.value = true;
  try {
    const reg = await api.getLlm();
    const profs = reg && reg.profiles ? reg.profiles : {};
    const list = [];
    for (const name of Object.keys(profs)) {
      const p = profs[name] || {};
      list.push({ name, provider: p.provider || "", model: p.model || "" });
    }
    // 排序：非 _example 优先，_example 置后；再按 name 字母序
    list.sort((a, b) => {
      const aEx = a.name.endsWith("_example") ? 1 : 0;
      const bEx = b.name.endsWith("_example") ? 1 : 0;
      if (aEx !== bEx) return aEx - bEx;
      return a.name.localeCompare(b.name);
    });
    llmProfilesCache.value = list;
    _llmProfilesLoaded = true;
  } catch (e) {
    console.warn("ensureLlmProfiles failed:", e);
  } finally {
    llmProfilesLoading.value = false;
  }
}
async function refreshLlmProfiles() {
  _llmProfilesLoaded = false;
  await ensureLlmProfiles();
}

/* ========== 工具函数 ========== */
function fmtTime(iso) {
 return iso ? String(iso).replace("T", " ") : "-"; 
}
function tsToHms(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/** 从嵌套对象读取 "a.b.c" 路径的值 */
function getByPath(obj, path, defaultValue = undefined) {
  if (!obj) return defaultValue;
  const parts = path.split(".");
  let cur = obj;
  for (const p of parts) {
    if (cur == null || typeof cur !== "object") return defaultValue;
    cur = cur[p];
  }
  return cur === undefined ? defaultValue : cur;
}

/** 在嵌套对象上按 "a.b.c" 路径设置值（自动创建中间节点） */
function setByPath(obj, path, value) {
  const parts = path.split(".");
  let cur = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    const key = parts[i];
    if (cur[key] == null || typeof cur[key] !== "object") cur[key] = {};
    cur = cur[key];
  }
  cur[parts[parts.length - 1]] = value;
}

/** YAML 工具（基于 CDN 引入的 js-yaml） */
function jsyamlLoad(text) {
  if (window.jsyaml) return window.jsyaml.load(text);
  try {
 return JSON.parse(text); 
} catch (e) {
 throw new Error("js-yaml 未加载完成，请刷新页面"); 
}
}
function jsyamlDump(obj) {
  if (window.jsyaml) return window.jsyaml.dump(obj, { noRefs: true, lineWidth: -1, sortKeys: false });
  return JSON.stringify(obj, null, 2);
}

/* ========== 共享状态 + 路由 ========== */
const AppState = reactive({
  setup: null,
  meta: null,
  route: "dashboard",
  routeParam: null,
});

function navigateTo(route, param) {
  const hash = param ? `#/${route}/${encodeURIComponent(param)}` : `#/${route}`;
  if (window.location.hash !== hash) window.location.hash = hash;
  else syncRouteFromHash();
}

function syncRouteFromHash() {
  const h = (window.location.hash || "#/dashboard").slice(2);
  const parts = h.split("/").filter(Boolean);
  AppState.route = parts[0] || "dashboard";
  AppState.routeParam = parts[1] ? decodeURIComponent(parts[1]) : null;
}

async function refreshSetup() {
  try {
 AppState.setup = await api.setupStatus(); 
} catch (e) {
 ElMessage.error(`无法连接到服务端：${  e.message}`); 
}
}

async function refreshMeta() {
  try {
 AppState.meta = await api.meta(); 
} catch (e) {}
}

/* ============================================================================
 * 组件：FieldInput —— 单字段控件（根据 schema.type 分派）
 * ========================================================================== */
const FieldInput = defineComponent({
  props: ["field", "modelValue"],
  emits: ["update:modelValue"],
  template: `
    <template v-if="field.type === 'select'">
      <el-select :model-value="val" @update:model-value="emit" style="width:100%;"
                 :placeholder="field.placeholder || '请选择'">
        <el-option v-for="opt in field.options || []" :key="opt" :value="opt" :label="opt || '(空)'" />
      </el-select>
    </template>
    <template v-else-if="field.type === 'llm_profile_ref'">
      <!-- LLM profile 下拉：选项来自 /api/setup/llm 的 profiles。
           默认显示所有已配置的 profile；带 _example 后缀的在描述里标注"模板"。 -->
      <el-select :model-value="val" @update:model-value="emit" filterable
                 style="width:100%;"
                 :placeholder="field.placeholder || '请选择已配置的 LLM profile'"
                 :loading="llmProfilesLoading">
        <template v-if="llmProfilesLoading">
          <el-option value="" label="加载中…" disabled />
        </template>
        <template v-else-if="!llmProfiles.length">
          <el-option value="" label="(尚未配置任何 LLM profile，请先去 LLM 模型页面新建)" disabled />
        </template>
        <el-option v-for="p in llmProfiles" :key="p.name" :value="p.name" :label="p.name">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">
            <span>
              <strong>{{ p.name }}</strong>
              <span v-if="p.name.endsWith('_example')"
                    style="margin-left:6px;color:#f59e0b;font-size:11px;">[模板]</span>
            </span>
            <span style="color:#6b7280;font-size:12px;">
              {{ p.provider }}<span v-if="p.model"> · {{ p.model }}</span>
            </span>
          </div>
        </el-option>
      </el-select>
      <div v-if="val && val.endsWith && val.endsWith('_example')"
           style="margin-top:4px;color:#f59e0b;font-size:12px;">
        ⚠️ 当前选择的是模板示例 profile，建议到「🤖 LLM 模型」页面复制一份、填好真实凭据后再引用。
      </div>
    </template>
    <template v-else-if="field.type === 'bool'">
      <el-switch :model-value="val === true" @update:model-value="emit" />
    </template>
    <template v-else-if="field.type === 'int' || field.type === 'float'">
      <el-input-number :model-value="numericVal" @update:model-value="emit"
                       :placeholder="field.placeholder"
                       :step="field.type === 'float' ? 0.1 : 1"
                       :precision="field.type === 'float' ? 2 : 0"
                       :controls-position="'right'"
                       style="width: 240px;" />
    </template>
    <template v-else-if="field.type === 'password'">
      <el-input :model-value="val" @update:model-value="emit" type="password" show-password
                :placeholder="field.placeholder || '敏感字段 — 建议走环境变量'" />
    </template>
    <template v-else-if="field.type === 'textarea'">
      <el-input :model-value="val" @update:model-value="emit" type="textarea" :rows="6"
                :placeholder="field.placeholder" />
    </template>
    <template v-else-if="field.type === 'list'">
      <el-select :model-value="val || []" @update:model-value="emit" multiple filterable
                 allow-create default-first-option :placeholder="field.placeholder || '回车新增一项'"
                 style="width:100%;" />
    </template>
    <template v-else-if="field.type === 'dict'">
      <div style="width:100%;">
        <el-input :model-value="dictText" @update:model-value="onDictInput"
                  type="textarea" :rows="4" class="yaml-editor"
                  :placeholder='field.placeholder || "{}"' />
        <div v-if="dictError" style="margin-top:4px;color:#dc2626;font-size:12px;">
          ⚠️ JSON 格式错误：{{ dictError }}（当前内容未保存，请修复后再提交）
        </div>
      </div>
    </template>
    <template v-else-if="field.type === 'workflow'">
      <div class="workflow-container">
        <div class="workflow-toolbar">
          <el-button size="small" @click="wfSelectAll">全选</el-button>
          <el-button size="small" @click="wfSelectRecommended">仅推荐</el-button>
          <el-button size="small" @click="wfClear">清空</el-button>
          <span style="color:#6b7280;font-size:12px;margin-left:8px;">
            已选 <b style="color:#1f2937;">{{ (val || []).length }}</b> / {{ workflowStatesMeta.length }} 个状态
          </span>
        </div>
        <div class="workflow-flow" ref="workflowFlowRef">
          <div v-for="(s, idx) in workflowStatesMeta" :key="s.key"
               class="workflow-node"
               :data-idx="idx"
               :class="{
                 selected: isWfSelected(s.key),
                 'is-recommended': s.recommended,
                 'is-first': idx === 0,
                 'row-first': rowFirstIndices.has(idx),
                 'row-last': rowLastIndices.has(idx),
               }"
               @click="toggleWf(s.key)">
            <div class="wf-head">
              <el-checkbox :model-value="isWfSelected(s.key)" @click.stop
                           @change="toggleWf(s.key)" />
              <span class="wf-order" v-if="isWfSelected(s.key)">
                {{ (val || []).indexOf(s.key) + 1 }}
              </span>
            </div>
            <div class="wf-body">
              <div class="wf-label">{{ s.label }}</div>
              <div class="wf-key"><code>{{ s.key }}</code></div>
              <div class="wf-desc">{{ s.desc }}</div>
              <el-tag v-if="s.group" type="info" size="small" effect="plain" style="margin-top:4px;">{{ s.group }}</el-tag>
            </div>
            <!-- 行末过渡箭头：当前节点是本行最后一个 **且不是整体最后一个**
                 时，右侧挂一个"→"示意流程继续到下一行开头的卡片。
                 用真实 DOM（而不是 ::after）是为了避开 is-recommended 的
                 ⭐ 伪元素占位，二者可以同时存在。 -->
            <span v-if="rowLastIndices.has(idx) && idx !== workflowStatesMeta.length - 1"
                  class="wf-tail-arrow" aria-hidden="true">→</span>
          </div>
        </div>
      </div>
    </template>
    <template v-else>
      <el-input :model-value="val" @update:model-value="emit" :placeholder="field.placeholder" />
    </template>
  `,
  setup(props, { emit }) {
    const val = computed(() => props.modelValue);
    const numericVal = computed(() => {
      const v = props.modelValue;
      if (v === "" || v == null) return undefined;
      const n = Number(v);
      return Number.isNaN(n) ? undefined : n;
    });
    // 若本字段是 llm_profile 引用，惰性加载一次全局 LLM profiles。
    if (props.field && props.field.type === "llm_profile_ref") {
      ensureLlmProfiles();
    }
    const emitVal = (v) => emit("update:modelValue", v);
    const asJson = (v) => {
      if (v == null || v === "") return "";
      // 兼容"历史脏数据"：旧版本把 textarea 原文（字符串）直接存进了
      // 绑定值。此时 v 本应是 object/null，却是 string → 尝试解析一次
      // 还原回 object；仍失败则按原字符串显示（JSON.stringify 会给它加
      // 外层引号 + 转义 \n/\"，就是用户看到的"没渲染"现象的来源）。
      if (typeof v === "string") {
        const t = v.trim();
        if (!t) return "";
        try {
          const parsed = JSON.parse(t);
          return JSON.stringify(parsed, null, 2);
        } catch (e) {
          return v;
        }
      }
      try {
 return JSON.stringify(v, null, 2); 
} catch (e) {
 return String(v); 
}
    };

    // ---- dict 类型专用：本地文本缓存 + JSON 错误提示 ----
    // 之前的实现在 JSON 解析失败时把"原始文本"回填到绑定值，导致 extra
    // 字段被污染成字符串，保存后持久化；下次再打开，asJson 对字符串做
    // JSON.stringify 会多一层引号与转义，出现用户看到的"没渲染"现象。
    //
    // 新实现：textarea 的值由 dictText 这个本地 ref 托管；用户输入时
    //   - 空白：emit {}；
    //   - 合法 JSON：emit 解析后的 object，并清空 dictError；
    //   - 非法：**不改动** emit 的值，只把错误写到 dictError，让 UI 高亮提示。
    // 外部 modelValue 变化（如编辑另一条 profile 时的重入）通过 watch
    // 同步到 dictText，不参与"每次按键 emit"的通路，避免抖动污染。
    const dictText = ref(asJson(props.modelValue));
    const dictError = ref("");
    watch(() => props.modelValue, (nv) => {
      // 父级外部赋值（load / editProfile）→ 把 object 转文本写到本地镜像
      const expected = asJson(nv);
      if (expected !== dictText.value) dictText.value = expected;
    });
    const onDictInput = (text) => {
      dictText.value = text;
      const t = (text || "").trim();
      if (!t) {
        dictError.value = "";
        emitVal({});
        return;
      }
      try {
        const parsed = JSON.parse(t);
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
          dictError.value = "必须是对象，例如 {\"key\": \"value\"}";
          return;
        }
        dictError.value = "";
        emitVal(parsed);
      } catch (e) {
        // 保留本地文本便于用户继续编辑；**不触发 emit** —— 绑定值维持
        // 最后一次合法状态，不会被污染。
        dictError.value = e.message || "JSON 解析失败";
      }
    };

    const workflowStates = computed(() => AppState.meta?.workflow_states || []);
    // workflow 状态的中文元数据（key / label / desc / group / recommended）
    const workflowStatesMeta = computed(() => {
      const meta = AppState.meta?.workflow_states_meta;
      if (Array.isArray(meta) && meta.length) return meta;
      // 后端未提供 meta 时退化为纯 key 列表
      return (AppState.meta?.workflow_states || []).map(k => ({
        key: k, label: k, desc: "", group: "", recommended: false,
      }));
    });
    const isWfSelected = (k) => Array.isArray(props.modelValue) && props.modelValue.includes(k);
    const toggleWf = (k) => {
      const cur = Array.isArray(props.modelValue) ? [...props.modelValue] : [];
      const i = cur.indexOf(k);
      if (i >= 0) {
        cur.splice(i, 1);
      } else {
        // 新加入的状态按 workflowStatesMeta 的推荐顺序插入到正确位置，
        // 保证"全选"后的默认顺序符合流水线逻辑；用户也可以通过先清空
        // 再按自己的顺序逐个勾选来定制。
        const metaOrder = workflowStatesMeta.value.map(m => m.key);
        const targetIdx = metaOrder.indexOf(k);
        let insertAt = cur.length;
        for (let j = 0; j < cur.length; j++) {
          if (metaOrder.indexOf(cur[j]) > targetIdx) {
 insertAt = j; break; 
}
        }
        cur.splice(insertAt, 0, k);
      }
      emitVal(cur);
    };
    const wfSelectAll = () => emitVal(workflowStatesMeta.value.map(m => m.key));
    const wfSelectRecommended = () => emitVal(
      workflowStatesMeta.value.filter(m => m.recommended).map(m => m.key)
    );
    const wfClear = () => emitVal([]);

    // -----------------------------------------------------------------------
    // 换行感知：标注"每行第一个 / 最后一个"节点，用于 CSS 控制箭头显隐。
    //
    // flex-wrap 布局下，CSS 无法原生检测"每行的第一个 flex item"（因为列数
    // 是响应式的、随容器宽度动态变化）。所以用 ResizeObserver 监听容器宽度
    // 变化，再读每个节点的 offsetTop：一旦某个节点的 offsetTop 大于上一个
    // 节点，就是"新一行的开头" —— 把该节点标为 row-first，让 CSS 隐藏其
    // 左侧 ::before 箭头；同时上一个节点标为 row-last。
    // -----------------------------------------------------------------------
    const workflowFlowRef = ref(null);
    const rowFirstIndices = reactive(new Set([0]));
    const rowLastIndices = reactive(new Set());

    const recomputeRowBreaks = () => {
      const container = workflowFlowRef.value;
      if (!container) return;
      const nodes = container.querySelectorAll(".workflow-node");
      if (!nodes.length) return;
      const firsts = new Set([0]);
      const lasts = new Set();
      let prevTop = nodes[0].offsetTop;
      for (let i = 1; i < nodes.length; i++) {
        const t = nodes[i].offsetTop;
        if (t > prevTop + 2) {   // 2px 容差，避免浮点误差误判
          firsts.add(i);
          lasts.add(i - 1);
          prevTop = t;
        }
      }
      lasts.add(nodes.length - 1);
      // 同步到 reactive Set（diff 后原地修改，避免整体替换触发无谓重渲染）
      rowFirstIndices.clear(); firsts.forEach(v => rowFirstIndices.add(v));
      rowLastIndices.clear();  lasts.forEach(v => rowLastIndices.add(v));
    };

    let resizeObserver = null;
    onMounted(() => {
      // 组件可能不是 workflow 类型，但是 setup 对所有 FieldInput 都会执行。
      // 这里只有在 ref 挂上后才会有效果；非 workflow 字段的 ref 永远是 null。
      nextTick(() => {
        if (!workflowFlowRef.value) return;
        recomputeRowBreaks();
        resizeObserver = new ResizeObserver(() => recomputeRowBreaks());
        resizeObserver.observe(workflowFlowRef.value);
      });
    });
    // 状态数增减时也触发重算
    watch(() => workflowStatesMeta.value.length, () => nextTick(recomputeRowBreaks));
    onBeforeUnmount(() => {
      if (resizeObserver) {
 resizeObserver.disconnect(); resizeObserver = null; 
}
    });

    return {
      val, numericVal, emit: emitVal, asJson,
      dictText, dictError, onDictInput,
      workflowStates, workflowStatesMeta,
      isWfSelected, toggleWf, wfSelectAll, wfSelectRecommended, wfClear,
      workflowFlowRef, rowFirstIndices, rowLastIndices,
      // LLM profile 下拉数据（供 type="llm_profile_ref" 使用）
      llmProfiles: llmProfilesCache, llmProfilesLoading,
    };
  },
});

/* ============================================================================
 * 组件：FieldRow —— 一行字段（label + badge + input + help + example）
 * ----------------------------------------------------------------------------
 * 支持 required_if 动态必填：当字段配置了 required_if + depends_on，且
 * 父字段当前值 ∈ required_if 列表时，视为必填。
 * ========================================================================== */
const FieldRow = defineComponent({
  components: { FieldInput },
  props: ["field", "modelValue", "effectiveRequired"],
  emits: ["update:modelValue"],
  template: `
    <div class="field-row" :class="{ required: isRequired, 'field-row-wide': field.type === 'workflow' }">
      <div class="field-label">
        <div class="label-text">
          <span>{{ field.label }}</span>
          <span class="badge badge-required" v-if="isRequired">必填</span>
          <span class="badge badge-optional" v-else>选填</span>
          <span class="badge badge-secret" v-if="field.secret">🔒 敏感</span>
        </div>
        <div class="label-key">{{ field.key }}</div>
        <div v-if="field.env_hint" class="label-key">
          <span class="badge badge-env">{{ field.env_hint }}</span>
        </div>
      </div>
      <div class="field-input">
        <field-input :field="field" :model-value="modelValue"
                     @update:model-value="v => $emit('update:modelValue', v)" />
        <div v-if="field.help" class="field-help" v-html="renderHelp(field.help)"></div>
        <div v-if="field.example" class="field-example">{{ field.example }}</div>
      </div>
    </div>
  `,
  setup(props) {
    const isRequired = computed(() => {
      // 父组件若显式传入 effectiveRequired（如解析了 required_if 的结果），优先用它
      if (props.effectiveRequired !== undefined && props.effectiveRequired !== null) {
        return !!props.effectiveRequired;
      }
      return !!props.field.required;
    });
    // 极简的 help 文案渲染：仅处理 `code` 和 **bold** 两种内联标记
    const renderHelp = (text) => {
      if (!text) return "";
      const escaped = String(text)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      return escaped
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    };
    return { isRequired, renderHelp };
  },
});

/* ============================================================================
 * 组件：FieldGroupedForm —— 分组渲染一组字段
 * ----------------------------------------------------------------------------
 * 【响应式】data 参数**必须是 reactive 对象**。本组件直接在 data 上原地
 * setByPath，不走 v-model、不克隆、不 emit。
 *
 * 【条件渲染】字段 schema 支持两种内置条件（无需父组件传 showField）：
 *   - depends_on + applies_to：仅当父字段值 ∈ applies_to 时才显示字段
 *   - depends_on + required_if：当父字段值 ∈ required_if 时该字段为必填
 * 父组件通过 props.showField 传入的自定义过滤会在内置过滤之后再应用。
 * ========================================================================== */
const FieldGroupedForm = defineComponent({
  components: { FieldRow },
  props: {
    schema: { type: Array, default: () => [] },
    data: { type: Object, required: true },
    /** 可选：根据分组名决定是否展示，返回 false 则该整组隐藏 */
    showGroup: { type: Function, default: null },
    /** 可选：按单个字段 key 做额外过滤（在内置 depends_on 过滤后再执行） */
    showField: { type: Function, default: null },
  },
  template: `
    <div>
      <div v-for="g in groups" :key="g.name" class="field-group" :class="{ collapsed: isCollapsed(g.name) }">
        <div class="field-group-header" @click="toggle(g.name)">
          <span>📁 {{ g.name }}  <span style="color:#9ca3af;font-weight:400;font-size:12px;margin-left:6px;">({{ g.fields.length }} 项)</span></span>
          <span class="group-arrow">▼</span>
        </div>
        <div class="field-table">
          <field-row v-for="f in g.fields" :key="f.key" :field="f"
                     :effective-required="computeRequired(f)"
                     :model-value="getVal(f.key, f.default)"
                     @update:model-value="v => setVal(f.key, v)" />
        </div>
      </div>
    </div>
  `,
  setup(props) {
    const collapsed = reactive({});
    const toggle = (name) => {
 collapsed[name] = !collapsed[name]; 
};
    const isCollapsed = (name) => !!collapsed[name];

    /** 判断 schema 的内置条件（depends_on + applies_to）是否满足 */
    const passesDependsOn = (f) => {
      if (!f.depends_on || !Array.isArray(f.applies_to) || !f.applies_to.length) return true;
      const parent = getByPath(props.data, f.depends_on);
      return f.applies_to.includes(parent);
    };

    /** 计算字段"动态必填"结果：先看 required，再看 required_if */
    const computeRequired = (f) => {
      if (f.required) return true;
      if (f.depends_on && Array.isArray(f.required_if) && f.required_if.length) {
        const parent = getByPath(props.data, f.depends_on);
        return f.required_if.includes(parent);
      }
      return false;
    };

    const groups = computed(() => {
      const map = new Map();
      for (const f of props.schema) {
        if (!passesDependsOn(f)) continue;              // 内置条件
        if (props.showField && !props.showField(f)) continue;  // 外部过滤
        const name = f.group || "其他";
        if (props.showGroup && !props.showGroup(name)) continue;
        if (!map.has(name)) map.set(name, { name, fields: [] });
        map.get(name).fields.push(f);
      }
      return Array.from(map.values());
    });

    const getVal = (key, def) => {
      const v = getByPath(props.data, key);
      return v === undefined ? def : v;
    };

    /** 原地写：Vue 响应式系统会自动追踪 */
    const setVal = (key, v) => {
      setByPath(props.data, key, v);
      // 字段级联动：source.format 变更时同步 source.path 的后缀，
      // 避免"选了 xlsx 但路径还是 .json 结尾"的典型配错。
      syncPathExtensionOnFormatChange(key, v);
    };

    /**
     * 当 ``key === 'source.format'`` 时，把兄弟字段 ``source.path`` 末尾
     * 的扩展名改成和新 format 对应的扩展名；仅在 path 当前后缀**也是**已知
     * 翻译格式后缀时才替换，避免把用户手动写的非常规文件名（如
     * ``i18n/strings.properties``）误伤。
     */
    const syncPathExtensionOnFormatChange = (key, newFormat) => {
      if (key !== "source.format" || !newFormat) return;
      const currentPath = getByPath(props.data, "source.path");
      if (!currentPath || typeof currentPath !== "string") return;

      // format → 规范扩展名（含点）；多备选扩展名用第一项作为默认写入值
      const FORMAT_EXT_MAP = {
        json:     [".json"],
        xlsx:     [".xlsx", ".xls"],
        csv:      [".csv"],
        xml:      [".xml"],
        dtxml:    [".dtxml"],
        html:     [".html", ".htm"],
        yaml:     [".yaml", ".yml"],
        xliff:    [".xlf", ".xliff"],
        markdown: [".md", ".markdown"],
        md:       [".md", ".markdown"],
      };
      const targetExts = FORMAT_EXT_MAP[String(newFormat).toLowerCase()];
      if (!targetExts || !targetExts.length) return;
      const newExt = targetExts[0];

      // 识别当前路径的后缀：扫描所有已知格式对应的扩展名，若命中则替换；
      // 若已经是目标 format 对应后缀之一，则无需操作。
      const lower = currentPath.toLowerCase();
      if (targetExts.some((ext) => lower.endsWith(ext))) return;

      const KNOWN_EXTS = Object.values(FORMAT_EXT_MAP).flat();
      const matched = KNOWN_EXTS.find((ext) => lower.endsWith(ext));
      if (!matched) return;  // 用户用的是非标后缀（如 .properties），不动它

      // 保留原路径的大小写与目录部分，仅替换末尾后缀
      const newPath = currentPath.slice(0, currentPath.length - matched.length) + newExt;
      if (newPath !== currentPath) {
        setByPath(props.data, "source.path", newPath);
      }
    };

    return { groups, toggle, isCollapsed, getVal, setVal, computeRequired };
  },
});

/* ============================================================================
 * 组件：Dashboard
 * ========================================================================== */
const Dashboard = defineComponent({
  template: `
    <div>
      <!-- 顶部欢迎 / 快捷操作 -->
      <div class="card" style="background: linear-gradient(135deg, #fff 0%, #f8fafc 100%);">
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px;">
          <div>
            <h2 style="margin:0 0 6px 0;font-size:20px;">
              {{ setup?.initialized ? '👋 欢迎回来' : '🚀 开始配置您的本地化流水线' }}
            </h2>
            <p style="margin:0;color:#6b7280;font-size:14px;">
              <span v-if="setup?.initialized">所有核心配置就绪，可以创建语种 profile 并开始运行。</span>
              <span v-else>检测到初始化尚未完成，请前往设置向导。</span>
            </p>
          </div>
          <div style="display:flex;gap:10px;">
            <el-button @click="openWizard" size="large">
              {{ setup?.initialized ? '🧰 重新初始化' : '🚀 初始化向导' }}
            </el-button>
            <el-button type="primary" size="large" @click="go('languages')">🌐 管理语种</el-button>
          </div>
        </div>
      </div>

      <!-- 统计卡 -->
      <div class="stat-grid">
        <div class="stat-card" :class="setup?.config_yaml_exists ? 'success' : 'warning'">
          <div class="stat-label">⚙️ 全局配置</div>
          <div class="stat-value">{{ setup?.config_yaml_exists ? '✓' : '—' }}</div>
          <div class="stat-sub">{{ setup?.config_yaml_exists ? 'conf/config.yaml 已就绪' : '尚未创建' }}</div>
        </div>
        <div class="stat-card" :class="setup?.llm_yaml_exists ? 'success' : 'warning'">
          <div class="stat-label">🤖 LLM 注册表</div>
          <div class="stat-value">{{ setup?.llm_yaml_exists ? '✓' : '—' }}</div>
          <div class="stat-sub">{{ setup?.llm_yaml_exists ? 'conf/llm.yaml 已就绪' : '尚未创建' }}</div>
        </div>
        <div class="stat-card info">
          <div class="stat-label">🌐 语种 Profile</div>
          <div class="stat-value">{{ setup?.languages_count || 0 }}</div>
          <div class="stat-sub">conf/languages/*.yaml</div>
        </div>
        <div class="stat-card primary">
          <div class="stat-label">📈 系统状态</div>
          <div class="stat-value" style="font-size: 20px;">{{ setup?.initialized ? '运行就绪' : '待初始化' }}</div>
          <div class="stat-sub">{{ setup?.initialized ? '可开始工作' : '请完成初始化' }}</div>
        </div>
      </div>

      <!-- 健康检查 -->
      <div class="card">
        <div class="card-header">
          <h3><span class="emoji">🩺</span> 配置健康检查</h3>
          <el-button @click="refresh" :icon="refreshIcon">刷新</el-button>
        </div>
        <div class="check-list">
          <div v-for="c in (setup?.checks || [])" :key="c.module"
               class="check-item" :class="'status-' + c.status">
            <div class="check-icon">
              <span v-if="c.status === 'ok'">✓</span>
              <span v-else-if="c.status === 'fail'">!</span>
              <span v-else-if="c.status === 'warn'">⚠</span>
              <span v-else>—</span>
            </div>
            <div class="check-body">
              <div class="check-title">{{ c.label }}</div>
              <div class="check-message">{{ c.message }}</div>
              <ul v-if="c.details && c.details.length" class="check-details">
                <li v-for="(d, i) in c.details" :key="i">{{ d }}</li>
              </ul>
              <div v-if="c.env_hints && c.env_hints.length" class="env-hints">
                <span v-for="h in c.env_hints" :key="h" class="env-hint">export {{ h }}=...</span>
              </div>
            </div>
            <div v-if="c.status === 'fail'" style="display:flex;align-items:center;">
              <el-button size="small" type="primary" @click="jumpToFix(c.module)">去修复</el-button>
            </div>
          </div>
        </div>
      </div>

      <!-- 最近运行 -->
      <div class="card">
        <div class="card-header">
          <h3><span class="emoji">🕒</span> 最近运行</h3>
          <el-button @click="go('runs')" link type="primary">查看全部 →</el-button>
        </div>
        <div v-if="!runs.length" class="empty-state">
          <div class="empty-icon">📭</div>
          <div class="empty-title">还没有任何运行记录</div>
          <div class="empty-desc">配置好一个语种 profile，到"语种配置"页点"立即运行"开始</div>
          <el-button type="primary" @click="go('languages')">去配置语种</el-button>
        </div>
        <el-table v-else :data="runs.slice(0, 5)" style="width:100%">
          <el-table-column prop="run_id" label="Run ID" min-width="260" show-overflow-tooltip />
          <el-table-column prop="language" label="语种" width="100" />
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <span :class="'run-status ' + row.status">{{ row.status }}</span>
            </template>
          </el-table-column>
          <el-table-column label="开始时间" width="180">
            <template #default="{ row }">{{ fmtTime(row.started_at) }}</template>
          </el-table-column>
          <el-table-column label="结束时间" min-width="180">
            <template #default="{ row }">{{ fmtTime(row.finished_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="110" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="toRun(row.run_id)">日志</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  `,
  setup() {
    const setup = computed(() => AppState.setup);
    const runs = ref([]);
    const refreshIcon = ref("Refresh");
    let timer = null;

    const load = async () => {
      try {
 runs.value = await api.listRuns(); 
} catch(e){}
    };
    const refresh = async () => {
 await refreshSetup(); await load(); ElMessage.success("已刷新"); 
};
    const go = (k) => navigateTo(k);
    const toRun = (id) => navigateTo("run", id);
    const openWizard = () => navigateTo("setup");
    const jumpToFix = (module) => {
      if (module === "llm") navigateTo("llm");
      else if (module === "languages") navigateTo("languages");
      else navigateTo("global-config");
    };

    onMounted(() => {
 load(); timer = setInterval(load, 5000); 
});
    onBeforeUnmount(() => timer && clearInterval(timer));
    return { setup, runs, refreshIcon, refresh, go, toRun, openWizard, jumpToFix, fmtTime };
  },
});

/* ============================================================================
 * 组件：SetupWizard —— 清爽的 4 步向导
 * ----------------------------------------------------------------------------
 * 核心设计：
 *   - 不再要求用户选"一审 / 二审"（它们是语种级配置，在"语种 Profile"创建时选）
 *   - 每一步直接显示该步的输入字段，不要先选再填
 *   - 已有配置时自动带入作为初始值
 * ========================================================================== */
const SetupWizard = defineComponent({
  components: { FieldGroupedForm },
  template: `
    <div class="wizard-page">
      <!-- Hero -->
      <div class="wizard-hero">
        <h1>🎮 TiMiHOKGameTranslator 初始化向导</h1>
        <p>只需 4 步完成基础配置。<b>一审 / 二审平台</b>是语种级配置，稍后在"语种 Profile"页面创建时按需选择。</p>
      </div>

      <!-- 步骤指示器 -->
      <div class="wizard-step-indicator">
        <div v-for="(name, i) in stepNames" :key="i" style="display:flex;align-items:center;">
          <div class="wizard-step" :class="{ active: step === i, done: step > i }">
            <div class="step-num"><span v-if="step > i">✓</span><span v-else>{{ i + 1 }}</span></div>
            <span>{{ name }}</span>
          </div>
          <div v-if="i < stepNames.length - 1" class="wizard-connector" :class="{ done: step > i }"></div>
        </div>
      </div>

      <!-- Step 0: 项目 + VCS -->
      <div v-if="step === 0" class="card">
        <div class="card-header"><h3><span class="emoji">⚙️</span> 项目基础 + 版本控制</h3></div>
        <el-alert type="info" :closable="false" show-icon style="margin-bottom:16px;"
                  title="第一次使用建议先把 vcs.type 选 'local' 跑通最简链路（无需远端 VCS，直接读写本地目录）；真实项目再切换到 svn / git / perforce。" />
        <field-grouped-form :schema="basicVcsSchema" :data="form" />
      </div>

      <!-- Step 1: LLM -->
      <div v-if="step === 1" class="card">
        <div class="card-header"><h3><span class="emoji">🤖</span> LLM 大模型配置</h3></div>
        <el-alert type="info" :closable="false" show-icon style="margin-bottom:16px;"
                  title="至少需要一个 profile。provider 选 'echo' 即可零依赖试跑（回显式占位 LLM）；接入 openai / 混元 / deepseek 等请选择对应 provider 并填 api_key（强烈建议走环境变量 GAME_TRANS_TOOLCHAIN__LLM__API_KEY）。" />
        <field-grouped-form :schema="llmSchema" :data="llmProfile" />
      </div>

      <!-- Step 2: 全局审校平台 + 通知（都可选，选 none 即跳过） -->
      <div v-if="step === 2">
        <div class="card">
          <div class="card-header"><h3><span class="emoji">🎨</span> 审校平台（可选，一审 / 二审统一使用）</h3></div>
          <el-alert type="info" :closable="false" show-icon style="margin-bottom:16px;">
            <template #default>
              <b>一个项目只需配置一个审校平台</b>。无论一审、二审还是轻校对，都使用这里选择的平台 ——
              只是在每个语种的 reviews.* 下填不同的 <code>project_id</code> 区分项目。
              <br/>如果不打算使用审校平台，保持 <code>none</code> 即可。
            </template>
          </el-alert>
          <div class="pick-grid">
            <div v-for="opt in platformOptions" :key="opt.value" class="pick-card"
                 :class="{ selected: form.platform.type === opt.value }"
                 @click="selectPlatform(opt.value)">
              <div class="pick-emoji">{{ opt.emoji }}</div>
              <div class="pick-title">{{ opt.label }}</div>
              <div class="pick-desc">{{ opt.desc }}</div>
            </div>
          </div>

          <div v-if="form.platform.type !== 'none'" style="margin-top:20px;">
            <field-grouped-form :schema="platformFieldsSchema" :data="form"
                                :show-field="(f) => shouldShowPlatformField(f)" />
          </div>
        </div>

        <div class="card">
          <div class="card-header"><h3><span class="emoji">📣</span> 通知渠道（可选）</h3></div>
          <div class="pick-grid">
            <div v-for="opt in notifyOptions" :key="opt.value" class="pick-card"
                 :class="{ selected: form.notification.type === opt.value }"
                 @click="selectNotify(opt.value)">
              <div class="pick-emoji">{{ opt.emoji }}</div>
              <div class="pick-title">{{ opt.label }}</div>
              <div class="pick-desc">{{ opt.desc }}</div>
            </div>
          </div>

          <div v-if="needsWebhook" style="margin-top:20px;">
            <field-grouped-form :schema="notifyFieldsSchema" :data="form"
                                :show-field="(f) => f.key !== 'notification.type'" />
          </div>
        </div>
      </div>

      <!-- Step 3: 完成 -->
      <div v-if="step === 3" class="card" style="text-align:center;padding:40px;">
        <div style="font-size:72px;margin-bottom:16px;">🎉</div>
        <h2 style="margin:0 0 8px 0;">准备就绪</h2>
        <p style="color:#6b7280;margin:0 0 20px 0;line-height:1.8;">
          点击下方按钮，将配置写入到 <code>conf/config.yaml</code> 与 <code>conf/llm.yaml</code>。<br/>
          完成后在"语种 Profile"页面创建第一个语种即可开始使用。
        </p>
        <div style="background:#f8fafc;border:1px solid #e5e7eb;border-radius:8px;padding:14px 20px;text-align:left;max-width:520px;margin:0 auto;">
          <div style="font-weight:600;margin-bottom:8px;">📋 本次配置概览</div>
          <div style="font-size:13px;color:#6b7280;line-height:1.8;">
            项目：<code>{{ form.project_code }}</code><br/>
            VCS：<code>{{ form.vcs.type }}</code><span v-if="form.vcs.url"> · {{ form.vcs.url }}</span><br/>
            LLM：<code>{{ llmProfile.name }}</code> ({{ llmProfile.provider }})<br/>
            全局平台：<code>{{ form.platform.type }}</code><br/>
            通知：<code>{{ form.notification.type }}</code>
          </div>
        </div>
      </div>

      <!-- 底部按钮 -->
      <div style="display:flex;justify-content:space-between;align-items:center;margin:24px 0 40px;">
        <el-button v-if="step > 0" @click="prevStep">← 上一步</el-button>
        <div v-else></div>
        <div style="color:#9ca3af;font-size:13px;">步骤 {{ step + 1 }} / {{ stepNames.length }}</div>
        <el-button v-if="step < 3" type="primary" size="large" @click="nextStep">下一步 →</el-button>
        <el-button v-else type="primary" size="large" :loading="submitting" @click="onSubmit">
          🚀 完成并写入配置
        </el-button>
      </div>
    </div>
  `,
  setup() {
    const step = ref(0);
    const submitting = ref(false);
    const stepNames = ["项目 & VCS", "LLM 模型", "审校 & 通知", "完成"];

    const platformOptions = [
      { value: "none", emoji: "🚫", label: "不启用", desc: "跳过全局审校平台" },
      { value: "phrase", emoji: "📘", label: "Phrase TMS", desc: "原 Memsource，支持 EU/US 账户" },
      { value: "crowdin", emoji: "🌍", label: "Crowdin", desc: "Crowdin API v2" },
    ];

    const notifyOptions = [
      { value: "none", emoji: "🔕", label: "不启用", desc: "不发送任何通知" },
      { value: "console", emoji: "💻", label: "控制台", desc: "仅打印到日志，无外部通知" },
      { value: "wecom", emoji: "💬", label: "企业微信", desc: "群机器人 webhook" },
    ];

    // reactive 对象 —— FieldGroupedForm 直接原地修改
    const form = reactive({
      project_code: "my_game",
      stage: "trunk_week",
      source_locale: "zh-CN",
      languages_dir: "conf/languages",
      vcs: { type: "local", url: "", revision: "HEAD", local_path: "", username: "", password: "",
             cli_timeout_seconds: 600, default_commit_message: "[TiMi_HOK_Game_Translator] commit translation data" },
      platform: { type: "none", api_base: "", api_token: "", project_id: "", extra: {} },
      notification: { type: "none", webhook: "", mentioned: [] },
      llm_profile: "default",
      workspace: { root: "", subdir: "workspace", state_filename: "workflow_state.json" },
      logging: { level: "INFO", directory: "logs", filename: "TiMi_HOK_Game_Translator.log", console: true },
    });

    const llmProfile = reactive({
      name: "default", provider: "echo", model: "echo-dev", api_base: "", api_key: "",
      temperature: 0.2, max_tokens: 1024, batch_size: 16,
      timeout_seconds: 60, retries: 3, retry_interval_seconds: 10, extra: {},
    });

    const globalSchema = ref([]);
    const llmProfileSchema = ref([]);

    // Step 0: 只显示 "项目基础" + "版本控制" 分组
    const basicVcsSchema = computed(() =>
      globalSchema.value.filter((f) => ["项目基础", "版本控制"].includes(f.group))
    );

    // Step 1: 完整 LLM profile schema
    const llmSchema = computed(() => llmProfileSchema.value);

    // Step 2: 全局审校平台字段（排除 platform.type 本身，根据平台类型过滤）
    const platformFieldsSchema = computed(() =>
      globalSchema.value.filter((f) => f.group === "审校平台")
    );

    // 根据选中的平台类型决定显示哪些字段
    //   - 排除 platform.type 本身（Setup 向导用卡片选择，而非下拉）
    //   - Phrase 专属字段的"选 Phrase 才显示"由 schema 的 applies_to 自动处理
    const shouldShowPlatformField = (f) => f.key !== "platform.type";

    // Step 2: 通知字段
    const notifyFieldsSchema = computed(() =>
      globalSchema.value.filter((f) => f.group === "通知")
    );

    // 选中企业微信时才需要显示 webhook 字段
    const needsWebhook = computed(() =>
      form.notification.type === "wecom"
    );

    const selectPlatform = (v) => {
      form.platform.type = v;
      // 自动填充 api_base 常用默认
      if (v === "crowdin" && !form.platform.api_base) {
        form.platform.api_base = "https://api.crowdin.com/api/v2";
      } else if (v === "phrase" && !form.platform.api_base) {
        form.platform.api_base = "https://cloud.memsource.com/web/api2";
      }
    };

    const selectNotify = (v) => {
 form.notification.type = v; 
};

    const loadSchemas = async () => {
      try {
        const [g, l] = await Promise.all([api.getSchema("global"), api.getSchema("llm_profile")]);
        globalSchema.value = g.fields;
        llmProfileSchema.value = l.fields;
      } catch (e) {
 ElMessage.error(`加载 schema 失败：${  e.message}`); 
}
    };

    const nextStep = () => {
      // 分步校验
      if (step.value === 0) {
        if (!form.project_code) {
 ElMessage.warning("project_code 必填"); return; 
}
        if (!form.vcs.type) {
 ElMessage.warning("vcs.type 必填"); return; 
}
        // local_path 对所有 vcs.type（含 mock）都必填 —— 它是流水线落地的工作副本目录
        if (!form.vcs.local_path) {
          ElMessage.warning("vcs.local_path 必填（流水线读写源文件/译文的根目录；local 推荐填绝对路径）");
          return;
        }
        // local 和老别名 mock 都不需要 vcs.url
        if (form.vcs.type !== "local" && form.vcs.type !== "mock") {
          if (!form.vcs.url) {
 ElMessage.warning("vcs.url 必填"); return; 
}
        }
      }
      if (step.value === 1) {
        if (!llmProfile.name) {
 ElMessage.warning("LLM profile 名称必填"); return; 
}
        if (!/^[a-zA-Z0-9_-]+$/.test(llmProfile.name)) {
          ElMessage.warning("profile 名称只允许字母、数字、下划线、连字符");
          return;
        }
        if (!llmProfile.provider) {
 ElMessage.warning("provider 必填"); return; 
}
        // provider=echo（老别名 mock）不需要其它字段
        if (llmProfile.provider !== "echo" && llmProfile.provider !== "mock") {
          if (!llmProfile.model) {
 ElMessage.warning("model 必填"); return; 
}
          const needsBase = ["openai_compatible", "venus", "hunyuan_translation"];
          if (needsBase.includes(llmProfile.provider) && !llmProfile.api_base) {
            ElMessage.warning(`provider=${llmProfile.provider} 需要填写 api_base`);
            return;
          }
          const needsKey = ["openai", "openai_compatible", "anthropic", "gemini", "hunyuan_translation"];
          if (needsKey.includes(llmProfile.provider) && !llmProfile.api_key) {
            ElNotification({
              type: "info", duration: 4000, title: "提示",
              message: "api_key 为空 —— 请确认已通过环境变量 GAME_TRANS_TOOLCHAIN__LLM__API_KEY 注入",
            });
          }
          if (llmProfile.provider === "venus") {
            const ex = llmProfile.extra || {};
            if (!ex.server_id || !ex.app_group_id) {
              ElMessage.warning("venus 需要填写 extra.server_id 和 extra.app_group_id");
              return;
            }
          }
          if (llmProfile.provider === "hunyuan_translation") {
            const ex = llmProfile.extra || {};
            if (!ex.wsid) {
              ElMessage.warning("hunyuan_translation 需要填写 extra.wsid");
              return;
            }
          }
        }
      }
      if (step.value === 2) {
        if (form.platform.type !== "none" && !form.platform.api_token
            && !form.platform.extra?.subject_token) {
          // 不强制 —— 允许走环境变量
          ElNotification({
            type: "info", duration: 3000,
            title: "提示", message: "api_token 为空 —— 请确保已通过环境变量 GAME_TRANS_TOOLCHAIN__PLATFORM__API_TOKEN 注入",
          });
        }
      }
      step.value += 1;
      scrollWizardToTop();
    };

    // 上一步：复用同一个滚动归位逻辑，避免用户进入下一个表单时还处于页面中段
    const prevStep = () => {
      if (step.value > 0) {
        step.value -= 1;
        scrollWizardToTop();
      }
    };

    // 把 .content 滚动容器（见 app.css：.content { overflow: auto }）滚回顶部。
    // 必须等 Vue 完成 DOM diff 后再滚，否则新表单还没渲染到位。
    const scrollWizardToTop = () => {
      nextTick(() => {
        const el = document.querySelector(".content");
        if (el && typeof el.scrollTo === "function") {
          el.scrollTo({ top: 0, behavior: "smooth" });
        } else if (el) {
          el.scrollTop = 0;
        }
        // 极端情况（如移动端）整个 window 也可能有滚动条，兜底归零
        try {
 window.scrollTo({ top: 0, behavior: "smooth" }); 
} catch {
 window.scrollTo(0, 0); 
}
      });
    };

    const onSubmit = async () => {
      submitting.value = true;
      try {
        form.llm_profile = llmProfile.name || "default";
        // 只把**用户实际填入的字段**写进 payload，避免 undefined/空值
        // 覆盖 llm.yaml 里已有示例 profile 的 placeholder（如 ""、注释等）。
        const profilePayload = {};
        const KEYS = ["provider", "model", "api_base", "api_key", "temperature",
                      "max_tokens", "batch_size", "timeout_seconds", "retries",
                      "retry_interval_seconds"];
        for (const k of KEYS) {
          const v = llmProfile[k];
          if (v !== undefined && v !== null && v !== "") {
            profilePayload[k] = v;
          }
        }
        // extra 单独处理：里面可能有嵌套字典（如 model_params / generation_config）
        if (llmProfile.extra && typeof llmProfile.extra === "object") {
          const cleanExtra = {};
          for (const k of Object.keys(llmProfile.extra)) {
            const v = llmProfile.extra[k];
            if (v !== undefined && v !== null && v !== "") {
              cleanExtra[k] = v;
            }
          }
          if (Object.keys(cleanExtra).length) {
            profilePayload.extra = cleanExtra;
          }
        }
        const llm = {
          default: llmProfile.name,
          profiles: { [llmProfile.name]: profilePayload },
        };
        // 透出一份偏好便于下次向导恢复
        const preferences = {
          platform_type: form.platform.type,
          notification_type: form.notification.type,
        };
        await api.setupInit({ config: form, llm, preferences });
        await refreshSetup();
        // 二次确认 setup 状态，确认已初始化再引导下一步
        const latest = AppState.setup;
        if (latest && latest.initialized) {
          try {
            await ElMessageBox.confirm(
              "配置已写入 conf/。接下来需要配置至少一个语种 profile（source.path / target_locale / 审校项目 ID 等），才能启动翻译流水线。",
              "🎉 初始化完成",
              {
                confirmButtonText: "前往配置语种",
                cancelButtonText: "回主控台",
                type: "success",
                center: true,
              },
            );
            navigateTo("languages");
          } catch (_cancel) {
            navigateTo("dashboard");
          }
        } else {
          // 不常见：init 成功但 status 未通过（例如用户配了 venus 但没填 secret_id）
          const missing = (latest && latest.missing_fields) || [];
          ElMessageBox.alert(
            `配置已写入，但以下字段仍需补齐（可以在相应页面继续编辑后再次刷新状态）：\n\n• ${ 
              missing.length ? missing.join("\n• ") : "（无详细信息，请在 Dashboard 查看 ⚠️ 配置健康检查）"}`,
            "⚠️ 配置未完全就绪",
            { confirmButtonText: "我知道了，去主控台看看", type: "warning" },
          ).finally(() => navigateTo("dashboard"));
        }
      } catch (e) {
        ElMessage.error(`初始化失败：${  e.message}`);
      } finally {
        submitting.value = false;
      }
    };

    onMounted(async () => {
      await loadSchemas();
      // 带入已有配置作为初始值
      try {
        const existing = await api.getGlobalConfig();
        if (existing && Object.keys(existing).length) {
          // **只在已经初始化过**时才回填 vcs 配置，否则 config.yaml 的示例值
          // （如 vcs.type: svn）会覆盖我们对首次用户更友好的默认 'local'。
          const alreadyInitialized = !!AppState.setup?.initialized;
          if (!alreadyInitialized && existing.vcs) {
            // 克隆一份浅拷贝，剔除 type 以保留前端的 'local' 默认
            const vcsSafe = { ...existing.vcs };
            delete vcsSafe.type;
            // 用剔除后的 vcs 覆盖原字段，但不动前端默认 type
            const existingSafe = { ...existing, vcs: vcsSafe };
            deepMergeInto(form, existingSafe);
          } else {
            deepMergeInto(form, existing);
          }
        }
        const existingLlm = await api.getLlm();
        if (existingLlm?.profiles && existingLlm.default && existingLlm.profiles[existingLlm.default]) {
          const p = existingLlm.profiles[existingLlm.default];
          llmProfile.name = existingLlm.default;
          for (const k of Object.keys(p || {})) llmProfile[k] = p[k];
        }
      } catch (e) {}
    });

    return {
      step, stepNames, submitting,
      platformOptions, notifyOptions,
      form, llmProfile,
      basicVcsSchema, llmSchema, platformFieldsSchema, notifyFieldsSchema, needsWebhook,
      shouldShowPlatformField,
      selectPlatform, selectNotify,
      nextStep, prevStep, onSubmit,
    };
  },
});

/** 原地深合并：把 source 的值合并到 target（reactive），保持引用不变 */
function deepMergeInto(target, source) {
  if (!source || typeof source !== "object") return;
  for (const k of Object.keys(source)) {
    const sv = source[k];
    if (sv && typeof sv === "object" && !Array.isArray(sv)
        && target[k] && typeof target[k] === "object" && !Array.isArray(target[k])) {
      deepMergeInto(target[k], sv);
    } else {
      target[k] = sv;
    }
  }
}

/* ============================================================================
 * 组件：GlobalConfigView —— 结构化表单 + YAML 原文双视图
 * ========================================================================== */
const GlobalConfigView = defineComponent({
  components: { FieldGroupedForm },
  template: `
    <div>
      <div class="card">
        <div class="toolbar">
          <div class="left">
            <h3 style="margin:0;"><span style="font-size:20px;">⚙️</span> 全局配置 (conf/config.yaml)</h3>
            <el-tag type="info">按分组填写</el-tag>
          </div>
          <div class="right">
            <div class="view-switch">
              <button :class="{active: view === 'form'}" @click="switchView('form')">📋 表单</button>
              <button :class="{active: view === 'yaml'}" @click="switchView('yaml')">📝 YAML</button>
            </div>
            <el-button @click="load">重新加载</el-button>
            <el-button type="primary" :loading="saving" @click="save">💾 保存</el-button>
          </div>
        </div>
        <el-alert type="info" :closable="false" style="margin-bottom:16px;" show-icon
                  title="所有敏感字段（🔒 标记）建议走环境变量注入。保存前会自动备份到 conf/.backup/。" />

        <field-grouped-form v-if="view === 'form'" :schema="schema" :data="data" />
        <el-input v-else v-model="yamlText" type="textarea" :rows="28" class="yaml-editor" />
      </div>
    </div>
  `,
  setup() {
    const view = ref("form");
    const data = reactive({});
    const yamlText = ref("");
    const schema = ref([]);
    const saving = ref(false);

    const resetData = (next) => {
      // 原地清空再合入，保持 reactive 引用
      for (const k of Object.keys(data)) delete data[k];
      if (next && typeof next === "object") Object.assign(data, next);
    };

    // 字段级条件渲染现已由 schema 的 depends_on + applies_to 元信息驱动，
    // FieldGroupedForm 内置支持，无需在此处再做自定义过滤。

    const load = async () => {
      try {
        const [cfg, sch] = await Promise.all([api.getGlobalConfig(), api.getSchema("global")]);
        resetData(cfg || {});
        yamlText.value = jsyamlDump(cfg || {});
        schema.value = sch.fields;
      } catch (e) {
 ElMessage.error(`加载失败：${  e.message}`); 
}
    };

    const switchView = (v) => {
      if (v === view.value) return;
      if (v === "yaml") {
        // 表单 → YAML：把 data 序列化
        yamlText.value = jsyamlDump({ ...data });
      } else {
        // YAML → 表单：解析回填
        try {
          const next = jsyamlLoad(yamlText.value) || {};
          resetData(next);
        } catch (e) {
          ElMessage.warning(`YAML 解析失败，表单保留上次值：${  e.message}`);
          return;
        }
      }
      view.value = v;
    };

    const save = async () => {
      let payload;
      if (view.value === "yaml") {
        try {
 payload = jsyamlLoad(yamlText.value) || {}; 
} catch (e) {
 ElMessage.error(`YAML 解析失败：${  e.message}`); return; 
}
      } else {
        payload = { ...data };
      }
      saving.value = true;
      try {
        await api.putGlobalConfig(payload);
        ElMessage.success("已保存");
        await refreshSetup();
        await load();
      } catch (e) {
 ElMessage.error(`保存失败：${  e.message}`); 
} finally {
 saving.value = false; 
}
    };

    onMounted(load);
    return { view, data, yamlText, schema, saving, load, save, switchView };
  },
});

/* ============================================================================
 * 组件：LlmView —— profile 列表 + 结构化编辑
 * ========================================================================== */
const LlmView = defineComponent({
  components: { FieldGroupedForm },
  template: `
    <div>
      <div class="card">
        <div class="toolbar">
          <div class="left">
            <h3 style="margin:0;"><span style="font-size:20px;">🤖</span> LLM 注册表 (conf/llm.yaml)</h3>
            <el-tag type="info">当前默认 profile: <code>{{ registry.default || '-' }}</code></el-tag>
          </div>
          <div class="right">
            <el-button type="primary" @click="newProfile">+ 新建 Profile</el-button>
            <el-button @click="load">重新加载</el-button>
          </div>
        </div>

        <div v-if="!profileList.length" class="empty-state">
          <div class="empty-icon">🤖</div>
          <div class="empty-title">还没有任何 LLM profile</div>
          <el-button type="primary" @click="newProfile">+ 新建</el-button>
        </div>

        <el-table v-else :data="profileList" style="width:100%">
          <el-table-column label="profile 名" width="220">
            <template #default="{ row }">
              <strong>{{ row.name }}</strong>
              <el-tag v-if="row.name === registry.default" type="success" size="small" style="margin-left:6px;">默认</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="provider" label="provider" width="180" />
          <el-table-column prop="model" label="model" />
          <el-table-column label="api_key" width="130">
            <template #default="{ row }">
              <el-tag :type="row.api_key ? 'success' : 'warning'" size="small">
                {{ row.api_key ? '已配置' : '走环境变量' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="260">
            <template #default="{ row }">
              <el-button size="small" @click="editProfile(row.name)">编辑</el-button>
              <el-button size="small" v-if="row.name !== registry.default" @click="setDefault(row.name)">设为默认</el-button>
              <el-button size="small" type="danger" @click="deleteProfile(row.name)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 编辑抽屉 -->
      <el-drawer v-model="drawerVisible" :title="editing ? '编辑 Profile: ' + currentName : '新建 Profile'"
                 direction="rtl" size="55%">
        <field-grouped-form :schema="schema" :data="currentProfile" />
        <div style="margin-top:20px;padding-top:16px;border-top:1px solid #e5e7eb;display:flex;justify-content:flex-end;gap:8px;">
          <el-button @click="drawerVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveProfile">💾 保存</el-button>
        </div>
      </el-drawer>
    </div>
  `,
  setup() {
    const registry = ref({ default: "", profiles: {} });
    const schema = ref([]);
    const drawerVisible = ref(false);
    const editing = ref(false);
    const currentName = ref("");
    const currentProfile = reactive({});
    const saving = ref(false);

    const resetProfile = (obj) => {
      for (const k of Object.keys(currentProfile)) delete currentProfile[k];
      if (obj) Object.assign(currentProfile, obj);
    };

    const profileList = computed(() => {
      const arr = [];
      for (const [name, prof] of Object.entries(registry.value.profiles || {})) {
        arr.push({ name, ...(prof || {}) });
      }
      return arr;
    });

    const load = async () => {
      try {
        const [reg, sch] = await Promise.all([api.getLlm(), api.getSchema("llm_profile")]);
        registry.value = reg || { default: "", profiles: {} };
        schema.value = sch.fields;
      } catch (e) {
 ElMessage.error(`加载失败：${  e.message}`); 
}
    };

    const editProfile = (name) => {
      editing.value = true;
      currentName.value = name;
      resetProfile({ name, ...(registry.value.profiles[name] || {}) });
      drawerVisible.value = true;
    };

    const newProfile = () => {
      editing.value = false;
      currentName.value = "";
      resetProfile({ name: "", provider: "echo", model: "", api_base: "", api_key: "",
                     temperature: 0.2, max_tokens: 1024, batch_size: 16,
                     timeout_seconds: 60, retries: 3, retry_interval_seconds: 10, extra: {} });
      drawerVisible.value = true;
    };

    const saveProfile = async () => {
      const p = currentProfile;
      if (!p.name) {
 ElMessage.warning("profile 名称必填"); return; 
}
      // 格式校验：仅允许字母、数字、下划线、连字符
      if (!/^[a-zA-Z0-9_-]+$/.test(p.name)) {
        ElMessage.warning("profile 名称只允许字母、数字、下划线(_)、连字符(-)");
        return;
      }
      if (!p.provider) {
 ElMessage.warning("provider 必填"); return; 
}
      // 唯一性校验：新建时若名字已存在、编辑时若改成一个已存在的别人的名字 → 冲突
      const existing = Object.keys(registry.value.profiles || {});
      const conflictTargetName = (!editing.value) ? p.name
                                                  : (p.name !== currentName.value ? p.name : null);
      if (conflictTargetName && existing.includes(conflictTargetName)) {
        ElMessage.error(`profile 名称 "${conflictTargetName}" 已存在。profile 名称必须全局唯一 —— config.yaml / 语种 profile 的 llm_profile 字段都是按此名引用的。`);
        return;
      }
      // 根据 provider 做条件必填校验
      if (p.provider !== "echo" && p.provider !== "mock") {
        if (!p.model) {
 ElMessage.warning("model 必填"); return; 
}
        const needsBase = ["openai_compatible", "venus", "hunyuan_translation"];
        if (needsBase.includes(p.provider) && !p.api_base) {
          ElMessage.warning(`provider=${p.provider} 需要填写 api_base`); return;
        }
        if (p.provider === "venus") {
          const ex = p.extra || {};
          if (!ex.server_id || !ex.app_group_id) {
            ElMessage.warning("venus 需要填写 extra.server_id 和 extra.app_group_id");
            return;
          }
        }
        if (p.provider === "hunyuan_translation") {
          const ex = p.extra || {};
          if (!ex.wsid) {
            ElMessage.warning("hunyuan_translation 需要填写 extra.wsid");
            return;
          }
        }
      }
      saving.value = true;
      try {
        const next = JSON.parse(JSON.stringify(registry.value));
        next.profiles = next.profiles || {};
        if (editing.value && currentName.value && currentName.value !== p.name) {
          delete next.profiles[currentName.value];
          if (next.default === currentName.value) next.default = p.name;
        }
        const { name, ...rest } = { ...p };
        next.profiles[name] = rest;
        if (!next.default) next.default = name;
        await api.putLlm(next);
        ElMessage.success("已保存");
        drawerVisible.value = false;
        await load();
        await refreshSetup();
        refreshLlmProfiles();   // 失效 LLM profile 下拉缓存
      } catch (e) {
 ElMessage.error(`保存失败：${  e.message}`); 
} finally {
 saving.value = false; 
}
    };

    const setDefault = async (name) => {
      try {
        const next = JSON.parse(JSON.stringify(registry.value));
        next.default = name;
        await api.putLlm(next);
        ElMessage.success(`已将 ${name} 设为默认`);
        await load();
        refreshLlmProfiles();
      } catch (e) {
 ElMessage.error(e.message); 
}
    };

    const deleteProfile = async (name) => {
      try {
 await ElMessageBox.confirm(`删除 profile ${name}？`, "警告", { type: "warning" }); 
} catch {
 return; 
}
      try {
        const next = JSON.parse(JSON.stringify(registry.value));
        delete next.profiles[name];
        if (next.default === name) next.default = Object.keys(next.profiles)[0] || "";
        await api.putLlm(next);
        ElMessage.success("已删除");
        await load();
        refreshLlmProfiles();
      } catch (e) {
 ElMessage.error(e.message); 
}
    };

    onMounted(load);
    return {
      registry, schema, profileList, drawerVisible, editing, currentName, currentProfile, saving,
      load, editProfile, newProfile, saveProfile, setDefault, deleteProfile,
    };
  },
});

/* ============================================================================
 * 组件：LanguagesView —— 列表 + 结构化编辑
 * ========================================================================== */
const LanguagesView = defineComponent({
  components: { FieldGroupedForm },
  template: `
    <div>
      <div class="card">
        <div class="toolbar">
          <div class="left">
            <h3 style="margin:0;"><span style="font-size:20px;">🌐</span> 语种 Profile ({{ items.length }} 个)</h3>
          </div>
          <div class="right">
            <el-button type="primary" @click="openNew">+ 新建语种</el-button>
          </div>
        </div>

        <div v-if="!items.length" class="empty-state">
          <div class="empty-icon">🌍</div>
          <div class="empty-title">还没有任何语种 profile</div>
          <div class="empty-desc">创建一个语种 profile 来开始您的本地化流水线</div>
          <el-button type="primary" size="large" @click="openNew">+ 新建第一个语种</el-button>
        </div>

        <el-table v-else :data="items" style="width:100%">
          <el-table-column label="ID" min-width="140">
            <template #default="{ row }">
              <strong>{{ row.id }}</strong>
              <div v-if="row.alias" style="color:#9ca3af;font-size:11px;margin-top:2px;">
                别名: {{ row.alias }}
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="display_name" label="显示名" min-width="140" />
          <el-table-column prop="target_locale" label="target_locale" width="130" />
          <el-table-column label="工作流" min-width="260">
            <template #default="{ row }">
              <el-tag v-for="w in (row.workflow || []).slice(0, 6)" :key="w" size="small" style="margin-right:4px;margin-bottom:2px;">{{ w }}</el-tag>
              <span v-if="(row.workflow || []).length > 6" style="color:#9ca3af;font-size:12px;">+{{ row.workflow.length - 6 }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="340" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openEdit(row.id)">✏️ 编辑</el-button>
              <el-button size="small" type="success" @click="runNow(row.id)">▶️ 运行</el-button>
              <el-button size="small" @click="openDup(row.id)">📋 克隆</el-button>
              <el-button size="small" type="danger" @click="onDelete(row.id)">🗑</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 编辑抽屉 -->
      <el-drawer v-model="editorVisible" direction="rtl" size="70%" :destroy-on-close="true"
                 class="lang-editor-drawer" :with-header="true">
        <!-- 自定义标题栏：左侧标题 + 右侧保存/取消按钮，永远可见无需滚动 -->
        <template #header="{ close }">
          <div class="drawer-header-wrap">
            <div class="drawer-title">
              <span class="drawer-title-icon">{{ editing ? '✏️' : '✨' }}</span>
              <span>{{ editing ? '编辑语种' : '新建语种' }}:</span>
              <b style="color:var(--primary);margin-left:4px;">{{ currentId }}</b>
              <span class="drawer-title-sub">视图：{{ view === 'form' ? '📋 表单' : '📝 YAML' }}</span>
            </div>
            <div class="drawer-actions">
              <el-button @click="editorVisible = false">取消</el-button>
              <el-button type="primary" :loading="saving" @click="save">💾 保存</el-button>
            </div>
          </div>
        </template>
        <!-- 平台 / 语种联动提醒 -->
        <el-alert v-if="platformHint" :closable="false" show-icon
                  :type="platformHint.type" :title="platformHint.title" style="margin-bottom:14px;">
          <template #default>
            <div v-html="platformHint.body"></div>
          </template>
        </el-alert>
        <div class="toolbar" style="margin-bottom:16px;">
          <div class="view-switch">
            <button :class="{active: view === 'form'}" @click="switchView('form')">📋 表单</button>
            <button :class="{active: view === 'yaml'}" @click="switchView('yaml')">📝 YAML</button>
          </div>
        </div>
        <field-grouped-form v-if="view === 'form'" :schema="schema" :data="currentData" />
        <el-input v-else v-model="yamlText" type="textarea" :rows="28" class="yaml-editor" />
      </el-drawer>

      <!-- 新建对话 -->
      <el-dialog v-model="newDialog" title="新建语种" width="520">
        <el-form label-width="140px">
          <el-form-item label="语种 ID *">
            <el-input v-model="newForm.id" placeholder="如 vi / ja / ko（文件名用）" />
          </el-form-item>
          <el-form-item label="显示名">
            <el-input v-model="newForm.display_name" placeholder="如 越南语" />
          </el-form-item>
          <el-form-item label="target_locale *">
            <el-input v-model="newForm.target_locale" placeholder="BCP-47 代码，如 vi" />
          </el-form-item>
          <el-form-item label="LLM profile">
            <el-select v-model="newForm.llm_profile" filterable clearable
                       style="width:100%;"
                       :placeholder="llmProfilesLoading
                                       ? '加载中…'
                                       : (llmProfiles.length
                                           ? '请选择已配置的 LLM profile'
                                           : '(尚未配置任何 LLM profile，可留空或前往「LLM 模型」新建)')"
                       :loading="llmProfilesLoading">
              <el-option v-for="p in llmProfiles" :key="p.name" :value="p.name" :label="p.name">
                <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">
                  <span>
                    <strong>{{ p.name }}</strong>
                    <span v-if="p.name.endsWith('_example')"
                          style="margin-left:6px;color:#f59e0b;font-size:11px;">[模板]</span>
                  </span>
                  <span style="color:#6b7280;font-size:12px;">
                    {{ p.provider }}<span v-if="p.model"> · {{ p.model }}</span>
                  </span>
                </div>
              </el-option>
            </el-select>
            <div v-if="newForm.llm_profile && newForm.llm_profile.endsWith('_example')"
                 style="margin-top:4px;color:#f59e0b;font-size:12px;">
              ⚠️ 这是模板示例 profile，建议到「🤖 LLM 模型」页面复制一份、填好真实凭据后再引用。
            </div>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="newDialog = false">取消</el-button>
          <el-button type="primary" @click="createNew">下一步：编辑完整配置</el-button>
        </template>
      </el-dialog>

      <!-- 克隆对话 -->
      <el-dialog v-model="dupDialog" title="克隆语种" width="420">
        <el-form label-width="120px">
          <el-form-item label="源语种"><el-input :model-value="dupSrc" disabled /></el-form-item>
          <el-form-item label="新语种 ID"><el-input v-model="dupId" placeholder="如 ko_test" /></el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="dupDialog = false">取消</el-button>
          <el-button type="primary" @click="doDuplicate">克隆</el-button>
        </template>
      </el-dialog>
    </div>
  `,
  setup() {
    const items = ref([]);
    const schema = ref([]);
    const editorVisible = ref(false);
    const editing = ref(false);
    const currentId = ref("");
    const currentData = reactive({});
    const yamlText = ref("");
    const view = ref("form");
    const saving = ref(false);
    // 全局 config 快照，用于：
    //   1) 新建语种时把 platform.project_id 默认带入 reviews.first/second.project_id
    //   2) 顶部提醒"审校平台上必须存在对应 source_locale → target_locale 的项目"
    const globalConfig = ref({});

    const newDialog = ref(false);
    const newForm = reactive({ id: "", display_name: "", target_locale: "", llm_profile: "" });

    const dupDialog = ref(false);
    const dupSrc = ref("");
    const dupId = ref("");

    const resetCurrent = (obj) => {
      for (const k of Object.keys(currentData)) delete currentData[k];
      if (obj) Object.assign(currentData, obj);
    };

    const load = async () => {
      try {
        const [list, sch, gc] = await Promise.all([
          api.listLanguages(),
          api.getSchema("language"),
          api.getGlobalConfig().catch(() => ({})),
        ]);
        items.value = list;
        schema.value = sch.fields;
        globalConfig.value = gc || {};
        // 顺手拉取一次 LLM profile 清单，新建对话框的下拉即可用
        ensureLlmProfiles();
      } catch (e) {
 ElMessage.error(`加载失败：${  e.message}`); 
}
    };

    const switchView = (v) => {
      if (v === view.value) return;
      if (v === "yaml") {
        yamlText.value = jsyamlDump({ ...currentData });
      } else {
        try {
          const next = jsyamlLoad(yamlText.value) || {};
          resetCurrent(next);
        } catch (e) {
          ElMessage.warning("YAML 解析失败，表单保留上次值"); return;
        }
      }
      view.value = v;
    };

    const openEdit = async (id) => {
      try {
        currentId.value = id;
        editing.value = true;
        const data = await api.getLanguage(id);
        resetCurrent(data || {});
        yamlText.value = jsyamlDump(data || {});
        view.value = "form";
        editorVisible.value = true;
      } catch (e) {
 ElMessage.error(`加载失败：${  e.message}`); 
}
    };

    const openNew = () => {
      Object.assign(newForm, { id: "", display_name: "", target_locale: "", llm_profile: "" });
      newDialog.value = true;
    };

    const createNew = () => {
      if (!newForm.id) {
 ElMessage.warning("语种 ID 必填"); return; 
}
      currentId.value = newForm.id;
      editing.value = false;
      // 从全局 config 带入默认值（审校平台类型 + project_id + source_locale）
      const gc = globalConfig.value || {};
      const platformProjectId = (gc.platform && gc.platform.project_id) || "";
      const platformType = (gc.platform && gc.platform.type) || "";
      const sourceLocale = gc.source_locale || "zh-CN";
      // 从全局 config.yaml 带入 notification。使用方可以：
      //   - 不改 → 直接复用全局 webhook + mentioned；
      //   - 清空 webhook / mentioned → 运行时字段级继承全局（见 cli._merge_notification）；
      //   - 整段改为 { type: "console" } → 本语种改走控制台通知。
      const globalNotify = gc.notification || {};
      const defaultNotification = {
        type: globalNotify.type || "console",
        webhook: globalNotify.webhook || "",
        mentioned: Array.isArray(globalNotify.mentioned) ? [...globalNotify.mentioned] : [],
      };
      const defaults = {
        id: newForm.id,
        display_name: newForm.display_name || newForm.id,
        source_locale: sourceLocale,
        target_locale: newForm.target_locale || newForm.id,
        locale_names: { cn: newForm.display_name || newForm.id, en: "" },
        source: { format: "xlsx", path: "", encoding: "utf-8" },
        llm_profile: newForm.llm_profile || "",
        strategy_config: {
          display_name: newForm.display_name || newForm.id,
          use_concurrent_by_default: true,
          default_max_workers: 32,
          progress_log_interval: 100,
        },
        // reviews 的 platform 字段由后端根据全局 config.yaml 的 platform.type 自动同步，
        // 这里只填各阶段的 project_id / project_name 等业务字段。
        // 一审 / 二审默认带入全局 platform.project_id，便于单项目多语种共用同一个平台项目；
        // 如需每语种独立项目 ID，在表单里改即可。
        reviews: {
          light: { project_id: "", project_name: `${newForm.id}_Light` },
          first: {
            project_id: platformProjectId,
            project_name: `${newForm.id}_First`,
            target_language_id: newForm.target_locale || newForm.id,
            poll_interval_seconds: 60,
          },
          second: {
            project_id: platformProjectId,
            project_name: `${newForm.id}_Second`,
            target_language_id: newForm.target_locale || newForm.id,
            poll_interval_seconds: 60,
          },
        },
        notification: defaultNotification,
        workflow: ["pull_vcs", "translate", "merge_data", "push_vcs"],
        merge_start_time: "",
      };
      // 提示用户：平台上必须预先创建该语种项目
      if (platformType && platformType !== "none" && platformProjectId) {
        ElNotification({
          title: "💡 平台项目联动",
          message: `已自动带入全局平台 ${platformType} 的 project_id = "${platformProjectId}"。\n请确认该项目在 ${platformType} 平台上已经为 ${sourceLocale} → ${newForm.target_locale || newForm.id} 开启了对应的目标语言。`,
          type: "info",
          duration: 8000,
          dangerouslyUseHTMLString: false,
        });
      }
      resetCurrent(defaults);
      yamlText.value = jsyamlDump(defaults);
      view.value = "form";
      newDialog.value = false;
      editorVisible.value = true;
    };

    const save = async () => {
      let payload;
      if (view.value === "yaml") {
        try {
 payload = jsyamlLoad(yamlText.value) || {}; 
} catch (e) {
 ElMessage.error(`YAML 解析失败：${  e.message}`); return; 
}
      } else {
        payload = { ...currentData };
      }
      saving.value = true;
      try {
        await api.saveLanguage(currentId.value, payload);
        ElMessage.success("已保存");
        editorVisible.value = false;
        await load();
        await refreshSetup();
      } catch (e) {
 ElMessage.error(`保存失败：${  e.message}`); 
} finally {
 saving.value = false; 
}
    };

    const runNow = async (id) => {
      try {
 await ElMessageBox.confirm(`立即运行语种 "${id}" 的工作流？`, "确认", { type: "warning" }); 
} catch {
 return; 
}
      try {
        const rec = await api.startRun({ language: id, fresh: false });
        ElNotification({ title: "已启动", type: "success", message: rec.run_id });
        navigateTo("run", rec.run_id);
      } catch (e) {
 ElMessage.error(`启动失败：${  e.message}`); 
}
    };

    const onDelete = async (id) => {
      try {
 await ElMessageBox.confirm(`确认删除语种 ${id}？文件将移到 conf/.backup/`, "警告", { type: "warning" }); 
} catch {
 return; 
}
      try {
 await api.deleteLanguage(id); ElMessage.success("已删除"); await load(); 
} catch (e) {
 ElMessage.error(`删除失败：${  e.message}`); 
}
    };

    const openDup = (id) => {
 dupSrc.value = id; dupId.value = ""; dupDialog.value = true; 
};

    const doDuplicate = async () => {
      if (!dupId.value) {
 ElMessage.warning("请填写新语种 ID"); return; 
}
      try {
        await api.duplicateLanguage(dupSrc.value, dupId.value);
        ElMessage.success("已克隆");
        dupDialog.value = false;
        await load();
      } catch (e) {
 ElMessage.error(`克隆失败：${  e.message}`); 
}
    };

    onMounted(load);

    /**
     * 平台 / 语种联动提醒。
     * 根据全局 config.yaml 的 platform.type 和 project_id，以及**当前正在编辑的语种**
     * 的 source_locale / target_locale，生成一条合适的提示：
     *   - 平台未启用（none / 空）→ info：无需平台
     *   - 平台已启用但 project_id 未填 → warning：请先在 Dashboard / 全局配置填 project_id
     *   - 平台已启用且 project_id 已填 → success：提醒检查平台上该项目是否已开启目标语言
     */
    const platformHint = computed(() => {
      if (!editorVisible.value) return null;
      const gc = globalConfig.value || {};
      const plat = gc.platform || {};
      const platType = plat.type || "none";
      const platProjectId = plat.project_id || "";
      const srcLoc = currentData.source_locale || gc.source_locale || "zh-CN";
      const tgtLoc = currentData.target_locale || currentId.value || "<未填>";
      if (!platType || platType === "none") {
        return {
          type: "info",
          title: "🌐 未启用审校平台",
          body: `当前全局 config.yaml 的 <code>platform.type = none</code>，所有审校阶段将被跳过。<br/>
                 如需启用 Phrase / Crowdin，请到 <b>全局配置</b> 页先完成平台配置。`,
        };
      }
      if (!platProjectId) {
        return {
          type: "warning",
          title: `⚠️ ${platType} 平台已启用但 project_id 未填`,
          body: `请先到 <b>全局配置</b> 页填入 <code>platform.project_id</code>（也可以在下方的
                 <code>reviews.first.project_id</code> / <code>reviews.second.project_id</code>
                 直接填写该语种独有的项目 ID）。<br/>
                 ⚡ 必须确保 <code>${platType}</code> 平台上**已经创建了该项目**，并且为
                 <b>${srcLoc} → ${tgtLoc}</b> 这一语言对开启了对应的目标语言。`,
        };
      }
      return {
        type: "success",
        title: `✅ 已关联到 ${platType} 项目 #${platProjectId}`,
        body: `一审 / 二审默认指向全局平台项目 <code>${platProjectId}</code>（可在下方 reviews.* 中覆盖）。<br/>
               ⚡ <b>请务必确认</b>：<code>${platType}</code> 平台上的该项目**已经为
               <b>${srcLoc} → ${tgtLoc}</b> 开启了目标语言**，否则推送任务时平台会拒绝接收。`,
      };
    });

    return {
      items, schema, editorVisible, editing, currentId, currentData, yamlText, view, saving,
      newDialog, newForm, dupDialog, dupSrc, dupId,
      globalConfig, platformHint,
      // 新建对话框的 LLM profile 下拉
      llmProfiles: llmProfilesCache, llmProfilesLoading,
      openEdit, openNew, createNew, save, runNow, onDelete, openDup, doDuplicate, switchView,
    };
  },
});

/* ============================================================================
 * 组件：RunsView
 * ========================================================================== */
const RunsView = defineComponent({
  template: `
    <div class="card">
      <div class="card-header">
        <h3><span class="emoji">📜</span> 运行历史</h3>
        <el-button @click="load">刷新</el-button>
      </div>
      <div v-if="!runs.length" class="empty-state">
        <div class="empty-icon">📭</div>
        <div class="empty-title">还没有任何运行记录</div>
        <el-button type="primary" @click="go('languages')">去配置语种并运行</el-button>
      </div>
      <el-table v-else :data="runs" style="width:100%">
        <el-table-column prop="run_id" label="Run ID" min-width="260" show-overflow-tooltip />
        <el-table-column prop="language" label="语种" width="100" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <span :class="'run-status ' + row.status">{{ row.status }}</span>
          </template>
        </el-table-column>
        <el-table-column label="开始时间" width="180">
          <template #default="{ row }">{{ fmtTime(row.started_at) }}</template>
        </el-table-column>
        <el-table-column label="结束时间" min-width="180">
          <template #default="{ row }">{{ fmtTime(row.finished_at) }}</template>
        </el-table-column>
        <el-table-column prop="exit_code" label="退出码" width="90" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="toRun(row.run_id)">日志</el-button>
            <el-button size="small" type="danger" v-if="row.status === 'running'" @click="stop(row.run_id)">停止</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  `,
  setup() {
    const runs = ref([]);
    let timer = null;
    const load = async () => {
 try {
 runs.value = await api.listRuns(); 
} catch(e){} 
};
    const stop = async (id) => {
 try {
 await api.stopRun(id); ElMessage.success("已发送停止"); await load(); 
} catch(e){
 ElMessage.error(e.message); 
} 
};
    onMounted(() => {
 load(); timer = setInterval(load, 5000); 
});
    onBeforeUnmount(() => timer && clearInterval(timer));
    return { runs, fmtTime, stop, go: (k) => navigateTo(k), toRun: (id) => navigateTo("run", id) };
  },
});

/* ============================================================================
 * 组件：RunDetailView
 * ========================================================================== */
const RunDetailView = defineComponent({
  template: `
    <div>
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
          <div>
            <h3 style="margin:0 0 6px 0;font-size:16px;">🖥 Run: <code>{{ runId }}</code></h3>
            <div v-if="rec" style="color:#6b7280;font-size:13px;">
              <span :class="'run-status ' + rec.status">{{ rec.status }}</span>
              <span style="margin-left:12px;">开始 {{ fmtTime(rec.started_at) }}</span>
              <span style="margin-left:12px;">结束 {{ fmtTime(rec.finished_at) }}</span>
            </div>
          </div>
          <div>
            <el-button @click="back">← 返回列表</el-button>
            <el-button type="danger" v-if="rec && rec.status === 'running'" @click="stop">⏹ 停止</el-button>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header"><h3><span class="emoji">📋</span> 实时日志（WebSocket）</h3></div>
        <div ref="logEl" class="log-view">
          <div v-for="(e, idx) in lines" :key="idx" :class="'log-line stream-' + (e.stream || 'stdout')">[{{ tsToHms(e.ts) }}] {{ e.line }}</div>
        </div>
      </div>
    </div>
  `,
  setup() {
    const runId = computed(() => AppState.routeParam);
    const rec = ref(null);
    const lines = ref([]);
    const logEl = ref(null);
    let ws = null;
    let pollTimer = null;

    const refreshRec = async () => {
 try {
 rec.value = await api.getRun(runId.value); 
} catch(e){} 
};
    const scrollBottom = () => {
      if (!logEl.value) return;
      requestAnimationFrame(() => {
 if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight; 
});
    };
    const addLine = (entry) => {
      lines.value.push(entry);
      if (lines.value.length > 10000) lines.value.splice(0, lines.value.length - 10000);
      scrollBottom();
    };
    const stop = async () => {
 try {
 await api.stopRun(runId.value); ElMessage.success("已发送停止信号"); 
} catch(e){
 ElMessage.error(e.message); 
} 
};
    const back = () => navigateTo("runs");

    onMounted(() => {
      api.tailLog(runId.value, 1000).then((resp) => {
        lines.value = resp.entries || [];
        scrollBottom();
      }).catch(()=>{});
      refreshRec();
      pollTimer = setInterval(refreshRec, 3000);

      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${window.location.host}/api/logs/ws?run_id=${encodeURIComponent(runId.value)}`);
      ws.onmessage = (ev) => {
        try {
 addLine(JSON.parse(ev.data)); 
} catch (e) {
 addLine({ ts: 0, stream: "stdout", line: ev.data }); 
}
      };
      ws.onerror = () => addLine({ ts: 0, stream: "meta", line: "[ws] error" });
      ws.onclose = () => addLine({ ts: 0, stream: "meta", line: "[ws] closed" });
    });

    onBeforeUnmount(() => {
 try {
 ws && ws.close(); 
} catch(e){} pollTimer && clearInterval(pollTimer); 
});
    return { runId, rec, lines, logEl, fmtTime, tsToHms, stop, back };
  },
});

/* ============================================================================
 * 组件：SchedulesView
 * ========================================================================== */
const SchedulesView = defineComponent({
  template: `
    <div>
      <div class="card">
        <div class="toolbar">
          <div class="left"><h3 style="margin:0;"><span style="font-size:20px;">⏰</span> 定时任务</h3></div>
          <div class="right"><el-button type="primary" @click="openNew">+ 新建定时任务</el-button></div>
        </div>
        <div v-if="!items.length" class="empty-state">
          <div class="empty-icon">⏰</div>
          <div class="empty-title">还没有任何定时任务</div>
          <div class="empty-desc">像流水线一样让语种工作流按 cron 规则自动运行</div>
          <el-button type="primary" @click="openNew">+ 新建</el-button>
        </div>
        <el-table v-else :data="items" style="width:100%">
          <el-table-column prop="id" label="ID" width="200" />
          <el-table-column prop="language" label="语种" width="120" />
          <el-table-column prop="cron" label="Cron 表达式" width="200">
            <template #default="{ row }"><code>{{ row.cron }}</code></template>
          </el-table-column>
          <el-table-column label="启用" width="100">
            <template #default="{ row }">
              <el-switch :model-value="row.enabled" @change="(v) => toggle(row.id, v)" />
            </template>
          </el-table-column>
          <el-table-column label="fresh" width="90">
            <template #default="{ row }">
              <el-tag :type="row.fresh ? 'warning' : 'info'" size="small">{{ row.fresh ? '是' : '否' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="描述" />
          <el-table-column label="操作" width="180">
            <template #default="{ row }">
              <el-button size="small" @click="edit(row)">编辑</el-button>
              <el-button size="small" type="danger" @click="onDelete(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <el-dialog v-model="dialog" :title="editing ? '编辑定时任务' : '新建定时任务'" width="560">
        <el-form label-width="120px">
          <el-form-item label="ID *">
            <el-input v-model="form.id" :disabled="editing" placeholder="唯一标识，如 vi_daily" />
          </el-form-item>
          <el-form-item label="语种 *">
            <el-select v-model="form.language" placeholder="选择已配置的语种" style="width:100%;">
              <el-option v-for="l in languages" :key="l.id" :value="l.id" :label="l.id + '  (' + l.display_name + ')'" />
            </el-select>
          </el-form-item>
          <el-form-item label="Cron *">
            <el-input v-model="form.cron" placeholder="分 时 日 月 周，例：0 2 * * *" />
            <div style="color:#9ca3af;font-size:12px;margin-top:4px;">
              💡 <code>0 2 * * *</code> 每日 02:00 · <code>*/15 * * * *</code> 每 15 分钟 · <code>30 9 * * 1-5</code> 工作日 09:30
            </div>
          </el-form-item>
          <el-form-item label="fresh 模式"><el-switch v-model="form.fresh" /></el-form-item>
          <el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
          <el-form-item label="描述"><el-input v-model="form.description" type="textarea" /></el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="dialog = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="save">💾 保存</el-button>
        </template>
      </el-dialog>
    </div>
  `,
  setup() {
    const items = ref([]);
    const languages = ref([]);
    const dialog = ref(false);
    const editing = ref(false);
    const saving = ref(false);
    const form = reactive({ id: "", language: "", cron: "0 2 * * *", enabled: true, fresh: false, description: "" });

    const load = async () => {
      try {
 items.value = await api.listSchedules(); 
} catch(e){}
      try {
 languages.value = await api.listLanguages(); 
} catch(e){}
    };
    const openNew = () => {
      editing.value = false;
      Object.assign(form, { id: "", language: "", cron: "0 2 * * *", enabled: true, fresh: false, description: "" });
      dialog.value = true;
    };
    const edit = (row) => {
 editing.value = true; Object.assign(form, row); dialog.value = true; 
};
    const save = async () => {
      if (!form.id || !form.language || !form.cron) {
 ElMessage.warning("ID / 语种 / Cron 均必填"); return; 
}
      saving.value = true;
      try {
 await api.saveSchedule(form.id, { ...form }); ElMessage.success("已保存"); dialog.value = false; await load(); 
} catch (e) {
 ElMessage.error(`保存失败：${  e.message}`); 
} finally {
 saving.value = false; 
}
    };
    const toggle = async (id, enabled) => {
 try {
 await api.toggleSchedule(id, enabled); await load(); 
} catch (e) {
 ElMessage.error(e.message); 
} 
};
    const onDelete = async (id) => {
      try {
 await ElMessageBox.confirm(`删除定时任务 ${id}？`, "警告", { type: "warning" }); 
} catch {
 return; 
}
      try {
 await api.deleteSchedule(id); ElMessage.success("已删除"); await load(); 
} catch (e) {
 ElMessage.error(e.message); 
}
    };
    onMounted(load);
    return { items, languages, dialog, editing, saving, form, openNew, edit, save, toggle, onDelete };
  },
});

/* ============================================================================
 * 顶层 App
 * ========================================================================== */
const App = defineComponent({
  components: {
    Dashboard,
    SetupWizard,
    GlobalConfigView,
    LlmView,
    LanguagesView,
    RunsView,
    RunDetailView,
    SchedulesView,
  },
  template: `
    <div class="layout">
      <aside class="sidebar">
        <div class="logo">
          <div class="logo-icon">🎮</div>
          <span>TiMiHOKGameTranslator</span>
        </div>

        <div class="nav-group-title">主导航</div>
        <div v-for="item in navMain" :key="item.key"
             class="nav-item" :class="{ active: activeNavKey === item.key }"
             @click="go(item.key)">
          <span class="nav-icon">{{ item.icon }}</span>
          <span>{{ item.label }}</span>
        </div>

        <div class="nav-group-title">配置管理</div>
        <div v-for="item in navConfig" :key="item.key"
             class="nav-item" :class="{ active: activeNavKey === item.key }"
             @click="go(item.key)">
          <span class="nav-icon">{{ item.icon }}</span>
          <span>{{ item.label }}</span>
        </div>

        <div class="sidebar-footer">
          <div>状态：<span v-if="setupReady" style="color:#10b981;">● 就绪</span><span v-else style="color:#f59e0b;">● 待初始化</span></div>
          <div style="margin-top:4px;">v0.1.0 · FastAPI + Vue3</div>
        </div>
      </aside>

      <div class="main">
        <div class="topbar">
          <div class="title">
            <span>{{ currentTitle }}</span>
            <span class="subtitle" v-if="subtitle">· {{ subtitle }}</span>
          </div>
          <div style="display:flex;gap:10px;align-items:center;">
            <el-tag v-if="!setupReady" type="warning" effect="dark">⚠️ 尚未初始化</el-tag>
            <el-tag v-else type="success" effect="plain">✓ 服务正常</el-tag>
          </div>
        </div>
        <div class="content">
          <component :is="currentView" />
        </div>
      </div>
    </div>
  `,
  setup() {
    const route = computed(() => AppState.route);
    const setupReady = computed(() => !!AppState.setup?.initialized);

    const navMain = [
      { key: "dashboard", label: "控制台", icon: "🏠" },
      { key: "languages", label: "语种 Profile", icon: "🌐" },
      { key: "schedules", label: "定时任务", icon: "⏰" },
      { key: "runs", label: "运行历史", icon: "📜" },
    ];
    const navConfig = [
      { key: "setup", label: "初始化向导", icon: "🚀" },
      { key: "global-config", label: "全局配置", icon: "⚙️" },
      { key: "llm", label: "LLM 模型", icon: "🤖" },
    ];

    const titles = {
      dashboard: "控制台",
      languages: "语种 Profile",
      schedules: "定时任务",
      runs: "运行历史",
      run: "运行详情",
      "global-config": "全局配置",
      llm: "LLM 模型注册表",
      setup: "初始化向导",
    };

    const subtitles = {
      dashboard: "总览与健康检查",
      languages: "每个语种一个 YAML 流水线",
      schedules: "cron 调度自动触发",
      runs: "历史任务与日志",
      "global-config": "conf/config.yaml",
      llm: "conf/llm.yaml",
      setup: "4 步完成初始化",
    };

    const viewMap = {
      dashboard: Dashboard,
      languages: LanguagesView,
      schedules: SchedulesView,
      runs: RunsView,
      run: RunDetailView,
      "global-config": GlobalConfigView,
      llm: LlmView,
      setup: SetupWizard,
    };

    const currentView = computed(() => {
      // 未初始化时，除非在"配置管理"类页面，否则强制跳转向导
      if (!setupReady.value && !["setup", "global-config", "llm"].includes(route.value)) {
        return SetupWizard;
      }
      return viewMap[route.value] || Dashboard;
    });
    const currentTitle = computed(() => {
      if (!setupReady.value && !["setup", "global-config", "llm"].includes(route.value)) return "初始化向导";
      return titles[route.value] || "控制台";
    });
    const subtitle = computed(() => subtitles[route.value] || "");
    // 侧栏高亮用的"规范化路由"：子视图映射到父菜单
    //   run (运行详情) → runs (运行历史)
    const navAlias = { run: "runs" };
    const activeNavKey = computed(() => {
      // 未初始化时，所有非配置管理页都被强制渲染为 SetupWizard（见 currentView），
      // 此时侧栏应高亮"初始化向导"，而不是实际 hash 路由（通常是 dashboard）。
      if (
        !setupReady.value
        && !["setup", "global-config", "llm"].includes(route.value)
      ) {
        return "setup";
      }
      return navAlias[route.value] || route.value;
    });
    const go = (k) => navigateTo(k);

    onMounted(async () => {
      syncRouteFromHash();
      window.addEventListener("hashchange", syncRouteFromHash);
      await refreshMeta();
      await refreshSetup();
    });

    onBeforeUnmount(() => window.removeEventListener("hashchange", syncRouteFromHash));

    return { route, setupReady, navMain, navConfig, currentView, currentTitle, subtitle, go, activeNavKey };
  },
});

/* ========== 启动 ========== */
const vueApp = createApp(App);
vueApp.use(ElementPlus);
if (window.ElementPlusIconsVue) {
  for (const [name, comp] of Object.entries(window.ElementPlusIconsVue)) {
    vueApp.component(name, comp);
  }
}
vueApp.mount("#app");
