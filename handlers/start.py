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

    if doc.exists:
        merchant_id = doc.to_dict().get("merchant_id")
        await message.answer(f"أهلاً بك مجدداً.\nرقمك التعريفي (Merchant ID) هو: {merchant_id}")
    else:
        merchant_id = str(uuid.uuid4())[:8] # إنشاء رقم تعريفي قصير
        doc_ref.set({
            "merchant_id": merchant_id,
            "username": message.from_user.username,
            "telegram_id": telegram_id
        })
        await message.answer(f"تم تسجيلك كتاجر.\nرقمك التعريفي (Merchant ID) هو: {merchant_id}")