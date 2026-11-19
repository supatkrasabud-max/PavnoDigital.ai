"""ทีม AI ของ PAVNO DIGITAL: Ami (ผู้ช่วย CEO), Yuki (การเงิน) และ Agent ฝ่ายต่าง ๆ"""
from __future__ import annotations

import json
import re
from collections import defaultdict, deque

from .ledger import (KINDS, SET_DEBT, SET_SAVING_GOAL, Ledger, baht, format_report,
                     period_range, today)
from .llm import run_agent

COMPANY = """บริษัท: PAVNO DIGITAL (https://www.pavnodigital.com/)
รายได้หลักตอนนี้:
- PAVNO Learn: สมุดฝึก PDF สำหรับเด็ก (ก-ฮ, ABC, ฮิรางานะ, คันจิ, จีน, คณิต 4 เล่ม, ระบายสี) 79–169 บาท ขายบนเว็บผ่าน Stripe
- Affiliate: ทำคลิปรีวิวสินค้า Shopee/TikTok แล้วรับค่าคอม (มีระบบหาสินค้าและเขียนบทให้ทุกเช้า)
- Etsy: ร้านขาย PDF ต่างประเทศ (รอยืนยันตัวตน Payoneer)
- บริการ IT และบริการติดตั้งพนักงาน AI บน LINE ให้ SME
เป้าหมายระยะยาวของ CEO: สร้างรายได้หลายช่องทางที่โตได้โดยไม่ต้องพึ่งงานประจำ ปลดหนี้ มีเงินเก็บของบริษัท
และสร้างระบบที่ดูแลครอบครัวขนาดใหญ่ได้
บัญชีทั้งหมดอยู่ใน Google Sheet "PAVNO บัญชี" (ใช้ร่วมกับเว็บแอป Yuki Ledger)
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
    "planner": ("ฝ่ายวางแผนธุรกิจ", """คุณคือ Agent ฝ่ายวางแผนธุรกิจของ PAVNO DIGITAL
หน้าที่: แปลงเป้าหมายของ CEO เป็นแผนที่ทำได้จริง เช่น แผน 30/90 วัน, ช่องทางรายได้ใหม่, การแบ่งเวลา,
ขั้นบันไดจากรายได้เสริมไปสู่รายได้หลักที่ไม่ต้องพึ่งงานประจำ และระบบที่ทำงานซ้ำได้ (อัตโนมัติ/จ้างคน)
กติกา:
- ทุกแผนต้องมี ตัวเลขเป้า, งานรายสัปดาห์, ต้นทุนเป็นบาท, ตัวชี้วัด และจุดตัดสินใจว่าจะทำต่อหรือหยุด
- ใช้ตัวเลขจริงที่ได้รับมาเท่านั้น ถ้าไม่มีข้อมูลให้บอกว่าเป็นสมมติฐาน ห้ามสัญญาว่ารวยเร็วหรือได้เงินแน่นอน
- ห้ามแนะนำ แชร์ลูกโซ่ การพนัน เทรดเก็งกำไร หรือกู้เงินมาลงทุน
- ไม่แนะนำหุ้น กองทุน หรือคริปโตรายตัว (ไม่ใช่ที่ปรึกษาการลงทุนที่มีใบอนุญาต) ให้แนะนำเฉพาะการลงทุนในธุรกิจของบริษัท
- ลำดับความสำคัญทางการเงิน: เงินสำรองฉุกเฉิน → ปิดหนี้ดอกเบี้ยสูง → ลงทุนต่อยอดธุรกิจที่พิสูจน์แล้ว"""),
}

AMI_SYSTEM = f"""คุณคือ Ami ผู้ช่วยส่วนตัวของ CEO บริษัท PAVNO DIGITAL ทำงานในกลุ่ม LINE ของบริษัท
{COMPANY}

