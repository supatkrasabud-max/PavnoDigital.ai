"""เรียก Claude API แบบเบา ๆ ผ่าน urllib (ไม่ต้องติดตั้งไลบรารีเพิ่ม)
และลูปการใช้ tool สำหรับ Agent"""
from __future__ import annotations

import json
import logging
import urllib.request
from typing import Callable

log = logging.getLogger("llm")

API_URL = "https://api.anthropic.com/v1/messages"


class ClaudeClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def create(self, **body) -> dict:
        req = urllib.request.Request(
            API_URL,
            data=json.dumps(body).encode(),
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read())


ToolHandler = Callable[[dict], str]


def run_agent(client, *, model: str, system: str, messages: list[dict],
              tools: list[dict] | None = None, handlers: dict[str, ToolHandler] | None = None,
              max_turns: int = 8, max_tokens: int = 2000) -> str:
    """ส่งข้อความให้ Agent แล้ววนเรียก tool จนกว่า Agent จะตอบเป็นข้อความสุดท้าย"""
    handlers = handlers or {}
    msgs = list(messages)
    for _ in range(max_turns):
        body = {"model": model, "max_tokens": max_tokens, "system": system, "messages": msgs}
        if tools:
            body["tools"] = tools
        resp = client.create(**body)
        content = resp.get("content", [])
        if resp.get("stop_reason") != "tool_use":
            return "".join(b.get("text", "") for b in content if b.get("type") == "text").strip()
        msgs.append({"role": "assistant", "content": content})
        results = []
        for block in content:
            if block.get("type") != "tool_use":
                continue
            fn = handlers.get(block["name"])
            try:
                out = fn(block.get("input", {})) if fn else f"ไม่รู้จัก tool {block['name']}"
                is_error = fn is None
            except Exception as e:  # ส่ง error กลับให้ Agent แก้เอง
                log.exception("tool %s failed", block["name"])
                out, is_error = f"ผิดพลาด: {e}", True
            results.append({"type": "tool_result", "tool_use_id": block["id"],
                            "content": str(out), "is_error": is_error})
        msgs.append({"role": "user", "content": results})
    return "ขออภัย งานนี้ซับซ้อนเกินไป ลองแบ่งเป็นคำสั่งย่อยนะคะ"
