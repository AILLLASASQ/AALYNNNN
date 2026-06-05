import uuid
from aiogram import Router, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db

router = Router()

def get_main_menu():
    """لوحة المفاتيح الرئيسية"""
    keyboard = [
        [InlineKeyboardButton(text="➕ إنشاء إعلان", callback_data="create_ad")],
        [InlineKeyboardButton(text="📋 عرض الإعلانات", callback_data="list_ads")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@router.message(CommandStart())
async def start_cmd(message: types.Message):
    telegram_id = str(message.from_user.id)
    doc_ref = db.collection("merchants").document(telegram_id)
    doc = doc_ref.get()

    if doc.exists:
        merchant_id = doc.to_dict().get("merchant_id")
    else:
        # تسجيل جديد
        merchant_id = str(uuid.uuid4())[:8].upper()
        doc_ref.set({
            "merchant_id": merchant_id,
            "username": message.from_user.username,
            "telegram_id": telegram_id
        })

    # تجهيز النص الجميل
    text = (
        f"أهلاً بك يا <b>{message.from_user.full_name}</b> 🌟\n\n"
        f"👤 <b>الايدي الخاص بك:</b> <code>{telegram_id}</code>\n"
        f"🏷️ <b>رقمك التعريفي:</b> <code>{merchant_id}</code>\n\n"
        f"اختر ما تود القيام به من القائمة أدناه 👇"
    )

    await message.answer(text, reply_markup=get_main_menu(), parse_mode="HTML")