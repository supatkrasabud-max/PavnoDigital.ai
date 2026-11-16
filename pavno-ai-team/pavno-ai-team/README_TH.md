# ทีม AI ของ PAVNO DIGITAL — คู่มือติดตั้ง

บอทนี้ทำให้กลุ่ม LINE ของคุณกลายเป็นห้องประชุมของบริษัท

- **Ami** ผู้ช่วย CEO: รับคำสั่ง แบ่งงานให้ฝ่ายสินค้า ฝ่ายการตลาด และฝ่ายบริการลูกค้า แล้วสรุปผลกลับมาให้
- **Yuki** ฝ่ายการเงิน: บันทึกบัญชีลง Google Sheets คุมงบ ขออนุมัติการใช้เงิน และส่งรายงานทุกวันจันทร์กับทุกวันที่ 1
- **Stripe**: เมื่อมีลูกค้าจ่ายเงิน Yuki จะบันทึกรายรับให้เองอัตโนมัติ

ค่าใช้จ่ายของระบบประมาณ 300–1,000 บาท/เดือน (ส่วนใหญ่เป็นค่า Claude API) ส่วน LINE OA แบบฟรี, Google Sheets และ Cloud Run ใช้ได้ฟรีในโควตาปกติ

ใช้เวลาติดตั้งประมาณ 1–2 ชั่วโมง ถ้าติดขั้นตอนไหน ส่งภาพหน้าจอมาถามได้เลย

---

## ขั้นที่ 1 — สร้างคีย์ Claude API

1. เข้า https://console.anthropic.com แล้วสมัครหรือล็อกอิน
2. ไปที่ **Billing** เติมเครดิต $20 แล้วตั้ง **Monthly spend limit** ไว้ที่ $20 เพื่อกันค่าใช้จ่ายบานปลาย
3. ไปที่ **API Keys** → Create Key → คัดลอกเก็บไว้ (ใช้เป็น `ANTHROPIC_API_KEY`)

## ขั้นที่ 2 — สร้างบอท LINE

1. สร้าง LINE Official Account (แพ็กเกจฟรี) ที่ https://manager.line.biz
2. ใน OA Manager ไปที่ **ตั้งค่า → Messaging API** แล้วกด **เปิดใช้ Messaging API**
3. ใน **ตั้งค่า → การตั้งค่าการตอบกลับ** ให้ **ปิด** ข้อความตอบกลับอัตโนมัติ และ **เปิด** Webhook
4. ใน **ตั้งค่า → บัญชี** ให้เปิด **อนุญาตให้บัญชีเข้าร่วมแชทกลุ่ม**
5. เข้า https://developers.line.biz → เลือก Channel ของบอท
   - แท็บ Basic settings → คัดลอก **Channel secret** (`LINE_CHANNEL_SECRET`)
   - แท็บ Messaging API → กด Issue **Channel access token** (`LINE_CHANNEL_ACCESS_TOKEN`)

## ขั้นที่ 3 — สร้างสมุดบัญชี Google Sheets

1. สร้าง Google Sheet เปล่าชื่อ `PAVNO บัญชี` แล้วคัดลอก ID จาก URL
   (ส่วนระหว่าง `/d/` กับ `/edit`) ใช้เป็น `GOOGLE_SHEET_ID`
2. เข้า https://console.cloud.google.com → สร้างโปรเจกต์ `pavno-ai`
3. เปิดใช้ **Google Sheets API** และ **Google Drive API**
4. ไปที่ IAM → **Service Accounts** → Create → แท็บ Keys → Add key → JSON → ดาวน์โหลดไฟล์
5. เปิดไฟล์ JSON คัดลอกอีเมล `client_email` แล้ว **แชร์ Google Sheet ให้อีเมลนี้เป็น Editor**
6. เนื้อหาไฟล์ JSON ทั้งหมดใช้เป็น `GOOGLE_SERVICE_ACCOUNT_JSON`

บอทจะสร้างแท็บ Ledger, Budget, Approvals และ Settings ให้เองตอนเริ่มทำงานครั้งแรก
งบตั้งต้นคือ ads 4,000 · accountant 3,000 · ai_api 700 · server 300 บาท/เดือน

## ขั้นที่ 4 — นำบอทขึ้นเซิร์ฟเวอร์ (Google Cloud Run)

ติดตั้ง [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) แล้วเปิด Terminal ในโฟลเดอร์นี้

1. คัดลอก `.env.example` เป็น `env.yaml` ในรูปแบบ `KEY: "value"` (หนึ่งบรรทัดต่อค่า) แล้วใส่ค่าจากขั้นที่ 1–3
   และตั้ง `CRON_SECRET` เป็นรหัสยาว ๆ ที่คิดเอง
2. รันคำสั่ง

```bash
gcloud auth login
gcloud config set project pavno-ai
gcloud run deploy pavno-ai-team --source . --region asia-southeast1 \
  --allow-unauthenticated --max-instances 1 --timeout 300 \
  --env-vars-file env.yaml
```

3. ระบบจะให้ URL เช่น `https://pavno-ai-team-xxxx.a.run.app` จดไว้

> ตั้ง `--max-instances 1` ไว้เพื่อให้บอทจำบทสนทนาได้ต่อเนื่องและไม่บันทึกซ้ำ

## ขั้นที่ 5 — เชื่อม LINE กับเซิร์ฟเวอร์

