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
    waiting_for_specific_btn_text = State()
    waiting_for_specific_btn_url = State()

# ================= دوال قاعدة البيانات (مساعدة للتزامن) =================
def fetch_ads_by_merchant(merchant_id):
    return list(db.collection("ads").where("merchant_id", "==", merchant_id).stream())

def search_ad_by_id(query):
    return list(db.collection("ads").where("ad_id", "==", query).limit(1).stream())

# ================= الدوال المساعدة والترتيب =================
def truncate_text(text, max_len=15):
    """دالة القص البرمجي التلقائي للنصوص الطويلة لمنع تمدد الكيبورد"""
    if not text: return "زر"
    text = str(text)
    return text[:max_len] + "..." if len(text) > max_len else text

def normalize_buttons(buttons_data):
    """تحويل الأزرار واسترجاعها مع احترام الترتيب اليدوي للتاجر"""
    if not buttons_data: return []
    if isinstance(buttons_data, str):
        try: buttons_data = json.loads(buttons_data)
        except: return []
            
    if not buttons_data: return []
    if isinstance(buttons_data[0], list): return buttons_data
    
    # حماية للبيانات القديمة
    return [[b] for b in buttons_data]

# ================= بناء واجهات الكيبورد =================
def get_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ إنشاء إعلان جديد", callback_data="create_ad")],
        [InlineKeyboardButton(text="📋 إعلاناتي", callback_data="list_ads")],
        [InlineKeyboardButton(text="ℹ️ شرح الاستخدام", callback_data="help_usage")]
    ])

def build_ad_markup(buttons_list):
    """الكيبورد النهائي عند النشر (للعملاء) مع القص التلقائي"""
    buttons_list = normalize_buttons(buttons_list)
    keyboard = []
    for row in buttons_list:
        keyboard.append([InlineKeyboardButton(text=truncate_text(btn['text']), url=btn['url']) for btn in row])
    return InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None

def build_merged_keyboard(buttons_list, doc_id):
    """كيبورد الإدارة للتاجر (مدمج وموفر للمساحة)"""
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

def build_preview_keyboard(buttons_list):
    """كيبورد المعاينة والتحكم التفاعلي أثناء الإنشاء (النظام السابق)"""
    buttons_list = normalize_buttons(buttons_list)
    keyboard = []
    
    for row in buttons_list:
        keyboard.append([InlineKeyboardButton(text=truncate_text(btn['text']), url=btn['url']) for btn in row])

    if not buttons_list:
        keyboard.append([InlineKeyboardButton(text="➕ إضافة زر", callback_data="add_btn_new")])
    else:
        last_row_len = len(buttons_list[-1])
        controls = []
        # هنا تم تحديد الحد الأقصى بـ 2 أزرار فقط لكل سطر
        if last_row_len < 2:
            controls.append(InlineKeyboardButton(text="➕ زر بجانبه", callback_data="add_btn_same"))
        controls.append(InlineKeyboardButton(text="⏬ زر بالأسفل", callback_data="add_btn_new"))
        keyboard.append(controls)

    if buttons_list:
        keyboard.append([
            InlineKeyboardButton(text="✏️ تعديل زر", callback_data="select_btn_to_edit"),
            InlineKeyboardButton(text="🗑️ مسح الكل", callback_data="clear_btns")
        ])
        
    keyboard.append([InlineKeyboardButton(text="✅ إنهاء وحفظ", callback_data="finish_ad")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

async def get_merchant_id(telegram_id: str):
    doc = await asyncio.to_thread(db.collection("merchants").document(telegram_id).get)
    return doc.to_dict().get("merchant_id") if doc.exists else None

async def show_ad_preview(message: types.Message, state: FSMContext, edit_mode=False):
    data = await state.get_data()
    desc = data.get('description', '')
    photo_id = data.get('photo_id')
    buttons = normalize_buttons(data.get('buttons', []))

    markup = build_preview_keyboard(buttons)
    text_preview = f"👀 <b>معاينة الإعلان:</b>\n\n{desc}" if desc else "👀 <b>معاينة الإعلان:</b>\nبدون نص"

    if edit_mode and data.get('preview_msg_id'):
        try:
            await message.bot.delete_message(message.chat.id, data['preview_msg_id'])
        except TelegramBadRequest:
            pass

    if photo_id:
        sent_msg = await message.answer_photo(photo=photo_id, caption=text_preview, reply_markup=markup, parse_mode="HTML")
    else:
        sent_msg = await message.answer(text_preview, reply_markup=markup, parse_mode="HTML")

    await state.update_data(preview_msg_id=sent_msg.message_id)

# ================= التفاعل مع الزر الوهمي ושرح الاستخدام =================
@router.callback_query(F.data == "ignore_btn")
async def ignore_btn_click(callback: types.CallbackQuery):
    await callback.answer("زر فاصِل ⚙️")

@router.callback_query(F.data == "help_usage")
async def show_help(callback: types.CallbackQuery):
    help_text = (
        "📚 <b>دليل الاستخدام:</b>\n\n"
        "1️⃣ <b>الإنشاء:</b> اضغط إنشاء، وأرسل المحتوى، ثم استخدم لوحة التحكم لإضافة وتوزيع الأزرار كما تشاء.\n"
        "2️⃣ <b>النشر:</b> بعد الحفظ، اكتب يوزر البوت ثم رقم الإعلان في أي محادثة لنشره.\n"
        "   <i>مثال:</i> <code>@يوزر_البوت 1A2B3C</code>\n\n"
        "💡 <i>الحد الأقصى 5 إعلانات. الحد الأقصى زرين في كل سطر.</i>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 رجوع", callback_data="start_menu")]])
    await callback.message.edit_text(help_text, parse_mode="HTML", reply_markup=markup)
    await callback.answer()

