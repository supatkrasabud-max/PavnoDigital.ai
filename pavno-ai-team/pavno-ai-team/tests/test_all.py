import base64
import hashlib
import hmac
import json
import time
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from app.agents import Team
from app.ledger import CsvBackend, Ledger, format_report, period_range, summarize, today
from app.line_api import split_text
from app.main import build_app


def cfg(**kw):
    base = dict(LINE_CHANNEL_SECRET="linesecret", LINE_CHANNEL_ACCESS_TOKEN="x", LINE_GROUP_ID="G1",
                CEO_USER_ID="U_CEO", ALLOWED_USER_IDS=[], ANTHROPIC_API_KEY="k",
                MODEL_LEAD="lead", MODEL_WORKER="worker", STRIPE_WEBHOOK_SECRET="whsec",
                NOTIFY_EACH_SALE=True, CRON_SECRET="cron", APPROVAL_THRESHOLD=2000.0,
                TIMEZONE="Asia/Bangkok")
    base.update(kw)
    return SimpleNamespace(**base)


class FakeClaude:
    """จำลอง Claude: เล่นตามสคริปต์คำตอบที่เตรียมไว้"""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def create(self, **body):
        self.calls.append(body)
        step = self.script.pop(0)
        if isinstance(step, str):
            return {"stop_reason": "end_turn", "content": [{"type": "text", "text": step}]}
        name, args = step
        return {"stop_reason": "tool_use",
                "content": [{"type": "tool_use", "id": f"t{len(self.calls)}", "name": name, "input": args}]}


class FakeLine:
    def __init__(self):
        self.sent = []

    def reply_or_push(self, token, to, text):
        self.sent.append(("reply", to, text))

    def push(self, to, text):
        self.sent.append(("push", to, text))


@pytest.fixture
def ledger(tmp_path):
    return Ledger(CsvBackend(str(tmp_path)))


# ------------------------------------------------------------------ ledger

def test_summary_math(ledger):
    d = today().isoformat()
    ledger.set_setting("debt_initial", 3_000_000)
    ledger.add_entry("capital", "ceo", 10_000)
    ledger.add_entry("income", "pdf", 99)
    ledger.add_entry("income", "bundle", 299)
    ledger.add_entry("expense", "ads", 4_500)
    ledger.add_entry("debt_payment", "loan", 1_000)
    s = ledger.summary(*period_range("this_month"))
    assert s["income"] == 398 and s["expense"] == 4500
    assert s["net_profit"] == -4102
    assert s["cash_balance"] == 10_000 + 398 - 4500 - 1000
    assert s["debt_remaining"] == 2_999_000
    ads = next(b for b in s["budget_status"] if b["category"] == "ads")
    assert ads["over"] is True  # งบ ads 4,000
    assert s["suggested_top_up"] == max(8000 - s["cash_balance"], 0)
    text = format_report(s, "ทดสอบ")
    assert "เกินงบ" in text and "หนี้คงเหลือ: 2,999,000 บาท" in text


def test_summary_period_filter():
    rows = [{"date": "2026-10-31", "kind": "income", "category": "pdf", "amount": 100},
            {"date": "2026-11-02", "kind": "income", "category": "pdf", "amount": 200}]
    s = summarize(rows, {}, 0, date(2026, 11, 1), date(2026, 11, 30))
    assert s["income"] == 200 and s["cash_balance"] == 300


def test_validation_and_dedupe(ledger):
    with pytest.raises(ValueError):
        ledger.add_entry("income", "pdf", -5)
    with pytest.raises(ValueError):
        ledger.add_entry("gift", "pdf", 5)
    ledger.add_entry("income", "pdf", 99, ref="cs_1")
    with pytest.raises(ValueError):
        ledger.add_entry("income", "pdf", 99, ref="cs_1")


def test_period_ranges():
    s, e = period_range("last_week")
    assert e - s == timedelta(days=6) and s.weekday() == 0
    s, e = period_range("last_month")
    assert s.day == 1 and (e + timedelta(days=1)).day == 1


def test_split_text():
    parts = split_text("ก" * 12000)
    assert len(parts) == 3 and all(len(p["text"]) <= 4900 for p in parts)


# ------------------------------------------------------------------ agents

def test_ami_delegates_and_asks_yuki(ledger):
    claude = FakeClaude([
        ("delegate", {"agent": "marketing", "task": "แผนโพสต์ 1 สัปดาห์"}),   # Ami
        "แผน: โพสต์ 5 วัน งบโฆษณา 1,000 บาท",                                # ฝ่ายการตลาด
        ("ask_yuki", {"request": "ขออนุมัติงบโฆษณา 1,000 บาท"}),            # Ami
        ("request_approval", {"category": "ads", "amount": 1000, "reason": "บูสต์โพสต์"}),  # Yuki
        "สร้างคำขอแล้วค่ะ",                                                  # Yuki
        "สรุป: ฝ่ายการตลาดทำแผนแล้ว รออนุมัติงบ 1,000 บาท",                     # Ami
    ])
    team = Team(claude, ledger, cfg())
    out = team.handle("Ami ทำแผนการตลาดสัปดาห์นี้", "U_CEO", "G1", is_group=True)
    assert out.startswith("Ami: สรุป")
    assert [c["model"] for c in claude.calls] == ["lead", "worker", "lead", "lead", "lead", "lead"]
    pend = ledger.pending_approvals()
    assert len(pend) == 1 and float(pend[0]["amount"]) == 1000
    # CEO อนุมัติด้วยข้อความ (ไม่เรียก AI)
    msg = team.handle(f"อนุมัติ {pend[0]['id']}", "U_CEO", "G1", True)
    assert "อนุมัติแล้ว" in msg and not ledger.pending_approvals()


