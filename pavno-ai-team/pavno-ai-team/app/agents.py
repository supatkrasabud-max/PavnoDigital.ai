"""ทีม AI ของ PAVNO DIGITAL: Ami (ผู้ช่วย CEO), Yuki (การเงิน) และ Agent ฝ่ายต่าง ๆ"""
from __future__ import annotations

import json
import re
from collections import defaultdict, deque

from .ledger import KINDS, Ledger, baht, format_report, period_range
from .llm import run_agent

COMPANY = """บริษัท: PAVNO DIGITAL (https://www.pavnodigital.com/)
ธุรกิจ: ขายไฟล์ดิจิทัลภาษาไทย — PDF ระบายสีพร้อมนิทานสำหรับเด็ก 4–7 ปี (COLOR & STORY),
แบบฝึกบวกลบพร้อมเฉลย (COUNT & DISCOVER), เทมเพลตพร้อมใช้ และคู่มือ AI กับการทำงาน
ราคาเป้าหมาย: ไฟล์เดี่ยว 59–99 บาท, แพ็กเกจ 249–399 บาท, เทมเพลต 149–299 บาท,
สมาชิกรายเดือน 149 บาท, ลิขสิทธิ์โรงเรียน 1,500–3,000 บาท/ปี,
บริการติดตั้งพนักงาน AI บน LINE ให้ SME 15,000–40,000 บาท/งาน
เป้าหมายบริษัท: มีกำไรทุกเดือนเพื่อชำระหนี้ 3,000,000 บาท งบดำเนินงานไม่เกิน 10,000 บาท/เดือน
ช่องทางรับเงิน: Stripe (PromptPay/บัตร)
ผู้บริหาร: CEO คือเจ้าของบริษัท ทุกการใช้เงินจริงต้องผ่าน Yuki และ CEO เป็นคนกดจ่ายเงินเอง"""

STYLE = """ตอบเป็นภาษาไทย กระชับ เหมาะกับการอ่านในแชต LINE (ไม่ใช้ markdown ตาราง ไม่ใช้ # หัวข้อ)
ห้ามแต่งตัวเลขยอดขายหรือข้อมูลบัญชีขึ้นเอง ถ้าไม่รู้ให้บอกว่าไม่รู้"""

WORKERS = {
    "product": ("ฝ่ายสินค้า", """คุณคือ Agent ฝ่ายสินค้าของ PAVNO DIGITAL
หน้าที่: คิดและเขียนเนื้อหาสินค้าดิจิทัล — โครงเรื่องนิทาน, รายการหน้าแบบฝึก, เนื้อหาเทมเพลต,
ชื่อสินค้า คำอธิบายสินค้า และราคาแนะนำ ให้พร้อมนำไปทำไฟล์ PDF ได้ทันที
เน้นสินค้าที่ทำได้เร็ว ต้นทุนต่ำ และขายเป็นแพ็กเกจได้ ระบุต้นทุนเป็นเงิน (ถ้ามี) ทุกครั้ง"""),
    "marketing": ("ฝ่ายการตลาด", """คุณคือ Agent ฝ่ายการตลาดของ PAVNO DIGITAL
หน้าที่: วางแผนคอนเทนต์ Facebook/TikTok/LINE, เขียนแคปชันพร้อมโพสต์, ออกแบบแคมเปญโฆษณา,
ร่างข้อความเสนอขายลิขสิทธิ์ให้โรงเรียน และข้อเสนอบริการให้ SME
ทุกแผนที่ต้องใช้เงินให้ระบุงบเป็นบาท และตัวชี้วัด (เช่น ต้นทุนต่อออเดอร์) ให้ชัด
งบโฆษณารวมต้องไม่เกินงบหมวด ads ที่ Yuki ตั้งไว้"""),
    "support": ("ฝ่ายบริการลูกค้า", """คุณคือ Agent ฝ่ายบริการลูกค้าของ PAVNO DIGITAL
หน้าที่: ร่างคำตอบลูกค้า (สุภาพ อบอุ่น), FAQ, นโยบายคืนเงิน, ข้อความหลังการขาย
และสรุปปัญหาที่ลูกค้าพบบ่อยเพื่อปรับปรุงสินค้า"""),
}

