import firebase_admin
from firebase_admin import credentials, firestore
from config import FIREBASE_CERT

def init_firebase():
    if not firebase_admin._apps:
        if isinstance(FIREBASE_CERT, dict):
            cred = credentials.Certificate(FIREBASE_CERT)
        else:
            cred = credentials.Certificate(FIREBASE_CERT)
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_firebase()