# ================= إنشاء وتعديل المحتوى (النظام التفاعلي) =================
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
    
    await state.update_data(description=text, photo_id=photo_id, buttons=[])
    await show_ad_preview(message, state)
    await state.set_state(None)

@router.callback_query(F.data.startswith("edit_content_"))
async def edit_content_prompt(callback: types.CallbackQuery, state: FSMContext):
    doc_id = callback.data.split("edit_content_")[1]
    doc_snapshot = await asyncio.to_thread(db.collection("ads").document(doc_id).get)
    doc = doc_snapshot.to_dict()
    
    await state.update_data(
        editing_doc_id=doc_id, 
        ad_id=doc.get('ad_id'), 
        buttons=normalize_buttons(doc.get('buttons', []))
    )
    await callback.message.answer("أرسل <b>الصورة والوصف الجديد</b>، أو <b>الوصف فقط</b>:", parse_mode="HTML")
    await state.set_state(AdForm.waiting_for_edit_content)

@router.message(AdForm.waiting_for_edit_content, F.text | F.photo)
async def process_edit_content(message: types.Message, state: FSMContext):
    text = message.text or message.caption or ""
    photo_id = message.photo[-1].file_id if message.photo else None
    
    await state.update_data(description=text, photo_id=photo_id)
    await show_ad_preview(message, state, edit_mode=True)
    await state.set_state(None)

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
        buttons=normalize_buttons(doc.get('buttons', []))
    )
    await show_ad_preview(callback.message, state)
    await callback.answer()

# ================= إضافة الأزرار يدوياً =================
@router.callback_query(F.data.startswith("add_btn_"))
async def prompt_btn_text(callback: types.CallbackQuery, state: FSMContext):
    is_new_row = (callback.data == "add_btn_new")
    await state.update_data(start_new_row=is_new_row)

    msg = await callback.message.answer("✏️ أرسل <b>اسم الزر</b> الآن:", parse_mode="HTML")
    await state.update_data(prompt_msg_id=msg.message_id)
    await state.set_state(AdForm.waiting_for_btn_text)
    await callback.answer()

@router.message(AdForm.waiting_for_btn_text, F.text)
async def process_btn_text(message: types.Message, state: FSMContext):
    await state.update_data(current_btn_text=message.text)
    data = await state.get_data()
    
    try: await message.bot.delete_message(message.chat.id, data.get('prompt_msg_id'))
    except TelegramBadRequest: pass
    try: await message.delete()
    except TelegramBadRequest: pass

    msg = await message.answer("🔗 ممتاز. أرسل الآن <b>رابط الزر</b> (https:// أو t.me/):", parse_mode="HTML")
    await state.update_data(prompt_msg_id=msg.message_id)
    await state.set_state(AdForm.waiting_for_btn_url)