def test_non_ceo_cannot_add_capital_or_approve(ledger):
    claude = FakeClaude([("add_entry", {"kind": "capital", "category": "ceo", "amount": 5000}),
                         "ทำไม่ได้ค่ะ"])
    team = Team(claude, ledger, cfg())
    team.handle("Yuki บันทึกเงินทุน 5000", "U_STAFF", "G1", True)
    tool_result = claude.calls[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] and "CEO" in tool_result["content"]
    assert ledger.entries() == []
    r = ledger.request_approval("ads", 500, "x", "Ami")
    assert "เฉพาะ CEO" in team.handle(f"อนุมัติ {r['id']}", "U_STAFF", "G1", True)


def test_group_ignores_unaddressed_messages(ledger):
    team = Team(FakeClaude([]), ledger, cfg())
    assert team.handle("กินข้าวยัง", "U_CEO", "G1", True) is None
    assert team.handle("groupid", "U_X", "G1", True) == "Group ID: G1"


# ------------------------------------------------------------------ http

def line_sig(body: bytes) -> str:
    return base64.b64encode(hmac.new(b"linesecret", body, hashlib.sha256).digest()).decode()


def stripe_sig(body: bytes) -> str:
    t = str(int(time.time()))
    v = hmac.new(b"whsec", f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={t},v1={v}"


def test_line_webhook(ledger):
    line = FakeLine()
    team = Team(FakeClaude([("add_entry", {"kind": "expense", "category": "ads", "amount": 800}),
                            "บันทึกค่าโฆษณา 800 บาทแล้วค่ะ"]), ledger, cfg())
    client = TestClient(build_app(team, line, cfg()))
    body = json.dumps({"events": [{"type": "message", "replyToken": "r",
                                   "source": {"type": "group", "groupId": "G1", "userId": "U_CEO"},
                                   "message": {"type": "text", "text": "ยูกิ จ่ายค่าโฆษณา 800"}}]}).encode()
    assert client.post("/callback", content=body, headers={"x-line-signature": "bad"}).status_code == 400
    assert client.post("/callback", content=body, headers={"x-line-signature": line_sig(body)}).status_code == 200
    assert line.sent[0][2].startswith("Yuki: บันทึก")
    assert ledger.entries()[0]["amount"] == 800


def test_stripe_webhook_records_once(ledger):
    line = FakeLine()
    client = TestClient(build_app(Team(FakeClaude([]), ledger, cfg()), line, cfg()))
    ev = {"type": "checkout.session.completed",
          "data": {"object": {"id": "cs_123", "payment_status": "paid", "amount_total": 29900,
                              "metadata": {"category": "bundle"}}}}
    body = json.dumps(ev).encode()
    r1 = client.post("/stripe/webhook", content=body, headers={"stripe-signature": stripe_sig(body)})
    r2 = client.post("/stripe/webhook", content=body, headers={"stripe-signature": stripe_sig(body)})
    bad = client.post("/stripe/webhook", content=body, headers={"stripe-signature": "t=1,v1=zz"})
    assert "recorded" in r1.json() and "skipped" in r2.json() and bad.status_code == 400
    assert [e["amount"] for e in ledger.entries()] == [299.0]
    assert "299 บาท" in line.sent[0][2]


def test_cron_report(ledger):
    line = FakeLine()
    ledger.add_entry("income", "pdf", 99, on_date=period_range("last_week")[0].isoformat())
    client = TestClient(build_app(Team(FakeClaude(["ยอดยังต่ำ ควรเพิ่มโพสต์"]), ledger, cfg()), line, cfg()))
    assert client.get("/cron/weekly?key=wrong").status_code == 403
    r = client.get("/cron/weekly?key=cron")
    assert r.status_code == 200 and "รายรับ: 99 บาท" in r.text and "ความเห็นจาก Yuki" in r.text
    assert line.sent[0][0] == "push" and line.sent[0][1] == "G1"


def test_thai_names_route(ledger):
    team = Team(FakeClaude(["สวัสดีค่ะ CEO"]), ledger, cfg())
    assert team.handle("อามิ สวัสดี", "U_CEO", "G1", True) == "Ami: สวัสดีค่ะ CEO"
    assert team.handle("amiga hello", "U_CEO", "G1", True) is None
