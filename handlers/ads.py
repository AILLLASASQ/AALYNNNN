import json
import asyncio
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InlineQuery, InlineQueryResultArticle, InputTextMessageContent, InlineQueryResultCachedPhoto
from aiogram.exceptions import TelegramBadRequest
from database import db

router = Router()

# ================= حالات البوت (FSM) =================
class AdForm(StatesGroup):
    waiting_for_content = State()
    waiting_for_edit_content = State()
    waiting_for_btn_text = State()
    waiting_for_btn_url = State()

# ================= دوال قاعدة البيانات (مساعدة للتزامن) =================
def fetch_ads_by_merchant(merchant_id):
    return list(db.collection("ads").where("merchant_id", "==", merchant_id).stream())

def search_ad_by_id(query):
    return list(db.collection("ads").where("ad_id", "==", query).limit(1).stream())

# ================= الدوال المساعدة والترتيب =================
def truncate_text(text, max_len=15):
    """دالة القص البرمجي التلقائي للنصوص الطويلة"""
    if not text: return "زر"
    text = str(text)
    return text[:max_len] + "..." if len(text) > max_len else text

def normalize_buttons(buttons_data):
    """استرجاع النظام اليدوي: احترام ترتيب التاجر بدون دمج تلقائي إجباري"""
    if not buttons_data: return []
    if isinstance(buttons_data, str):
        try: buttons_data = json.loads(buttons_data)
        except: return []
            
    if not buttons_data: return []
    
    # إذا كانت البيانات بالفعل مصفوفة داخل مصفوفة (الوضع الصحيح للترتيب اليدوي)
    if isinstance(buttons_data[0], list): 
        return buttons_data
        
    # حماية من أي أخطاء سابقة: وضع كل زر في سطر كافتراضي
    return [[b] for b in buttons_data]

# ================= بناء واجهات الكيبورد =================
def get_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ إنشاء إعلان جديد", callback_data="create_ad")],
        [InlineKeyboardButton(text="📋 إعلاناتي", callback_data="list_ads")],
        [InlineKeyboardButton(text="ℹ️ شرح الاستخدام", callback_data="help_usage")]
    ])

def build_ad_markup(buttons_list):
    """الكيبورد النهائي عند النشر (للعملاء)"""
    buttons_list = normalize_buttons(buttons_list)
    keyboard = []
    for row in buttons_list:
        keyboard.append([InlineKeyboardButton(text=truncate_text(btn['text']), url=btn['url']) for btn in row])
    return InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None

