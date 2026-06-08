import json
import asyncio
import time
from datetime import datetime, timedelta
from typing import List, Optional

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineQueryResultCachedPhoto,
)
from aiogram.exceptions import TelegramBadRequest

from config import CHANNEL_USERNAME, FREE_LIMIT, PAID_LIMIT, SUB_CHECK_TTL
from database import db

router = Router()

# ================= نظام الحماية ضد السبام =================
check_sub_cooldowns = {}
COOLDOWN_SECONDS = 10  # عدد ثواني الانتظار بين كل ضغطة تحقق

# ================= حالات البوت (FSM) =================
class AdForm(StatesGroup):
    waiting_for_content = State()
    waiting_for_edit_content = State()
    waiting_for_btn_text = State()
    waiting_for_btn_url = State()
    waiting_for_specific_btn_text = State()
    waiting_for_specific_btn_url = State()

# ================= دوال قاعدة البيانات (مساعدة للتزامن) =================
def fetch_ads_by_merchant(merchant_id: str) -> List:
    return list(db.collection("ads").where("merchant_id", "==", merchant_id).stream())

def search_ad_by_id(query: str) -> List:
    return list(db.collection("ads").where("ad_id", "==", query).limit(1).stream())

# ================= دوال التخزين المؤقت للاشتراك (Firestore) =================
def get_user_doc_ref_sync(telegram_id: str):
    return db.collection("merchants").document(telegram_id)

def read_subscription_cache_sync(telegram_id: str) -> Optional[dict]:
    doc = get_user_doc_ref_sync(telegram_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    return {
        "is_subscribed": data.get("is_subscribed"),
        "sub_checked_at": data.get("sub_checked_at")
    }

def write_subscription_cache_sync(telegram_id: str, is_subscribed: bool, checked_at_iso: str):
    get_user_doc_ref_sync(telegram_id).set({
        "is_subscribed": is_subscribed,
        "sub_checked_at": checked_at_iso
    }, merge=True)

# ================= فحص الاشتراك (مع خيار تجاوز الكاش) =================
async def is_user_subscribed(bot: types.Bot, user_id: int, force_refresh: bool = False) -> bool:
    try:
        if not force_refresh:
            cache = await asyncio.to_thread(read_subscription_cache_sync, str(user_id))
            if cache and cache.get("is_subscribed") is not None and cache.get("sub_checked_at"):
                try:
                    checked_at = datetime.fromisoformat(cache["sub_checked_at"])
                    if (datetime.utcnow() - checked_at) < timedelta(seconds=SUB_CHECK_TTL):
                        return bool(cache["is_subscribed"])
                except Exception:
                    pass

        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        is_sub = member.status in ("member", "administrator", "creator")
        
        await asyncio.to_thread(write_subscription_cache_sync, str(user_id), bool(is_sub), datetime.utcnow().isoformat())
        return bool(is_sub)
    except Exception as e:
        print(f"Error checking sub: {e}")
        return False

# ================= الدوال المساعدة والترتيب =================
def truncate_text(text, max_len=25):
    if not text: return "زر"
    text = str(text)
    return text[:max_len] + "..." if len(text) > max_len else text

def normalize_buttons(buttons_data):
    if not buttons_data: return []
    if isinstance(buttons_data, str):
        try: buttons_data = json.loads(buttons_data)
        except Exception: return []
    if not buttons_data: return []
    if isinstance(buttons_data[0], list): return buttons_data
    return [[b] for b in buttons_data]

# ================= بناء واجهات الكيبورد =================
def get_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ إنشاء إعلان جديد", callback_data="create_ad")],
        [InlineKeyboardButton(text="📋 إعلاناتي", callback_data="list_ads")],
        [InlineKeyboardButton(text="ℹ️ شرح الاستخدام", callback_data="help_usage")]
    ])

def build_ad_markup(buttons_list):
    buttons_list = normalize_buttons(buttons_list)
    keyboard = []
    for row in buttons_list:
        keyboard.append([InlineKeyboardButton(text=truncate_text(btn['text']), url=btn['url']) for btn in row])
    return InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None

