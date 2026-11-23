#!/usr/bin/env bash
# ติดตั้งบอท LINE ของ PAVNO (Ami + Yuki) บน Google Cloud Run ผ่าน Cloud Shell
#
# วิธีใช้ (ใน Cloud Shell ของ console.cloud.google.com):
#   git clone https://github.com/supatkrasabud-max/PavnoDigital.ai.git
#   cd PavnoDigital.ai/pavno-ai-team/pavno-ai-team
#   bash deploy/cloudshell-setup.sh
#
# รันซ้ำได้: ถ้ามีของเดิมอยู่แล้วจะข้าม หรืออัปเดตเป็นค่าใหม่
# คีย์ลับทั้งหมดเก็บใน Secret Manager (ไม่อยู่ในโค้ด ไม่อยู่ในไฟล์ ไม่โชว์บนจอ)
set -euo pipefail

REGION="asia-southeast1"
SERVICE="pavno-ai-team"
SA_NAME="pavno-ledger"
SHEET_ID="${SHEET_ID:-148qT0GBDFxBPUFcAh3rDRAHAoJ1Qx6ziLUIeTnPALpI}"   # Google Sheet "PAVNO บัญชี"

echo "== 0/6 รันเทสต์ก่อนติดตั้ง"
python3 -m pip install -q --user -r requirements.txt pytest httpx
python3 -m pytest -q || { echo "เทสต์ไม่ผ่าน ยกเลิกการติดตั้ง"; exit 1; }
[[ "${TEST_ONLY:-}" == "1" ]] && { echo "TEST_ONLY=1 หยุดหลังเทสต์"; exit 0; }

PROJECT="$(gcloud config get-value project 2>/dev/null)"
if [[ -z "$PROJECT" ]]; then
  echo "ยังไม่ได้เลือกโปรเจกต์: รัน  gcloud projects list  แล้ว  gcloud config set project <PROJECT_ID>  ก่อน"; exit 1
fi
SA_EMAIL="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
echo "== โปรเจกต์: $PROJECT  ภูมิภาค: $REGION"

echo "== 1/6 เปิดใช้บริการที่ต้องใช้"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com cloudscheduler.googleapis.com sheets.googleapis.com drive.googleapis.com

echo "== 2/6 สร้าง service account สำหรับอ่าน-เขียน Google Sheet"
gcloud iam service-accounts describe "$SA_EMAIL" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "$SA_NAME" --display-name "PAVNO ledger bot"

secret_exists() { gcloud secrets describe "$1" >/dev/null 2>&1; }
put_secret() {  # put_secret NAME (อ่านค่าจาก stdin)
  if secret_exists "$1"; then gcloud secrets versions add "$1" --data-file=- >/dev/null
  else gcloud secrets create "$1" --replication-policy=automatic --data-file=- >/dev/null; fi
  echo "   เก็บ $1 แล้ว"
}
ask_secret() {  # ask_secret NAME "คำอธิบาย"
  if secret_exists "$1" && [[ "${FORCE_ASK:-}" != "1" ]]; then echo "   มี $1 อยู่แล้ว (ข้าม)"; return; fi
  local v; read -r -s -p "   วาง $2 แล้วกด Enter (ตัวอักษรจะไม่แสดง): " v; echo
  [[ -n "$v" ]] || { echo "   ค่าว่าง ยกเลิก"; exit 1; }
  printf '%s' "$v" | put_secret "$1"
}

echo "== 3/6 เก็บคีย์ลับใน Secret Manager"
if ! secret_exists GOOGLE_SERVICE_ACCOUNT_JSON; then
  tmp="$(mktemp)"; gcloud iam service-accounts keys create "$tmp" --iam-account "$SA_EMAIL" >/dev/null
  put_secret GOOGLE_SERVICE_ACCOUNT_JSON < "$tmp"; shred -u "$tmp" 2>/dev/null || rm -f "$tmp"
else echo "   มี GOOGLE_SERVICE_ACCOUNT_JSON อยู่แล้ว (ข้าม)"; fi
ask_secret ANTHROPIC_API_KEY "Claude API key (sk-ant-...)"
ask_secret LINE_CHANNEL_SECRET "LINE Channel secret"
ask_secret LINE_CHANNEL_ACCESS_TOKEN "LINE Channel access token"
if ! secret_exists CRON_SECRET; then head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | put_secret CRON_SECRET; fi
if ! secret_exists STRIPE_WEBHOOK_SECRET; then printf 'unset' | put_secret STRIPE_WEBHOOK_SECRET; fi

RUN_SA="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')-compute@developer.gserviceaccount.com"
SECRETS="ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,LINE_CHANNEL_SECRET=LINE_CHANNEL_SECRET:latest,LINE_CHANNEL_ACCESS_TOKEN=LINE_CHANNEL_ACCESS_TOKEN:latest,GOOGLE_SERVICE_ACCOUNT_JSON=GOOGLE_SERVICE_ACCOUNT_JSON:latest,CRON_SECRET=CRON_SECRET:latest,STRIPE_WEBHOOK_SECRET=STRIPE_WEBHOOK_SECRET:latest"
EXTRA=""
# แจ้ง error ทาง Telegram (ไม่บังคับ): ตั้งด้วย  ADD_TELEGRAM=1 bash deploy/cloudshell-setup.sh
[[ "${ADD_TELEGRAM:-}" == "1" ]] && FORCE_ASK=1 ask_secret TELEGRAM_BOT_TOKEN "Telegram bot token (จาก @BotFather)"
if secret_exists TELEGRAM_BOT_TOKEN; then
  SECRETS="$SECRETS,TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest"; EXTRA="TELEGRAM_BOT_TOKEN"
