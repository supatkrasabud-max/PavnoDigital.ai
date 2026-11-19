"""พนักงาน AI 2 คนที่ทำงานตามเวลา

1) Affiliate Researcher (ทุกเช้า 06:00)
   ค้นสินค้าขายดี Shopee / TikTok Shop → ให้คะแนน 25 → เขียนมุมคลิป ฮุก บท แคปชัน เวลาโพสต์
   → ลงแท็บ Pipeline_Affiliate แล้วส่งเข้า LINE
2) Sales Agent (จันทร์–ศุกร์ 06:30 และสรุป 17:00)
   หาลีด SME จากแหล่งสาธารณะ → ร่างข้อความเฉพาะราย → รอ CEO อนุมัติ (บอทไม่ส่งหาลูกค้าเอง)

คะแนนและเกณฑ์ผ่านคำนวณด้วยโค้ด ไม่ปล่อยให้ AI ตัดสินเอง
"""
from __future__ import annotations

import json
import re
from datetime import timedelta

from .ledger import Ledger, num, today
from .llm import extract_json, research

# ---------------------------------------------------------------- เกณฑ์ Affiliate
PASS_SCORE = 17
MIN_COMMISSION_BAHT = 15
MIN_COMMISSION_PCT = 8
MIN_RATING = 4.5
POST_WINDOW = "19:00–22:00"
DISCLOSURE = "#ค่าคอม #Ad"
WEEK_TARGET = {"affiliate_proposed": 20, "affiliate_picked": 5, "affiliate_scripts": 5,
               "sales_leads": 30, "sales_drafts": 15}

AFF_PASS = "ผ่าน"
AFF_CHECK = "รอเช็กค่าคอม"   # คะแนนถึงแต่ยังไม่รู้ค่าคอม/รีวิวจริง → CEO เช็กในแอป Affiliate
AFF_FAIL = "ไม่ผ่าน"
AFF_DONE = "ทำคลิปแล้ว"

LEAD_NEW = "ลีดใหม่"
LEAD_WAIT = "รออนุมัติ"
LEAD_OK = "อนุมัติแล้ว รอส่ง"
LEAD_SENT = "ส่งแล้ว"
LEAD_REPLY = "ลูกค้าตอบกลับ"
LEAD_NO = "ไม่ส่ง"
LEAD_INBOUND = "ทักเข้ามาเอง"


def parse_commission(text, price: float) -> tuple[float | None, float | None]:
    """"12%" / "25 บาท" / "12% (30 บาท)" → (บาท, %) ค่าที่ไม่รู้เป็น None"""
    s = str(text or "").replace(",", "")
    pct = re.search(r"(\d+(?:\.\d+)?)\s*%", s)
    baht = re.search(r"(\d+(?:\.\d+)?)\s*(?:บาท|฿|thb)", s, re.I)
    p = float(pct.group(1)) if pct else None
    b = float(baht.group(1)) if baht else None
    if b is None and p is not None and price:
        b = round(price * p / 100, 2)
    if p is None and b is not None and price:
        p = round(b / price * 100, 2)
    return b, p