def build_merged_keyboard(buttons_list, doc_id):
    """كيبورد إدارة الإعلان للتاجر"""
    buttons_list = normalize_buttons(buttons_list)
    keyboard = []
    
    for row in buttons_list:
        keyboard.append([InlineKeyboardButton(text=truncate_text(btn['text']), url=btn['url']) for btn in row])
        
    keyboard.append([InlineKeyboardButton(text="--- أدوات الإدارة ---", callback_data="ignore_btn")])
    
    keyboard.append([
        InlineKeyboardButton(text="✏️ المحتوى", callback_data=f"edit_content_{doc_id}"),
        InlineKeyboardButton(text="🔘 الأزرار", callback_data=f"edit_buttons_{doc_id}")
    ])
    keyboard.append([
        InlineKeyboardButton(text="🗑️ حذف", callback_data=f"delete_ad_{doc_id}"),
        InlineKeyboardButton(text="🔙 رجوع", callback_data="list_ads")
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def build_draft_keyboard(buttons_list):
    """كيبورد المسودة النهائي"""
    buttons_list = normalize_buttons(buttons_list)
    keyboard = []
    
    for row in buttons_list:
        keyboard.append([InlineKeyboardButton(text=truncate_text(btn['text']), url=btn['url']) for btn in row])
        
    keyboard.append([InlineKeyboardButton(text="--- خيارات المسودة ---", callback_data="ignore_btn")])
    keyboard.append([
        InlineKeyboardButton(text="✅ نشر", callback_data="publish_ad"),
        InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_ad")
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

async def get_merchant_id(telegram_id: str):
    doc = await asyncio.to_thread(db.collection("merchants").document(telegram_id).get)
    return doc.to_dict().get("merchant_id") if doc.exists else None

# ================= التفاعل مع الزر الوهمي وشرح الاستخدام =================
@router.callback_query(F.data == "ignore_btn")
async def ignore_btn_click(callback: types.CallbackQuery):
    await callback.answer("زر فاصِل ⚙️")

@router.callback_query(F.data == "help_usage")
async def show_help(callback: types.CallbackQuery):
    help_text = (
        "📚 <b>دليل الاستخدام:</b>\n\n"
        "1️⃣ <b>الإنشاء:</b> اضغط إنشاء، وأرسل المحتوى، ثم أرسل أسماء وروابط الأزرار بالترتيب.\n"
        "2️⃣ <b>النشر:</b> بعد الحفظ، اكتب يوزر البوت ثم رقم الإعلان في أي محادثة لنشره.\n"
        "   <i>مثال:</i> <code>@يوزر_البوت 1A2B3C</code>\n\n"
        "💡 <i>الحد الأقصى 5 إعلانات.</i>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 رجوع", callback_data="start_menu")]])
    await callback.message.edit_text(help_text, parse_mode="HTML", reply_markup=markup)
    await callback.answer()

# ================= نظام المسودة وتخصيص الأزرار =================
@router.callback_query(F.data == "create_ad")
async def start_creating_ad(callback: types.CallbackQuery, state: FSMContext):
    merchant_id = await get_merchant_id(str(callback.from_user.id))
    ads = await asyncio.to_thread(fetch_ads_by_merchant, merchant_id)
    
    if len(ads) >= 5:
        await callback.answer("❌ الحد الأقصى 5 إعلانات. احذف إعلاناً لإضافة جديد.", show_alert=True)
        return

    await callback.message.edit_text("أرسل <b>صورة مع الوصف</b>، أو <b>الوصف فقط</b>:", parse_mode="HTML")
    await state.set_state(AdForm.waiting_for_content)

@router.message(AdForm.waiting_for_content, F.text | F.photo)
async def process_content(message: types.Message, state: FSMContext):
    text = message.text or message.caption or ""
    photo_id = message.photo[-1].file_id if message.photo else None
    
    # تعيين start_new_row=True بشكل افتراضي لأول زر
    await state.update_data(description=text, photo_id=photo_id, buttons=[], start_new_row=True)
    await message.answer("✅ تم حفظ المحتوى.\n\nالآن أرسل <b>اسم الزر الأول</b> (مثال: شراء).\nإذا كنت لا تريد إضافة أزرار، أرسل /done", parse_mode="HTML")
    await state.set_state(AdForm.waiting_for_btn_text)

@router.message(AdForm.waiting_for_btn_text, F.text)
async def process_btn_text(message: types.Message, state: FSMContext):
    if message.text.strip().lower() == '/done':
        await show_final_draft(message, state)
        return
        
    await state.update_data(current_btn_text=message.text)
    await message.answer(f"🔗 ممتاز. أرسل الآن <b>رابط الزر</b> (https:// أو t.me/):", parse_mode="HTML")
    await state.set_state(AdForm.waiting_for_btn_url)

@router.message(AdForm.waiting_for_btn_url, F.text)
async def process_btn_url(message: types.Message, state: FSMContext):
    url = message.text.strip()
    if not url.startswith(('https://', 't.me/')) or len(url) < 10:
        await message.answer("❌ الرابط غير صحيح. يجب أن يبدأ بـ <b>https://</b> أو <b>t.me/</b> ويكون كاملاً.\nأرسل الرابط مجدداً:", parse_mode="HTML")
        return

    data = await state.get_data()
    buttons = data.get('buttons', [])
    current_text = data.get('current_btn_text', 'زر')
    start_new_row = data.get('start_new_row', True)
    
    new_btn = {'text': current_text, 'url': url}
    
    # نظام إضافة الأزرار اليدوي الدقيق
    if start_new_row or not buttons:
        buttons.append([new_btn])
    else:
        # السماح بحد أقصى زرين في السطر للحفاظ على التنسيق
        if len(buttons[-1]) < 2:
            buttons[-1].append(new_btn)
        else:
            buttons.append([new_btn]) # إجبار النزول لسطر جديد إذا امتلأ السطر

    await state.update_data(buttons=buttons)
    
    # سؤال المستخدم عن مكان الزر القادم لإعطائه التحكم المطلق
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⬅️ زر بجانبه", callback_data="add_btn_same"),
            InlineKeyboardButton(text="⏬ سطر جديد", callback_data="add_btn_new")
        ],
        [InlineKeyboardButton(text="✅ إنهاء الأزرار والمعاينة", callback_data="finish_btn_setup")]
    ])
    
    await message.answer(f"✅ تم إضافة زر ( {current_text} ).\nأين تريد وضع الزر القادم؟", reply_markup=markup)
    await state.set_state(None) # تجميد الإدخال النصي حتى يختار

