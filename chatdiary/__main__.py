import argparse
import json
from pathlib import Path

from . import config
from .db import connect, upsert_conversation
from .parse import load_conversations, parse_conversation
from .render import write_day


def cmd_import(args):
    conn = connect(config.DB_PATH)
    for path in args.files:
        convs = load_conversations(json.loads(Path(path).read_text()))
        for raw in convs:
            conv = parse_conversation(raw)
            n = upsert_conversation(conn, conv)
            print(f"{path}: {conv.title!r} → {n} 条消息")


def cmd_days(args):
    conn = connect(config.DB_PATH)
    rows = conn.execute(
        """SELECT life_day, COUNT(*) AS n, COUNT(DISTINCT conversation_id) AS c FROM messages
           WHERE life_day IS NOT NULL AND hidden = 0 AND role IN ('user', 'assistant')
           GROUP BY life_day ORDER BY life_day"""
    ).fetchall()
    for r in rows:
        print(f"{r['life_day']}  {r['n']:>4} 条消息  {r['c']:>3} 个对话")


def cmd_render(args):
    conn = connect(config.DB_PATH)
    data = write_day(conn, args.day)
    print(f"{args.day}: {data['message_count']} 条消息 → {config.DAYS_DIR}/{args.day}.json / .md")


def cmd_search(args):
    conn = connect(config.DB_PATH)
    rows = conn.execute(
        """SELECT m.life_day, c.title, m.role, snippet(messages_fts, 0, '[', ']', '…', 12) AS snip
           FROM messages_fts JOIN messages m ON m.rowid = messages_fts.rowid
           JOIN conversations c ON c.id = m.conversation_id
           WHERE messages_fts MATCH ? ORDER BY m.create_time DESC LIMIT 50""",
        (args.query,),
    ).fetchall()
    for r in rows:
        print(f"{r['life_day']}  {r['title']}  [{r['role']}]  {r['snip']}")


def cmd_login(args):
    from .fetch import login
    login()


def cmd_fetch(args):
    from .fetch import fetch
    fetch(limit=args.limit, headless=args.headless)


def main():
    p = argparse.ArgumentParser(prog="chatdiary")
    sub = p.add_subparsers(required=True)

    s = sub.add_parser("import", help="导入对话 JSON（单个对话或对话列表）")
    s.add_argument("files", nargs="+")
    s.set_defaults(func=cmd_import)

    s = sub.add_parser("days", help="列出所有生活日及消息数")
    s.set_defaults(func=cmd_days)

    s = sub.add_parser("render", help="导出某个生活日的 JSON 和 Markdown")
    s.add_argument("day", help="YYYY-MM-DD")
    s.set_defaults(func=cmd_render)

    s = sub.add_parser("search", help="全文搜索（至少 3 个字符）")
    s.add_argument("query")
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("login", help="打开 Chrome 登录 ChatGPT（登录状态保存在 profile/）")
    s.set_defaults(func=cmd_login)

    s = sub.add_parser("fetch", help="从 ChatGPT 抓取新增或有变化的对话并导入")
    s.add_argument("--limit", type=int, help="最多抓取 N 个对话（试跑用）")
    s.add_argument("--headless", action="store_true", help="不显示浏览器窗口")
    s.set_defaults(func=cmd_fetch)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
