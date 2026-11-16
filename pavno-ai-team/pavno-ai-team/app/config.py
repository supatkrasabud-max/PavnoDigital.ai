"""ตั้งค่าทั้งหมดอ่านจาก Environment Variables (ดูตัวอย่างใน .env.example)"""
import os


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


class Settings:
    # LINE Messaging API
    LINE_CHANNEL_SECRET = _get("LINE_CHANNEL_SECRET")
    LINE_CHANNEL_ACCESS_TOKEN = _get("LINE_CHANNEL_ACCESS_TOKEN")
    # กลุ่ม LINE ที่ใช้ประชุม (พิมพ์ "groupid" ในกลุ่มเพื่อดูค่า)
    LINE_GROUP_ID = _get("LINE_GROUP_ID")
    # LINE user id ของ CEO (พิมพ์ "myid" เพื่อดูค่า) — มีสิทธิ์อนุมัติงบ/บันทึกเงินทุน
    CEO_USER_ID = _get("CEO_USER_ID")
    # ถ้าใส่ไว้ บอทจะตอบเฉพาะ user id เหล่านี้ (คั่นด้วย ,)
    ALLOWED_USER_IDS = [x for x in _get("ALLOWED_USER_IDS").split(",") if x.strip()]

    # Claude API
    ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY")
    MODEL_LEAD = _get("MODEL_LEAD", "claude-sonnet-5-5")      # Ami และ Yuki
    MODEL_WORKER = _get("MODEL_WORKER", "claude-haiku-5-5")   # ฝ่ายสินค้า/การตลาด/บริการลูกค้า

    # สมุดบัญชี: "sheets" (Google Sheets) หรือ "csv" (ทดสอบในเครื่อง)
    LEDGER_BACKEND = _get("LEDGER_BACKEND", "csv")
    GOOGLE_SHEET_ID = _get("GOOGLE_SHEET_ID")
    GOOGLE_SERVICE_ACCOUNT_JSON = _get("GOOGLE_SERVICE_ACCOUNT_JSON")
    CSV_DIR = _get("CSV_DIR", "./data")

    # Stripe
    STRIPE_WEBHOOK_SECRET = _get("STRIPE_WEBHOOK_SECRET")
    NOTIFY_EACH_SALE = _get("NOTIFY_EACH_SALE", "false").lower() == "true"

    # รหัสลับสำหรับ Cloud Scheduler เรียกรายงานอัตโนมัติ
    CRON_SECRET = _get("CRON_SECRET")

    # กฎการเงิน
    APPROVAL_THRESHOLD = float(_get("APPROVAL_THRESHOLD", "2000"))
    TIMEZONE = _get("TIMEZONE", "Asia/Bangkok")


settings = Settings()
