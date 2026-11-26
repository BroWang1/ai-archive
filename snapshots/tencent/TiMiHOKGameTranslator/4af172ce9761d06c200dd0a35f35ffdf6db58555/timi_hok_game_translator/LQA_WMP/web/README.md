# LQA Web

![License](https://img.shields.io/badge/license-Apache%202.0-blue)

Vue 3 + Vite 5 + TypeScript + Element Plus + fast-crud, 基于 [v3-admin-vite](https://github.com/un-pany/v3-admin-vite)

## 本地开发

要求 Node.js 20+、pnpm 11

```bash
cd web
pnpm install
pnpm dev            # http://localhost:3333
```

开发时接口请求 `/api-pro/*` 由 Vite 代理到后端, 默认 `http://127.0.0.1:8000/`, 需要指向其他地址时新建 `.env.development.local` (已被 git 忽略):

```
VITE_PROXY_TARGET = 'http://192.168.1.10:8000/'
```

## 构建

```bash
pnpm build          # 输出到 dist/
```

生产环境默认前后端同域部署, 由 Nginx 把 `/api-pro/` 和 `/media/` 反向代理到后端, 参考 [nginx.conf](nginx.conf)

## 环境变量

| 变量 | 说明 |
|---|---|
| `VITE_APP_TITLE` | 页面标题 |
| `VITE_BASE_API` | 后端接口前缀, 默认 `/api-pro` |
| `VITE_RESOURCE_API` | 截图等资源地址前缀, 默认 `/api-pro` |
| `VITE_PROXY_TARGET` | 仅开发环境: Vite 代理的后端地址 |
| `VITE_ADMIN_CONTACT` | 403 页面展示的管理员联系方式 (选填) |
| `VITE_PUBLIC_PATH` | 部署子路径, 默认 `/` |

## 代码检查

```bash
pnpm lint
pnpm test
```

## 许可证

本目录基于 v3-admin-vite，现以 **Apache-2.0** 开源，详见 [LICENSE](../LICENSE)。
