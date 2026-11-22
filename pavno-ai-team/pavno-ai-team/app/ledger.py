"""สมุดบัญชีของ Yuki

ใช้ Google Sheet "PAVNO บัญชี" ชุดเดียวกับเว็บแอป Yuki Ledger (finance/yuki-ledger)
โค้ดภายในใช้ชื่อคอลัมน์ภาษาอังกฤษ แล้วแปลงเป็นชื่อแท็บ/คอลัมน์ภาษาไทยตอนอ่าน-เขียนชีต

  แท็บ           ใช้ทำอะไร
  รายการ         รายรับ รายจ่าย ลงทุน เงินเก็บ เงินทุน CEO ชำระหนี้ (ทุกรายการ)
  งบรายเดือน     วงเงินต่อเดือนแต่ละหมวด
  เป้าหมาย       เป้ารายรับ/กำไร/เงินเก็บ (แถว "ค่าเริ่มต้น" หรือ yyyy-MM)
  ช่องทาง        ช่องทางรายได้ + เป้ารายรับต่อเดือน
  ตั้งค่า        ค่าอื่น ๆ เช่น ยอดหนี้เริ่มต้น เป้าเงินเก็บสะสม
  คำขออนุมัติ    คำขอใช้เงินที่รอ CEO อนุมัติ

มี 2 แบบ: Google Sheets (ใช้งานจริง) และ CSV (ทดสอบในเครื่อง)
"""
from __future__ import annotations

import csv
import json
import os
import threading
import uuid
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

# kind ภายใน -> ประเภทในชีต (ตรงกับเว็บแอป)
KINDS = {
    "income": "รายรับ",
    "expense": "รายจ่าย",
    "invest": "ลงทุน",
    "saving": "เงินเก็บ",
    "capital": "เงินทุน CEO",
    "debt_payment": "ชำระหนี้",
}
KIND_FROM_TH = {v: k for k, v in KINDS.items()}

DEFAULT_GOAL_KEY = "ค่าเริ่มต้น"
SET_DEBT = "ยอดหนี้เริ่มต้น"
SET_SAVING_GOAL = "เป้าเงินเก็บสะสมของบริษัท"

