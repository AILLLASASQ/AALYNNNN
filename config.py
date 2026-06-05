import os
import json
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
# في Render سنقوم بنسخ محتوى ملف جيسون ولصقه في هذا المتغير
FIREBASE_CREDENTIALS_JSON = os.environ.get("FIREBASE_CREDENTIALS_JSON")

if FIREBASE_CREDENTIALS_JSON:
    try:
        FIREBASE_CERT = json.loads(FIREBASE_CREDENTIALS_JSON)
    except json.JSONDecodeError:
        FIREBASE_CERT = None
else:
    # للتشغيل المحلي، ضع ملف المفتاح بجانب هذا الملف
    FIREBASE_CERT = "firebase_cert.json"