def build_merged_keyboard(buttons_list, doc_id):
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
    buttons_list = normalize_buttons(buttons_list)
    keyboard = []
    for row in buttons_list:
        keyboard.append([InlineKeyboardButton(text=truncate_text(btn['text']), url=btn['url']) for btn in row])

    if not buttons_list:
        keyboard.append([InlineKeyboardButton(text="➕ إضافة زر", callback_data="add_btn_new")])
    else:
        last_row_len = len(buttons_list[-1])
        controls = []
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

def get_subscribe_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 اشترك في القناة", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
        [InlineKeyboardButton(text="✅ تحقق من الاشتراك", callback_data="check_subscription")],
        [InlineKeyboardButton(text="🔙 رجوع", callback_data="start_menu")]
    ])

# ================= جلب بيانات التاجر بالكامل (مع الرصيد التراكمي) =================
async def get_merchant_data(telegram_id: str) -> dict:
    try:
        doc_snapshot = await asyncio.to_thread(db.collection("merchants").document(telegram_id).get)
        if doc_snapshot.exists:
            return doc_snapshot.to_dict()
        return {}
    except Exception:
        return {}

# ================= معاينة الإعلان =================
async def show_ad_preview(message: types.Message, state: FSMContext, edit_mode=False):
    data = await state.get_data()
    desc = data.get('description', '')
    photo_id = data.get('photo_id')
    buttons = normalize_buttons(data.get('buttons', []))

    markup = build_preview_keyboard(buttons)
    text_preview = f"👀 <b>معاينة الإعلان:</b>\n\n{desc}" if desc else "👀 <b>معاينة الإعلان:</b>\nبدون نص"

    if edit_mode and data.get('preview_msg_id'):
        try: await message.bot.delete_message(message.chat.id, data['preview_msg_id'])
        except TelegramBadRequest: pass

    if photo_id:
        sent_msg = await message.answer_photo(photo=photo_id, caption=text_preview, reply_markup=markup, parse_mode="HTML")
    else:
        sent_msg = await message.answer(text_preview, reply_markup=markup, parse_mode="HTML")

    await state.update_data(preview_msg_id=sent_msg.message_id)

# ================= التفاعل العام =================
@router.callback_query(F.data == "ignore_btn")
async def ignore_btn_click(callback: types.CallbackQuery):
    await callback.answer("زر فاصِل ⚙️")