# ชื่อแท็บจริง + (คีย์ภายใน, หัวคอลัมน์ในชีต)
SHEETS: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "Ledger": ("รายการ", [
        ("id", "ID"), ("date", "วันที่"), ("kind", "ประเภท"), ("channel", "ช่องทาง"),
        ("category", "หมวด"), ("amount", "จำนวนเงิน"), ("pay", "ชำระด้วย"), ("note", "หมายเหตุ"),
        ("created", "บันทึกเมื่อ"), ("recorded_by", "บันทึกโดย"), ("ref", "อ้างอิง")]),
    "Budget": ("งบรายเดือน", [("category", "หมวด"), ("monthly_limit", "งบต่อเดือน (บาท)")]),
    "Goals": ("เป้าหมาย", [("month", "เดือน (yyyy-MM หรือ ค่าเริ่มต้น)"), ("income", "เป้ารายรับ"),
                           ("profit", "เป้ากำไร"), ("saving", "เป้าเงินเก็บ")]),
    "Channels": ("ช่องทาง", [("name", "ช่องทาง"), ("target", "เป้ารายรับต่อเดือน (บาท)")]),
    "Settings": ("ตั้งค่า", [("key", "ตั้งค่า"), ("value", "ค่า")]),
    "Approvals": ("คำขออนุมัติ", [
        ("id", "รหัส"), ("created", "วันที่ขอ"), ("category", "หมวด"), ("amount", "จำนวนเงิน"),
        ("reason", "เหตุผล"), ("requested_by", "ผู้ขอ"), ("status", "สถานะ"), ("decided", "วันที่ตัดสิน")]),
    # พนักงานคนที่ 1: Affiliate Researcher (คะแนน 5 ข้อ ข้อละ 0–5 รวม 25 ผ่านที่ 17)
    "Affiliate": ("Pipeline_Affiliate", [
        ("id", "รหัส"), ("date", "วันที่"), ("platform", "แพลตฟอร์ม"), ("product", "สินค้า"),
        ("url", "ลิงก์"), ("price", "ราคา (บาท)"), ("commission", "ค่าคอม"), ("rating", "รีวิว"),
        ("s_demand", "คะแนน กำลังขาย"), ("s_commission", "คะแนน ค่าคอม"), ("s_rating", "คะแนน รีวิว"),
        ("s_clip", "คะแนน เหมาะกับคลิป"), ("s_price", "คะแนน ราคา"), ("total", "รวม /25"),
        ("status", "สถานะ"), ("angle", "มุมคลิป"), ("hook", "ฮุก 3 วินาที"), ("script", "บท"),
        ("caption", "แคปชัน"), ("post_time", "เวลาโพสต์"), ("source", "แหล่งข้อมูล"), ("note", "หมายเหตุ")]),
    # พนักงานคนที่ 2: Sales Agent (ทุกข้อความต้องให้ CEO อนุมัติก่อนส่ง)
    "Sales": ("Pipeline_Sales", [
        ("id", "รหัส"), ("date", "วันที่"), ("business", "ธุรกิจ"), ("type", "ประเภทธุรกิจ"),
        ("area", "พื้นที่"), ("contact", "ช่องทางติดต่อสาธารณะ"), ("source", "แหล่งข้อมูล"),
        ("offer", "ข้อเสนอ"), ("score", "คะแนน /10"), ("reason", "เหตุผล"), ("draft", "ร่างข้อความ"),
        ("status", "สถานะ"), ("updated", "อัปเดตล่าสุด"), ("reply", "ลูกค้าตอบ"), ("next_step", "ขั้นต่อไป")]),
    # โพสต์เพจ Facebook: Ami ส่งร่างให้ CEO อนุมัติใน LINE แล้วตั้งเวลาโพสต์ผ่าน Graph API (app/facebook.py)
    "Facebook": ("โพสต์_Facebook", [
        ("id", "รหัส"), ("date", "วันที่โพสต์"), ("time", "เวลา"), ("product", "สินค้า"), ("title", "หัวข้อ"),
        ("text", "ข้อความ"), ("images", "รูป (บรรทัดละ 1 ลิงก์)"), ("status", "สถานะ"),
        ("fb_id", "รหัสโพสต์ Facebook"), ("updated", "อัปเดตล่าสุด"), ("note", "หมายเหตุ")]),
}

DEFAULT_BUDGET = {
    "ค่าโฆษณา": 3000,
    "ซอฟต์แวร์และ AI": 1500,
    "ซื้อสินค้ามารีวิว": 1500,
    "อุปกรณ์": 500,
    "ค่าธรรมเนียมแพลตฟอร์ม": 500,
    "รายจ่ายอื่น": 1000,
}
DEFAULT_CHANNELS = {"เว็บ PAVNO": 5000, "Etsy": 0, "Shopee": 10000, "TikTok": 5000,
                    "Facebook": 0, "บริการ IT": 0, "ทั่วไป": 0}


def today(tz: str = "Asia/Bangkok") -> date:
    return datetime.now(ZoneInfo(tz)).date()


def num(x) -> float:
    """แปลงค่าจากชีตเป็นตัวเลข (รองรับ "1,200.00" และค่าว่าง)"""
    if x in (None, ""):
        return 0.0
    try:
        return float(str(x).replace(",", ""))
    except ValueError:
        return 0.0


@dataclass
class Entry:
    date: str
    kind: str
    category: str
    amount: float
    note: str = ""
    recorded_by: str = "Yuki"
    ref: str = ""
    channel: str = ""
    pay: str = ""
    created: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


# --------------------------------------------------------------------------- backends

