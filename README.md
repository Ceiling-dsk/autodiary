# chatgpt-diary

个人 ChatGPT 聊天归档与日记系统。

## 结构

- `chatdiary/parse.py` — 解析对话 JSON（mapping 树 → 消息，标记主线分支）
- `chatdiary/db.py` — SQLite 存储，按 message_id 幂等 upsert，FTS5 全文索引
- `chatdiary/lifeday.py` — 生活日计算（凌晨 4:00 切分，时区见 `config.py`）
- `chatdiary/render.py` — 按生活日导出 JSON / Markdown
- `chatdiary/fetch.py` — 用本机 Chrome 调用网页版 backend-api 抓取对话（增量、可断点续跑）

## 安装

需要 macOS + Google Chrome（路径见 `config.py` 的 `CHROME`）。

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 用法

```sh
.venv/bin/python -m chatdiary login          # 打开独立的 Chrome 窗口登录，完成后 ⌘Q 关闭
.venv/bin/python -m chatdiary fetch          # 抓取新增/有变化的对话，原始 JSON 存 data/raw/
.venv/bin/python -m chatdiary fetch --limit 5  # 试跑
python3 -m chatdiary import samples/*.json   # 导入
python3 -m chatdiary days                    # 列出生活日
python3 -m chatdiary render 2026-10-08       # 导出到 data/days/
python3 -m chatdiary search 关键词            # 全文搜索（至少 3 个字）
python3 -m unittest                          # 测试
```

`data/`、`samples/`、`profile/`、`.env` 均已在 `.gitignore` 中，个人数据不会进仓库。
