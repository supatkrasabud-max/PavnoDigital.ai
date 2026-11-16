"""สมุดบัญชีของ Yuki

เก็บข้อมูล 4 แท็บ:
  Ledger    : รายการเงินเข้า-ออกทุกรายการ
  Budget    : วงเงินต่อเดือนแต่ละหมวด
  Approvals : คำขอใช้เงินที่รอ CEO อนุมัติ
  Settings  : ค่าอื่น ๆ เช่น ยอดหนี้เริ่มต้น

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

KINDS = {
    "income": "รายรับ",
    "expense": "รายจ่าย",
    "capital": "เงินทุนจาก CEO",
    "debt_payment": "ชำระหนี้",
}

SHEETS = {
    "Ledger": ["id", "date", "kind", "category", "amount", "note", "recorded_by", "ref"],
    "Budget": ["category", "monthly_limit"],
    "Approvals": ["id", "created", "category", "amount", "reason", "requested_by", "status", "decided"],
    "Settings": ["key", "value"],
}

DEFAULT_BUDGET = {
    "ads": 4000,
    "accountant": 3000,
    "ai_api": 700,
    "server": 300,
}


def today(tz: str = "Asia/Bangkok") -> date:
    return datetime.now(ZoneInfo(tz)).date()


@dataclass
class Entry:
    date: str
    kind: str
    category: str
    amount: float
    note: str = ""
    recorded_by: str = "Yuki"
    ref: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


# --------------------------------------------------------------------------- backends

class _Backend:
    """อินเทอร์เฟซร่วม: อ่าน/เขียนแถวในแต่ละแท็บ"""

    def rows(self, sheet: str) -> list[dict]:
        raise NotImplementedError

    def append(self, sheet: str, row: dict) -> None:
        raise NotImplementedError

    def overwrite(self, sheet: str, rows: list[dict]) -> None:
        raise NotImplementedError


class CsvBackend(_Backend):
    def __init__(self, folder: str):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)
        self._lock = threading.Lock()
        for name, headers in SHEETS.items():
            path = self._path(name)
            if not os.path.exists(path):
                with open(path, "w", newline="", encoding="utf-8") as f:
                    csv.DictWriter(f, fieldnames=headers).writeheader()

    def _path(self, sheet: str) -> str:
        return os.path.join(self.folder, f"{sheet}.csv")

    def rows(self, sheet: str) -> list[dict]:
        with self._lock, open(self._path(sheet), newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def append(self, sheet: str, row: dict) -> None:
        with self._lock, open(self._path(sheet), "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=SHEETS[sheet]).writerow(
                {k: row.get(k, "") for k in SHEETS[sheet]})

    def overwrite(self, sheet: str, rows: list[dict]) -> None:
        with self._lock, open(self._path(sheet), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=SHEETS[sheet])
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in SHEETS[sheet]})


class SheetsBackend(_Backend):
    """Google Sheets ผ่าน service account (pip install gspread google-auth)"""

    def __init__(self, sheet_id: str, service_account_json: str):
        import gspread  # noqa: import เฉพาะตอนใช้งานจริง
        info = json.loads(service_account_json)
        gc = gspread.service_account_from_dict(info)
        self.book = gc.open_by_key(sheet_id)
        existing = {ws.title for ws in self.book.worksheets()}
        for name, headers in SHEETS.items():
            if name not in existing:
                ws = self.book.add_worksheet(title=name, rows=1000, cols=len(headers))
                ws.append_row(headers)

    def _ws(self, sheet: str):
        return self.book.worksheet(sheet)

    def rows(self, sheet: str) -> list[dict]:
        return self._ws(sheet).get_all_records(expected_headers=SHEETS[sheet])

    def append(self, sheet: str, row: dict) -> None:
        self._ws(sheet).append_row([row.get(k, "") for k in SHEETS[sheet]],
                                   value_input_option="USER_ENTERED")

    def overwrite(self, sheet: str, rows: list[dict]) -> None:
        ws = self._ws(sheet)
        ws.clear()
        ws.update([SHEETS[sheet]] + [[r.get(k, "") for k in SHEETS[sheet]] for r in rows])


# --------------------------------------------------------------------------- ledger

class Ledger:
    def __init__(self, backend: _Backend, tz: str = "Asia/Bangkok"):
        self.b = backend
        self.tz = tz
        if not self.b.rows("Budget"):
            for cat, limit in DEFAULT_BUDGET.items():
                self.b.append("Budget", {"category": cat, "monthly_limit": limit})

    # ---- รายการบัญชี
    def add_entry(self, kind: str, category: str, amount: float, note: str = "",
                  recorded_by: str = "Yuki", on_date: str | None = None, ref: str = "") -> Entry:
        if kind not in KINDS:
            raise ValueError(f"kind ต้องเป็นหนึ่งใน {list(KINDS)}")
        amount = round(float(amount), 2)
        if amount <= 0:
            raise ValueError("จำนวนเงินต้องมากกว่า 0")
        if ref and any(r.get("ref") == ref for r in self.b.rows("Ledger")):
            raise ValueError(f"รายการอ้างอิง {ref} ถูกบันทึกไปแล้ว")
        e = Entry(date=on_date or today(self.tz).isoformat(), kind=kind,
                  category=(category or "other").strip().lower(), amount=amount,
                  note=note, recorded_by=recorded_by, ref=ref)
        self.b.append("Ledger", asdict(e))
        return e

    def entries(self, start: date | None = None, end: date | None = None) -> list[dict]:
        out = []
        for r in self.b.rows("Ledger"):
            try:
                d = date.fromisoformat(str(r["date"]))
                r = {**r, "amount": float(r["amount"])}
            except (ValueError, KeyError):
                continue
            if start and d < start:
                continue
            if end and d > end:
                continue
            out.append(r)
        return out

    # ---- งบประมาณ
    def budgets(self) -> dict[str, float]:
        return {str(r["category"]).lower(): float(r["monthly_limit"]) for r in self.b.rows("Budget")}

    def set_budget(self, category: str, monthly_limit: float) -> None:
        rows = [r for r in self.b.rows("Budget") if str(r["category"]).lower() != category.lower()]
        rows.append({"category": category.lower(), "monthly_limit": float(monthly_limit)})
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

    # ---- คำขออนุมัติ
    def request_approval(self, category: str, amount: float, reason: str, requested_by: str) -> dict:
        row = {"id": "A" + uuid.uuid4().hex[:4].upper(), "created": today(self.tz).isoformat(),
               "category": category.lower(), "amount": float(amount), "reason": reason,
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

    # ---- สรุป
    def summary(self, start: date, end: date) -> dict:
        return summarize(self.entries(), self.budgets(),
                         float(self.get_setting("debt_initial", "0") or 0), start, end)


def summarize(all_entries: list[dict], budgets: dict[str, float], debt_initial: float,
              start: date, end: date) -> dict:
    """คำนวณสรุปช่วงเวลา (ฟังก์ชันบริสุทธิ์ ทดสอบได้ง่าย)"""
    period = [e for e in all_entries if start <= date.fromisoformat(str(e["date"])) <= end]

    def total(rows, kind):
        return round(sum(float(e["amount"]) for e in rows if e["kind"] == kind), 2)

    expense_by_cat: dict[str, float] = {}
    for e in period:
        if e["kind"] == "expense":
            expense_by_cat[e["category"]] = round(expense_by_cat.get(e["category"], 0) + float(e["amount"]), 2)

    income_by_cat: dict[str, float] = {}
    for e in period:
        if e["kind"] == "income":
            income_by_cat[e["category"]] = round(income_by_cat.get(e["category"], 0) + float(e["amount"]), 2)

    # งบเดือนนี้ใช้ไปเท่าไร (นับตั้งแต่วันที่ 1 ของเดือนที่ end อยู่)
    month_start = end.replace(day=1)
    month_spend: dict[str, float] = {}
    for e in all_entries:
        d = date.fromisoformat(str(e["date"]))
        if e["kind"] == "expense" and month_start <= d <= end:
            month_spend[e["category"]] = month_spend.get(e["category"], 0) + float(e["amount"])
    budget_status = []
    for cat in sorted(set(budgets) | set(month_spend)):
        limit = budgets.get(cat, 0.0)
        spent = round(month_spend.get(cat, 0.0), 2)
        budget_status.append({"category": cat, "limit": limit, "spent": spent,
                              "over": spent > limit})

    upto = [e for e in all_entries if date.fromisoformat(str(e["date"])) <= end]
    cash = (total(upto, "capital") + total(upto, "income")
            - total(upto, "expense") - total(upto, "debt_payment"))
    debt_paid = total(upto, "debt_payment")
    monthly_budget = round(sum(budgets.values()), 2)
    income = total(period, "income")
    expense = total(period, "expense")
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "income": income,
        "income_by_category": income_by_cat,
        "expense": expense,
        "expense_by_category": expense_by_cat,
        "net_profit": round(income - expense, 2),
        "capital_in": total(period, "capital"),
        "debt_paid_in_period": total(period, "debt_payment"),
        "cash_balance": round(cash, 2),
        "debt_initial": debt_initial,
        "debt_remaining": round(max(debt_initial - debt_paid, 0), 2),
        "monthly_budget_total": monthly_budget,
        "budget_status": budget_status,
        # เงินที่ควรเติมเพื่อให้มีพอจ่ายงบเดือนหน้าเต็มเดือน
        "suggested_top_up": round(max(monthly_budget - cash, 0), 2),
        "orders": sum(1 for e in period if e["kind"] == "income"),
    }


def period_range(name: str, tz: str = "Asia/Bangkok") -> tuple[date, date]:
    t = today(tz)
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
    raise ValueError("period ต้องเป็น this_week, last_week, this_month, last_month หรือ all")


def baht(x: float) -> str:
    return f"{x:,.0f} บาท" if float(x).is_integer() else f"{x:,.2f} บาท"


def format_report(s: dict, title: str) -> str:
    lines = [f"📒 {title}", f"ช่วง {s['start']} ถึง {s['end']}", ""]
    lines.append(f"รายรับ: {baht(s['income'])} ({s['orders']} รายการ)")
    for c, v in sorted(s["income_by_category"].items(), key=lambda x: -x[1]):
        lines.append(f"  • {c}: {baht(v)}")
    lines.append(f"รายจ่าย: {baht(s['expense'])}")
    for c, v in sorted(s["expense_by_category"].items(), key=lambda x: -x[1]):
        lines.append(f"  • {c}: {baht(v)}")
    lines.append(f"กำไรสุทธิ: {baht(s['net_profit'])}")
    if s["capital_in"]:
        lines.append(f"เงินทุนที่เติมเข้า: {baht(s['capital_in'])}")
    if s["debt_paid_in_period"]:
        lines.append(f"ชำระหนี้ในช่วงนี้: {baht(s['debt_paid_in_period'])}")
    lines += ["", f"เงินสดคงเหลือ: {baht(s['cash_balance'])}"]
    if s["debt_initial"]:
        lines.append(f"หนี้คงเหลือ: {baht(s['debt_remaining'])} จาก {baht(s['debt_initial'])}")
    lines += ["", "งบเดือนนี้ (ใช้ไป / วงเงิน):"]
    for b in s["budget_status"]:
        flag = " ⚠️ เกินงบ" if b["over"] else ""
        lines.append(f"  • {b['category']}: {baht(b['spent'])} / {baht(b['limit'])}{flag}")
    lines += ["", f"ยอดแนะนำให้ CEO เติมทุน: {baht(s['suggested_top_up'])}"]
    return "\n".join(lines)


def make_ledger(settings) -> Ledger:
    if settings.LEDGER_BACKEND == "sheets":
        backend = SheetsBackend(settings.GOOGLE_SHEET_ID, settings.GOOGLE_SERVICE_ACCOUNT_JSON)
    else:
        backend = CsvBackend(settings.CSV_DIR)
    return Ledger(backend, settings.TIMEZONE)
