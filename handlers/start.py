import asyncio
import uuid
from aiogram import Router, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from database import db
from handlers.ads import get_main_menu, is_user_subscribed

router = Router()

@router.message(CommandStart())
async def start_cmd(message: types.Message, state: FSMContext):
    # مسح أي عمليات معلقة وتنظيف الذاكرة
    await state.clear() 

    telegram_id = str(message.from_user.id)
    doc_ref = db.collection("merchants").document(telegram_id)
    doc = await asyncio.to_thread(doc_ref.get)
    
    # تسجيل التاجر الجديد إذا لم يكن مسجلاً
    if not doc.exists:
        short_id = str(uuid.uuid4().hex[:6]).upper()
        await asyncio.to_thread(doc_ref.set, {
            "merchant_id": short_id,
            "username": message.from_user.username,
            "is_subscribed": False,
            "total_ads_created": 0,
            "is_banned": False
        })
    else:
        # تحديث اليوزر نيم إذا تغير
        current_username = message.from_user.username
        if doc.to_dict().get("username") != current_username:
            await asyncio.to_thread(doc_ref.set, {"username": current_username}, merge=True)

    # التحقق من الاشتراك
    subscribed = await is_user_subscribed(message.bot, message.from_user.id)
    
    welcome_text = (
        f"👋 <b>مرحباً بك يا {message.from_user.first_name} في بوت الإعلانات!</b>\n\n"
        f"هذا البوت يتيح لك إنشاء إعلانات بأزرار شفافة (Inline Buttons) ومشاركتها في أي مكان بسهولة.\n\n"
        f"👇 استخدم القائمة أدناه للبدء:"
    )
    
    await message.answer(welcome_text, reply_markup=get_main_menu(subscribed), parse_mode="HTML")