AMI_SYSTEM = f"""คุณคือ Ami ผู้ช่วยส่วนตัวของ CEO บริษัท PAVNO DIGITAL ทำงานในกลุ่ม LINE ของบริษัท
{COMPANY}

หน้าที่ของคุณ:
- รับคำสั่งจาก CEO แตกเป็นงานย่อย แล้วมอบหมายให้ Agent ที่เหมาะสมด้วย tool delegate
  (product = ฝ่ายสินค้า, marketing = ฝ่ายการตลาด, support = ฝ่ายบริการลูกค้า)
- เรื่องเงิน งบ บัญชี การขอใช้เงิน ให้ถาม Yuki ด้วย tool ask_yuki เสมอ ห้ามตัดสินเรื่องเงินเอง
- รวบรวมผลงานจากทุกฝ่าย แล้วสรุปให้ CEO: ทำอะไรไปแล้ว ผลลัพธ์ งบที่ต้องใช้ และสิ่งที่ CEO ต้องตัดสินใจ
- ถ้างานไหนต้องใช้เงิน ให้ส่งให้ Yuki สร้างคำขออนุมัติ แล้วบอก CEO ว่าต้องพิมพ์อนุมัติรหัสอะไร
{STYLE}"""

YUKI_SYSTEM = f"""คุณคือ Yuki เจ้าหน้าที่การเงินและบัญชีของบริษัท PAVNO DIGITAL
{COMPANY}

หน้าที่ของคุณ:
- บันทึกรายรับ รายจ่าย เงินทุนที่ CEO เติม และการชำระหนี้ ลงสมุดบัญชีด้วย tool เท่านั้น
- คุมงบประมาณรายเดือนตามหมวด เตือนเมื่อใกล้เกินหรือเกินงบ
- ค่าใช้จ่ายที่เกินงบหมวด หรือเกิน {{threshold}} บาท ต้องสร้างคำขออนุมัติ (request_approval) ให้ CEO ก่อน
- สรุปตัวเลขจาก tool get_summary เท่านั้น ห้ามคำนวณหรือเดายอดเอง
- บอก CEO เสมอว่าควรเติมทุนเท่าไรเพื่อให้บริษัทเดินต่อได้
- หมวดที่ใช้: ads, accountant, ai_api, server, product, other (รายรับ: pdf, bundle, subscription, school_license, service)
- คุณไม่มีสิทธิ์จ่ายเงินจริง และไม่ใช่ผู้ทำบัญชีตามกฎหมาย งบการเงินประจำปีต้องให้นักบัญชีที่ขึ้นทะเบียนรับรอง
ผู้สั่งงานตอนนี้ {{who}}
{STYLE}"""

YUKI_TOOLS = [
    {"name": "add_entry", "description": "บันทึกรายการบัญชี",
     "input_schema": {"type": "object", "properties": {
         "kind": {"type": "string", "enum": list(KINDS)},
         "category": {"type": "string"},
         "amount": {"type": "number", "description": "จำนวนเงินบาท ค่าบวก"},
         "note": {"type": "string"},
         "date": {"type": "string", "description": "YYYY-MM-DD ไม่ใส่ = วันนี้"}},
         "required": ["kind", "category", "amount"]}},
    {"name": "get_summary", "description": "สรุปบัญชีตามช่วงเวลา",
     "input_schema": {"type": "object", "properties": {
         "period": {"type": "string",
                    "enum": ["this_week", "last_week", "this_month", "last_month", "all"]}},
         "required": ["period"]}},
    {"name": "list_budgets", "description": "ดูวงเงินงบประมาณรายเดือนทุกหมวด",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "set_budget", "description": "ตั้ง/แก้วงเงินงบรายเดือนของหมวด (CEO เท่านั้น)",
     "input_schema": {"type": "object", "properties": {
         "category": {"type": "string"}, "monthly_limit": {"type": "number"}},
         "required": ["category", "monthly_limit"]}},
    {"name": "set_debt", "description": "ตั้งยอดหนี้เริ่มต้นของบริษัท (CEO เท่านั้น)",
     "input_schema": {"type": "object", "properties": {"amount": {"type": "number"}},
                      "required": ["amount"]}},
    {"name": "request_approval", "description": "สร้างคำขอใช้เงินให้ CEO อนุมัติ",
     "input_schema": {"type": "object", "properties": {
         "category": {"type": "string"}, "amount": {"type": "number"},
         "reason": {"type": "string"}, "requested_by": {"type": "string"}},
         "required": ["category", "amount", "reason"]}},
    {"name": "list_pending", "description": "ดูคำขอที่รออนุมัติ",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "decide_approval", "description": "อนุมัติหรือปฏิเสธคำขอ (CEO เท่านั้น)",
     "input_schema": {"type": "object", "properties": {
         "approval_id": {"type": "string"}, "approve": {"type": "boolean"}},
         "required": ["approval_id", "approve"]}},
]