@router.callback_query(F.data.in_({"add_btn_same", "add_btn_new"}))
async def prompt_next_btn(callback: types.CallbackQuery, state: FSMContext):
    is_new_row = (callback.data == "add_btn_new")
    await state.update_data(start_new_row=is_new_row)
    
    try: await callback.message.delete() # مسح الكيبورد الصغير للحفاظ على نظافة المحادثة
    except TelegramBadRequest: pass
    
    await callback.message.answer("✏️ أرسل <b>اسم الزر التالي</b>:", parse_mode="HTML")
    await state.set_state(AdForm.waiting_for_btn_text)
    await callback.answer()

@router.callback_query(F.data == "finish_btn_setup")
async def finish_btn_setup(callback: types.CallbackQuery, state: FSMContext):
    try: await callback.message.delete()
    except TelegramBadRequest: pass
    await show_final_draft(callback.message, state)
    await callback.answer()

# ================= عرض المسودة والحفظ =================
async def show_final_draft(message: types.Message, state: FSMContext):
    data = await state.get_data()
    desc = data.get('description', '')
    photo_id = data.get('photo_id')
    buttons = data.get('buttons', [])

    markup = build_draft_keyboard(buttons)
    text_preview = f"👀 <b>معاينة الإعلان النهائي:</b>\n\n{desc}" if desc else "👀 <b>معاينة الإعلان النهائي:</b>\nبدون نص"

    if photo_id:
        await message.answer_photo(photo=photo_id, caption=text_preview, reply_markup=markup, parse_mode="HTML")
    else:
        await message.answer(text_preview, reply_markup=markup, parse_mode="HTML")
        
    await state.set_state(None)

