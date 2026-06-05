from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import db

router = Router()

class AdCreation(StatesGroup):
    waiting_for_content = State()

@router.message(Command("create_ad"))
async def cmd_create_ad(message: types.Message, state: FSMContext):
    await message.answer("أرسل تفاصيل الإعلان الآن:")
    await state.set_state(AdCreation.waiting_for_content)

@router.message(AdCreation.waiting_for_content, F.text)
async def process_ad_content(message: types.Message, state: FSMContext):
    telegram_id = str(message.from_user.id)
    doc = db.collection("merchants").document(telegram_id).get()
    
    if not doc.exists:
        await message.answer("يجب التسجيل أولاً عبر /start")
        await state.clear()
        return

    merchant_id = doc.to_dict().get("merchant_id")
    
    # حفظ الإعلان في Firestore
    ad_ref = db.collection("ads").document()
    ad_ref.set({
        "ad_id": ad_ref.id,
        "merchant_id": merchant_id,
        "content": message.text,
        "status": "active"
    })
    
    await message.answer(f"تم حفظ إعلانك بنجاح!\nرقم الإعلان الداخلي: {ad_ref.id[:8]}")
    await state.clear()
    
@router.message(Command("my_ads"))
async def cmd_my_ads(message: types.Message):
    telegram_id = str(message.from_user.id)
    doc = db.collection("merchants").document(telegram_id).get()
    
    if not doc.exists:
        await message.answer("الرجاء الضغط على /start أولاً لتسجيلك في النظام.")
        return

    merchant_id = doc.to_dict().get("merchant_id")
    
    # جلب إعلانات التاجر فقط
    ads_query = db.collection("ads").where("merchant_id", "==", merchant_id).stream()
    
    ads_list = list(ads_query)
    if not ads_list:
        await message.answer("ليس لديك إعلانات مسجلة حالياً.")
        return
        
    response = "إعلاناتك المسجلة:\n"
    for ad in ads_list:
        ad_data = ad.to_dict()
        response += f"- إعلان رقم {ad_data.get('ad_id')[:8]} | الحالة: {ad_data.get('status')}\n"
        
    await message.answer(response)