class _Backend:
    """อ่าน/เขียนแถวในแต่ละแท็บ (คีย์ภายใน) โดยแปลงเป็นแท็บ/คอลัมน์ภาษาไทยให้"""

    def _raw_rows(self, phys: str, headers: list[str]) -> list[list]:
        raise NotImplementedError

    def _raw_append(self, phys: str, values: list) -> None:
        raise NotImplementedError

    def _raw_overwrite(self, phys: str, headers: list[str], rows: list[list]) -> None:
        raise NotImplementedError

    @staticmethod
    def _to_cell(sheet: str, key: str, value):
        if sheet == "Ledger" and key == "kind":
            return KINDS.get(value, value)
        return value

    @staticmethod
    def _from_cell(sheet: str, key: str, value):
        if sheet == "Ledger" and key == "kind":
            return KIND_FROM_TH.get(str(value), str(value))
        return value

    def rows(self, sheet: str) -> list[dict]:
        phys, cols = SHEETS[sheet]
        out = []
        for raw in self._raw_rows(phys, [h for _, h in cols]):
            if not raw or all(v in ("", None) for v in raw):
                continue
            raw = list(raw) + [""] * (len(cols) - len(raw))
            out.append({k: self._from_cell(sheet, k, raw[i]) for i, (k, _) in enumerate(cols)})
        return out

    def append(self, sheet: str, row: dict) -> None:
        phys, cols = SHEETS[sheet]
        self._raw_append(phys, [self._to_cell(sheet, k, row.get(k, "")) for k, _ in cols])

    def overwrite(self, sheet: str, rows: list[dict]) -> None:
        phys, cols = SHEETS[sheet]
        self._raw_overwrite(phys, [h for _, h in cols],
                            [[self._to_cell(sheet, k, r.get(k, "")) for k, _ in cols] for r in rows])


