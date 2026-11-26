# 贡献指南

感谢你对 LQA 项目的关注, 以下是参与贡献的基本流程和规范

## 提交 Issue

- 提交前请先搜索是否已有相关 Issue, 避免重复
- **Bug 报告**: 请说明复现步骤、预期行为、实际行为，以及环境信息 (操作系统、Python/Node 版本、部署方式)
- **功能建议**: 请描述使用场景和期望的行为, 无需提供完整的实现方案

## 提交 Pull Request

1. Fork 本仓库, 在自己的 Fork 上创建分支, 分支名建议体现改动内容, 如 `fix/bugzilla-reopen` 或 `feat/dingtalk-notify`
2. 保持每个 PR 聚焦于单一目的, 便于 Review
3. 提交前请确认:
   - 后端: `python manage.py migrate` 无误, 如有新模型请附带 migration 文件; 相关逻辑有基本测试或冒烟验证
   - 前端: `pnpm lint` 通过, `pnpm build` 无报错
4. PR 描述中说明改动内容、测试方式, 以及是否有破坏性变更

## 本地开发环境

见 [README.md](README.md) 的快速概览, 或各子目录的详细文档:

- 后端: [server/README.md](server/README.md)
- 前端: [web/README.md](web/README.md)

## 代码规范

**后端 (Python)**

- 遵循项目现有风格, 参考 `server/.pylintrc`
- 数据校验使用 Pydantic schema, 接口返回统一走 `libs/base.py` 中的基类
- 新增缺陷系统适配器请继承 `libs/bugtracker/base.py` 中的 `BugTracker` 抽象基类, 在 `libs/bugtracker/__init__.py` 的 `TRACKER_TYPES` 中注册, 并在 `scripts/test_bugtracker.py` 中补充测试

**前端 (TypeScript / Vue)**

- 组件放在对应业务目录下, CRUD 配置与视图分文件
- API 请求统一走 `src/api/` 目录下的封装, 不直接调用 axios
- `pnpm lint` 包含 ESLint + Prettier, 提交前请确保通过

## 分支与版本

- `main` 为主分支, 保持可发布状态
- 重大功能或破坏性变更请在 Issue 中先讨论再动手

## 许可证

提交代码即表示你同意将贡献以 [Apache-2.0 License](LICENSE) 授权给本项目
