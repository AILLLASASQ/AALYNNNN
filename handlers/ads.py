from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InlineQuery, InlineQueryResultArticle, InputTextMessageContent
from database import db

router = Router()

class AdForm(StatesGroup):
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_edit_title = State()
    waiting_for_edit_description = State()

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

@router.callback_query(F.data == "create_ad")
async def start_creating_ad(callback: types.CallbackQuery, state: FSMContext):
    merchant_id = get_merchant_id(str(callback.from_user.id))
    
    ads = list(db.collection("ads").where("merchant_id", "==", merchant_id).stream())
    if len(ads) >= 5:
        await callback.answer("❌ الحد الأقصى 5 إعلانات. احذف إعلاناً لإضافة جديد.", show_alert=True)
        return

    await callback.message.edit_text("أرسل <b>عنوان</b> الإعلان الآن:", parse_mode="HTML")
    await state.set_state(AdForm.waiting_for_title)

@router.message(AdForm.waiting_for_title, F.text)
async def process_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("أرسل <b>وصف</b> الإعلان الآن:", parse_mode="HTML")
    await state.set_state(AdForm.waiting_for_description)

@router.message(AdForm.waiting_for_description, F.text)
async def process_description(message: types.Message, state: FSMContext):
    data = await state.get_data()
    merchant_id = get_merchant_id(str(message.from_user.id))
    
    ad_ref = db.collection("ads").document()
    short_id = ad_ref.id[:6].upper()
    
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
        f"اذهب لأي محادثة واكتب يوزر البوت ثم رقم إعلانك لنشره مباشرة."
    )
    
    await message.answer(success_text, parse_mode="HTML", reply_markup=get_main_menu())
    await state.clear()

@router.callback_query(F.data == "list_ads")
async def list_my_ads(callback: types.CallbackQuery):
    merchant_id = get_merchant_id(str(callback.from_user.id))
    ads = list(db.collection("ads").where("merchant_id", "==", merchant_id).stream())
    
    if not ads:
        await callback.message.edit_text("ليس لديك إعلانات حالياً.", reply_markup=get_main_menu())
        return

    keyboard = []
    for ad in ads:
        ad_data = ad.to_dict()
        keyboard.append([InlineKeyboardButton(text=f"📢 {ad_data['title']}", callback_data=f"view_ad_{ad_data['doc_id']}")])
    
    keyboard.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="start_menu")])
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text("📋 <b>قائمة إعلاناتك:</b>", parse_mode="HTML", reply_markup=markup)

@router.callback_query(F.data == "start_menu")
async def return_to_start(callback: types.CallbackQuery):
    await callback.message.edit_text("اختر ما تود القيام به:", reply_markup=get_main_menu())

@router.callback_query(F.data.startswith("view_ad_"))
async def view_ad_details(callback: types.CallbackQuery):
    doc_id = callback.data.split("view_ad_")[1]
    doc = db.collection("ads").document(doc_id).get()
    
    if not doc.exists:
        await callback.answer("❌ الإعلان غير موجود.", show_alert=True)
        return
        
    ad = doc.to_dict()
    text = f"🆔 <b>رقم الإعلان:</b> <code>{ad['ad_id']}</code>\n📌 <b>العنوان:</b> {ad['title']}\n📝 <b>الوصف:</b>\n{ad['description']}"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_ad_controls(doc_id))

@router.callback_query(F.data.startswith("delete_ad_"))
async def delete_ad(callback: types.CallbackQuery):
    doc_id = callback.data.split("delete_ad_")[1]
    db.collection("ads").document(doc_id).delete()
    await callback.answer("✅ تم الحذف!", show_alert=True)
    await list_my_ads(callback)

@router.callback_query(F.data.startswith("edit_title_"))
async def edit_title_prompt(callback: types.CallbackQuery, state: FSMContext):
    doc_id = callback.data.split("edit_title_")[1]
    await state.update_data(editing_doc_id=doc_id)
    await callback.message.edit_text("أرسل <b>العنوان الجديد</b>:", parse_mode="HTML")
    await state.set_state(AdForm.waiting_for_edit_title)

@router.message(AdForm.waiting_for_edit_title, F.text)
async def save_new_title(message: types.Message, state: FSMContext):
    data = await state.get_data()
    db.collection("ads").document(data['editing_doc_id']).update({"title": message.text})
    await message.answer("✅ تم تحديث العنوان!", reply_markup=get_main_menu())
    await state.clear()

@router.callback_query(F.data.startswith("edit_desc_"))
async def edit_desc_prompt(callback: types.CallbackQuery, state: FSMContext):
    doc_id = callback.data.split("edit_desc_")[1]
    await state.update_data(editing_doc_id=doc_id)
    await callback.message.edit_text("أرسل <b>الوصف الجديد</b>:", parse_mode="HTML")
    await state.set_state(AdForm.waiting_for_edit_description)

@router.message(AdForm.waiting_for_edit_description, F.text)
async def save_new_desc(message: types.Message, state: FSMContext):
    data = await state.get_data()
    db.collection("ads").document(data['editing_doc_id']).update({"description": message.text})
    await message.answer("✅ تم تحديث الوصف!", reply_markup=get_main_menu())
    await state.clear()

@router.inline_query()
async def inline_ad_search(inline_query: InlineQuery):
    query = inline_query.query.strip().upper()
    if not query: return

    ads_query = db.collection("ads").where("ad_id", "==", query).limit(1).stream()
    ads_list = list(ads_query)
    if not ads_list: return

    ad_data = ads_list[0].to_dict()
    ad_text = f"📢 <b>{ad_data['title']}</b>\n\n📝 {ad_data['description']}\n\n🆔 <b>رقم الإعلان:</b> <code>{ad_data['ad_id']}</code>"

    result = InlineQueryResultArticle(
        id=ad_data['doc_id'],
        title=f"إعلان: {ad_data['title']}",
        description="اضغط للنشر",
        input_message_content=InputTextMessageContent(message_text=ad_text, parse_mode="HTML")
    )
    await inline_query.answer([result], cache_time=5)