class CsvBackend(_Backend):
    def __init__(self, folder: str):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)
        self._lock = threading.Lock()
        for phys, cols in SHEETS.values():
            path = self._path(phys)
            if not os.path.exists(path):
                with open(path, "w", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow([h for _, h in cols])

    def _path(self, phys: str) -> str:
        return os.path.join(self.folder, f"{phys}.csv")

    def _raw_rows(self, phys, headers):
        with self._lock, open(self._path(phys), newline="", encoding="utf-8") as f:
            return list(csv.reader(f))[1:]

    def _raw_append(self, phys, values):
        with self._lock, open(self._path(phys), "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(values)

    def _raw_overwrite(self, phys, headers, rows):
        with self._lock, open(self._path(phys), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(headers)
            w.writerows(rows)


class SheetsBackend(_Backend):
    """Google Sheets ผ่าน service account (pip install gspread google-auth)
    แชร์ชีต "PAVNO บัญชี" ให้อีเมล service account เป็น Editor ก่อนใช้งาน"""

    def __init__(self, sheet_id: str, service_account_json: str):
        import gspread  # noqa: import เฉพาะตอนใช้งานจริง
        info = json.loads(service_account_json)
        gc = gspread.service_account_from_dict(info)
        self.book = gc.open_by_key(sheet_id)
        existing = {ws.title for ws in self.book.worksheets()}
        for phys, cols in SHEETS.values():
            if phys not in existing:  # แท็บที่เว็บแอปยังไม่ได้สร้าง (เช่น คำขออนุมัติ)
                ws = self.book.add_worksheet(title=phys, rows=1000, cols=len(cols))
                ws.append_row([h for _, h in cols])

    def _ws(self, phys: str):
        return self.book.worksheet(phys)

    def _raw_rows(self, phys, headers):
        values = self._ws(phys).get_all_values(value_render_option="UNFORMATTED_VALUE",
                                               date_time_render_option="FORMATTED_STRING")
        return values[1:]

    def _raw_append(self, phys, values):
        self._ws(phys).append_row(values, value_input_option="USER_ENTERED")

    def _raw_overwrite(self, phys, headers, rows):
        ws = self._ws(phys)
        ws.batch_clear([f"A2:{chr(64 + len(headers))}{max(ws.row_count, 2)}"])
        if rows:
            ws.update(range_name="A2", values=rows, value_input_option="USER_ENTERED")


# --------------------------------------------------------------------------- ledger

class Ledger:
    def __init__(self, backend: _Backend, tz: str = "Asia/Bangkok"):
        self.b = backend
        self.tz = tz
        if not self.b.rows("Budget"):
            for cat, limit in DEFAULT_BUDGET.items():
                self.b.append("Budget", {"category": cat, "monthly_limit": limit})
        if not self.b.rows("Channels"):
            for name, target in DEFAULT_CHANNELS.items():
                self.b.append("Channels", {"name": name, "target": target})

    # ---- รายการบัญชี
    def add_entry(self, kind: str, category: str, amount: float, note: str = "",
                  recorded_by: str = "Yuki", on_date: str | None = None, ref: str = "",
                  channel: str = "") -> Entry:
        if kind not in KINDS:
            raise ValueError(f"kind ต้องเป็นหนึ่งใน {list(KINDS)}")
        amount = round(float(amount), 2)
        if amount <= 0:
            raise ValueError("จำนวนเงินต้องมากกว่า 0")
        if ref and any(str(r.get("ref")) == ref for r in self.b.rows("Ledger")):
            raise ValueError(f"รายการอ้างอิง {ref} ถูกบันทึกไปแล้ว")
        now = datetime.now(ZoneInfo(self.tz))
        e = Entry(date=on_date or now.date().isoformat(), kind=kind,
                  category=(category or "อื่น ๆ").strip(), amount=amount, note=note,
                  recorded_by=recorded_by, ref=ref, channel=(channel or "").strip(),
                  pay="หักจากแพลตฟอร์ม" if recorded_by == "Stripe" else "",
                  created=now.strftime("%Y-%m-%d %H:%M"))
        self.b.append("Ledger", asdict(e))
        return e

    def entries(self, start: date | None = None, end: date | None = None) -> list[dict]:
        out = []
        for r in self.b.rows("Ledger"):
            try:
                d = date.fromisoformat(str(r["date"])[:10])
            except (ValueError, KeyError):
                continue
            r = {**r, "date": d.isoformat(), "amount": num(r.get("amount"))}
            if start and d < start:
                continue
            if end and d > end:
                continue
            out.append(r)
        return out

    # ---- งบประมาณ
    def budgets(self) -> dict[str, float]:
        return {str(r["category"]).strip(): num(r["monthly_limit"]) for r in self.b.rows("Budget") if r["category"]}

    def set_budget(self, category: str, monthly_limit: float) -> None:
        rows = [r for r in self.b.rows("Budget") if str(r["category"]).strip() != category.strip()]
        rows.append({"category": category.strip(), "monthly_limit": float(monthly_limit)})
        self.b.overwrite("Budget", rows)

    # ---- ค่าตั้งต้น
    def get_setting(self, key: str, default: str = "") -> str:
        for r in self.b.rows("Settings"):
            if r["key"] == key:
                return str(r["value"])
        return default

    def set_setting(self, key: str, value) -> None:
        rows = [r for r in self.b.rows("Settings") if r["key"] != key]
        rows.append({"key": key, "value": value})
        self.b.overwrite("Settings", rows)

    # ---- เป้าหมาย
    def goal_for(self, month: str) -> dict:
        rows = {str(r["month"]).strip(): r for r in self.b.rows("Goals")}
        r = rows.get(month)
        custom = r is not None
        r = r or rows.get(DEFAULT_GOAL_KEY) or {}
        return {"income": num(r.get("income")), "profit": num(r.get("profit")),
                "saving": num(r.get("saving")), "custom": custom}

    def set_goal(self, month: str | None, income: float, profit: float, saving: float) -> dict:
        key = month or DEFAULT_GOAL_KEY
        rows = [r for r in self.b.rows("Goals") if str(r["month"]).strip() != key]
        rows.append({"month": key, "income": float(income), "profit": float(profit), "saving": float(saving)})
        self.b.overwrite("Goals", rows)
        return rows[-1]

    def channels(self) -> dict[str, float]:
        return {str(r["name"]).strip(): num(r["target"]) for r in self.b.rows("Channels") if r["name"]}

    def set_channel(self, name: str, target: float) -> None:
        rows = [r for r in self.b.rows("Channels") if str(r["name"]).strip() != name.strip()]
        rows.append({"name": name.strip(), "target": float(target)})
        self.b.overwrite("Channels", rows)

    # ---- คำขออนุมัติ
    def request_approval(self, category: str, amount: float, reason: str, requested_by: str) -> dict:
        row = {"id": "A" + uuid.uuid4().hex[:4].upper(), "created": today(self.tz).isoformat(),
               "category": category.strip(), "amount": float(amount), "reason": reason,
               "requested_by": requested_by, "status": "pending", "decided": ""}
        self.b.append("Approvals", row)
        return row

    def pending_approvals(self) -> list[dict]:
        return [r for r in self.b.rows("Approvals") if r["status"] == "pending"]

    def decide_approval(self, approval_id: str, approve: bool) -> dict:
        rows = self.b.rows("Approvals")
        found = None
        for r in rows:
            if str(r["id"]).upper() == approval_id.upper() and r["status"] == "pending":
                r["status"] = "approved" if approve else "rejected"
                r["decided"] = today(self.tz).isoformat()
                found = r
        if not found:
            raise ValueError(f"ไม่พบคำขอ {approval_id} ที่รออนุมัติ")
        self.b.overwrite("Approvals", rows)
        return found

    # ---- Pipeline (Affiliate / Sales)
    def add_pipeline(self, sheet: str, row: dict, prefix: str) -> dict:
        row = {**row, "id": prefix + uuid.uuid4().hex[:4].upper(),
               "date": row.get("date") or today(self.tz).isoformat()}
        self.b.append(sheet, row)
        return row

    def pipeline(self, sheet: str, since: date | None = None) -> list[dict]:
        out = []
        for r in self.b.rows(sheet):
            try:
                d = date.fromisoformat(str(r.get("date"))[:10])
            except ValueError:
                continue
            if since is None or d >= since:
                out.append(r)
        return out

    def update_pipeline(self, sheet: str, row_id: str, **fields) -> dict:
        rows = self.b.rows(sheet)
        found = None
        for r in rows:
            if str(r["id"]).upper() == row_id.upper():
                r.update(fields)
                found = r
        if not found:
            raise ValueError(f"ไม่พบรหัส {row_id}")
        self.b.overwrite(sheet, rows)
        return found

    # ---- สรุป
    def summary(self, start: date, end: date) -> dict:
        month = end.strftime("%Y-%m")
        return summarize(self.entries(), self.budgets(), num(self.get_setting(SET_DEBT, "0")),
                         start, end, goal=self.goal_for(month), channel_targets=self.channels(),
                         saving_goal_total=num(self.get_setting(SET_SAVING_GOAL, "0")))


def summarize(all_entries: list[dict], budgets: dict[str, float], debt_initial: float,
              start: date, end: date, goal: dict | None = None,
              channel_targets: dict[str, float] | None = None, saving_goal_total: float = 0) -> dict:
    """คำนวณสรุปช่วงเวลา + ความคืบหน้าเทียบเป้าของเดือนที่ end อยู่ (ฟังก์ชันบริสุทธิ์)"""
    def d(e):
        return date.fromisoformat(str(e["date"])[:10])

    def total(rows, kind):
        return round(sum(float(e["amount"]) for e in rows if e["kind"] == kind), 2)

    def by(rows, kind, key):
        out: dict[str, float] = {}
        for e in rows:
            if e["kind"] == kind:
                k = str(e.get(key) or "-")
                out[k] = round(out.get(k, 0) + float(e["amount"]), 2)
        return out

    period = [e for e in all_entries if start <= d(e) <= end]
    month_start = end.replace(day=1)
    month = [e for e in all_entries if month_start <= d(e) <= end]
    upto = [e for e in all_entries if d(e) <= end]

    month_spend = by(month, "expense", "category")
    budget_status = []
    for cat in sorted(set(budgets) | set(month_spend)):
        limit = budgets.get(cat, 0.0)
        spent = round(month_spend.get(cat, 0.0), 2)
        budget_status.append({"category": cat, "limit": limit, "spent": spent, "over": spent > limit})

    # ความคืบหน้าเดือนนี้เทียบเป้า
    goal = goal or {"income": 0, "profit": 0, "saving": 0}
    m_income, m_expense = total(month, "income"), total(month, "expense")
    days_in_month = ((month_start + timedelta(days=32)).replace(day=1) - month_start).days
    elapsed = end.day / days_in_month
    progress = {
        "month": month_start.strftime("%Y-%m"),
        "day": end.day, "days_in_month": days_in_month,
        "income": m_income, "income_goal": goal["income"],
        "profit": round(m_income - m_expense, 2), "profit_goal": goal["profit"],
        "saving": total(month, "saving"), "saving_goal": goal["saving"],
        # ควรได้ถึงวันนี้ ถ้าจะทันเป้าแบบเฉลี่ยรายวัน
        "income_pace_target": round(goal["income"] * elapsed, 2),
    }
    m_channels = by(month, "income", "channel")
    channels = []
    for name in sorted(set(channel_targets or {}) | set(m_channels)):
        t = (channel_targets or {}).get(name, 0.0)
        a = m_channels.get(name, 0.0)
        if t or a:
            channels.append({"name": name, "target": t, "income": a})
    channels.sort(key=lambda c: (-c["income"], -c["target"]))

    cash = (total(upto, "capital") + total(upto, "income") - total(upto, "expense")
            - total(upto, "debt_payment") - total(upto, "invest") - total(upto, "saving"))
    debt_paid = total(upto, "debt_payment")
    monthly_budget = round(sum(budgets.values()), 2)
    income = total(period, "income")
    expense = total(period, "expense")
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "income": income,
        "income_by_category": by(period, "income", "category"),
        "income_by_channel": by(period, "income", "channel"),
        "expense": expense,
        "expense_by_category": by(period, "expense", "category"),
        "net_profit": round(income - expense, 2),
        "saving": total(period, "saving"),
        "invest": total(period, "invest"),
        "capital_in": total(period, "capital"),
        "debt_paid_in_period": total(period, "debt_payment"),
        "cash_balance": round(cash, 2),
        "saving_total": total(upto, "saving"),
        "saving_goal_total": saving_goal_total,
        "debt_initial": debt_initial,
        "debt_remaining": round(max(debt_initial - debt_paid, 0), 2),
        "monthly_budget_total": monthly_budget,
        "budget_status": budget_status,
        "suggested_top_up": round(max(monthly_budget - cash, 0), 2),
        "orders": sum(1 for e in period if e["kind"] == "income"),
        "month_progress": progress,
        "channels": channels,
    }


def period_range(name: str, tz: str = "Asia/Bangkok") -> tuple[date, date]:
    t = today(tz)
    if name == "today":
        return t, t
    if name == "yesterday":
        y = t - timedelta(days=1)
        return y, y
    if name == "this_week":
        return t - timedelta(days=t.weekday()), t
    if name == "last_week":
        end = t - timedelta(days=t.weekday() + 1)
        return end - timedelta(days=6), end
    if name == "this_month":
        return t.replace(day=1), t
    if name == "last_month":
        end = t.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    if name == "all":
        return date(2000, 1, 1), t
    raise ValueError("period ต้องเป็น today, yesterday, this_week, last_week, this_month, last_month หรือ all")


def baht(x: float) -> str:
    return f"{x:,.0f} บาท" if float(x).is_integer() else f"{x:,.2f} บาท"


def _pct(a: float, t: float) -> str:
    return f"{a / t * 100:.0f}%" if t else "-"


def _bar(a: float, t: float, width: int = 10) -> str:
    if not t:
        return ""
    n = max(0, min(width, round(a / t * width)))
    return "▓" * n + "░" * (width - n) + " "


def format_report(s: dict, title: str) -> str:
    lines = [f"📒 {title}", f"ช่วง {s['start']} ถึง {s['end']}", ""]
    lines.append(f"รายรับ: {baht(s['income'])} ({s['orders']} รายการ)")
    for c, v in sorted(s["income_by_category"].items(), key=lambda x: -x[1]):
        lines.append(f"  • {c}: {baht(v)}")
    lines.append(f"รายจ่าย: {baht(s['expense'])}")
    for c, v in sorted(s["expense_by_category"].items(), key=lambda x: -x[1]):
        lines.append(f"  • {c}: {baht(v)}")
    lines.append(f"กำไรสุทธิ: {baht(s['net_profit'])}")
    if s["saving"]:
        lines.append(f"โอนเข้าเงินเก็บ: {baht(s['saving'])}")
    if s["invest"]:
        lines.append(f"ลงทุนต่อยอด: {baht(s['invest'])}")
    if s["capital_in"]:
        lines.append(f"เงินทุนที่เติมเข้า: {baht(s['capital_in'])}")
    if s["debt_paid_in_period"]:
        lines.append(f"ชำระหนี้ในช่วงนี้: {baht(s['debt_paid_in_period'])}")

    p = s["month_progress"]
    lines += ["", f"🎯 เป้าเดือน {p['month']} (วันที่ {p['day']}/{p['days_in_month']})"]
    lines.append(f"  รายรับ {_bar(p['income'], p['income_goal'])}{baht(p['income'])} / {baht(p['income_goal'])} ({_pct(p['income'], p['income_goal'])})")
    if p["income_goal"] and p["income"] < p["income_pace_target"]:
        lines.append(f"    ช้ากว่าแผน {baht(p['income_pace_target'] - p['income'])} (ควรได้ {baht(p['income_pace_target'])} ถึงวันนี้)")
    lines.append(f"  กำไร {_bar(max(p['profit'], 0), p['profit_goal'])}{baht(p['profit'])} / {baht(p['profit_goal'])} ({_pct(p['profit'], p['profit_goal'])})")
    lines.append(f"  เงินเก็บ {_bar(p['saving'], p['saving_goal'])}{baht(p['saving'])} / {baht(p['saving_goal'])} ({_pct(p['saving'], p['saving_goal'])})")
    if s["saving_goal_total"]:
        lines.append(f"  เงินเก็บสะสม {baht(s['saving_total'])} / {baht(s['saving_goal_total'])} ({_pct(s['saving_total'], s['saving_goal_total'])})")
    if s["channels"]:
        lines.append("  ช่องทาง (เดือนนี้ / เป้า):")
        for c in s["channels"]:
            lines.append(f"   • {c['name']}: {baht(c['income'])} / {baht(c['target'])}")

    lines += ["", f"เงินสดหมุนเวียน: {baht(s['cash_balance'])}"]
    if s["debt_initial"]:
        lines.append(f"หนี้คงเหลือ: {baht(s['debt_remaining'])} จาก {baht(s['debt_initial'])}")
    over = [b for b in s["budget_status"] if b["over"]]
    if over:
        lines.append("⚠️ เกินงบ: " + ", ".join(f"{b['category']} {baht(b['spent'])}/{baht(b['limit'])}" for b in over))
    return "\n".join(lines)


def make_ledger(settings) -> Ledger:
    if settings.LEDGER_BACKEND == "sheets":
        backend = SheetsBackend(settings.GOOGLE_SHEET_ID, settings.GOOGLE_SERVICE_ACCOUNT_JSON)
    else:
        backend = CsvBackend(settings.CSV_DIR)
    return Ledger(backend, settings.TIMEZONE)