@router.callback_query(F.data == "publish_ad")
async def publish_ad(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data:
        await callback.answer("❌ انتهت صلاحية المسودة.", show_alert=True)
        return
        
    merchant_id = await get_merchant_id(str(callback.from_user.id))
    buttons_json = json.dumps(normalize_buttons(data.get('buttons', [])))
    
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except: pass

    if data.get('editing_doc_id'):
        doc_id = data['editing_doc_id']
        update_data = {
            "description": data.get('description', ''),
            "photo_id": data.get('photo_id'),
            "buttons": buttons_json 
        }
        await asyncio.to_thread(db.collection("ads").document(doc_id).set, update_data, merge=True)
        short_id = data.get('ad_id') or doc_id[:6].upper()
        await callback.message.answer(f"✅ تم التحديث بنجاح! رقم الإعلان: <code>{short_id}</code>", parse_mode="HTML", reply_markup=get_main_menu())
    else:
        ad_ref = db.collection("ads").document()
        short_id = ad_ref.id[:6].upper()
        new_data = {
            "doc_id": ad_ref.id,
            "ad_id": short_id,
            "merchant_id": merchant_id,
            "description": data.get('description', ''),
            "photo_id": data.get('photo_id'),
            "buttons": buttons_json 
        }
        await asyncio.to_thread(ad_ref.set, new_data)
        await callback.message.answer(f"✅ <b>تم النشر!</b>\nرقم الإعلان: <code>{short_id}</code>", parse_mode="HTML", reply_markup=get_main_menu())
        
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "cancel_ad")
async def cancel_ad(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try: await callback.message.delete()
    except: pass
    await callback.message.answer("❌ تم إلغاء المسودة.", reply_markup=get_main_menu())
    await callback.answer()

# ================= تعديل إعلانات سابقة =================
@router.callback_query(F.data.startswith("edit_content_"))
async def edit_content_prompt(callback: types.CallbackQuery, state: FSMContext):
    doc_id = callback.data.split("edit_content_")[1]
    doc_snapshot = await asyncio.to_thread(db.collection("ads").document(doc_id).get)
    doc = doc_snapshot.to_dict()
    
    await state.update_data(
        editing_doc_id=doc_id, 
        ad_id=doc.get('ad_id'), 
        buttons=doc.get('buttons', [])
    )
    await callback.message.answer("أرسل <b>الصورة والوصف الجديد</b>، أو <b>الوصف فقط</b>:", parse_mode="HTML")
    await state.set_state(AdForm.waiting_for_edit_content)

@router.message(AdForm.waiting_for_edit_content, F.text | F.photo)
async def process_edit_content(message: types.Message, state: FSMContext):
    text = message.text or message.caption or ""
    photo_id = message.photo[-1].file_id if message.photo else None
    
    await state.update_data(description=text, photo_id=photo_id)
    await show_final_draft(message, state)

@router.callback_query(F.data.startswith("edit_buttons_"))
async def edit_buttons_prompt(callback: types.CallbackQuery, state: FSMContext):
    doc_id = callback.data.split("edit_buttons_")[1]
    doc_snapshot = await asyncio.to_thread(db.collection("ads").document(doc_id).get)
    doc = doc_snapshot.to_dict()
    
    await state.update_data(
        editing_doc_id=doc_id,
        ad_id=doc.get('ad_id'),
        description=doc.get('description', ''),
        photo_id=doc.get('photo_id'),
        buttons=[], # مسح الأزرار القديمة
        start_new_row=True # التجهيز لإنشاء سطر جديد
    )
    await callback.message.answer("⚙️ سيتم إعادة تعيين الأزرار.\n\nأرسل <b>اسم الزر الأول</b>، أو أرسل /done لإزالة جميع الأزرار والإنهاء:", parse_mode="HTML")
    await state.set_state(AdForm.waiting_for_btn_text)
    await callback.answer()

# ================= عرض وإدارة القائمة =================
@router.callback_query(F.data == "list_ads")
async def list_my_ads(callback: types.CallbackQuery):
    merchant_id = await get_merchant_id(str(callback.from_user.id))
    ads = await asyncio.to_thread(fetch_ads_by_merchant, merchant_id)
    
    if not ads:
        try: await callback.message.edit_text("ليس لديك إعلانات حالياً.", reply_markup=get_main_menu())
        except: pass
        return

    keyboard = []
    for ad in ads:
        ad_data = ad.to_dict()
        desc = ad_data.get('description', '')
        short_desc = (str(desc)[:15].replace("\n", " ") + "...") if desc else "إعلان بصورة"
        keyboard.append([InlineKeyboardButton(text=f"📢 {short_desc} ({ad_data['ad_id']})", callback_data=f"view_ad_{ad_data['doc_id']}")])
    
    keyboard.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="start_menu")])
    try: await callback.message.edit_text("📋 <b>قائمة إعلاناتك:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    except: pass
    await callback.answer()

@router.callback_query(F.data.startswith("view_ad_"))
async def view_ad_details(callback: types.CallbackQuery):
    doc_id = callback.data.split("view_ad_")[1]
    doc_snapshot = await asyncio.to_thread(db.collection("ads").document(doc_id).get)
    
    if not doc_snapshot.exists:
        await callback.answer("❌ الإعلان غير موجود.", show_alert=True)
        return
        
    ad = doc_snapshot.to_dict()
    markup = build_merged_keyboard(ad.get('buttons', []), doc_id)
    
    try: await callback.message.delete()
    except: pass
    
    if ad.get('photo_id'):
        await callback.message.answer_photo(photo=ad.get('photo_id'), caption=ad.get('description', ''), reply_markup=markup)
    else:
        await callback.message.answer(ad.get('description', '') or "بدون نص", reply_markup=markup)
    await callback.answer()

@router.callback_query(F.data == "start_menu")
async def return_to_start(callback: types.CallbackQuery):
    try: await callback.message.edit_text("اختر ما تود القيام به:", reply_markup=get_main_menu())
    except: pass
    await callback.answer()
    
@router.callback_query(F.data.startswith("delete_ad_"))
async def delete_ad(callback: types.CallbackQuery):
    doc_id = callback.data.split("delete_ad_")[1]
    await asyncio.to_thread(db.collection("ads").document(doc_id).delete)
    await callback.answer("✅ تم الحذف!", show_alert=True)
    await list_my_ads(callback)

# ================= وضع الإنلاين =================
@router.inline_query()
async def inline_ad_search(inline_query: InlineQuery):
    query = inline_query.query.strip().upper()
    if not query: return

    ads_list = await asyncio.to_thread(search_ad_by_id, query)
    if not ads_list: return

    ad_data = ads_list[0].to_dict()
    desc = ad_data.get('description', '')
    markup = build_ad_markup(ad_data.get('buttons', []))
    title_text = desc[:30] + "..." if desc else "إعلان بصورة"

    if ad_data.get('photo_id'):
        result = InlineQueryResultCachedPhoto(
            id=ad_data['doc_id'],
            photo_file_id=ad_data['photo_id'],
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