1. LINE Developers → Messaging API → **Webhook URL** = `https://<URL ของคุณ>/callback` → กด Verify → เปิด Use webhook
2. สร้างกลุ่ม LINE ของบริษัท แล้วเชิญบอทเข้ากลุ่ม
3. พิมพ์ `groupid` ในกลุ่ม และพิมพ์ `myid` (ด้วยบัญชีของคุณ)
4. นำค่าที่ได้ไปอัปเดตบอท

```bash
gcloud run services update pavno-ai-team --region asia-southeast1 \
  --update-env-vars LINE_GROUP_ID=Cxxxx,CEO_USER_ID=Uxxxx
```

## ขั้นที่ 6 — ตั้งรายงานอัตโนมัติของ Yuki

```bash
gcloud scheduler jobs create http yuki-weekly --location asia-southeast1 \
  --schedule "0 9 * * 1" --time-zone "Asia/Bangkok" --http-method GET \
  --uri "https://<URL ของคุณ>/cron/weekly?key=<CRON_SECRET>"

gcloud scheduler jobs create http yuki-monthly --location asia-southeast1 \
  --schedule "0 9 1 * *" --time-zone "Asia/Bangkok" --http-method GET \
  --uri "https://<URL ของคุณ>/cron/monthly?key=<CRON_SECRET>"
```

ทุกวันจันทร์ 09:00 จะได้รายงานของสัปดาห์ก่อน และทุกวันที่ 1 จะได้รายงานของเดือนก่อน

## ขั้นที่ 7 — เชื่อม Stripe (หลังเปิดรับเงินแล้ว)

1. Stripe Dashboard → Developers → **Webhooks** → Add endpoint
2. URL = `https://<URL ของคุณ>/stripe/webhook`
3. เลือก event `checkout.session.completed` และ `checkout.session.async_payment_succeeded`
4. คัดลอก **Signing secret** (`whsec_...`) ไปอัปเดตเป็น `STRIPE_WEBHOOK_SECRET`

ทุกการขายจะถูกบันทึกเป็นรายรับหมวด `pdf` ถ้าต้องการแยกหมวด ให้ใส่ metadata `category` ใน Checkout
ค่าธรรมเนียม Stripe ให้ Yuki บันทึกเป็นรายจ่ายหมวด `other` ตอนสิ้นเดือนจากรายงาน Payout

---

## วิธีสั่งงานในกลุ่ม LINE

ขึ้นต้นข้อความด้วยชื่อคนที่ต้องการสั่ง (ข้อความอื่นในกลุ่มบอทจะไม่ตอบ)

| พิมพ์ | ผลลัพธ์ |
|---|---|
| `Yuki ตั้งยอดหนี้เริ่มต้น 3,000,000 บาท` | ตั้งยอดหนี้ไว้ติดตามในรายงาน |
| `Yuki บันทึกเงินทุนจาก CEO 8,000 บาท` | บันทึกเงินที่คุณเติมเข้าบริษัท |
| `Yuki จ่ายค่าโฆษณา Facebook 1,200 บาท` | บันทึกรายจ่ายและเตือนถ้าเกินงบ |
| `Yuki สรุปเดือนนี้` | สรุปรายรับ รายจ่าย กำไร เงินสด หนี้คงเหลือ |
| `Yuki ปรับงบ ads เป็น 5,000` | แก้วงเงินงบรายเดือน (CEO เท่านั้น) |
| `Ami ให้ฝ่ายสินค้าออกแบบแพ็กเกจระบายสีอนุบาล 5 เล่ม` | ฝ่ายสินค้าเขียนเนื้อหาและราคา แล้ว Ami สรุปให้ |
| `Ami วางแผนโฆษณาสัปดาห์หน้า งบไม่เกิน 1,000` | ฝ่ายการตลาดวางแผน และ Yuki สร้างคำขออนุมัติ |
| `อนุมัติ A1B2` / `ไม่อนุมัติ A1B2` | ตอบคำขอใช้เงิน (CEO เท่านั้น) |
| `รายงาน` | รายงานบัญชีสัปดาห์นี้ทันที |

## ข้อจำกัดที่ควรรู้

- Agent **ไม่สามารถจ่ายเงินจริง** หรือเข้าบัญชีธนาคารได้ คุณเป็นคนกดจ่ายเองทุกครั้ง แล้วแจ้ง Yuki ให้บันทึก
- Yuki ช่วยทำบัญชีบริหาร แต่งบการเงินประจำปีของบริษัทจำกัดยังต้องให้ผู้ทำบัญชีที่ขึ้นทะเบียนและผู้สอบบัญชี CPA รับรอง
- LINE OA แบบฟรี push ได้ 300 ข้อความ/เดือน การตอบกลับคำสั่ง (reply) ไม่นับโควตา รายงานอัตโนมัติใช้ประมาณ 5–6 ข้อความ/เดือน
- ถ้าตั้ง `CEO_USER_ID` ไว้ จะมีแค่คุณที่บันทึกเงินทุน แก้งบ และอนุมัติได้ ถ้าไม่ตั้ง ทุกคนในกลุ่มทำได้
- ชื่อรุ่นโมเดลตั้งได้ใน `MODEL_LEAD` และ `MODEL_WORKER` ถ้ารุ่นใดเลิกให้บริการ ให้เปลี่ยนเป็นรุ่นที่แสดงใน console.anthropic.com

## ทดสอบในเครื่อง (สำหรับนักพัฒนา)

```bash
pip install -r requirements.txt pytest httpx
python -m pytest -q          # ทดสอบทั้งหมด (ไม่ต้องใช้คีย์จริง)
LEDGER_BACKEND=csv uvicorn app.main:build_app --factory --port 8080
```