@router.callback_query(F.data == "help_usage")
async def show_help(callback: types.CallbackQuery):
    help_text = (
        "📚 <b>دليل الاستخدام:</b>\n\n"
        "1️⃣ اضغط إنشاء، وأرسل المحتوى، ثم استخدم لوحة التحكم لإضافة الأزرار.\n"
        "2️⃣ بعد الحفظ، انسخ كود النشر والصقه في أي محادثة.\n\n"
        f"💡 النظام يمنحك رصيد مجاني (تراكمي) لـ {FREE_LIMIT} إعلانات.\nالمشتركون في القناة يحصلون على {PAID_LIMIT} إعلانات نشطة بلا قيود تراكمية."
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 رجوع", callback_data="start_menu")]])
    try: await callback.message.edit_text(help_text, parse_mode="HTML", reply_markup=markup)
    except TelegramBadRequest: await callback.message.answer(help_text, parse_mode="HTML", reply_markup=markup)
    await callback.answer()

# ================= إنشاء إعلان جديد (نظام الرصيد التراكمي Lifetime Quota) =================
@router.callback_query(F.data == "create_ad")
async def start_creating_ad(callback: types.CallbackQuery, state: FSMContext):
    telegram_id = str(callback.from_user.id)
    merchant_data = await get_merchant_data(telegram_id)
    merchant_id = merchant_data.get("merchant_id")
    
    if not merchant_id:
        await callback.answer("❌ يرجى الضغط على /start لتسجيل حسابك وتحديث بياناتك أولاً.", show_alert=True)
        return

    # جلب الرصيد التراكمي (كم إعلان صممه في حياته)
    total_ads_created = merchant_data.get("total_ads_created", 0)
    ads = await asyncio.to_thread(fetch_ads_by_merchant, merchant_id)
    subscribed = await is_user_subscribed(callback.bot, callback.from_user.id)

    # التحقق من القيود التراكمية لغير المشتركين
    if not subscribed:
        if total_ads_created >= FREE_LIMIT:
            try:
                await callback.message.edit_text(
                    f"❌ <b>نفد رصيدك المجاني!</b>\n\nلقد قمت بإنشاء ({FREE_LIMIT}) إعلانات مسبقاً (النظام تراكمي).\n📢 اشترك في القناة لتتمكن من إنشاء حتى {PAID_LIMIT} إعلانات وإدارتها بلا قيود:",
                    reply_markup=get_subscribe_keyboard(),
                    parse_mode="HTML"
                )
            except TelegramBadRequest: pass
            return
    else:
        # المشتركون يُحاسبون على عدد الإعلانات "النشطة" فقط، وليس التراكمي
        if len(ads) >= PAID_LIMIT:
            await callback.answer(f"❌ وصلت للحد الأقصى {PAID_LIMIT} إعلانات نشطة.", show_alert=True)
            return

    try: await callback.message.edit_text("أرسل <b>صورة مع الوصف</b>، أو <b>الوصف فقط</b>:", parse_mode="HTML")
    except TelegramBadRequest: await callback.message.answer("أرسل <b>صورة مع الوصف</b>، أو <b>الوصف فقط</b>:", parse_mode="HTML")
    
    await state.set_state(AdForm.waiting_for_content)

@router.message(AdForm.waiting_for_content, F.text | F.photo)
async def process_content(message: types.Message, state: FSMContext):
    text = message.text or message.caption or ""
    photo_id = message.photo[-1].file_id if message.photo else None

    await state.update_data(description=text, photo_id=photo_id, buttons=[])
    await show_ad_preview(message, state)
    await state.set_state(None)

# ================= قفل التعديل وتحرير المحتوى =================
@router.callback_query(F.data.startswith("edit_content_"))
async def edit_content_prompt(callback: types.CallbackQuery, state: FSMContext):
    subscribed = await is_user_subscribed(callback.bot, callback.from_user.id)
    if not subscribed:
        await callback.answer("❌ لا يمكنك تعديل الإعلانات إلا إذا كنت عضواً في القناة.", show_alert=True)
        return

    doc_id = callback.data.split("edit_content_")[1]
    doc_snapshot = await asyncio.to_thread(db.collection("ads").document(doc_id).get)
    doc = doc_snapshot.to_dict() if doc_snapshot.exists else {}

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
    subscribed = await is_user_subscribed(callback.bot, callback.from_user.id)
    if not subscribed:
        await callback.answer("❌ لا يمكنك تعديل الإعلانات إلا إذا كنت عضواً في القناة.", show_alert=True)
        return

    doc_id = callback.data.split("edit_buttons_")[1]
    doc_snapshot = await asyncio.to_thread(db.collection("ads").document(doc_id).get)
    doc = doc_snapshot.to_dict() if doc_snapshot.exists else {}

    await state.update_data(
        editing_doc_id=doc_id,
        ad_id=doc.get('ad_id'),
        description=doc.get('description', ''),
        photo_id=doc.get('photo_id'),
        buttons=normalize_buttons(doc.get('buttons', []))
    )
    await show_ad_preview(callback.message, state)
    await callback.answer()

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
        msg = await message.answer("❌ الرابط غير صحيح. يجب أن يبدأ بـ <b>https://</b> أو <b>t.me/</b>.\nأرسل الرابط مجدداً:", parse_mode="HTML")
        await state.update_data(prompt_msg_id=msg.message_id)
        return

    buttons = normalize_buttons(data.get('buttons', []))
    start_new_row = data.get('start_new_row', True)
    new_btn = {'text': data['current_btn_text'], 'url': url}

    if start_new_row or not buttons:
        buttons.append([new_btn])
    else:
        if len(buttons[-1]) < 2:
            buttons[-1].append(new_btn)
        else:
            buttons.append([new_btn])

    await state.update_data(buttons=buttons)

    try:
        await show_ad_preview(message, state, edit_mode=True)
        await state.set_state(None)
    except Exception:
        if start_new_row or len(buttons[-1]) == 1:
            buttons.pop()
        else:
            buttons[-1].pop()
        await state.update_data(buttons=buttons)
        msg = await message.answer("❌ عذراً، تيليجرام يرفض هذا الرابط. يرجى إرسال رابط صالح:")
        await state.update_data(prompt_msg_id=msg.message_id)

@router.callback_query(F.data == "select_btn_to_edit")
async def select_btn_to_edit(callback: types.CallbackQuery, state: FSMContext):
    subscribed = await is_user_subscribed(callback.bot, callback.from_user.id)
    if not subscribed:
        await callback.answer("❌ لا يمكنك تعديل الأزرار إلا إذا كنت عضواً في القناة.", show_alert=True)
        return

    data = await state.get_data()
    buttons = normalize_buttons(data.get('buttons', []))

    keyboard = []
    idx = 0
    for row in buttons:
        kb_row = []
        for btn in row:
            kb_row.append(InlineKeyboardButton(text=truncate_text(btn['text']), callback_data=f"edit_btn_idx_{idx}"))
            kb_row.append(InlineKeyboardButton(text="🗑️ مسح", callback_data=f"delete_btn_idx_{idx}"))
            idx += 1
        keyboard.append(kb_row)

    keyboard.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_preview")])
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    try: await callback.message.bot.delete_message(callback.message.chat.id, data.get('preview_msg_id'))
    except TelegramBadRequest: pass

    sent_msg = await callback.message.answer("اختر الزر الذي تود تعديله أو حذفه:", reply_markup=markup)
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

@router.callback_query(F.data.startswith("delete_btn_idx_"))
async def delete_specific_btn(callback: types.CallbackQuery, state: FSMContext):
    idx_to_delete = int(callback.data.split("_")[-1])
    data = await state.get_data()
    buttons = normalize_buttons(data.get('buttons', []))

    current_idx = 0
    removed = False
    for r_idx, row in enumerate(buttons):
        for c_idx in range(len(row)):
            if current_idx == idx_to_delete:
                buttons[r_idx].pop(c_idx)
                if len(buttons[r_idx]) == 0:
                    buttons.pop(r_idx)
                removed = True
                break
            current_idx += 1
        if removed: break

    if removed:
        await state.update_data(buttons=buttons)
        try: await show_ad_preview(callback.message, state, edit_mode=True)
        except Exception: pass
        await callback.answer("🗑️ تم حذف الزر")
    else:
        await callback.answer("❌ لم أتمكن من العثور على الزر.", show_alert=True)

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
        msg = await message.answer("❌ الرابط غير صحيح. يجب أن يبدأ بـ <b>https://</b> أو <b>t.me/</b>.\nأرسل الرابط مجدداً:", parse_mode="HTML")
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
        telegram_id = str(callback.from_user.id)
        merchant_data = await get_merchant_data(telegram_id)
        merchant_id = merchant_data.get("merchant_id")

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

            update_text = (
                f"✅ <b>تم التحديث بنجاح!</b>\n\n"
                f"👇 اضغط لنسخ كود النشر السريع:\n"
                f"<code>@dddddddddh_bot {short_id}</code>"
            )
            await callback.message.answer(update_text, parse_mode="HTML", reply_markup=get_main_menu())

        else:
            subscribed = await is_user_subscribed(callback.bot, callback.from_user.id)
            total_ads_created = merchant_data.get("total_ads_created", 0)
            ads = await asyncio.to_thread(fetch_ads_by_merchant, merchant_id) if merchant_id else []
            
            # التحقق النهائي قبل الحفظ (سد الثغرة)
            if not subscribed and total_ads_created >= FREE_LIMIT:
                try: await callback.message.delete()
                except TelegramBadRequest: pass
                
                await callback.message.answer(
                    f"❌ لا يمكنك حفظ الإعلان الآن. لقد استهلكت رصيدك التراكمي ({FREE_LIMIT}).\nاشترك في القناة للحصول على {PAID_LIMIT} إعلانات.",
                    reply_markup=get_subscribe_keyboard()
                )
                await state.clear()
                return
            elif subscribed and len(ads) >= PAID_LIMIT:
                try: await callback.message.delete()
                except TelegramBadRequest: pass
                
                await callback.message.answer(f"❌ وصلت للحد الأقصى {PAID_LIMIT} إعلانات نشطة.", reply_markup=get_main_menu())
                await state.clear()
                return

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
            
            # زيادة الرصيد التراكمي للتاجر
            await asyncio.to_thread(
                db.collection("merchants").document(telegram_id).set,
                {"total_ads_created": total_ads_created + 1},
                merge=True
            )

            success_text = (
                f"✅ <b>تم إنشاء إعلانك بنجاح!</b>\n\n"
                f"👇 اضغط على النص بالأسفل لنسخه:\n"
                f"<code>@dddddddddh_bot {short_id}</code>"
            )
            await callback.message.answer(success_text, parse_mode="HTML", reply_markup=get_main_menu())

        await state.clear()
        await callback.answer("✅ تم الحفظ")
    except Exception:
        await callback.message.answer(f"❌ حدث خطأ داخلي أثناء الحفظ.")
        await callback.answer()

# ================= عرض الإعلانات (نظام الإخفاء) =================
@router.callback_query(F.data == "list_ads")
async def list_my_ads(callback: types.CallbackQuery):
    await callback.answer()

    telegram_id = str(callback.from_user.id)
    merchant_data = await get_merchant_data(telegram_id)
    merchant_id = merchant_data.get("merchant_id")
    
    if not merchant_id:
        await callback.message.answer("❌ يرجى الضغط على /start لتحديث بياناتك.")
        return

    ads = await asyncio.to_thread(fetch_ads_by_merchant, merchant_id)

    if not ads:
        try: await callback.message.edit_text("ليس لديك إعلانات حالياً.", reply_markup=get_main_menu())
        except TelegramBadRequest:
            try: await callback.message.delete()
            except TelegramBadRequest: pass
            await callback.message.answer("ليس لديك إعلانات حالياً.", reply_markup=get_main_menu())
        return

    subscribed = await is_user_subscribed(callback.bot, callback.from_user.id)
    
    if not subscribed:
        visible_ads = ads[:FREE_LIMIT]
        hidden_count = len(ads) - len(visible_ads)
    else:
        visible_ads = ads
        hidden_count = 0

    keyboard = []
    for ad in visible_ads:
        ad_data = ad.to_dict()
        desc = ad_data.get('description', '')
        if not desc or str(desc).strip() == "":
            desc = "إعلان بصورة"

        short_desc = str(desc)[:15].replace("\n", " ") + "..."
        keyboard.append([InlineKeyboardButton(text=f"📢 {short_desc} ({ad_data['ad_id']})", callback_data=f"view_ad_{ad_data['doc_id']}")])

    if hidden_count > 0:
        keyboard.append([InlineKeyboardButton(text=f"🔒 لديك {hidden_count} إعلانات مخفية (اشترك لإظهارها)", callback_data="show_subscribe_prompt")])
    elif not subscribed:
        keyboard.insert(0, [InlineKeyboardButton(text=f"🔒 اشترك لرفع الحد إلى {PAID_LIMIT}", callback_data="show_subscribe_prompt")])

    keyboard.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="start_menu")])
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    try: await callback.message.edit_text("📋 <b>قائمة إعلاناتك:</b>", parse_mode="HTML", reply_markup=markup)
    except TelegramBadRequest:
        try: await callback.message.delete()
        except TelegramBadRequest: pass
        await callback.message.answer("📋 <b>قائمة إعلاناتك:</b>", parse_mode="HTML", reply_markup=markup)

