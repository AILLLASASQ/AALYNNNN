import os
import json
import threading
from typing import Optional
import firebase_admin
from firebase_admin import credentials, firestore
from config import FIREBASE_CREDENTIALS_JSON

_db = None
_db_lock = threading.Lock()

def _init_firebase():
    global _db
    if _db is not None:
        return _db

    # تهيئة الاعتماديات من متغير البيئة أو ملف محلي
    cred_obj = None
    if FIREBASE_CREDENTIALS_JSON:
        try:
            cred_dict = json.loads(FIREBASE_CREDENTIALS_JSON)
            cred_obj = credentials.Certificate(cred_dict)
        except Exception:
            cred_obj = None

    if not cred_obj:
        # افتراضيًا يحاول استخدام ملف محلي باسم firebase_cert.json
        if os.path.exists("firebase_cert.json"):
            cred_obj = credentials.Certificate("firebase_cert.json")
        else:
            raise RuntimeError("Firebase credentials not found. Set FIREBASE_CREDENTIALS_JSON or provide firebase_cert.json")

    # تهيئة التطبيق إذا لم يكن مهيأً
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred_obj)

    _db = firestore.client()
    return _db

def get_db():
    global _db
    with _db_lock:
        if _db is None:
            _init_firebase()
    return _db

# تصدير متغير db للاستخدام في باقي الملفات
db = get_db()