def score_product(c: dict) -> dict:
    """ให้คะแนน 5 ข้อ ข้อละ 0–5 รวม 25 และตัดสินสถานะ
    ข้อที่มีตัวเลขจริง (ค่าคอม รีวิว ราคา) คำนวณด้วยสูตร ส่วนกำลังขายและความเหมาะกับคลิปใช้คะแนนจาก AI"""
    price = num(c.get("price"))
    rating = num(c.get("rating")) or None
    baht, pct = parse_commission(c.get("commission"), price)

    def clamp(x):
        return max(0, min(5, int(round(num(x)))))

    s_demand = clamp(c.get("s_demand"))
    s_clip = clamp(c.get("s_clip"))
    if baht is None and pct is None:
        s_comm = clamp(c.get("s_commission")) or 3   # ยังไม่รู้ ให้กลาง ๆ แล้วรอเช็ก
    elif (baht or 0) >= 50 or (pct or 0) >= 15:
        s_comm = 5
    elif (baht or 0) >= 30 or (pct or 0) >= 12:
        s_comm = 4
    elif (baht or 0) >= MIN_COMMISSION_BAHT or (pct or 0) >= MIN_COMMISSION_PCT:
        s_comm = 3
    else:
        s_comm = 1
    if rating is None:
        s_rating = clamp(c.get("s_rating")) or 3
    else:
        s_rating = 5 if rating >= 4.8 else 4 if rating >= 4.6 else 3 if rating >= MIN_RATING else 1
    if not price:
        s_price = 3
    elif 150 <= price <= 800:
        s_price = 5
    elif 100 <= price <= 1500:
        s_price = 3
    else:
        s_price = 1
    total = s_demand + s_comm + s_rating + s_clip + s_price

    comm_known = baht is not None or pct is not None
    comm_ok = (baht or 0) >= MIN_COMMISSION_BAHT or (pct or 0) >= MIN_COMMISSION_PCT
    rating_ok = rating is not None and rating >= MIN_RATING
    reasons = []
    if comm_known and not comm_ok:
        reasons.append(f"ค่าคอมต่ำกว่า {MIN_COMMISSION_BAHT} บาท/{MIN_COMMISSION_PCT}%")
    if rating is not None and not rating_ok:
        reasons.append(f"รีวิวต่ำกว่า {MIN_RATING}")
    if s_clip < 3:
        reasons.append("ไม่เหมาะกับคลิปสั้น")
    if total < PASS_SCORE:
        reasons.append(f"คะแนน {total}/25 ต่ำกว่า {PASS_SCORE}")
    if reasons:
        status = AFF_FAIL
    elif comm_known and rating_ok:
        status = AFF_PASS
    else:
        status = AFF_CHECK
    return {"s_demand": s_demand, "s_commission": s_comm, "s_rating": s_rating, "s_clip": s_clip,
            "s_price": s_price, "total": total, "status": status, "reasons": reasons,
            "commission": (f"{pct:g}%" if pct is not None else "") + (f" ({baht:g} บาท)" if baht is not None else "")
            if comm_known else str(c.get("commission") or "")}


def with_disclosure(caption: str) -> str:
    caption = (caption or "").strip()
    missing = [t for t in ("#ค่าคอม", "#Ad") if t.lower() not in caption.lower()]
    return (caption + " " + " ".join(missing)).strip() if missing else caption


# ---------------------------------------------------------------- prompts
AFF_SYSTEM = f"""คุณคือ Affiliate Researcher ของ PAVNO DIGITAL หาสินค้าใน Shopee และ TikTok Shop ประเทศไทย
ที่กำลังขายดีและเหมาะทำคลิปสั้นรีวิวเพื่อรับค่าคอม
กติกา:
- ค้นจากหน้าเว็บสาธารณะเท่านั้น (บทความ ข่าวโปรโมชัน หน้าเทรนด์ หน้าสินค้าที่เปิดดูได้โดยไม่ต้องล็อกอิน)
- ห้ามแต่งตัวเลข: ราคา รีวิว ยอดขาย ค่าคอม ถ้าไม่เจอจากแหล่งจริงให้เว้นว่าง "" (ระบบจะให้ CEO เช็กในแอปเอง)
- ใส่ลิงก์แหล่งที่มาที่ใช้จริงในช่อง source
- ห้ามสินค้าที่ผิดกฎหมาย อาหารเสริม/ยา/เครื่องสำอางที่อ้างสรรพคุณเกินจริง สินค้าลอกแบรนด์ และสินค้าผู้ใหญ่
- บทต้องพูดจากการใช้จริงหรือโชว์สินค้าจริง ห้ามเขียนรีวิวปลอม ห้ามอ้างผลที่วัดไม่ได้
- เวลาโพสต์อยู่ในช่วง {POST_WINDOW} (ช่วงทดสอบ)
- แคปชันต้องมี {DISCLOSURE} เสมอ"""