fi
# โพสต์เพจ Facebook ผ่าน Ami (ไม่บังคับ): ตั้งด้วย  ADD_FACEBOOK=1 bash deploy/cloudshell-setup.sh
[[ "${ADD_FACEBOOK:-}" == "1" ]] && FORCE_ASK=1 ask_secret FB_PAGE_TOKEN "Facebook Page access token (แบบไม่หมดอายุ)"
if secret_exists FB_PAGE_TOKEN; then
  SECRETS="$SECRETS,FB_PAGE_TOKEN=FB_PAGE_TOKEN:latest"; EXTRA="$EXTRA FB_PAGE_TOKEN"
fi
for s in GOOGLE_SERVICE_ACCOUNT_JSON ANTHROPIC_API_KEY LINE_CHANNEL_SECRET LINE_CHANNEL_ACCESS_TOKEN CRON_SECRET STRIPE_WEBHOOK_SECRET $EXTRA; do
  gcloud secrets add-iam-policy-binding "$s" --member "serviceAccount:$RUN_SA" \
    --role roles/secretmanager.secretAccessor >/dev/null
done

echo "== 4/6 นำบอทขึ้น Cloud Run (ใช้เวลา 3–5 นาที)"
EXISTING_ENV=""
if gcloud run services describe "$SERVICE" --region "$REGION" >/dev/null 2>&1; then
  EXISTING_ENV="yes"
fi
ENV_VARS="LEDGER_BACKEND=sheets,GOOGLE_SHEET_ID=${SHEET_ID},TIMEZONE=Asia/Bangkok,MODEL_LEAD=claude-sonnet-5-5,MODEL_WORKER=claude-haiku-5-5,FB_PAGE_ID=${FB_PAGE_ID:-61597020621548}"
gcloud run deploy "$SERVICE" --source . --region "$REGION" \
  --allow-unauthenticated --max-instances 1 --memory 512Mi --timeout 900 \
  $( [[ -z "$EXISTING_ENV" ]] && echo "--set-env-vars $ENV_VARS" || echo "--update-env-vars $ENV_VARS" ) \
  --set-secrets "$SECRETS"
URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"

echo "== 5/6 ตั้งรายงานอัตโนมัติ (เวลาไทย)"
CRON="$(gcloud secrets versions access latest --secret CRON_SECRET)"
job() {  # job NAME "CRON" PATH
  local args=(--location "$REGION" --schedule "$2" --time-zone "Asia/Bangkok" --http-method GET --attempt-deadline 900s --uri "${URL}$3?key=${CRON}")
  if gcloud scheduler jobs describe "$1" --location "$REGION" >/dev/null 2>&1; then
    gcloud scheduler jobs update http "$1" "${args[@]}" >/dev/null
  else
    gcloud scheduler jobs create http "$1" "${args[@]}" >/dev/null
  fi
  echo "   $1: $2"
}
job yuki-daily   "0 8 * * *" /cron/daily
job yuki-weekly  "0 9 * * 1" /cron/weekly
job yuki-monthly "0 9 1 * *" /cron/monthly
job affiliate-research "0 6 * * *" /cron/affiliate
job sales-research     "30 6 * * 1-5" /cron/sales
job sales-summary      "0 17 * * 1-5" /cron/sales-summary

echo "== 6/6 เสร็จแล้ว"
cat <<EOF

ขั้นต่อไป (ทำเองครั้งเดียว):
 1) แชร์ Google Sheet "PAVNO บัญชี" ให้อีเมลนี้เป็น Editor:
      $SA_EMAIL
 2) LINE Developers > Messaging API > Webhook URL:
      ${URL}/callback
    กด Verify แล้วเปิด Use webhook
 3) เพิ่มบอทเป็นเพื่อนใน LINE แล้วพิมพ์  myid  จากนั้นรันใน Cloud Shell:
      gcloud run services update $SERVICE --region $REGION --update-env-vars CEO_USER_ID=<ค่าที่ได้>
    (จนกว่าจะตั้ง CEO_USER_ID ใครที่แอดบอทก็คุยได้ ให้ตั้งทันที)
 4) ถ้าใช้กลุ่ม LINE: เชิญบอทเข้ากลุ่ม พิมพ์ groupid แล้วตั้ง LINE_GROUP_ID แบบเดียวกัน
    ถ้าไม่ตั้ง รายงานอัตโนมัติจะส่งเข้าแชต 1:1 ของ CEO

ทดสอบรายงานทันที:  curl "${URL}/cron/daily?key=\$(gcloud secrets versions access latest --secret CRON_SECRET)"
EOF