AMI_TOOLS = [
    {"name": "delegate", "description": "มอบหมายงานให้ Agent ฝ่ายต่าง ๆ และรับผลงานกลับมา",
     "input_schema": {"type": "object", "properties": {
         "agent": {"type": "string", "enum": list(WORKERS)},
         "task": {"type": "string", "description": "รายละเอียดงานที่ชัดเจน พร้อมบริบท"}},
         "required": ["agent", "task"]}},
    {"name": "ask_yuki", "description": "ถามหรือสั่งงาน Yuki เรื่องเงิน งบ บัญชี คำขออนุมัติ",
     "input_schema": {"type": "object", "properties": {"request": {"type": "string"}},
                      "required": ["request"]}},
]

# ชื่อต้องตามด้วยช่องว่าง/เครื่องหมาย/จบข้อความ (\b ใช้กับสระไทยไม่ได้)
YUKI_RE = re.compile(r"^\s*(@?yuki|ยูกิ)(?=[\s,:]|$)[\s,:]*", re.I)
AMI_RE = re.compile(r"^\s*(@?ami|อามิ|เอมิ)(?=[\s,:]|$)[\s,:]*", re.I)


class CeoOnly(Exception):
    pass


class Team:
    def __init__(self, client, ledger: Ledger, settings):
        self.client = client
        self.ledger = ledger
        self.s = settings
        self.history: dict[str, deque] = defaultdict(lambda: deque(maxlen=12))

    # ---------------------------------------------------------------- routing
    def is_ceo(self, user_id: str) -> bool:
        return not self.s.CEO_USER_ID or user_id == self.s.CEO_USER_ID

    def handle(self, text: str, user_id: str, chat_id: str, is_group: bool) -> str | None:
        """คืนข้อความตอบกลับ หรือ None ถ้าไม่ต้องตอบ"""
        t = text.strip()
        low = t.lower()
        if low in ("groupid", "/groupid"):
            return f"Group ID: {chat_id}"
        if low in ("myid", "/myid"):
            return f"User ID ของคุณ: {user_id}"
        if self.s.ALLOWED_USER_IDS and user_id not in self.s.ALLOWED_USER_IDS:
            return None
        if low in ("/report", "รายงาน"):
            return self.report("this_week", "รายงานบัญชีสัปดาห์นี้")
        m = re.match(r"^\s*(อนุมัติ|ไม่อนุมัติ)\s+([A-Za-z0-9]+)\s*$", t)
        if m:
            if not self.is_ceo(user_id):
                return "เฉพาะ CEO เท่านั้นที่อนุมัติได้ค่ะ"
            try:
                r = self.ledger.decide_approval(m.group(2), m.group(1) == "อนุมัติ")
            except ValueError as e:
                return str(e)
            word = "อนุมัติแล้ว" if r["status"] == "approved" else "ไม่อนุมัติ"
            return (f"Yuki: {word} {r['id']} — {r['category']} {baht(float(r['amount']))}"
                    f" ({r['reason']})\nเมื่อจ่ายเงินจริงแล้ว พิมพ์ \"Yuki บันทึกจ่าย ...\" ได้เลยค่ะ")

        if YUKI_RE.match(t):
            body = YUKI_RE.sub("", t, count=1) or "สรุปสถานะการเงินสัปดาห์นี้"
            return "Yuki: " + self._chat(chat_id, "yuki", body, user_id)
        if AMI_RE.match(t):
            body = AMI_RE.sub("", t, count=1) or "สวัสดี"
            return "Ami: " + self._chat(chat_id, "ami", body, user_id)
        if not is_group:  # แชต 1:1 ส่งให้ Ami ทุกข้อความ
            return "Ami: " + self._chat(chat_id, "ami", t, user_id)
        return None

    def _chat(self, chat_id: str, who: str, text: str, user_id: str) -> str:
        key = f"{chat_id}:{who}"
        hist = self.history[key]
        msgs = list(hist) + [{"role": "user", "content": text}]
        if who == "yuki":
            answer = self.run_yuki(msgs, user_id)
        else:
            answer = self.run_ami(msgs, user_id)
        hist.append({"role": "user", "content": text})
        hist.append({"role": "assistant", "content": answer or "-"})
        return answer

    # ---------------------------------------------------------------- agents
    def run_ami(self, messages: list[dict], user_id: str) -> str:
        handlers = {
            "delegate": lambda a: self.run_worker(a["agent"], a["task"]),
            "ask_yuki": lambda a: self.run_yuki(
                [{"role": "user", "content": f"(จาก Ami) {a['request']}"}], user_id),
        }
        return run_agent(self.client, model=self.s.MODEL_LEAD, system=AMI_SYSTEM,
                         messages=messages, tools=AMI_TOOLS, handlers=handlers, max_turns=10)

    def run_worker(self, agent: str, task: str) -> str:
        if agent not in WORKERS:
            return f"ไม่มีฝ่าย {agent}"
        name, prompt = WORKERS[agent]
        system = f"{prompt}\n\n{COMPANY}\n{STYLE}"
        out = run_agent(self.client, model=self.s.MODEL_WORKER, system=system,
                        messages=[{"role": "user", "content": task}], max_tokens=3000)
        return f"[{name}]\n{out}"

    def run_yuki(self, messages: list[dict], user_id: str) -> str:
        ceo = self.is_ceo(user_id)
        system = (YUKI_SYSTEM.replace("{threshold}", f"{self.s.APPROVAL_THRESHOLD:,.0f}")
                  .replace("{who}", "คือ CEO" if ceo else "ไม่ใช่ CEO (ห้ามบันทึกเงินทุน/อนุมัติ/แก้งบ)"))
        return run_agent(self.client, model=self.s.MODEL_LEAD, system=system,
                         messages=messages, tools=YUKI_TOOLS, handlers=self.yuki_handlers(ceo))

    def yuki_handlers(self, ceo: bool) -> dict:
        L = self.ledger

        def need_ceo():
            if not ceo:
                raise CeoOnly("คำสั่งนี้ทำได้เฉพาะ CEO")

        def add_entry(a):
            if a["kind"] == "capital":
                need_ceo()
            e = L.add_entry(a["kind"], a["category"], a["amount"], a.get("note", ""),
                            on_date=a.get("date") or None)
            return f"บันทึกแล้ว #{e.id}: {KINDS[e.kind]} {e.category} {baht(e.amount)} วันที่ {e.date}"

        def get_summary(a):
            start, end = period_range(a["period"], self.s.TIMEZONE)
            return json.dumps(L.summary(start, end), ensure_ascii=False)

        def set_budget(a):
            need_ceo()
            L.set_budget(a["category"], a["monthly_limit"])
            return f"ตั้งงบ {a['category']} = {baht(a['monthly_limit'])}/เดือน แล้ว"

        def set_debt(a):
            need_ceo()
            L.set_setting("debt_initial", float(a["amount"]))
            return f"ตั้งยอดหนี้เริ่มต้น {baht(a['amount'])} แล้ว"

        def request_approval(a):
            r = L.request_approval(a["category"], a["amount"], a["reason"],
                                   a.get("requested_by", "Ami"))
            return (f"สร้างคำขอ {r['id']} แล้ว ให้ CEO พิมพ์ \"อนุมัติ {r['id']}\" "
                    f"หรือ \"ไม่อนุมัติ {r['id']}\" ในกลุ่ม")

        def decide(a):
            need_ceo()
            r = L.decide_approval(a["approval_id"], a["approve"])
            return f"{r['id']} สถานะ {r['status']}"

        return {
            "add_entry": add_entry,
            "get_summary": get_summary,
            "list_budgets": lambda a: json.dumps(L.budgets(), ensure_ascii=False),
            "set_budget": set_budget,
            "set_debt": set_debt,
            "request_approval": request_approval,
            "list_pending": lambda a: json.dumps(L.pending_approvals(), ensure_ascii=False) or "[]",
            "decide_approval": decide,
        }

    # ---------------------------------------------------------------- reports
    def report(self, period: str, title: str, with_comment: bool = True) -> str:
        start, end = period_range(period, self.s.TIMEZONE)
        s = self.ledger.summary(start, end)
        text = format_report(s, title)
        pending = self.ledger.pending_approvals()
        if pending:
            text += "\n\nรออนุมัติ: " + ", ".join(
                f"{p['id']} {p['category']} {baht(float(p['amount']))}" for p in pending)
        if with_comment:
            try:
                comment = run_agent(
                    self.client, model=self.s.MODEL_LEAD, max_tokens=600,
                    system=YUKI_SYSTEM.replace("{threshold}", "-").replace("{who}", "ระบบรายงานอัตโนมัติ"),
                    messages=[{"role": "user", "content":
                               "เขียนความเห็นสั้น ๆ 3–5 บรรทัดถึง CEO จากตัวเลขนี้ "
                               "(จุดที่ต้องระวัง สิ่งที่ควรทำต่อ และยอดที่ควรเติมทุน):\n"
                               + json.dumps(s, ensure_ascii=False)}])
                if comment:
                    text += "\n\nความเห็นจาก Yuki:\n" + comment
            except Exception:
                pass  # รายงานตัวเลขยังส่งได้ แม้ AI ล่ม
        return text
