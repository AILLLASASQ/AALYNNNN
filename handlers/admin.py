import asyncio
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import OWNER_ID
from database import db
from handlers.ads import normalize_buttons, truncate_text
from aiogram.exceptions import TelegramBadRequest

router = Router()

# ================= حالات الإدراج (FSM) =================
class AdminState(StatesGroup):
    waiting_for_info_id = State()
    waiting_for_ban_id = State()
    waiting_for_unban_id = State()
    waiting_for_broadcast_msg = State()

# ================= التحقق من المالك =================
def is_owner(user_id):
    return str(user_id) == str(OWNER_ID)

# ================= أزرار لوحة التحكم =================
def get_admin_keyboard():
    keyboard = [
        [InlineKeyboardButton(text="📊 إحصائيات البوت", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🔍 استعلام عن تاجر", callback_data="admin_info")],
        [
            InlineKeyboardButton(text="🚫 حظر تاجر", callback_data="admin_ban"),
            InlineKeyboardButton(text="✅ فك حظر", callback_data="admin_unban")
        ],
        [InlineKeyboardButton(text="📢 إذاعة (رسالة للكل)", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="❌ إغلاق اللوحة", callback_data="admin_close")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ================= فتح اللوحة =================
@router.message(Command("admin"))
async def show_admin_panel(message: types.Message, state: FSMContext):
    if not is_owner(message.from_user.id): return
    await state.clear()
    await message.reply("🛠️ <b>لوحة تحكم المالك</b>\n\nاختر الإجراء الذي تريده:", reply_markup=get_admin_keyboard(), parse_mode="HTML")

# ================= إغلاق اللوحة =================
@router.callback_query(F.data == "admin_close")
async def close_admin_panel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()

# ================= الإحصائيات =================
@router.callback_query(F.data == "admin_stats")
async def show_stats(callback: types.CallbackQuery):
    merchants = list(await asyncio.to_thread(lambda: list(db.collection("merchants").stream())))
    ads = list(await asyncio.to_thread(lambda: list(db.collection("ads").stream())))
    
    banned_count = sum(1 for m in merchants if m.to_dict().get("is_banned", False))
    
    text = (
        f"📊 <b>إحصائيات البوت:</b>\n\n"
        f"👥 إجمالي التجار: {len(merchants)}\n"
        f"📢 إجمالي الإعلانات: {len(ads)}\n"
        f"🚫 الحسابات المحظورة: {banned_count}"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_keyboard(), parse_mode="HTML")

# ================= الاستعلام =================
@router.callback_query(F.data == "admin_info")
async def ask_info_id(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🔍 أرسل <b>الآيدي (ID)</b> الخاص بالتاجر للاستعلام عنه:", parse_mode="HTML")
    await state.set_state(AdminState.waiting_for_info_id)

@router.message(AdminState.waiting_for_info_id)
async def process_info(message: types.Message, state: FSMContext):
    target_id = message.text.strip()
    doc = await asyncio.to_thread(db.collection("merchants").document(target_id).get)
    
    if not doc.exists:
        await message.reply("❌ التاجر غير موجود.", reply_markup=get_admin_keyboard())
    else:
        data = doc.to_dict()
        merchant_id = data.get('merchant_id')
        text = (f"👤 <b>بيانات التاجر:</b>\n\n"
                f"🆔 الآيدي: <code>{target_id}</code>\n"
                f"👤 اليوزر: @{data.get('username', 'بدون يوزر')}\n"
                f"📊 الإعلانات: {data.get('total_ads_created', 0)}\n"
                f"✅ مشترك: {'نعم' if data.get('is_subscribed') else 'لا'}\n"
                f"🚫 محظور: {'نعم' if data.get('is_banned') else 'لا'}")
        
        # إنشاء لوحة أزرار مخصصة للنتيجة
        keyboard = []
        if merchant_id:
            keyboard.append([InlineKeyboardButton(text="👀 عرض إعلانات التاجر", callback_data=f"adm_ads_{merchant_id}")])
        keyboard.append([InlineKeyboardButton(text="🔙 رجوع للوحة", callback_data="admin_stats")])
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

        await message.reply(text, parse_mode="HTML", reply_markup=markup)
    await state.clear()

# ================= الحظر =================
@router.callback_query(F.data == "admin_ban")
async def ask_ban_id(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🚫 أرسل <b>الآيدي (ID)</b> للتاجر الذي تريد حظره نهائياً:", parse_mode="HTML")
    await state.set_state(AdminState.waiting_for_ban_id)

@router.message(AdminState.waiting_for_ban_id)
async def process_ban(message: types.Message, state: FSMContext):
    target_id = message.text.strip()
    await asyncio.to_thread(db.collection("merchants").document(target_id).set, {"is_banned": True}, merge=True)
    await message.reply(f"✅ تم حظر التاجر `{target_id}` بنجاح.", parse_mode="Markdown", reply_markup=get_admin_keyboard())
    await state.clear()

# ================= فك الحظر =================
@router.callback_query(F.data == "admin_unban")
async def ask_unban_id(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✅ أرسل <b>الآيدي (ID)</b> للتاجر لفك الحظر عنه:", parse_mode="HTML")
    await state.set_state(AdminState.waiting_for_unban_id)

@router.message(AdminState.waiting_for_unban_id)
async def process_unban(message: types.Message, state: FSMContext):
    target_id = message.text.strip()
    await asyncio.to_thread(db.collection("merchants").document(target_id).set, {"is_banned": False}, merge=True)
    await message.reply(f"✅ تم فك الحظر عن `{target_id}`.", parse_mode="Markdown", reply_markup=get_admin_keyboard())
    await state.clear()

# ================= الإذاعة =================
@router.callback_query(F.data == "admin_broadcast")
async def ask_broadcast_msg(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📢 أرسل <b>الرسالة</b> التي تريد إرسالها لجميع مستخدمي البوت الآن:", parse_mode="HTML")
    await state.set_state(AdminState.waiting_for_broadcast_msg)

@router.message(AdminState.waiting_for_broadcast_msg)
async def process_broadcast(message: types.Message, state: FSMContext):
    users = list(await asyncio.to_thread(lambda: list(db.collection("merchants").stream())))
    msg_to_send = message.html_text
    
    await message.reply(f"⏳ جاري إرسال الرسالة إلى {len(users)} تاجر...")
    success = 0
    
    for user in users:
        try:
            await message.bot.send_message(user.id, msg_to_send, parse_mode="HTML")
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
            
    await message.reply(f"✅ اكتملت الإذاعة!\nوصلت إلى: {success} تاجر.", reply_markup=get_admin_keyboard())
    await state.clear()

    # ================= عرض قائمة إعلانات تاجر معين للمالك =================
@router.callback_query(F.data.startswith("adm_ads_"))
async def admin_view_user_ads(callback: types.CallbackQuery):
    merchant_id = callback.data.split("adm_ads_")[1]
    ads = list(await asyncio.to_thread(lambda: list(db.collection("ads").where("merchant_id", "==", merchant_id).stream())))

    if not ads:
        await callback.answer("❌ هذا التاجر لا يملك أي إعلانات حالياً.", show_alert=True)
        return

    keyboard = []
    for ad in ads:
        ad_data = ad.to_dict()
        desc = ad_data.get('description', 'إعلان بصورة')
        short_desc = str(desc)[:20].replace("\n", " ") + "..."
        keyboard.append([InlineKeyboardButton(text=f"📢 {short_desc}", callback_data=f"adm_view_ad_{ad_data['doc_id']}")])

    keyboard.append([InlineKeyboardButton(text="❌ إغلاق", callback_data="admin_close")])
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await callback.message.answer(f"📋 <b>إعلانات التاجر ({len(ads)}):</b>\nاختر إعلاناً لمعاينته:", parse_mode="HTML", reply_markup=markup)
    await callback.answer()

# ================= معاينة الإعلان المٌحدد =================
@router.callback_query(F.data.startswith("adm_view_ad_"))
async def admin_view_specific_ad(callback: types.CallbackQuery):
    doc_id = callback.data.split("adm_view_ad_")[1]
    doc_snapshot = await asyncio.to_thread(db.collection("ads").document(doc_id).get)

    if not doc_snapshot.exists:
        await callback.answer("❌ الإعلان غير موجود أو تم حذفه.", show_alert=True)
        return

    ad = doc_snapshot.to_dict()
    desc = ad.get('description', '')
    photo_id = ad.get('photo_id')
    
    # بناء أزرار الإعلان مع زر الحذف الخاص بالإدارة
    buttons_list = normalize_buttons(ad.get('buttons', []))
    admin_keyboard = []
    for row in buttons_list:
        admin_keyboard.append([InlineKeyboardButton(text=truncate_text(btn['text']), url=btn['url']) for btn in row])
    
    admin_keyboard.append([InlineKeyboardButton(text="--- أدوات الرقابة ---", callback_data="ignore_btn")])
    admin_keyboard.append([InlineKeyboardButton(text="🗑️ حذف الإعلان نهائياً", callback_data=f"adm_del_ad_{doc_id}")])
    markup = InlineKeyboardMarkup(inline_keyboard=admin_keyboard)

    full_desc = f"👀 <b>معاينة الإدارة للإعلان:</b>\n\n{desc}"

    if photo_id:
        await callback.message.answer_photo(photo=photo_id, caption=full_desc, reply_markup=markup, parse_mode="HTML")
    else:
        await callback.message.answer(full_desc, reply_markup=markup, parse_mode="HTML")
    await callback.answer()

# ================= حذف الإعلان من قبل المالك =================
@router.callback_query(F.data.startswith("adm_del_ad_"))
async def admin_delete_ad(callback: types.CallbackQuery):
    doc_id = callback.data.split("adm_del_ad_")[1]
    await asyncio.to_thread(db.collection("ads").document(doc_id).delete)
    
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest: pass
    
    await callback.message.reply("✅ <b>تم حذف الإعلان المخالف بنجاح من قاعدة البيانات.</b>", parse_mode="HTML")
    await callback.answer("تم الحذف!", show_alert=True)