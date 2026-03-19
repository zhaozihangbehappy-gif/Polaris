# Trialogue v2

最小可信三方群聊实现。`tmux` 只负责承载界面，`chat.py` 只做 `@mention` 解析，`launcher.sh` 只做 CLI 调用，`_audit.py` 负责审计和 session 确认。

## 文件

- `start.sh`: 唯一启动入口，创建 `tmux` 群聊窗口。
- `chat.py`: 群聊界面，只调用 `launcher.sh`。
- `launcher.sh`: 执行 `claude` / `codex`，并把审计数据交给 `_audit.py`。
- `_audit.py`: 写审计日志、确认 session、生成 `--meta-file`。
- `deploy-level2.sh`: Level 2 部署脚本。
- `trialogue-v2.conf.example`: 本地配置模板。

## 配置

先复制模板，再按本机路径修改：

```bash
cp scripts/trialogue-v2/trialogue-v2.conf.example scripts/trialogue-v2/trialogue-v2.conf
```

`trialogue-v2.conf` 已加入 `.gitignore`，不要把机器私有路径提交进仓库。

## 运行

Level 1：

```bash
bash scripts/trialogue-v2/start.sh "讨论主题"
```

Level 2 部署：

```bash
sudo bash scripts/trialogue-v2/deploy-level2.sh
```

## 文档

- `docs/trialogue-v2-spec.md`
- `docs/trialogue-v2-level2-plan.md`
