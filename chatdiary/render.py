"""把一个生活日的消息导出为 JSON 和 Markdown。"""

import json
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from . import config
from .lifeday import window


def collect_day(conn: sqlite3.Connection, day: str) -> dict:
    rows = conn.execute(
        """SELECT m.*, c.title FROM messages m JOIN conversations c ON c.id = m.conversation_id
           WHERE m.life_day = ? AND m.hidden = 0 AND m.role IN ('user', 'assistant')
           ORDER BY m.create_time""",
        (day,),
    ).fetchall()

    zone = ZoneInfo(config.TIMEZONE)
    convs: dict[str, dict] = {}
    for r in rows:
        conv = convs.setdefault(r["conversation_id"], {
            "id": r["conversation_id"], "title": r["title"], "messages": [],
        })
        conv["messages"].append({
            "id": r["id"],
            "role": r["role"],
            "time": datetime.fromtimestamp(r["create_time"], zone).isoformat(),
            "model": r["model"],
            "on_main_branch": bool(r["on_main_branch"]),
            "text": r["text"],
        })

    start, end = window(day)
    return {
        "life_day": day,
        "timezone": config.TIMEZONE,
        "window": [start.isoformat(), end.isoformat()],
        "message_count": len(rows),
        "conversations": list(convs.values()),
    }


def to_markdown(data: dict) -> str:
    lines = [f"# {data['life_day']}", "", f"时间窗口：{data['window'][0]} → {data['window'][1]}", ""]
    for conv in data["conversations"]:
        lines += [f"## {conv['title'] or '(无标题)'}", ""]
        for m in conv["messages"]:
            who = "我" if m["role"] == "user" else "ChatGPT"
            branch = "" if m["on_main_branch"] else "（非主线分支）"
            lines += [f"**{who}** · {m['time'][11:16]}{branch} <!-- {m['id']} -->", "", m["text"], ""]
    return "\n".join(lines)


def write_day(conn: sqlite3.Connection, day: str) -> dict:
    data = collect_day(conn, day)
    config.DAYS_DIR.mkdir(parents=True, exist_ok=True)
    (config.DAYS_DIR / f"{day}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
    (config.DAYS_DIR / f"{day}.md").write_text(to_markdown(data))
    return data
