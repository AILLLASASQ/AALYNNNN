from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db

router = Router()

# ================= حالات البوت (FSM) =================
class AdForm(StatesGroup):
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_edit_title = State()
    waiting_for_edit_description = State()

# ================= الدوال المساعدة =================
def get_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ إنشاء إعلان جديد", callback_data="create_ad")],
        [InlineKeyboardButton(text="📋 إعلاناتي", callback_data="list_ads")]
    ])

def get_ad_controls(ad_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ تعديل العنوان", callback_data=f"edit_title_{ad_id}"),
         InlineKeyboardButton(text="📝 تعديل الوصف", callback_data=f"edit_desc_{ad_id}")],
        [InlineKeyboardButton(text="🗑️ حذف الإعلان", callback_data=f"delete_ad_{ad_id}")],
        [InlineKeyboardButton(text="🔙 رجوع للقائمة", callback_data="list_ads")]
    ])

def get_merchant_id(telegram_id: str):
    doc = db.collection("merchants").document(telegram_id).get()
    return doc.to_dict().get("merchant_id") if doc.exists else None

# ================= إنشاء الإعلان =================
@router.callback_query(F.data == "create_ad")
async def start_creating_ad(callback: types.CallbackQuery, state: FSMContext):
    merchant_id = get_merchant_id(str(callback.from_user.id))
    
    # التحقق من الحد الأقصى للإعلانات
    ads = list(db.collection("ads").where("merchant_id", "==", merchant_id).stream())
    if len(ads) >= 5:
        await callback.answer("❌ عذراً، لقد وصلت للحد الأقصى (5 إعلانات). يرجى حذف إعلان لإضافة جديد.", show_alert=True)
        return

    await callback.message.edit_text("أرسل <b>عنوان</b> الإعلان الآن (مثال: حساب للبيع):", parse_mode="HTML")
    await state.set_state(AdForm.waiting_for_title)

@router.message(AdForm.waiting_for_title, F.text)
async def process_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("ممتاز! الآن أرسل <b>وصف</b> الإعلان (التفاصيل، السعر، إلخ):", parse_mode="HTML")
    await state.set_state(AdForm.waiting_for_description)

@router.message(AdForm.waiting_for_description, F.text)
async def process_description(message: types.Message, state: FSMContext):
    data = await state.get_data()
    merchant_id = get_merchant_id(str(message.from_user.id))
    
    # حفظ الإعلان في فايربيس
    ad_ref = db.collection("ads").document()
    short_id = ad_ref.id[:6].upper() # رقم إعلان قصير للعملاء
    
    ad_ref.set({
        "doc_id": ad_ref.id,
        "ad_id": short_id,
        "merchant_id": merchant_id,
        "title": data['title'],
        "description": message.text,
    })

    success_text = (
        f"✅ <b>تم إنشاء إعلانك بنجاح!</b>\n\n"
        f"🆔 <b>رقم الإعلان:</b> <code>{short_id}</code>\n\n"
        f"📌 <b>طريقة الاستخدام:</b>\n"
        f"قم بنسخ (رقم الإعلان) وشاركه مع عملائك، أو اربطه بالمتجر الخاص بك. "
        f"أي شخص يبحث عن هذا الرقم ستظهر له تفاصيل إعلانك مباشرة."
    )
    
    await message.answer(success_text, parse_mode="HTML", reply_markup=get_main_menu())
    await state.clear()

# ================= عرض الإعلانات =================
@router.callback_query(F.data == "list_ads")
async def list_my_ads(callback: types.CallbackQuery):
    merchant_id = get_merchant_id(str(callback.from_user.id))
    ads = list(db.collection("ads").where("merchant_id", "==", merchant_id).stream())
    
    if not ads:
        await callback.message.edit_text("ليس لديك أي إعلانات حالياً.", reply_markup=get_main_menu())
        return

    keyboard = []
    for ad in ads:
        ad_data = ad.to_dict()
        keyboard.append([InlineKeyboardButton(text=f"📢 {ad_data['title']} ({ad_data['ad_id']})", callback_data=f"view_ad_{ad_data['doc_id']}")])
    
    keyboard.append([InlineKeyboardButton(text="➕ إنشاء إعلان جديد", callback_data="create_ad")])
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text("📋 <b>قائمة إعلاناتك:</b>\nاضغط على الإعلان لإدارته:", parse_mode="HTML", reply_markup=markup)

# ================= عرض تفاصيل الإعلان =================
@router.callback_query(F.data.startswith("view_ad_"))
async def view_ad_details(callback: types.CallbackQuery):
    doc_id = callback.data.split("view_ad_")[1]
    doc = db.collection("ads").document(doc_id).get()
    
    if not doc.exists:
        await callback.answer("❌ هذا الإعلان لم يعد موجوداً.", show_alert=True)
        return
        
    ad = doc.to_dict()
    text = (
        f"🆔 <b>رقم الإعلان:</b> <code>{ad['ad_id']}</code>\n"
        f"📌 <b>العنوان:</b> {ad['title']}\n"
        f"📝 <b>الوصف:</b>\n{ad['description']}\n"
    )
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_ad_controls(doc_id))

# ================= حذف الإعلان =================
@router.callback_query(F.data.startswith("delete_ad_"))
async def delete_ad(callback: types.CallbackQuery):
    doc_id = callback.data.split("delete_ad_")[1]
    db.collection("ads").document(doc_id).delete()
    await callback.answer("✅ تم حذف الإعلان بنجاح!", show_alert=True)
    await list_my_ads(callback) # العودة لقائمة الإعلانات

# ================= تعديل العنوان =================
@router.callback_query(F.data.startswith("edit_title_"))
async def edit_title_prompt(callback: types.CallbackQuery, state: FSMContext):
    doc_id = callback.data.split("edit_title_")[1]
    await state.update_data(editing_doc_id=doc_id)
    await callback.message.edit_text("أرسل <b>العنوان الجديد</b> للإعلان الآن:", parse_mode="HTML")
    await state.set_state(AdForm.waiting_for_edit_title)

@router.message(AdForm.waiting_for_edit_title, F.text)
async def save_new_title(message: types.Message, state: FSMContext):
    data = await state.get_data()
    doc_id = data['editing_doc_id']
    
    db.collection("ads").document(doc_id).update({"title": message.text})
    await message.answer("✅ تم تحديث العنوان بنجاح!", reply_markup=get_main_menu())
    await state.clear()

# ================= تعديل الوصف =================
@router.callback_query(F.data.startswith("edit_desc_"))
async def edit_desc_prompt(callback: types.CallbackQuery, state: FSMContext):
    doc_id = callback.data.split("edit_desc_")[1]
    await state.update_data(editing_doc_id=doc_id)
    await callback.message.edit_text("أرسل <b>الوصف الجديد</b> للإعلان الآن:", parse_mode="HTML")
    await state.set_state(AdForm.waiting_for_edit_description)

@router.message(AdForm.waiting_for_edit_description, F.text)
async def save_new_desc(message: types.Message, state: FSMContext):
    data = await state.get_data()
    doc_id = data['editing_doc_id']
    
    db.collection("ads").document(doc_id).update({"description": message.text})
    await message.answer("✅ تم تحديث الوصف بنجاح!", reply_markup=get_main_menu())
    await state.clear()