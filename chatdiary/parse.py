"""把 ChatGPT 对话 JSON（backend-api 详情或官方导出）解析成扁平的消息列表。"""

import json
from dataclasses import dataclass


@dataclass
class Message:
    id: str
    conversation_id: str
    parent_id: str | None
    role: str
    content_type: str
    text: str
    create_time: float | None
    model: str | None
    on_main_branch: bool
    hidden: bool
    raw_json: str


@dataclass
class Conversation:
    id: str
    title: str | None
    create_time: float | None
    update_time: float | None
    messages: list[Message]


def load_conversations(obj) -> list[dict]:
    """接受单个对话（backend-api 详情）或对话列表（官方导出 conversations.json）。"""
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict) and "mapping" in obj:
        return [obj]
    raise ValueError("无法识别的对话 JSON 结构：缺少 mapping")


def main_branch_ids(mapping: dict, current_node: str | None) -> set[str]:
    """从 current_node 沿 parent 回溯，得到界面上显示的那条主线。"""
    ids = set()
    node_id = current_node
    while node_id and node_id in mapping and node_id not in ids:
        ids.add(node_id)
        node_id = mapping[node_id].get("parent")
    return ids


def extract_text(content: dict) -> str:
    ctype = content.get("content_type")
    if ctype in ("text", "multimodal_text"):
        out = []
        for part in content.get("parts") or []:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict):
                # 图片/文件/语音等非文本片段只留占位符，原始结构保存在 raw_json
                kind = part.get("content_type", "attachment")
                if part.get("text"):
                    out.append(part["text"])
                else:
                    out.append(f"[{kind}]")
        return "\n".join(p for p in out if p)
    if ctype in ("code", "execution_output"):
        return content.get("text") or ""
    if ctype == "tether_quote":
        return content.get("text") or ""
    if ctype == "tether_browsing_display":
        return content.get("result") or ""
    return content.get("text") or ""


def parse_conversation(conv: dict) -> Conversation:
    conv_id = conv.get("conversation_id") or conv.get("id")
    if not conv_id:
        raise ValueError("对话缺少 id")
    mapping = conv.get("mapping") or {}
    main_ids = main_branch_ids(mapping, conv.get("current_node"))

    messages = []
    for node_id, node in mapping.items():
        msg = node.get("message")
        if not msg:
            continue
        role = (msg.get("author") or {}).get("role", "unknown")
        meta = msg.get("metadata") or {}
        content = msg.get("content") or {}
        messages.append(Message(
            id=msg.get("id") or node_id,
            conversation_id=conv_id,
            parent_id=node.get("parent"),
            role=role,
            content_type=content.get("content_type", "unknown"),
            text=extract_text(content),
            create_time=msg.get("create_time"),
            model=meta.get("model_slug"),
            on_main_branch=node_id in main_ids,
            hidden=role == "system" or bool(meta.get("is_visually_hidden_from_conversation")),
            raw_json=json.dumps(msg, ensure_ascii=False),
        ))

    return Conversation(
        id=conv_id,
        title=conv.get("title"),
        create_time=conv.get("create_time"),
        update_time=conv.get("update_time"),
        messages=messages,
    )