หน้าที่ของคุณ:
- รับคำสั่งจาก CEO แตกเป็นงานย่อย แล้วมอบหมายให้ Agent ที่เหมาะสมด้วย tool delegate
  (product = ฝ่ายสินค้า, marketing = ฝ่ายการตลาด, support = ฝ่ายบริการลูกค้า, planner = ฝ่ายวางแผนธุรกิจ)
- เรื่องเงิน งบ บัญชี เป้าหมายรายได้ การขอใช้เงิน ให้ถาม Yuki ด้วย tool ask_yuki เสมอ ห้ามตัดสินเรื่องเงินเอง
- เมื่อ CEO ขอแผนธุรกิจหรือแผนการเงิน ให้ถาม Yuki เอาตัวเลขจริงและเป้าปัจจุบันก่อน แล้วส่งตัวเลขนั้นให้ planner วางแผน
- งานที่ต้องลงมือทำบนคอมพิวเตอร์ (แก้เว็บ ทำไฟล์ ทำคลิป) ให้สรุปเป็นรายการงานให้ CEO นำไปสั่ง Claude Code ต่อ
- รวบรวมผลงานจากทุกฝ่าย แล้วสรุปให้ CEO: ทำอะไรไปแล้ว ผลลัพธ์ งบที่ต้องใช้ และสิ่งที่ CEO ต้องตัดสินใจ
- ถ้างานไหนต้องใช้เงิน ให้ส่งให้ Yuki สร้างคำขออนุมัติ แล้วบอก CEO ว่าต้องพิมพ์อนุมัติรหัสอะไร
{STYLE}"""

YUKI_SYSTEM = f"""คุณคือ Yuki เจ้าหน้าที่การเงินและบัญชีของบริษัท PAVNO DIGITAL
{COMPANY}

หน้าที่ของคุณ:
- บันทึกรายรับ รายจ่าย ลงทุน เงินเก็บ เงินทุนที่ CEO เติม และการชำระหนี้ ลงสมุดบัญชีด้วย tool เท่านั้น
  ใส่ช่องทาง (channel) ของรายรับทุกครั้ง เช่น เว็บ PAVNO, Shopee, TikTok, Etsy, บริการ IT
- คุมงบประมาณรายเดือนตามหมวด เตือนเมื่อใกล้เกินหรือเกินงบ
- ดูแลเป้าหมาย: เป้ารายรับ กำไร เงินเก็บรายเดือน เป้าแต่ละช่องทาง และเป้าเงินเก็บสะสม (get_goals / set_goal / set_channel_target)
- ค่าใช้จ่ายที่เกินงบหมวด หรือเกิน {{threshold}} บาท ต้องสร้างคำขออนุมัติ (request_approval) ให้ CEO ก่อน
- สรุปตัวเลขจาก tool get_summary เท่านั้น ห้ามคำนวณหรือเดายอดเอง
- หมวดที่ใช้ (ภาษาไทย ตรงกับชีต): รายจ่าย = ค่าโฆษณา, ซอฟต์แวร์และ AI, ค่าธรรมเนียมแพลตฟอร์ม, ซื้อสินค้ามารีวิว,
  อุปกรณ์, ค่าพิมพ์และค่าส่ง, ค่าอินเทอร์เน็ตและโทรศัพท์, ภาษี, รายจ่ายอื่น
  รายรับ = ขายไฟล์ PDF (เว็บ/Stripe), ขาย Etsy, ค่าคอม Shopee Affiliate, ค่าคอม TikTok Affiliate, บริการ IT / รับจ้าง, รายรับอื่น
  เงินเก็บ = เงินเก็บบริษัท, เงินสำรองฉุกเฉิน, กันไว้จ่ายภาษี / ลงทุน = ต่อยอดธุรกิจ
