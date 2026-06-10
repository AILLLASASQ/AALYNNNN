from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery, InlineQuery
from database import db
import asyncio

class BanMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        user_id = None
        
        # استخراج الآيدي بناءً على نوع الحدث
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
        elif isinstance(event, InlineQuery):
            user_id = event.from_user.id

        if user_id:
            # فحص حالة الحظر من قاعدة البيانات
            doc = await asyncio.to_thread(db.collection("merchants").document(str(user_id)).get)
            if doc.exists and doc.to_dict().get("is_banned", False):
                
                # الرد المناسب بناءً على المكان الذي حاول التاجر استخدامه
                if isinstance(event, Message):
                    await event.answer("🚫 <b>حسابك محظور من استخدام البوت.</b>\nيرجى التواصل مع الإدارة.", parse_mode="HTML")
                elif isinstance(event, CallbackQuery):
                    await event.answer("🚫 حسابك محظور!", show_alert=True)
                elif isinstance(event, InlineQuery):
                    # إرجاع نتيجة فارغة في وضع الإنلاين لمنع ظهور إعلاناته
                    await event.answer([], cache_time=1, is_personal=True)
                
                # إيقاف العملية ومنعها من الوصول لأي كود آخر
                return 

        # في حال لم يكن محظوراً، نمرر الطلب ليعمل البوت بشكل طبيعي
        return await handler(event, data)