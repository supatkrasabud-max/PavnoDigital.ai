"""เรียก Claude API แบบเบา ๆ ผ่าน urllib (ไม่ต้องติดตั้งไลบรารีเพิ่ม)
และลูปการใช้ tool สำหรับ Agent"""
from __future__ import annotations

import json
import logging
import urllib.error
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
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:  # งานค้นเว็บใช้เวลาได้หลายนาที
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            # เดิมได้แค่ "HTTP Error 400: Bad Request" ไม่รู้สาเหตุ ให้แนบข้อความจาก Claude API มาด้วย
            try:
                detail = json.loads(e.read()).get("error", {}).get("message", "")
            except Exception:
                detail = ""
            raise ClaudeAPIError(f"Claude API {e.code}: {detail or e.reason}") from None


class ClaudeAPIError(RuntimeError):
    pass


ToolHandler = Callable[[dict], str]

# ค้นเว็บฝั่งเซิร์ฟเวอร์ของ Anthropic (ประมาณ $10 ต่อ 1,000 ครั้งค้น + ค่า token)
WEB_SEARCH = {"type": "web_search_20260209", "name": "web_search",
              "user_location": {"type": "approximate", "country": "TH", "timezone": "Asia/Bangkok"}}


def research(client, *, model: str, system: str, prompt: str, max_searches: int = 6,
             max_tokens: int = 16000, max_rounds: int = 4) -> str:
    """ให้ Claude ค้นเว็บแล้วตอบ คืนข้อความทั้งหมด (รองรับ pause_turn ที่เกิดตอนค้นนาน)"""
    msgs = [{"role": "user", "content": prompt}]
    tool = {**WEB_SEARCH, "max_uses": max_searches}
    text = ""
    for _ in range(max_rounds):
        resp = client.create(model=model, max_tokens=max_tokens, system=system,
                             messages=msgs, tools=[tool])
        content = resp.get("content", [])
        text += "".join(b.get("text", "") for b in content if b.get("type") == "text")
        if resp.get("stop_reason") != "pause_turn":
            return text.strip()
        msgs = msgs + [{"role": "assistant", "content": content}]
    return text.strip()


def extract_json(text: str):
    """ดึง JSON ก้อนสุดท้ายจากคำตอบ (รองรับ ```json ... ``` หรือ [ ... ] เปล่า ๆ)"""
    import re
    blocks = re.findall(r"```(?:json)?\s*(.*?)```", text, re.S)
    for cand in reversed(blocks + [text]):
        cand = cand.strip()
        for opener, closer in (("[", "]"), ("{", "}")):
            i, j = cand.find(opener), cand.rfind(closer)
            if i != -1 and j > i:
                try:
                    return json.loads(cand[i:j + 1])
                except json.JSONDecodeError:
                    continue
    raise ValueError("ไม่พบ JSON ในคำตอบ")


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