@router.message(AdForm.waiting_for_btn_url, F.text)
async def process_btn_url(message: types.Message, state: FSMContext):
    url = message.text.strip()
    data = await state.get_data()

    try: await message.bot.delete_message(message.chat.id, data.get('prompt_msg_id'))
    except TelegramBadRequest: pass
    try: await message.delete()
    except TelegramBadRequest: pass

    if not url.startswith(('https://', 't.me/')) or len(url) < 10:
        msg = await message.answer("❌ الرابط غير صحيح. يجب أن يبدأ بـ <b>https://</b> أو <b>t.me/</b> ويكون كاملاً.\nأرسل الرابط مجدداً:", parse_mode="HTML")
        await state.update_data(prompt_msg_id=msg.message_id)
        return

    buttons = normalize_buttons(data.get('buttons', []))
    start_new_row = data.get('start_new_row', True)
    new_btn = {'text': data['current_btn_text'], 'url': url}

    if start_new_row or not buttons:
        buttons.append([new_btn])
    else:
        # حماية إضافية للحد الأقصى
        if len(buttons[-1]) < 2:
            buttons[-1].append(new_btn)
        else:
            buttons.append([new_btn])
        
    await state.update_data(buttons=buttons)

    try:
        await show_ad_preview(message, state, edit_mode=True)
        await state.set_state(None)
    except Exception:
        # التراجع إذا رفض تيليجرام الرابط
        if start_new_row or len(buttons[-1]) == 1:
            buttons.pop()
        else:
            buttons[-1].pop()
        await state.update_data(buttons=buttons)
        msg = await message.answer("❌ عذراً، تيليجرام يرفض هذا الرابط. يرجى إرسال رابط صالح:")
        await state.update_data(prompt_msg_id=msg.message_id)

# ================= تعديل زر معين =================
@router.callback_query(F.data == "select_btn_to_edit")
async def select_btn_to_edit(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    buttons = normalize_buttons(data.get('buttons', []))
    
    keyboard = []
    idx = 0
    for row in buttons:
        kb_row = []
        for btn in row:
            kb_row.append(InlineKeyboardButton(text=truncate_text(btn['text']), callback_data=f"edit_btn_idx_{idx}"))
            idx += 1
        keyboard.append(kb_row)
    
    keyboard.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_preview")])
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    try: await callback.message.bot.delete_message(callback.message.chat.id, data.get('preview_msg_id'))
    except TelegramBadRequest: pass
    
    sent_msg = await callback.message.answer("اختر الزر الذي تود تعديله من القائمة أدناه:", reply_markup=markup)
    await state.update_data(preview_msg_id=sent_msg.message_id)
    await callback.answer()

@router.callback_query(F.data == "back_to_preview")
async def back_to_preview(callback: types.CallbackQuery, state: FSMContext):
    await show_ad_preview(callback.message, state, edit_mode=True)
    await callback.answer()

@router.callback_query(F.data.startswith("edit_btn_idx_"))
async def ask_specific_btn_text(callback: types.CallbackQuery, state: FSMContext):
    idx = int(callback.data.split("_")[-1])
    await state.update_data(editing_btn_idx=idx)
    
    msg = await callback.message.answer("✏️ أرسل <b>الاسم الجديد</b> للزر:", parse_mode="HTML")
    await state.update_data(prompt_msg_id=msg.message_id)
    await state.set_state(AdForm.waiting_for_specific_btn_text)
    await callback.answer()

@router.message(AdForm.waiting_for_specific_btn_text, F.text)
async def process_specific_btn_text(message: types.Message, state: FSMContext):
    await state.update_data(current_btn_text=message.text)
    data = await state.get_data()
    
    try: await message.bot.delete_message(message.chat.id, data.get('prompt_msg_id'))
    except TelegramBadRequest: pass
    try: await message.delete()
    except TelegramBadRequest: pass

    msg = await message.answer("🔗 ممتاز. أرسل الآن <b>الرابط الجديد</b> (https:// أو t.me/):", parse_mode="HTML")
    await state.update_data(prompt_msg_id=msg.message_id)
    await state.set_state(AdForm.waiting_for_specific_btn_url)

@router.message(AdForm.waiting_for_specific_btn_url, F.text)
async def process_specific_btn_url(message: types.Message, state: FSMContext):
    url = message.text.strip()
    data = await state.get_data()

    try: await message.bot.delete_message(message.chat.id, data.get('prompt_msg_id'))
    except TelegramBadRequest: pass
    try: await message.delete()
    except TelegramBadRequest: pass

    if not url.startswith(('https://', 't.me/')) or len(url) < 10:
        msg = await message.answer("❌ الرابط غير صحيح. يجب أن يبدأ بـ <b>https://</b> أو <b>t.me/</b> حصراً.\nأرسل الرابط مجدداً:", parse_mode="HTML")
        await state.update_data(prompt_msg_id=msg.message_id)
        return

    buttons = normalize_buttons(data.get('buttons', []))
    idx_to_edit = data.get('editing_btn_idx')
    
    current_idx = 0
    old_btn = None
    target_r, target_c = -1, -1
    
    for r_idx, row in enumerate(buttons):
        for c_idx, btn in enumerate(row):
            if current_idx == idx_to_edit:
                old_btn = buttons[r_idx][c_idx]
                target_r, target_c = r_idx, c_idx
                buttons[r_idx][c_idx] = {'text': data['current_btn_text'], 'url': url}
                break
            current_idx += 1
        if old_btn: break

    await state.update_data(buttons=buttons)

    try:
        await show_ad_preview(message, state, edit_mode=True)
        await state.set_state(None)
    except Exception:
        if old_btn:
            buttons[target_r][target_c] = old_btn
            await state.update_data(buttons=buttons)
        msg = await message.answer("❌ عذراً، تيليجرام يرفض هذا الرابط. يرجى إرسال رابط صالح:")
        await state.update_data(prompt_msg_id=msg.message_id)

@router.callback_query(F.data == "clear_btns")
async def clear_btns(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(buttons=[])
    await show_ad_preview(callback.message, state, edit_mode=True)
    await callback.answer("🗑️ تم مسح الأزرار")

# ================= إنهاء وحفظ الإعلان =================
@router.callback_query(F.data == "finish_ad")
async def finish_ad(callback: types.CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        merchant_id = await get_merchant_id(str(callback.from_user.id))
        
        buttons_data = normalize_buttons(data.get('buttons', []))
        buttons_json = json.dumps(buttons_data) 
        
        try: await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest: pass

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

            success_text = (
                f"✅ <b>تم إنشاء إعلانك بنجاح!</b>\n\n"
                f"🆔 <b>رقم الإعلان:</b> <code>{short_id}</code>\n\n"
                f"اذهب لأي محادثة واكتب يوزر البوت ثم رقم إعلانك لنشره."
            )
            await callback.message.answer(success_text, parse_mode="HTML", reply_markup=get_main_menu())
            
        await state.clear()
        await callback.answer("✅ تم الحفظ")
    except Exception as e:
        await callback.message.answer(f"❌ حدث خطأ داخلي أثناء الحفظ.")
        await callback.answer()

# ================= عرض وإدارة الإعلانات =================
@router.callback_query(F.data == "list_ads")
async def list_my_ads(callback: types.CallbackQuery):
    await callback.answer()
    
    merchant_id = await get_merchant_id(str(callback.from_user.id))
    if not merchant_id:
        await callback.message.answer("❌ يرجى الضغط على /start لتحديث بياناتك.")
        return

    ads = await asyncio.to_thread(fetch_ads_by_merchant, merchant_id)
    
    if not ads:
        try: await callback.message.edit_text("ليس لديك إعلانات حالياً.", reply_markup=get_main_menu())
        except TelegramBadRequest: pass
        return

    keyboard = []
    for ad in ads:
        ad_data = ad.to_dict()
        desc = ad_data.get('description', '')
        if not desc or str(desc).strip() == "":
            desc = "إعلان بصورة"
            
        short_desc = str(desc)[:15].replace("\n", " ") + "..."
        keyboard.append([InlineKeyboardButton(text=f"📢 {short_desc} ({ad_data['ad_id']})", callback_data=f"view_ad_{ad_data['doc_id']}")])
    
    keyboard.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="start_menu")])
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    try: await callback.message.edit_text("📋 <b>قائمة إعلاناتك:</b>", parse_mode="HTML", reply_markup=markup)
    except TelegramBadRequest: pass

