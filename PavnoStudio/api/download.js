// ส่งลิงก์ดาวน์โหลดให้ลูกค้าหลังชำระเงิน
// หน้า /thanks/ เรียก /api/download?session_id=cs_... (Stripe ใส่ session_id ให้ตอน redirect หลังจ่ายเงิน)
// ฟังก์ชันนี้ถาม Stripe ว่า session นั้นจ่ายเงินแล้วจริงและเป็นสินค้าตัวไหน จึงคืนลิงก์ไฟล์ของสินค้านั้น
//
// ตั้งค่าใน Vercel > Settings > Environment Variables (ห้ามใส่ค่าจริงในโค้ด เพราะ repo เป็นสาธารณะ):
//   STRIPE_SECRET_KEY  Restricted key ของ Stripe ที่มีสิทธิ์ Read: Checkout Sessions และ Payment Links
//   DOWNLOAD_LINKS     JSON จับคู่รหัสสินค้ากับลิงก์ไฟล์ เช่น
//                      {"thai-abc":"https://drive.google.com/...","abc-tracing":[{"label":"A4","url":"..."},{"label":"US Letter","url":"..."}]}

// ต้องตรงกับ dist/assets/payment-links.js (เพิ่มสินค้าใหม่ต้องเพิ่มทั้งสองที่)
const PAY_LINKS = {
  'thai-abc': 'https://buy.stripe.com/5kQ3cu87dcVD2cg3RB5os07',
  'abc-tracing': 'https://buy.stripe.com/8x23cufzFg7PaIM5ZJ5os08',
  'hiragana': 'https://buy.stripe.com/aFa5kC87ddZH2cg87R5os09',
  'kanji-g1': 'https://buy.stripe.com/4gMcN4gDJaNv6swafZ5os0a',
  'chinese-60': 'https://buy.stripe.com/bJeaEW0ELaNvbMQ73N5os0b',
  'math-add': 'https://buy.stripe.com/14A28qfzFf3L18c3RB5os0c',
  'math-sub': 'https://buy.stripe.com/6oU7sKbjpg7Pg36fAj5os0d',
  'math-mul': 'https://buy.stripe.com/dRmaEWbjp6xf6sw9bV5os0e',
  'math-div': 'https://buy.stripe.com/3cI9AS739aNv2cgbk35os0f',
  'math-bundle': 'https://buy.stripe.com/cNi00ibjp8Fn0481Jt5os0g',
  'coloring': 'https://buy.stripe.com/cNidR8bjp5tb4ko2Nx5os0h',
};

const NAMES = {
  'thai-abc': 'ฝึกเขียน ก-ฮ มีรูปภาพ',
  'abc-tracing': 'ABC Tracing Picture Workbook',
  'hiragana': 'ฝึกเขียนฮิรางานะ 46 ตัว',
  'kanji-g1': 'คันจิ ป.1 80 ตัว',
  'chinese-60': 'อักษรจีนพื้นฐาน 60 ตัว',
  'math-add': 'บวกเลข 2,000 ข้อ',
  'math-sub': 'ลบเลข 2,000 ข้อ',
  'math-mul': 'คูณเลข 2,000 ข้อ',
  'math-div': 'หารเลข 2,000 ข้อ',
  'math-bundle': 'คณิตชุดรวม 8,000 ข้อ (บวก ลบ คูณ หาร)',
  'coloring': 'สมุดระบายสีการ์ตูนน่ารัก 24 ตัว',
};

// ลิงก์ดาวน์โหลดใช้ได้กี่วันนับจากวันชำระเงิน
const VALID_DAYS = 90;

function json(res, status, body) {
  res.status(status).setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  return res.end(JSON.stringify(body));
}

function productForLink(url) {
  const clean = String(url || '').split('?')[0].replace(/\/$/, '');
  return Object.keys(PAY_LINKS).find((id) => PAY_LINKS[id] === clean) || '';
}

function filesFor(id) {
  let links;
  try {
    links = JSON.parse(process.env.DOWNLOAD_LINKS || '{}');
  } catch {
    return [];
  }
  const entry = links[id];
  const list = Array.isArray(entry) ? entry : entry ? [entry] : [];
  return list
    .map((item) => (typeof item === 'string' ? { label: '', url: item } : { label: String(item.label || ''), url: String(item.url || '') }))
    .filter((item) => /^https:\/\//.test(item.url));
}

export default async function handler(req, res) {
  if (req.method !== 'GET') return json(res, 405, { error: 'method_not_allowed' });

  if (!process.env.STRIPE_SECRET_KEY || !process.env.DOWNLOAD_LINKS) {
    return json(res, 503, { error: 'not_configured' });
  }

  const sessionId = typeof req.query.session_id === 'string' ? req.query.session_id : '';
  if (!/^cs_[A-Za-z0-9_]{10,200}$/.test(sessionId)) {
    return json(res, 400, { error: 'bad_session' });
  }

  let session;
  try {
    const response = await fetch(
      `https://api.stripe.com/v1/checkout/sessions/${sessionId}?expand[]=payment_link`,
      { headers: { Authorization: `Bearer ${process.env.STRIPE_SECRET_KEY}` } },
    );
    if (response.status === 404) return json(res, 404, { error: 'not_found' });
    if (!response.ok) {
      console.error('stripe_error', response.status);
      return json(res, 502, { error: 'stripe_error' });
    }
    session = await response.json();
  } catch (error) {
    console.error('stripe_unreachable', error && error.message);
    return json(res, 502, { error: 'stripe_error' });
  }

  // PromptPay และบัตรจะเป็น paid ทันทีที่จ่ายสำเร็จ ถ้ายังไม่ paid ให้ลูกค้ารอแล้วลองใหม่
  if (session.payment_status !== 'paid') return json(res, 402, { error: 'not_paid' });

  const ageDays = (Date.now() / 1000 - Number(session.created || 0)) / 86400;
  if (ageDays > VALID_DAYS) return json(res, 410, { error: 'expired' });

  const link = session.payment_link && typeof session.payment_link === 'object' ? session.payment_link.url : '';
  const id = productForLink(link);
  if (!id) {
    console.error('unknown_payment_link', link);
    return json(res, 404, { error: 'unknown_product' });
  }

  const files = filesFor(id);
  if (!files.length) {
    console.error('no_download_link_for', id);
    return json(res, 503, { error: 'file_missing', product: id, name: NAMES[id] });
  }

  return json(res, 200, { product: id, name: NAMES[id], files });
}