- คุณไม่มีสิทธิ์จ่ายเงินจริง และไม่ใช่ผู้ทำบัญชีตามกฎหมาย งบการเงินประจำปีต้องให้นักบัญชีที่ขึ้นทะเบียนรับรอง
ผู้สั่งงานตอนนี้ {{who}}
{STYLE}"""

YUKI_TOOLS = [
    {"name": "add_entry", "description": "บันทึกรายการบัญชี",
     "input_schema": {"type": "object", "properties": {
         "kind": {"type": "string", "enum": list(KINDS),
                  "description": "income=รายรับ expense=รายจ่าย invest=ลงทุน saving=เงินเก็บ capital=เงินทุน CEO debt_payment=ชำระหนี้"},
         "category": {"type": "string"},
         "channel": {"type": "string", "description": "ช่องทาง เช่น Shopee, TikTok, เว็บ PAVNO"},
         "amount": {"type": "number", "description": "จำนวนเงินบาท ค่าบวก"},
         "note": {"type": "string"},
         "date": {"type": "string", "description": "YYYY-MM-DD ไม่ใส่ = วันนี้"}},
         "required": ["kind", "category", "amount"]}},
    {"name": "get_summary", "description": "สรุปบัญชีตามช่วงเวลา พร้อมความคืบหน้าเทียบเป้าของเดือน",
     "input_schema": {"type": "object", "properties": {
         "period": {"type": "string",
                    "enum": ["today", "yesterday", "this_week", "last_week", "this_month", "last_month", "all"]}},
         "required": ["period"]}},
    {"name": "get_goals", "description": "ดูเป้าหมายของเดือน เป้าแต่ละช่องทาง และเป้าเงินเก็บสะสม",
     "input_schema": {"type": "object", "properties": {
         "month": {"type": "string", "description": "YYYY-MM ไม่ใส่ = เดือนนี้"}}}},
    {"name": "set_goal", "description": "ตั้งเป้ารายรับ/กำไร/เงินเก็บรายเดือน (CEO เท่านั้น) ไม่ใส่ month = ใช้ทุกเดือน",
     "input_schema": {"type": "object", "properties": {
         "month": {"type": "string", "description": "YYYY-MM หรือเว้นว่างเพื่อเป็นค่าเริ่มต้น"},
         "income": {"type": "number"}, "profit": {"type": "number"}, "saving": {"type": "number"},
         "saving_total": {"type": "number", "description": "เป้าเงินเก็บสะสมของบริษัท (ไม่บังคับ)"}},
         "required": ["income", "profit", "saving"]}},
    {"name": "set_channel_target", "description": "เพิ่มช่องทางรายได้ใหม่ หรือแก้เป้ารายรับต่อเดือนของช่องทาง (CEO เท่านั้น)",
     "input_schema": {"type": "object", "properties": {
         "name": {"type": "string"}, "target": {"type": "number"}},
         "required": ["name", "target"]}},
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

HELP = """คำสั่งที่ใช้ได้ (แชต 1:1 กับบอท ไม่ต้องพิมพ์ชื่อก็ได้ / ในกลุ่มให้ขึ้นต้นด้วย Ami หรือ Yuki)

สรุปทันที (ไม่เสียค่า AI):
• สรุปวันนี้ • เป้า • รายงาน (สัปดาห์นี้) • สรุปเดือนนี้

บันทึกเงิน:
• Yuki ได้ค่าคอม Shopee 1,250 บาท
• Yuki จ่ายค่าโฆษณา TikTok 300
• Yuki โอนเข้าเงินเก็บบริษัท 2,000

ตั้งเป้า:
• Yuki ตั้งเป้าทุกเดือน รายรับ 30,000 กำไร 15,000 เงินเก็บ 5,000
• Yuki ตั้งเป้าเงินเก็บสะสม 500,000
• Yuki เพิ่มช่องทาง Lazada เป้า 3,000

วางแผนและสั่งงาน:
• Ami วางแผน 90 วันให้รายได้ถึง 50,000 ต่อเดือน
• Ami ทำแผนคอนเทนต์ TikTok สัปดาห์นี้
• อนุมัติ A1B2 / ไม่อนุมัติ A1B2