AFF_PROMPT = """วันนี้ {date} หาสินค้าใหม่ {n} รายการ (ไม่ซ้ำกับรายการเหล่านี้: {recent})
แล้วตอบเป็น JSON array เท่านั้นในบล็อก ```json โดยแต่ละรายการมีช่อง:
platform ("Shopee" หรือ "TikTok Shop"), product, url, price (ตัวเลขบาท หรือ ""), commission (เช่น "10%" หรือ ""),
rating (เช่น 4.8 หรือ ""), s_demand (0–5 กำลังขายแค่ไหน), s_clip (0–5 โชว์ผลในคลิปสั้นได้ชัดแค่ไหน),
s_commission (0–5 เดาจากหมวดสินค้า ใช้เมื่อไม่รู้ค่าคอม), s_rating (0–5 ใช้เมื่อไม่รู้คะแนนรีวิว),
angle (มุมคลิป 1 บรรทัด), hook (ประโยค 3 วินาทีแรก), script (บท 15–30 วินาที แบ่งช็อต),
caption (แคปชันพร้อม #ค่าคอม #Ad), post_time (เช่น "20:30"), source (ลิงก์แหล่งข้อมูล), note"""

SALES_SYSTEM = """คุณคือ Sales Agent ของ PAVNO DIGITAL หาลูกค้าธุรกิจ (SME) ในไทยสำหรับ 3 ข้อเสนอ:
1) PAVNO Learn: สมุดฝึกอ่านเขียน ก-ฮ ABC คณิต สำหรับเด็ก (เหมาะกับโรงเรียนอนุบาล ศูนย์รับเลี้ยงเด็ก สถาบันกวดวิชา ร้านหนังสือ)
2) บริการ IT: ดูแลคอมพิวเตอร์ เครือข่าย เว็บไซต์ (เหมาะกับออฟฟิศเล็ก คลินิก ร้านค้า)
3) ติดตั้งพนักงาน AI บน LINE OA: ตอบลูกค้า รับออเดอร์ สรุปยอดอัตโนมัติ (เหมาะกับร้านอาหาร คลินิก ร้านค้าออนไลน์)
กติกา (PDPA และความน่าเชื่อถือ):
- เก็บเฉพาะข้อมูล "ธุรกิจ" ที่เปิดเผยต่อสาธารณะ: ชื่อกิจการ ประเภท พื้นที่ และช่องทางติดต่อของกิจการ (เว็บ เพจ LINE OA เบอร์ร้าน)
- ห้ามเก็บข้อมูลส่วนตัวของบุคคล เช่น เบอร์มือถือส่วนตัว อีเมลส่วนตัว ที่อยู่บ้าน
- ใส่ลิงก์แหล่งที่มาจริงทุกราย ห้ามแต่งชื่อธุรกิจหรือช่องทางติดต่อ
- ร่างข้อความสุภาพ สั้น (ไม่เกิน 6 บรรทัด) อ้างถึงสิ่งที่เห็นจริงของกิจการนั้น บอกประโยชน์ 1 ข้อ ชวนคุยต่อ 1 คำถาม
  และปิดท้ายด้วย "หากไม่สะดวกรับข้อมูล แจ้งได้เลยครับ จะไม่ติดต่ออีก"
- ห้ามสัญญาผลลัพธ์ที่วัดไม่ได้ ห้ามอ้างว่าเคยคุยกันมาก่อน"""

SALES_PROMPT = """วันนี้ {date} หาลีดใหม่ {n} ราย (ไม่ซ้ำกับ: {recent}) เน้นพื้นที่ {area}
ให้คะแนนความเหมาะสม 0–10 แล้วเขียนร่างข้อความให้ {d} รายที่คะแนนสูงสุด (รายอื่นเว้น draft เป็น "")
ตอบเป็น JSON array เท่านั้นในบล็อก ```json แต่ละรายมีช่อง:
business, type, area, contact (ช่องทางของกิจการที่เปิดเผย), source (ลิงก์), offer ("PAVNO Learn" / "บริการ IT" / "พนักงาน AI LINE"),
score (0–10), reason (ทำไมเหมาะ 1 บรรทัด), draft, next_step"""


