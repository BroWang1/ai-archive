// core
import { createApp } from 'vue';
import App from '@/App.vue';
import store from '@/store';
import router from '@/router';
import '@/router/permission';
// load
import { loadSvg } from '@/icons';
import { loadPlugins } from '@/plugins';
import { loadDirectives } from '@/directives';
// css
import 'uno.css';
import 'normalize.css';
import 'element-plus/dist/index.css';
import 'element-plus/theme-chalk/dark/css-vars.css';
import 'vxe-table/lib/style.css';
import 'vxe-table-plugin-element/dist/style.css';
import '@/styles/index.scss';

import registerGlobalComponents from '@/components';

// fast-crud
import FastCrud from '@/fast-crud';
import { registerGlobUtils } from '@/utils/register.js';

const app = createApp(App);

/** 变量挂载 */
registerGlobUtils(app);

/** 加载插件 */
loadPlugins(app);
/** 加载全局 SVG */
loadSvg(app);
/** 加载自定义指令 */
loadDirectives(app);
/** 加载 fast-crud */
app.use(FastCrud);

app.use(registerGlobalComponents);

app.use(store).use(router);
router.isReady().then(() => {
  app.mount('#app');
});