รายงานอัตโนมัติ: ทุกวัน 08:00 · ทุกวันจันทร์ 09:00 · ทุกวันที่ 1 เวลา 09:00"""

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
        # ข้อมูลการเงินเป็นความลับ: ถ้าไม่ได้ระบุ ALLOWED_USER_IDS จะตอบเฉพาะ CEO
        allowed = self.s.ALLOWED_USER_IDS or ([self.s.CEO_USER_ID] if self.s.CEO_USER_ID else [])
        if allowed and user_id not in allowed:
            return None
        if low in ("/report", "รายงาน", "สรุปสัปดาห์"):
            return self.report("this_week", "รายงานบัญชีสัปดาห์นี้")
        if low in ("สรุปวันนี้", "/today"):
            return self.report("today", "สรุปวันนี้", with_comment=False)
        if low in ("สรุปเดือนนี้", "/month"):
            return self.report("this_month", "สรุปเดือนนี้")
        if low in ("เป้า", "เป้าหมาย", "/goal"):
            return self.report("this_month", "ความคืบหน้าเทียบเป้า", with_comment=False)
        if low in ("help", "/help", "วิธีใช้", "คำสั่ง"):
            return HELP
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
                            on_date=a.get("date") or None, channel=a.get("channel", ""))
            ch = f" ช่องทาง {e.channel}" if e.channel else ""
            return f"บันทึกแล้ว #{e.id}: {KINDS[e.kind]} {e.category}{ch} {baht(e.amount)} วันที่ {e.date}"

        def get_goals(a):
            month = a.get("month") or today(self.s.TIMEZONE).strftime("%Y-%m")
            return json.dumps({"month": month, "goal": L.goal_for(month), "channels": L.channels(),
                               "saving_goal_total": L.get_setting(SET_SAVING_GOAL, "0")}, ensure_ascii=False)

        def set_goal(a):
            need_ceo()
            month = (a.get("month") or "").strip() or None
            L.set_goal(month, a["income"], a["profit"], a["saving"])
            if a.get("saving_total") is not None:
                L.set_setting(SET_SAVING_GOAL, float(a["saving_total"]))
            return (f"ตั้งเป้า{' เดือน ' + month if month else 'ค่าเริ่มต้นทุกเดือน'} แล้ว: รายรับ {baht(a['income'])} "
                    f"กำไร {baht(a['profit'])} เงินเก็บ {baht(a['saving'])}")

        def set_channel_target(a):
            need_ceo()
            L.set_channel(a["name"], a["target"])
            return f"ช่องทาง {a['name']} เป้า {baht(a['target'])}/เดือน แล้ว"

        def get_summary(a):
            start, end = period_range(a["period"], self.s.TIMEZONE)
            return json.dumps(L.summary(start, end), ensure_ascii=False)

        def set_budget(a):
            need_ceo()
            L.set_budget(a["category"], a["monthly_limit"])
            return f"ตั้งงบ {a['category']} = {baht(a['monthly_limit'])}/เดือน แล้ว"

        def set_debt(a):
            need_ceo()
            L.set_setting(SET_DEBT, float(a["amount"]))
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
            "get_goals": get_goals,
            "set_goal": set_goal,
            "set_channel_target": set_channel_target,
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
                               f"นี่คือ{title} เขียนถึง CEO ไม่เกิน 6 บรรทัด: "
                               "1) สถานะเทียบเป้า (ทัน/ช้ากว่าแผนเท่าไร) "
                               "2) งานสำคัญ 3 อย่างที่ควรทำในช่วงถัดไปเพื่อให้ถึงเป้า (เจาะจง ทำได้ทันที) "
                               "3) เรื่องเงินที่ต้องระวัง ใช้ตัวเลขจากข้อมูลนี้เท่านั้น:\n"
                               + json.dumps(s, ensure_ascii=False)}])
                if comment:
                    text += "\n\nความเห็นและงานถัดไปจาก Yuki:\n" + comment
            except Exception:
                pass  # รายงานตัวเลขยังส่งได้ แม้ AI ล่ม
        return text
