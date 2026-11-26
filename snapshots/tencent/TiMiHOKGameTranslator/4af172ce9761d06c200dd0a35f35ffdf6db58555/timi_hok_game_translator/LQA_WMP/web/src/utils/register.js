import { isDevMode } from './env.ts';

export function registerGlobUtils(app) {
  /* eslint-disable */
  app.config.globalProperties.isDevMode = isDevMode;
  app.config.globalProperties.$log = console.log;
  app.config.globalProperties.$sleep = time => new Promise(resolve => setTimeout(resolve, time));
  /* eslint-enable */
}
