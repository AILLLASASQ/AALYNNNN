import time
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, slow_mode_delay=3.0):
        self.user_timeouts = {}
        self.slow_mode_delay = slow_mode_delay

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user_id = None
        
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id

        if user_id:
            current_time = time.time()
            last_time = self.user_timeouts.get(user_id, 0)
            
            # إذا كانت المدة بين الضغطتين أقل من المسموح
            if current_time - last_time < self.slow_mode_delay:
                if isinstance(event, CallbackQuery):
                    # إرسال تنبيه منبثق عند الضغط على زر
                    await event.answer("⏳ يرجى الانتظار بضع ثوانٍ بين كل ضغطة وأخرى.", show_alert=True)
                # تجاهل الطلب تماماً وعدم تمريره للكود
                return 
            
            # تحديث وقت آخر استخدام
            self.user_timeouts[user_id] = current_time

        return await handler(event, data)