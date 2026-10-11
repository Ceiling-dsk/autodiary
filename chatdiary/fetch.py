"""用本机 Chrome + Playwright 调用网页版的 backend-api 抓取对话。

Playwright 自己启动的浏览器会被 Cloudflare 识别成机器人，所以这里以普通进程启动本机 Chrome：
登录时完全不接入自动化；抓取时开调试端口，再用 Playwright 通过 CDP 连上去。
请求都在页面里用 fetch 发出，自动带上 cookie；accessToken 只存在页面的 JS 变量里，不回传到 Python。
"""

import json
import socket
import subprocess
import time
import urllib.request
from datetime import datetime

from . import config
from .db import connect, mark_fetched, remote_update_times, set_projects, upsert_conversation
from .parse import parse_conversation

BASE = "https://chatgpt.com"
REQUEST_INTERVAL = 1.0
RETRY_WAITS = [5, 15, 60]

_FETCH_JS = """
async ([url, reset]) => {
  if (reset || !window.__cdTok) {
    const s = await (await fetch('/api/auth/session')).json();
    window.__cdTok = s.accessToken || null;
  }
  if (!window.__cdTok) return {status: -1, text: ''};
  const r = await fetch(url, {headers: {Authorization: 'Bearer ' + window.__cdTok}});
  return {status: r.status, text: await r.text()};
}
"""


class NotLoggedIn(Exception):
    pass


def _chrome(*args) -> subprocess.Popen:
    config.PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        [config.CHROME, f"--user-data-dir={config.PROFILE_DIR}",
         "--no-first-run", "--no-default-browser-check", *args],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def login():
    """打开一个独立的 Chrome 窗口供手动登录；关闭窗口即结束。"""
    print("已打开 Chrome 窗口：请登录 ChatGPT，看到聊天界面后关闭这个 Chrome 窗口（⌘Q）即可。")
    _chrome(BASE).wait()
    print("Chrome 已关闭，登录状态保存在 profile/")


def _connect(playwright, headless: bool):
    port = _free_port()
    proc = _chrome(f"--remote-debugging-port={port}", *(["--headless=new"] if headless else []),
                   "about:blank")
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1)
            break
        except OSError:
            time.sleep(0.5)
    else:
        proc.terminate()
        raise SystemExit("Chrome 启动失败（如果 profile/ 正被另一个 Chrome 窗口占用，请先关掉它）")
    browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    ctx = browser.contexts[0]
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(BASE, wait_until="domcontentloaded")
    return proc, browser, page


class Client:
    def __init__(self, page):
        self.page = page
        self.last = 0.0

    def get(self, path: str):
        """GET 一个 backend-api 路径，返回解析后的 JSON；404 返回 None。"""
        reset = False
        for attempt in range(len(RETRY_WAITS) + 1):
            wait = self.last + REQUEST_INTERVAL - time.time()
            if wait > 0:
                time.sleep(wait)
            r = self.page.evaluate(_FETCH_JS, [path, reset])
            self.last = time.time()
            status = r["status"]
            if status == 200:
                return json.loads(r["text"])
            if status == 404:
                return None
            if status == -1:
                raise NotLoggedIn
            if status == 401 and not reset:
                reset = True  # token 过期，重新取一次
                continue
            if status in (429, 500, 502, 503, 504) and attempt < len(RETRY_WAITS):
                print(f"  HTTP {status}，{RETRY_WAITS[attempt]} 秒后重试")
                time.sleep(RETRY_WAITS[attempt])
                continue
            raise RuntimeError(f"HTTP {status}: {path}")


def _ts(v) -> float | None:
    """列表接口里的时间可能是 ISO 字符串或数字时间戳。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()


def list_conversations(client: Client) -> list[dict]:
    """返回 [{id, update_time, project}]。普通对话的 total 不可信，必须翻到空页为止。"""
    out = []
    offset = 0
    while True:
        data = client.get(f"/backend-api/conversations?offset={offset}&limit=100&order=updated")
        items = (data or {}).get("items") or []
        if not items:
            break
        for it in items:
            out.append({"id": it["id"], "update_time": _ts(it.get("update_time")), "project": None})
        offset += len(items)
    print(f"普通对话 {len(out)} 个")

    projects = []
    cursor = None
    while True:
        q = "conversations_per_gizmo=0" + (f"&cursor={cursor}" if cursor else "")
        data = client.get(f"/backend-api/gizmos/snorlax/sidebar?{q}") or {}
        for it in data.get("items") or []:
            g = it["gizmo"]["gizmo"]
            projects.append((g["id"], (g.get("display") or {}).get("name")))
        cursor = data.get("cursor")
        if not cursor:
            break

    n_before = len(out)
    for gid, name in projects:
        cursor = "0"
        while cursor is not None:
            data = client.get(f"/backend-api/gizmos/{gid}/conversations?cursor={cursor}") or {}
            for it in data.get("items") or []:
                out.append({"id": it["id"], "update_time": _ts(it.get("update_time")), "project": name})
            cursor = data.get("cursor")
    print(f"项目 {len(projects)} 个，项目内对话 {len(out) - n_before} 个")

    # 项目里的对话大多也会出现在普通列表里：按 id 合并，保留项目名
    uniq: dict[str, dict] = {}
    for c in out:
        if c["id"] in uniq:
            uniq[c["id"]]["project"] = uniq[c["id"]]["project"] or c["project"]
        else:
            uniq[c["id"]] = c
    return list(uniq.values())


def fetch(limit: int | None = None, headless: bool = False):
    from playwright.sync_api import sync_playwright

    conn = connect(config.DB_PATH)
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    known = remote_update_times(conn)

    with sync_playwright() as p:
        proc, browser, page = _connect(p, headless=headless)
        try:
            client = Client(page)
            convs = list_conversations(client)
            set_projects(conn, {c["id"]: c["project"] for c in convs})
            todo = [c for c in convs
                    if c["update_time"] is None or known.get(c["id"]) != c["update_time"]]
            print(f"共 {len(convs)} 个对话，需要抓取 {len(todo)} 个，其余未变化跳过")
            if limit is not None:
                todo = todo[:limit]

            done = missing = 0
            for i, c in enumerate(todo, 1):
                raw = client.get(f"/backend-api/conversation/{c['id']}")
                if raw is None:
                    missing += 1
                    print(f"[{i}/{len(todo)}] {c['id'][:8]} 不存在（404），跳过")
                    continue
                (config.RAW_DIR / f"{c['id']}.json").write_text(json.dumps(raw, ensure_ascii=False))
                conv = parse_conversation(raw)
                n = upsert_conversation(conn, conv)
                mark_fetched(conn, conv.id, c["project"], c["update_time"])
                done += 1
                print(f"[{i}/{len(todo)}] {c['id'][:8]}  {n} 条消息")
            print(f"完成：抓取 {done} 个，404 {missing} 个")
        except NotLoggedIn:
            raise SystemExit("未登录或登录已过期，请先运行：python -m chatdiary login")
        finally:
            browser.close()
            proc.terminate()
