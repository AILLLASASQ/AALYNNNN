import os
from dotenv import load_dotenv

load_dotenv()

# Bot and Firebase
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_ID")
# سجل الإدارة المباشر
LOG_GROUP_ID = os.getenv("LOG_GROUP_ID")

# In Render: set FIREBASE_CREDENTIALS_JSON to the JSON string of the service account key
FIREBASE_CREDENTIALS_JSON = os.getenv("FIREBASE_CREDENTIALS_JSON")

# Channel and limits
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@YourChannel")  # ضع اسم قناتك هنا مع @
FREE_LIMIT = int(os.getenv("FREE_LIMIT", 2))
PAID_LIMIT = int(os.getenv("PAID_LIMIT", 10))

# Optional: cache TTL for subscription checks (seconds)
SUB_CHECK_TTL = int(os.getenv("SUB_CHECK_TTL", 60 * 60 * 24))  # 24 ساعة افتراضياً
