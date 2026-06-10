import asyncio
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import OWNER_ID
from database import db

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
        text = (f"👤 <b>بيانات التاجر:</b>\n\n"
                f"🆔 الآيدي: <code>{target_id}</code>\n"
                f"👤 اليوزر: @{data.get('username', 'بدون يوزر')}\n"
                f"📊 الإعلانات: {data.get('total_ads_created', 0)}\n"
                f"✅ مشترك: {'نعم' if data.get('is_subscribed') else 'لا'}\n"
                f"🚫 محظور: {'نعم' if data.get('is_banned') else 'لا'}")
        await message.reply(text, parse_mode="HTML", reply_markup=get_admin_keyboard())
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