@router.callback_query(F.data.startswith("view_ad_"))
async def view_ad_details(callback: types.CallbackQuery):
    doc_id = callback.data.split("view_ad_")[1]
    doc_snapshot = await asyncio.to_thread(db.collection("ads").document(doc_id).get)
    
    if not doc_snapshot.exists:
        await callback.answer("❌ الإعلان غير موجود.", show_alert=True)
        return
        
    ad = doc_snapshot.to_dict()
    desc = ad.get('description', '')
    photo_id = ad.get('photo_id')
    
    markup = build_merged_keyboard(ad.get('buttons', []), doc_id)
    
    try: await callback.message.delete()
    except TelegramBadRequest: pass
    
    if photo_id:
        await callback.message.answer_photo(photo=photo_id, caption=desc, reply_markup=markup)
    else:
        await callback.message.answer(desc or "بدون نص", reply_markup=markup)
        
    await callback.answer()

@router.callback_query(F.data == "start_menu")
async def return_to_start(callback: types.CallbackQuery):
    await callback.answer()
    try: await callback.message.edit_text("اختر ما تود القيام به:", reply_markup=get_main_menu())
    except TelegramBadRequest: pass
    
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
    photo_id = ad_data.get('photo_id')
    
    markup = build_ad_markup(ad_data.get('buttons', []))
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