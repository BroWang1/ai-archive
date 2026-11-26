# 扩展指南：新增一种 VCS 后端

假设你在使用 [Fossil](https://fossil-scm.org)，希望 `TiMi_HOK_Game_Translator` 也能驱动它。
下面演示如何用约 30 行代码接入一个新后端。

## 1. 继承 `VcsClient`

在 `my_project/fossil_client.py` 中：

```python
from TiMi_HOK_Game_Translator.vcs import VcsClient, VcsStatus


class FossilClient(VcsClient):
    """Fossil SCM 的 VcsClient 实现。"""

    cli_name = "fossil"  # TiMi_HOK_Game_Translator 会检查 PATH 中是否存在此可执行文件。

    def checkout(self) -> VcsStatus:
        self._run(["fossil", "clone", self.url, self.local_path])
        return VcsStatus(revision=self.get_revision())

    def update(self, revision=None) -> VcsStatus:
        cmd = ["fossil", "update"]
        if revision:
            cmd.append(revision)
        self._run(cmd)
        return VcsStatus(revision=self.get_revision())

    def add(self, paths):
        self._run(["fossil", "add", *paths])

    def commit(self, paths, message=None):
        self._run(["fossil", "commit", "-m", message or self.default_commit_message, *paths])
        return VcsStatus(revision=self.get_revision(), modified_paths=list(paths))

    def revert(self, paths):
        self._run(["fossil", "revert", *paths])

    def status(self, paths=None):
        out = self._run(["fossil", "changes"], check=False).stdout
        modified = [line.split()[-1] for line in out.splitlines() if line]
        return VcsStatus(revision=self.get_revision(), modified_paths=modified)

    def cleanup(self):
        self._run(["fossil", "revert"], check=False)

    def get_revision(self) -> str:
        return self._run(["fossil", "info"], check=False).stdout.strip().split()[0]
```

## 2. 注册后端

在包被 import 时注册一次即可，通常放在你的 `__init__.py` 里：

```python
# my_project/__init__.py
from TiMi_HOK_Game_Translator.vcs import register_vcs_client
from .fossil_client import FossilClient

register_vcs_client("fossil", FossilClient)
```

## 3. 在 `config.yaml` 中指向它

```yaml
vcs:
  type: fossil
  url: https://fossil.example.com/myrepo
  local_path: ""    # → 解析为 {workspace}/vcs
```

## 4. 在运行前 import 你的插件

`TiMi_HOK_Game_Translator` 并不知道 `my_project` 的存在，所以你需要确保它被 import 到，
常见两种做法：

- **console-script 包装器**：在自己的 CLI 入口里 import 该插件后再调用
  `TiMi_HOK_Game_Translator.cli.main`；
- **`PYTHONSTARTUP` / `.pth` 文件**：随包分发一个 `.pth` 文件，其中
  `import my_project` 一行让解释器启动时自动加载。

至此，`PullVcsState` 与 `PushVcsState` 都会调用你的 `fossil` 客户端，
而 `TiMi_HOK_Game_Translator` 的所有单元测试仍然通过——因为框架从不假设某个具体后端。

## 测试你的插件

参考 `tests/unit/test_vcs_git.py` 的写法：

- **不要**调用真实 CLI，改为 patch `VcsClient._run` 并返回构造好的
  `VcsCommandResult` 对象；
- 至少覆盖：`checkout`、带/不带消息的 `commit`、`status` 解析、
  `cleanup` 与 至少一条重试/异常路径。

完整示例可看 `tests/unit/test_vcs_*.py`。
