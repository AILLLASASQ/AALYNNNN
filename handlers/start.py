import uuid
from aiogram import Router, types
from aiogram.filters import CommandStart
from database import db

router = Router()

@router.message(CommandStart())
async def start_cmd(message: types.Message):
    telegram_id = str(message.from_user.id)
    doc_ref = db.collection("merchants").document(telegram_id)
    doc = doc_ref.get()

    # النص التعريفي للأوامر
    welcome_text = (
        "<b>مرحباً بك في نظام إدارة الإعلانات.</b>\n\n"
        "📌 <b>قائمة الأوامر المتاحة:</b>\n"
        "• /create_ad - لإنشاء إعلان جديد\n"
        "• /my_ads - لعرض إعلاناتك\n\n"
    )

    if doc.exists:
        merchant_id = doc.to_dict().get("merchant_id")
        await message.answer(
            f"{welcome_text}أهلاً بك مجدداً.\nرقمك التعريفي (Merchant ID) هو: <code>{merchant_id}</code>", 
            parse_mode="HTML"
        )
    else:
        merchant_id = str(uuid.uuid4())[:8]
        doc_ref.set({
            "merchant_id": merchant_id,
            "username": message.from_user.username,
            "telegram_id": telegram_id
        })
        await message.answer(
            f"{welcome_text}تم تسجيلك كتاجر.\nرقمك التعريفي (Merchant ID) هو: <code>{merchant_id}</code>", 
            parse_mode="HTML"
        )