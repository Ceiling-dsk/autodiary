# chatgpt-diary

个人 ChatGPT 聊天归档与日记系统。

## 结构

- `chatdiary/parse.py` — 解析对话 JSON（mapping 树 → 消息，标记主线分支）
- `chatdiary/db.py` — SQLite 存储，按 message_id 幂等 upsert，FTS5 全文索引
- `chatdiary/lifeday.py` — 生活日计算（凌晨 4:00 切分，时区见 `config.py`）
- `chatdiary/render.py` — 按生活日导出 JSON / Markdown

## 用法

```sh
python3 -m chatdiary import samples/*.json   # 导入
python3 -m chatdiary days                    # 列出生活日
python3 -m chatdiary render 2026-10-08       # 导出到 data/days/
python3 -m chatdiary search 关键词            # 全文搜索（至少 3 个字）
python3 -m unittest                          # 测试
```

`data/`、`samples/`、`profile/`、`.env` 均已在 `.gitignore` 中，个人数据不会进仓库。