class Pipelines:
    def __init__(self, client, ledger: Ledger, settings):
        self.client = client
        self.ledger = ledger
        self.s = settings

    def _model(self):
        return getattr(self.s, "MODEL_RESEARCH", "") or self.s.MODEL_LEAD

    def _week_start(self):
        t = today(self.s.TIMEZONE)
        return t - timedelta(days=t.weekday())

    # ------------------------------------------------------------ Affiliate
    def run_affiliate(self, n: int = 4, dry: bool = False) -> str:
        t = today(self.s.TIMEZONE)
        recent = [r["product"] for r in self.ledger.pipeline("Affiliate", t - timedelta(days=21))]
        text = research(self.client, model=self._model(), system=AFF_SYSTEM,
                        prompt=AFF_PROMPT.format(date=t.isoformat(), n=n,
                                                 recent=json.dumps(recent[-40:], ensure_ascii=False)))
        items = extract_json(text)
        if isinstance(items, dict):
            items = items.get("items") or [items]
        rows = []
        for c in items[:n]:
            sc = score_product(c)
            row = {"platform": c.get("platform", ""), "product": c.get("product", ""),
                   "url": c.get("url", ""), "price": c.get("price", ""), "rating": c.get("rating", ""),
                   "commission": sc["commission"], "s_demand": sc["s_demand"],
                   "s_commission": sc["s_commission"], "s_rating": sc["s_rating"], "s_clip": sc["s_clip"],
                   "s_price": sc["s_price"], "total": sc["total"], "status": sc["status"],
                   "angle": c.get("angle", ""), "hook": c.get("hook", ""), "script": c.get("script", ""),
                   "caption": with_disclosure(c.get("caption", "")), "post_time": c.get("post_time", ""),
                   "source": c.get("source", ""),
                   "note": "; ".join(sc["reasons"]) or str(c.get("note", ""))}
            if not dry:
                row = self.ledger.add_pipeline("Affiliate", row, "AF")
            else:
                row["id"] = "AF-TEST"
            rows.append(row)
        rows.sort(key=lambda r: -num(r["total"]))
        return format_affiliate(rows, t.isoformat(), self.week_progress())

    # ------------------------------------------------------------ Sales
    def run_sales(self, n: int = 6, drafts: int = 3, dry: bool = False) -> str:
        t = today(self.s.TIMEZONE)
        recent = [r["business"] for r in self.ledger.pipeline("Sales", t - timedelta(days=90))]
        area = getattr(self.s, "SALES_AREA", "") or "กรุงเทพฯ และปริมณฑล"
        text = research(self.client, model=self._model(), system=SALES_SYSTEM, max_searches=8,
                        prompt=SALES_PROMPT.format(date=t.isoformat(), n=n, d=drafts, area=area,
                                                   recent=json.dumps(recent[-80:], ensure_ascii=False)))
        items = extract_json(text)
        if isinstance(items, dict):
            items = items.get("items") or [items]
        rows = []
        for c in items[:n]:
            if not c.get("business") or not c.get("source"):
                continue  # ไม่มีแหล่งที่มา ไม่บันทึก
            row = {k: c.get(k, "") for k in ("business", "type", "area", "contact", "source", "offer",
                                             "score", "reason", "draft", "next_step")}
            row["status"] = LEAD_WAIT if str(row["draft"]).strip() else LEAD_NEW
            row["updated"] = t.isoformat()
            if not dry:
                row = self.ledger.add_pipeline("Sales", row, "S")
            else:
                row["id"] = "S-TEST"
            rows.append(row)
        return format_sales(rows, t.isoformat())

    def sales_summary(self) -> str:
        t = today(self.s.TIMEZONE).isoformat()
        rows = self.ledger.pipeline("Sales")
        today_rows = [r for r in rows if str(r["date"])[:10] == t]
        waiting = [r for r in rows if r["status"] == LEAD_WAIT]
        to_send = [r for r in rows if r["status"] == LEAD_OK]
        replies = [r for r in rows if r["status"] in (LEAD_REPLY, LEAD_INBOUND) and str(r.get("updated"))[:10] == t]
        lines = [f"💼 สรุปงานขาย {t}",
                 f"ลีดใหม่วันนี้: {len(today_rows)} ราย",
                 f"รอ CEO อนุมัติ: {len(waiting)} ฉบับ" + (" → พิมพ์ \"ลีด\" เพื่อดู" if waiting else ""),
                 f"อนุมัติแล้วแต่ยังไม่ส่ง: {len(to_send)} ฉบับ",
                 f"ลูกค้าตอบ/ทักเข้ามาวันนี้: {len(replies)} ราย"]
        for r in replies:
            lines.append(f"  • {r['id']} {r['business']}: {str(r.get('reply'))[:80]}")
        lines += ["", self.week_progress()]
        return "\n".join(lines)

    def week_progress(self) -> str:
        ws = self._week_start()
        aff = self.ledger.pipeline("Affiliate", ws)
        sales = self.ledger.pipeline("Sales", ws)
        picked = [r for r in aff if r["status"] in (AFF_PASS, AFF_CHECK, AFF_DONE)]
        scripts = [r for r in picked if str(r.get("script")).strip()]
        drafts = [r for r in sales if str(r.get("draft")).strip()]
        w = WEEK_TARGET
        return ("📈 เป้าสัปดาห์นี้ (ตั้งแต่วันจันทร์)\n"
                f"  Affiliate เสนอ {len(aff)}/{w['affiliate_proposed']} · คัดผ่าน {len(picked)}/{w['affiliate_picked']}"
                f" · บท {len(scripts)}/{w['affiliate_scripts']}\n"
                f"  Sales ลีด {len(sales)}/{w['sales_leads']} · ร่างข้อความ {len(drafts)}/{w['sales_drafts']}")

    # ------------------------------------------------------------ คำสั่งจาก LINE (CEO)
    def command(self, text: str) -> str | None:
        t = text.strip()
        low = t.lower()
        L = self.ledger
        now = today(self.s.TIMEZONE).isoformat()
        if low in ("ลีด", "leads"):
            rows = [r for r in L.pipeline("Sales") if r["status"] in (LEAD_WAIT, LEAD_OK)]
            if not rows:
                return "ไม่มีร่างข้อความที่รออนุมัติ"
            return "\n\n".join(format_lead(r) for r in rows[:5]) + (
                f"\n\n(มีอีก {len(rows) - 5} ฉบับในแท็บ Pipeline_Sales)" if len(rows) > 5 else "")
        if low in ("สินค้าวันนี้", "affiliate"):
            rows = [r for r in L.pipeline("Affiliate") if str(r["date"])[:10] == now]
            return format_affiliate(rows, now, self.week_progress()) if rows else "วันนี้ยังไม่มีรายการสินค้า"
        m = re.match(r"^(อนุมัติลีด|ไม่อนุมัติลีด|ส่งแล้ว)\s+(S[0-9A-F]{4})\s*$", t, re.I)
        if m:
            status = {"อนุมัติลีด": LEAD_OK, "ไม่อนุมัติลีด": LEAD_NO, "ส่งแล้ว": LEAD_SENT}[m.group(1)]
            r = L.update_pipeline("Sales", m.group(2), status=status, updated=now)
            if status == LEAD_OK:
                return (f"อนุมัติ {r['id']} แล้ว คัดลอกข้อความนี้ไปส่งเองทาง {r['contact'] or 'ช่องทางของร้าน'}\n"
                        f"ส่งเสร็จพิมพ์ \"ส่งแล้ว {r['id']}\"\n\n{r['draft']}")
            return f"{r['id']} {r['business']}: {status}"
        m = re.match(r"^ตอบกลับ\s+(S[0-9A-F]{4})\s+(.+)$", t, re.I | re.S)
        if m:
            r = L.update_pipeline("Sales", m.group(1), status=LEAD_REPLY, reply=m.group(2).strip(), updated=now)
            return f"🔔 บันทึกแล้ว {r['id']} {r['business']} ตอบกลับ: {r['reply']}\nขั้นต่อไป: {r.get('next_step') or 'นัดคุย/ส่งรายละเอียด'}"
        m = re.match(r"^ค่าคอม\s+(AF[0-9A-F]{4})\s+(.+)$", t, re.I)
        if m:
            rows = [r for r in L.pipeline("Affiliate") if str(r["id"]).upper() == m.group(1).upper()]
            if not rows:
                return f"ไม่พบ {m.group(1)}"
            r = rows[0]
            # ใส่รีวิวมาด้วยได้ เช่น "ค่าคอม AF12 10% รีวิว 4.8"
            rv = re.search(r"รีวิว\s*(\d(?:\.\d+)?)", m.group(2))
            sc = score_product({**r, "commission": m.group(2), "rating": rv.group(1) if rv else r.get("rating")})
            r = L.update_pipeline("Affiliate", r["id"], commission=sc["commission"],
                                  rating=rv.group(1) if rv else r.get("rating"),
                                  s_commission=sc["s_commission"], s_rating=sc["s_rating"],
                                  total=sc["total"], status=sc["status"], note="; ".join(sc["reasons"]))
            return f"{r['id']} {r['product']}: ค่าคอม {r['commission']} คะแนน {r['total']}/25 → {r['status']}"
        m = re.match(r"^ถ่ายแล้ว\s+(AF[0-9A-F]{4})\s*$", t, re.I)
        if m:
            r = L.update_pipeline("Affiliate", m.group(1), status=AFF_DONE)
            return f"{r['id']} {r['product']}: {AFF_DONE} อย่าลืมใส่ {DISCLOSURE} ในแคปชันนะคะ"
        return None

    def inbound(self, user_id: str, text: str) -> dict:
        """คนนอกทักเข้า LINE OA → บันทึกเป็นลีด (แจ้ง CEO ทันทีที่ main.py)"""
        now = today(self.s.TIMEZONE).isoformat()
        return self.ledger.add_pipeline("Sales", {
            "business": "ผู้ติดต่อทาง LINE OA", "contact": f"LINE userId {user_id}", "source": "LINE OA",
            "status": LEAD_INBOUND, "updated": now, "reply": text[:500], "next_step": "CEO ตอบกลับใน LINE OA Manager"}, "S")


