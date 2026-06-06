from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InlineQuery, InlineQueryResultArticle, InputTextMessageContent, InlineQueryResultCachedPhoto
from database import db

router = Router()

# ================= حالات البوت =================
class AdForm(StatesGroup):
    waiting_for_content = State()
    waiting_for_buttons = State()
    waiting_for_edit_content = State()
    waiting_for_edit_buttons = State()

# ================= الدوال المساعدة =================
def get_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ إنشاء إعلان جديد", callback_data="create_ad")],
        [InlineKeyboardButton(text="📋 إعلاناتي", callback_data="list_ads")]
    ])

def get_ad_controls(doc_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ تعديل المحتوى (صورة/وصف)", callback_data=f"edit_content_{doc_id}")],
        [InlineKeyboardButton(text="🔘 تعديل الأزرار", callback_data=f"edit_buttons_{doc_id}")],
        [InlineKeyboardButton(text="🗑️ حذف الإعلان", callback_data=f"delete_ad_{doc_id}")],
        [InlineKeyboardButton(text="🔙 رجوع للقائمة", callback_data="list_ads")]
    ])

def get_merchant_id(telegram_id: str):
    doc = db.collection("merchants").document(telegram_id).get()
    return doc.to_dict().get("merchant_id") if doc.exists else None

def build_ad_markup(buttons_data):
    """تحويل مصفوفة الأزرار من قاعدة البيانات إلى أزرار تيليجرام"""
    keyboard = []
    if buttons_data:
        for row in buttons_data:
            kb_row = [InlineKeyboardButton(text=btn['text'], url=btn['url']) for btn in row]
            keyboard.append(kb_row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None

def parse_buttons(text: str):
    """استخراج الأزرار من النص المدخل. الحد الأقصى 3 لكل سطر."""
    buttons_data = []
    for line in text.split('\n'):
        row = []
        for part in line.split('|')[:3]: # قصر العدد على 3 في السطر
            if '-' in part:
                btn_text, btn_url = part.split('-', 1)
                # التأكد من أنه رابط صالح لتجنب أخطاء تيليجرام
                if btn_url.strip().startswith(('http://', 'https://', 't.me/')):
                    row.append({'text': btn_text.strip(), 'url': btn_url.strip()})
        if row:
            buttons_data.append(row)
    return buttons_data

# ================= إنشاء الإعلان =================
@router.callback_query(F.data == "create_ad")
async def start_creating_ad(callback: types.CallbackQuery, state: FSMContext):
    merchant_id = get_merchant_id(str(callback.from_user.id))
    
    ads = list(db.collection("ads").where("merchant_id", "==", merchant_id).stream())
    if len(ads) >= 5:
        await callback.answer("❌ الحد الأقصى 5 إعلانات. احذف إعلاناً لإضافة جديد.", show_alert=True)
        return

    await callback.message.edit_text("أرسل <b>صورة مع الوصف</b>، أو <b>الوصف فقط</b> الآن:", parse_mode="HTML")
    await state.set_state(AdForm.waiting_for_content)

@router.message(AdForm.waiting_for_content, F.text | F.photo)
async def process_content(message: types.Message, state: FSMContext):
    # استخراج النص (سواء كان رسالة عادية أو وصف لصورة)
    text = message.text or message.caption or ""
    # استخراج معرف الصورة إذا وجدت
    photo_id = message.photo[-1].file_id if message.photo else None
    
    await state.update_data(description=text, photo_id=photo_id)
    
    instruction = (
        "✅ تم حفظ المحتوى.\n\n"
        "هل تود إضافة أزرار أسفل الإعلان؟\n"
        "أرسل الأزرار بهذا التنسيق (كل سطر يمثل صف، بحد أقصى 3 أزرار مفصولة بـ |):\n\n"
        "<code>النص - الرابط | النص - الرابط | النص - الرابط</code>\n"
        "<code>النص - الرابط</code>"
    )
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ تخطي (بدون أزرار)", callback_data="skip_buttons")]
    ])
    
    await message.answer(instruction, parse_mode="HTML", reply_markup=markup)
    await state.set_state(AdForm.waiting_for_buttons)

async def save_ad(message: types.Message, state: FSMContext, buttons_data=None):
    data = await state.get_data()
    merchant_id = get_merchant_id(str(message.from_user.id))
    buttons_data = buttons_data or []
    
    if data.get('editing_doc_id'):
        # تحديث إعلان موجود
        doc_id = data['editing_doc_id']
        update_data = {}
        if 'description' in data: update_data['description'] = data['description']
        if 'photo_id' in data: update_data['photo_id'] = data['photo_id']
        if buttons_data is not None and not 'description' in data: 
            update_data['buttons'] = buttons_data
            
        db.collection("ads").document(doc_id).update(update_data)
        short_id = db.collection("ads").document(doc_id).get().to_dict().get('ad_id')
        await message.answer(f"✅ تم التحديث بنجاح! رقم الإعلان: <code>{short_id}</code>", parse_mode="HTML", reply_markup=get_main_menu())
    else:
        # إنشاء إعلان جديد
        ad_ref = db.collection("ads").document()
        short_id = ad_ref.id[:6].upper()
        ad_ref.set({
            "doc_id": ad_ref.id,
            "ad_id": short_id,
            "merchant_id": merchant_id,
            "description": data.get('description', ''),
            "photo_id": data.get('photo_id'),
            "buttons": buttons_data
        })
        
        success_text = (
            f"✅ <b>تم إنشاء إعلانك بنجاح!</b>\n\n"
            f"🆔 <b>رقم الإعلان:</b> <code>{short_id}</code>\n\n"
            f"اذهب لأي محادثة واكتب يوزر البوت ثم رقم إعلانك لنشره."
        )
        await message.answer(success_text, parse_mode="HTML", reply_markup=get_main_menu())
        
    await state.clear()