@router.callback_query(F.data == "show_subscribe_prompt")
async def show_subscribe_prompt(callback: types.CallbackQuery):
    try:
        await callback.message.edit_text(
            f"📢 للوصول إلى كامل إعلاناتك ({PAID_LIMIT})، يرجى الاشتراك في القناة:",
            reply_markup=get_subscribe_keyboard()
        )
    except TelegramBadRequest: pass
    await callback.answer()

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

# ================= زر التحقق ضد السبام =================
@router.callback_query(F.data == "check_subscription")
async def check_subscription(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    current_time = time.time()

    # حماية السبام Cooldown
    if user_id in check_sub_cooldowns:
        time_passed = current_time - check_sub_cooldowns[user_id]
        if time_passed < COOLDOWN_SECONDS:
            remaining = int(COOLDOWN_SECONDS - time_passed)
            await callback.answer(f"⏳ يرجى الانتظار {remaining} ثوانٍ قبل المحاولة مرة أخرى.", show_alert=True)
            return

    check_sub_cooldowns[user_id] = current_time

    subscribed = await is_user_subscribed(callback.bot, user_id, force_refresh=True)
    
    if subscribed:
        check_sub_cooldowns.pop(user_id, None)
        try:
            await callback.message.delete()
            await callback.message.answer(
                "✅ تم التحقق من اشتراكك بنجاح!\nالآن يمكنك استخدام جميع ميزات البوت.",
                reply_markup=get_main_menu()
            )
        except TelegramBadRequest:
            await callback.answer("✅ تم التحقق من اشتراكك بنجاح.", show_alert=True)
    else:
        try:
            await callback.message.delete()
            await callback.message.answer(
                "❌ <b>لم نتمكن من العثور على اشتراكك!</b>\n\nيرجى الانضمام للقناة أولاً ثم العودة والضغط على تحقق.",
                parse_mode="HTML",
                reply_markup=get_subscribe_keyboard()
            )
        except TelegramBadRequest:
            await callback.answer("❌ لم يتم العثور على اشتراكك. تأكد من الانضمام ثم حاول مجدداً.", show_alert=True)

# ================= القائمة الرئيسية والرجوع =================
@router.callback_query(F.data == "start_menu")
async def return_to_start(callback: types.CallbackQuery):
    await callback.answer()

    user_name = callback.from_user.first_name
    user_id = callback.from_user.id

    welcome_text = (
        f"👋 <b>أهلاً بعودتك يا {user_name}</b>\n\n"
        f"🆔 <b>الآيدي:</b> <code>{user_id}</code>\n\n"
        f"🎛️ اختر ما تود القيام به من الأزرار أدناه:"
    )

    try: await callback.message.edit_text(welcome_text, parse_mode="HTML", reply_markup=get_main_menu())
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

# ================= المراقبة الفورية (ChatMemberUpdated) =================
@router.chat_member()
async def chat_member_update_handler(event: types.ChatMemberUpdated):
    target_channel = CHANNEL_USERNAME.replace('@', '')
    if event.chat.username != target_channel:
        return

    user_id = str(event.from_user.id)
    new_status = event.new_chat_member.status
    
    # حالة: غادر أو تم طرده
    if new_status in ['left', 'kicked']:
        await asyncio.to_thread(write_subscription_cache_sync, user_id, False, datetime.utcnow().isoformat())
        try:
            await event.bot.send_message(
                event.from_user.id,
                "⚠️ <b>تنبيه:</b> لقد غادرت قناتنا الرسمية!\n\n🔒 تم إخفاء إعلاناتك الإضافية وتم قفل خاصية التعديل. يرجى العودة للقناة لتفعيلها.",
                parse_mode="HTML",
                reply_markup=get_subscribe_keyboard()
            )
        except Exception: pass
            
    # حالة: انضم
    elif new_status in ['member', 'administrator', 'creator']:
        await asyncio.to_thread(write_subscription_cache_sync, user_id, True, datetime.utcnow().isoformat())
        try:
            await event.bot.send_message(
                event.from_user.id,
                "✅ <b>شكراً لانضمامك!</b>\n\n🔓 تم تفعيل جميع إعلاناتك وصلاحيات التعديل بنجاح.",
                parse_mode="HTML"
            )
        except Exception: pass