# ---------------------------------------------------------------- ข้อความ LINE
def format_affiliate(rows: list[dict], day: str, progress: str) -> str:
    good = [r for r in rows if r["status"] in (AFF_PASS, AFF_CHECK)]
    lines = [f"🛒 Affiliate วันนี้ {day}: เสนอ {len(rows)} · ผ่านเกณฑ์ {len(good)}",
             f"เกณฑ์: {PASS_SCORE}/25 ขึ้นไป · ค่าคอม ≥{MIN_COMMISSION_BAHT} บาทหรือ ≥{MIN_COMMISSION_PCT}% · รีวิว ≥{MIN_RATING}"]
    for r in good:
        lines += ["", f"[{r['id']}] {r['product']} ({r['platform']}) {r['total']}/25 · {r['status']}",
                  f"ราคา {r['price'] or '-'} · ค่าคอม {r['commission'] or 'ยังไม่รู้'} · รีวิว {r['rating'] or '-'}",
                  f"มุมคลิป: {r['angle']}", f"ฮุก 3 วิ: {r['hook']}", f"บท: {r['script']}",
                  f"แคปชัน: {r['caption']}", f"โพสต์: {r['post_time'] or POST_WINDOW}", f"ลิงก์: {r['url'] or r['source']}"]
        if r["status"] == AFF_CHECK:
            lines.append(f"→ เช็กในแอป Affiliate แล้วพิมพ์ \"ค่าคอม {r['id']} 10% รีวิว 4.8\"")
    fails = [r for r in rows if r["status"] == AFF_FAIL]
    if fails:
        lines += ["", "ไม่ผ่าน: " + ", ".join(f"{r['product']} ({r['note']})" for r in fails)]
    lines += ["", f"ถ่ายเสร็จพิมพ์ \"ถ่ายแล้ว <รหัส>\" · ทุกคลิปต้องมี {DISCLOSURE}", progress]
    return "\n".join(lines)


def format_lead(r: dict) -> str:
    return (f"[{r['id']}] {r['business']} ({r['type']}, {r['area']}) · {r['offer']} · {r['score']}/10\n"
            f"ติดต่อ: {r['contact']} · ที่มา: {r['source']}\n"
            f"ร่าง:\n{r['draft']}\n"
            f"→ \"อนุมัติลีด {r['id']}\" หรือ \"ไม่อนุมัติลีด {r['id']}\"")


def format_sales(rows: list[dict], day: str) -> str:
    drafts = [r for r in rows if r["status"] == LEAD_WAIT]
    lines = [f"💼 Sales Agent {day}: ลีดใหม่ {len(rows)} ราย · ร่างข้อความ {len(drafts)} ฉบับ (รอ CEO อนุมัติ)",
             "บอทไม่ส่งหาลูกค้าเอง CEO อนุมัติแล้วคัดลอกไปส่งเอง"]
    for r in drafts:
        lines += ["", format_lead(r)]
    others = [r for r in rows if r["status"] != LEAD_WAIT]
    if others:
        lines += ["", "ลีดอื่น (ยังไม่ร่าง): " + ", ".join(f"{r['business']} ({r['score']}/10)" for r in others)]
    return "\n".join(lines)