@router.message(AdForm.waiting_for_buttons, F.text)
async def process_buttons(message: types.Message, state: FSMContext):
    buttons_data = parse_buttons(message.text)
    await save_ad(message, state, buttons_data)

@router.callback_query(F.data == "skip_buttons")
async def skip_buttons_callback(callback: types.CallbackQuery, state: FSMContext):
    await save_ad(callback.message, state, [])
    await callback.answer()

# ================= عرض الإعلانات =================
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
        # عرض أول 15 حرف من الوصف كعنوان للإعلان في القائمة
        short_desc = ad_data.get('description', 'إعلان بصورة')[:15] + "..."
        keyboard.append([InlineKeyboardButton(text=f"📢 {short_desc} ({ad_data['ad_id']})", callback_data=f"view_ad_{ad_data['doc_id']}")])
    
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
    desc = ad.get('description', '')
    photo_id = ad.get('photo_id')
    buttons = ad.get('buttons', [])
    markup = build_ad_markup(buttons)
    
    # حذف الرسالة السابقة لترتيب الشاشة
    await callback.message.delete()
    
    # إرسال شكل الإعلان الفعلي
    if photo_id:
        await callback.message.answer_photo(photo=photo_id, caption=desc, reply_markup=markup)
    else:
        await callback.message.answer(desc or "بدون نص", reply_markup=markup)
        
    # إرسال لوحة التحكم
    await callback.message.answer(f"⚙️ <b>أدوات التحكم بالإعلان ({ad['ad_id']})</b>", parse_mode="HTML", reply_markup=get_ad_controls(doc_id))

# ================= تعديل وحذف =================
@router.callback_query(F.data.startswith("delete_ad_"))
async def delete_ad(callback: types.CallbackQuery):
    doc_id = callback.data.split("delete_ad_")[1]
    db.collection("ads").document(doc_id).delete()
    await callback.answer("✅ تم الحذف!", show_alert=True)
    await list_my_ads(callback)

@router.callback_query(F.data.startswith("edit_content_"))
async def edit_content_prompt(callback: types.CallbackQuery, state: FSMContext):
    doc_id = callback.data.split("edit_content_")[1]
    await state.update_data(editing_doc_id=doc_id)
    await callback.message.answer("أرسل <b>الصورة والوصف الجديد</b>، أو <b>الوصف فقط</b>:", parse_mode="HTML")
    await state.set_state(AdForm.waiting_for_edit_content)

@router.message(AdForm.waiting_for_edit_content, F.text | F.photo)
async def process_edit_content(message: types.Message, state: FSMContext):
    text = message.text or message.caption or ""
    photo_id = message.photo[-1].file_id if message.photo else None
    
    await state.update_data(description=text, photo_id=photo_id)
    # الاحتفاظ بالأزرار القديمة كما هي، وتمرير None للأزرار ليقوم بالتخطي في دالة الحفظ
    await save_ad(message, state, None)

@router.callback_query(F.data.startswith("edit_buttons_"))
async def edit_buttons_prompt(callback: types.CallbackQuery, state: FSMContext):
    doc_id = callback.data.split("edit_buttons_")[1]
    await state.update_data(editing_doc_id=doc_id)
    
    instruction = (
        "أرسل الأزرار الجديدة (ستستبدل الأزرار القديمة).\n"
        "صيغة الإرسال (حتى 3 أزرار في السطر):\n"
        "<code>النص - الرابط | النص - الرابط</code>\n\n"
        "لإزالة كل الأزرار اضغط تخطي."
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➡️ إزالة الأزرار (تخطي)", callback_data="skip_buttons")]])
    await callback.message.answer(instruction, parse_mode="HTML", reply_markup=markup)
    await state.set_state(AdForm.waiting_for_edit_buttons)

@router.message(AdForm.waiting_for_edit_buttons, F.text)
async def process_edit_buttons(message: types.Message, state: FSMContext):
    buttons_data = parse_buttons(message.text)
    await save_ad(message, state, buttons_data)

# ================= وضع الإنلاين =================
@router.inline_query()
async def inline_ad_search(inline_query: InlineQuery):
    query = inline_query.query.strip().upper()
    if not query: return

    ads_query = db.collection("ads").where("ad_id", "==", query).limit(1).stream()
    ads_list = list(ads_query)
    if not ads_list: return

    ad_data = ads_list[0].to_dict()
    desc = ad_data.get('description', '')
    photo_id = ad_data.get('photo_id')
    markup = build_ad_markup(ad_data.get('buttons', []))

    # إنشاء عنوان مختصر للنتيجة في قائمة الإنلاين
    title_text = desc[:30] + "..." if desc else "إعلان بصورة"

    if photo_id:
        result = InlineQueryResultCachedPhoto(
            id=ad_data['doc_id'],
            photo_file_id=photo_id,
            title=f"إعلان: {title_text}",
            caption=desc,
            reply_markup=markup
        )
    else:
        result = InlineQueryResultArticle(
            id=ad_data['doc_id'],
            title=f"إعلان: {title_text}",
            description="اضغط للنشر",
            input_message_content=InputTextMessageContent(message_text=desc, parse_mode="HTML"),
            reply_markup=markup
        )
        
    await inline_query.answer([result], cache_time=5)