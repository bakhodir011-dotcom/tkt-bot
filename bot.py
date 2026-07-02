import asyncio
import csv
import io
import json
import logging
import re
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    BufferedInputFile,
)

# ── Configuration ──────────────────────────────────────────────────────────────
BOT_TOKEN     = "8950472577:AAGZzPCmzKFDo9SrCvvQ5rHzl1nqcu-83Mg"
ADMIN_IDS        = {"216445816", "133078937"}
DB_FILE          = Path("registrations.json")
PAYMENT_PDF_PATH = Path("TKT Payment instructions.pdf")

# ── Local storage (JSON file) ──────────────────────────────────────────────────
def load_db() -> dict:
    if DB_FILE.exists():
        return json.loads(DB_FILE.read_text(encoding="utf-8"))
    return {"counter": 0, "registrations": [], "closed_dates": []}

def save_db(db: dict):
    DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")

def next_reg_id(db: dict) -> str:
    db["counter"] += 1
    return f"TKT-{datetime.now().year}-{db['counter']:04d}"

def is_duplicate(db: dict, passport: str, exam_date: str, module: str) -> bool:
    return any(
        r["passport"] == passport and r["exam_date"] == exam_date and r["module"] == module
        for r in db["registrations"]
    )

# ── FSM States ─────────────────────────────────────────────────────────────────
class Admin(StatesGroup):
    broadcast_input = State()
    search_input    = State()

class Reg(StatesGroup):
    language  = State()
    full_name = State()
    month     = State()
    date      = State()
    module    = State()
    passport  = State()
    phone     = State()
    email     = State()
    confirm   = State()
    photo     = State()

TOTAL_STEPS = 7

# ── Localisation ───────────────────────────────────────────────────────────────
T = {
    "uz": {
        "welcome":          "TKT Ro'yxatga olish botiga xush kelibsiz!\n\n📋 <b>Imtihon ma'lumotlari:</b>\n🏫 <b>Imtihon markazi:</b> Innovative Centre — UZ050\n📝 <b>Imtihon:</b> TKT (Teaching Knowledge Test)\n📍 <b>Manzil:</b> Samarqand sh., Gagarin ko'chasi, 95A\n💰 <b>Imtihon to'lovi:</b> 686,000 so'm\n📢 <b>Telegram kanal:</b> @tkt_uzb",
        "full_name":        "👤 Ism va familiyangizni kiriting:",
        "select_month":     "📅 Oyni tanlang:",
        "select_date":      "📅 Sanani tanlang:",
        "select_module":    "📚 Modulni tanlang:",
        "passport":         "🪪 Pasport yoki ID raqamingizni kiriting (masalan: AA1234567):",
        "passport_err":     "❌ Pasport yoki ID raqamini to'g'ri formatda yuboring (masalan: AA1234567):",
        "duplicate":        "⚠️ Bu pasport raqami ushbu sana va modul uchun allaqachon ro'yxatga olingan.",
        "phone":            "📞 Telefon raqamingizni yuboring (998 bilan boshlab) yoki pastdagi tugmani bosing:",
        "phone_err":        "❌ To'g'ri telefon raqami yuboring (998 bilan boshlab):",
        "phone_btn":        "📱 Raqamni ulashish",
        "email":            "📧 Email manzilingizni yuboring:",
        "email_err":        "❌ To'g'ri email manzil yuboring:",
        "confirm_title":    "📋 Ma'lumotlaringizni tekshiring:",
        "confirm_ok":       "✅ Tasdiqlash",
        "confirm_restart":  "🔄 Qaytadan boshlash",
        "photo":            "📸 Pasportingizning ANIQ skanini yuboring\n(Aniq skansiz ro'yxatga olish amalga oshirilmaydi).",
        "photo_err":        "❌ Iltimos, rasm yuboring.",
        "thank_you":        "✅ Rahmat! Ro'yxatga olish muvaffaqiyatli yakunlandi.",
        "reg_another":      "🔁 Boshqa nomzodni ro'yxatga olish",
        "cancelled":        "❌ Ro'yxatga olish bekor qilindi. Boshlash uchun /start yuboring.",
        "exam_details":     "Sizning imtihon ma'lumotlaringiz:",
        "name_label":       "Ism",
        "module_label":     "Modul",
        "date_label":       "Sana",
        "time_label":       "Vaqt",
        "location_label":   "Manzil",
        "fee_label":        "Imtihon to'lovi",
        "contact_label":    "Savollar uchun",
        "step":             "📍 Qadam {step} / {total}",
        "back":             "⬅️ Orqaga",
        "months":           {"August": "Avgust", "September": "Sentabr", "October": "Oktabr", "November": "Noyabr", "December": "Dekabr"},
    },
    "ru": {
        "welcome":          "Добро пожаловать в бот регистрации TKT!\n\n📋 <b>Информация об экзамене:</b>\n🏫 <b>Центр:</b> Innovative Centre — UZ050\n📝 <b>Экзамен:</b> TKT (Teaching Knowledge Test)\n📍 <b>Адрес:</b> г. Самарканд, ул. Гагарина, 95A\n💰 <b>Стоимость:</b> 686,000 сум\n📢 <b>Telegram канал:</b> @tkt_uzb",
        "full_name":        "👤 Введите ваше полное имя:",
        "select_month":     "📅 Выберите месяц:",
        "select_date":      "📅 Выберите дату:",
        "select_module":    "📚 Выберите модуль:",
        "passport":         "🪪 Введите номер паспорта или ID (например: AA1234567):",
        "passport_err":     "❌ Отправьте номер в правильном формате (например: AA1234567):",
        "duplicate":        "⚠️ Этот номер паспорта уже зарегистрирован на выбранную дату и модуль.",
        "phone":            "📞 Отправьте номер телефона (начиная с 998) или нажмите кнопку ниже:",
        "phone_err":        "❌ Отправьте корректный номер (начиная с 998):",
        "phone_btn":        "📱 Поделиться номером",
        "email":            "📧 Отправьте адрес электронной почты:",
        "email_err":        "❌ Отправьте корректный адрес электронной почты:",
        "confirm_title":    "📋 Проверьте ваши данные:",
        "confirm_ok":       "✅ Подтвердить",
        "confirm_restart":  "🔄 Начать заново",
        "photo":            "📸 Отправьте ЧЁТКИЙ скан паспорта\n(Без чёткого скана регистрация не будет принята).",
        "photo_err":        "❌ Пожалуйста, отправьте фото.",
        "thank_you":        "✅ Спасибо! Регистрация успешно завершена.",
        "reg_another":      "🔁 Зарегистрировать другого кандидата",
        "cancelled":        "❌ Регистрация отменена. Отправьте /start чтобы начать снова.",
        "exam_details":     "Данные вашего экзамена:",
        "name_label":       "Имя",
        "module_label":     "Модуль",
        "date_label":       "Дата",
        "time_label":       "Время",
        "location_label":   "Адрес",
        "fee_label":        "Стоимость экзамена",
        "contact_label":    "По вопросам",
        "step":             "📍 Шаг {step} из {total}",
        "back":             "⬅️ Назад",
        "months":           {"August": "Август", "September": "Сентябрь", "October": "Октябрь", "November": "Ноябрь", "December": "Декабрь"},
    },
    "en": {
        "welcome":          "Welcome to TKT Registration bot!\n\n📋 <b>Exam details:</b>\n🏫 <b>Exam centre:</b> Innovative Centre — UZ050\n📝 <b>Exam:</b> TKT (Teaching Knowledge Test)\n📍 <b>Location:</b> Samarkand city, Gagarin street, 95A\n💰 <b>Exam fee:</b> 686,000 so'm\n📢 <b>Telegram channel:</b> @tkt_uzb",
        "full_name":        "👤 Enter your full name:",
        "select_month":     "📅 Select Month:",
        "select_date":      "📅 Select a date:",
        "select_module":    "📚 Please select the module:",
        "passport":         "🪪 Please enter your Passport or ID Number (e.g. AA1234567):",
        "passport_err":     "❌ Send Passport or ID in the correct format (e.g. AA1234567):",
        "duplicate":        "⚠️ This passport is already registered for the selected date and module.",
        "phone":            "📞 Send your phone number (including 998) or press the button below:",
        "phone_err":        "❌ Send a valid phone number (including 998):",
        "phone_btn":        "📱 Share Phone Number",
        "email":            "📧 Send your email address:",
        "email_err":        "❌ Send a valid email address:",
        "confirm_title":    "📋 Please review your details:",
        "confirm_ok":       "✅ Confirm",
        "confirm_restart":  "🔄 Start Over",
        "photo":            "📸 Please send the CLEAR scan of your passport\n(Without a clear scan your registration will not be processed).",
        "photo_err":        "❌ Please send a photo.",
        "thank_you":        "✅ Thank you! Your registration has been successfully completed.",
        "reg_another":      "🔁 Register another candidate",
        "cancelled":        "❌ Registration cancelled. Send /start to begin again.",
        "exam_details":     "Your exam details:",
        "name_label":       "Name",
        "module_label":     "Module",
        "date_label":       "Date",
        "time_label":       "Time",
        "location_label":   "Location",
        "fee_label":        "Exam fee",
        "contact_label":    "Any questions",
        "step":             "📍 Step {step} of {total}",
        "back":             "⬅️ Back",
        "months":           {"August": "August", "September": "September", "October": "October", "November": "November", "December": "December"},
    },
}

MODULE_TIMES = {
    "TKT Module 1": "10:00",
    "TKT Module 2": "12:00",
    "TKT Module 3": "14:00",
}

EXAM_DATES = {
    "August":    ["August 2",    "August 9",    "August 23"],
    "September": ["September 6", "September 13","September 20"],
    "October":   ["October 4",   "October 11",  "October 18"],
    "November":  ["November 1",  "November 8",  "November 15"],
    "December":  ["December 6",  "December 13", "December 20"],
}

ALL_MONTHS = ["August", "September", "October", "November", "December"]

# ── Helpers ────────────────────────────────────────────────────────────────────
def step(lang: str, n: int) -> str:
    return T[lang]["step"].format(step=n, total=TOTAL_STEPS)

def confirm_text(lang: str, data: dict) -> str:
    return (
        f"{T[lang]['confirm_title']}\n\n"
        f"👤 <b>Name:</b> {data.get('full_name','')}\n"
        f"📅 <b>Exam Date:</b> {data.get('exam_date','')}\n"
        f"📚 <b>Module:</b> {data.get('module','')}\n"
        f"🪪 <b>Passport/ID:</b> {data.get('passport','')}\n"
        f"📞 <b>Phone:</b> +{data.get('phone','')}\n"
        f"📧 <b>Email:</b> {data.get('email','')}\n"
    )

# ── Keyboards ──────────────────────────────────────────────────────────────────
def kb_lang():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇿 O'zbek",  callback_data="lang_uz")],
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")],
    ])

def kb_month(lang):
    db     = load_db()
    closed = set(db.get("closed_dates", []))
    labels = T[lang]["months"]
    rows   = [
        [InlineKeyboardButton(text=labels[m], callback_data=f"month_{m}")]
        for m in ALL_MONTHS
        if any(d not in closed for d in EXAM_DATES[m])
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_date(month, lang):
    db     = load_db()
    closed = set(db.get("closed_dates", []))
    rows   = [
        [InlineKeyboardButton(text=d, callback_data=f"date_{d}")]
        for d in EXAM_DATES[month] if d not in closed
    ]
    rows.append([InlineKeyboardButton(text=T[lang]["back"], callback_data="back_month")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_module(lang):
    rows = [[InlineKeyboardButton(text=f"TKT Module {i}", callback_data=f"module_{i}")] for i in [1, 2, 3]]
    rows.append([InlineKeyboardButton(text=T[lang]["back"], callback_data="back_date")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_phone(lang):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=T[lang]["phone_btn"], request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True,
    )

def kb_confirm(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=T[lang]["confirm_ok"],      callback_data="confirm_yes")],
        [InlineKeyboardButton(text=T[lang]["confirm_restart"], callback_data="confirm_restart")],
    ])

def kb_reg_another(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=T[lang]["reg_another"], callback_data="reg_another")]
    ])

RE_PASSPORT = re.compile(r'^[A-Z]{2}\d{7}$')
RE_PHONE    = re.compile(r'^998\d{9}$')
RE_EMAIL    = re.compile(r'^[\w\.\+\-]+@[\w\-]+\.\w{2,}$')

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

# ── /start ─────────────────────────────────────────────────────────────────────
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(Reg.language)
    await message.answer(
        "Tilni tanlang / Выберите язык / Select Language:",
        reply_markup=kb_lang(),
    )

# ── /cancel ────────────────────────────────────────────────────────────────────
@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "en")
    await state.clear()
    await message.answer(T[lang]["cancelled"], reply_markup=ReplyKeyboardRemove())

# ── Language ───────────────────────────────────────────────────────────────────
@dp.callback_query(Reg.language, F.data.startswith("lang_"))
async def on_lang(cb: types.CallbackQuery, state: FSMContext):
    lang = cb.data.split("_")[1]
    await state.update_data(lang=lang)
    await state.set_state(Reg.full_name)
    await cb.message.edit_text(T[lang]["welcome"], parse_mode="HTML")
    await cb.message.answer(f"{step(lang, 1)}\n\n{T[lang]['full_name']}")
    await cb.answer()

# ── Full Name ──────────────────────────────────────────────────────────────────
@dp.message(Reg.full_name)
async def on_full_name(message: types.Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        return
    data = await state.get_data()
    lang = data["lang"]
    await state.update_data(full_name=name)
    await state.set_state(Reg.month)
    await message.answer(
        f"{step(lang, 2)}\n\n{T[lang]['select_month']}",
        reply_markup=kb_month(lang),
    )

# ── Month ──────────────────────────────────────────────────────────────────────
@dp.callback_query(Reg.month, F.data.startswith("month_"))
async def on_month(cb: types.CallbackQuery, state: FSMContext):
    month = cb.data[6:]
    data  = await state.get_data()
    lang  = data["lang"]
    await state.update_data(month=month)
    await state.set_state(Reg.date)
    await cb.message.edit_text(
        f"{step(lang, 3)}\n\n{T[lang]['select_date']}",
        reply_markup=kb_date(month, lang),
    )
    await cb.answer()

@dp.callback_query(Reg.date, F.data == "back_month")
async def back_to_month(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data["lang"]
    await state.set_state(Reg.month)
    await cb.message.edit_text(
        f"{step(lang, 2)}\n\n{T[lang]['select_month']}",
        reply_markup=kb_month(lang),
    )
    await cb.answer()

# ── Date ───────────────────────────────────────────────────────────────────────
@dp.callback_query(Reg.date, F.data.startswith("date_"))
async def on_date(cb: types.CallbackQuery, state: FSMContext):
    date = cb.data[5:]
    data = await state.get_data()
    lang = data["lang"]
    await state.update_data(exam_date=date)
    await state.set_state(Reg.module)
    await cb.message.edit_text(
        f"{step(lang, 4)}\n\n{T[lang]['select_module']}",
        reply_markup=kb_module(lang),
    )
    await cb.answer()

@dp.callback_query(Reg.module, F.data == "back_date")
async def back_to_date(cb: types.CallbackQuery, state: FSMContext):
    data  = await state.get_data()
    lang  = data["lang"]
    month = data["month"]
    await state.set_state(Reg.date)
    await cb.message.edit_text(
        f"{step(lang, 3)}\n\n{T[lang]['select_date']}",
        reply_markup=kb_date(month, lang),
    )
    await cb.answer()

# ── Module ─────────────────────────────────────────────────────────────────────
@dp.callback_query(Reg.module, F.data.startswith("module_"))
async def on_module(cb: types.CallbackQuery, state: FSMContext):
    num    = cb.data.split("_")[1]
    module = f"TKT Module {num}"
    data   = await state.get_data()
    lang   = data["lang"]
    await state.update_data(module=module)
    await state.set_state(Reg.passport)
    await cb.message.edit_text(f"{step(lang, 5)}\n\n{T[lang]['passport']}")
    await cb.answer()

# ── Passport ───────────────────────────────────────────────────────────────────
@dp.message(Reg.passport)
async def on_passport(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data["lang"]
    text = (message.text or "").strip().upper()

    if not RE_PASSPORT.match(text):
        await message.answer(T[lang]["passport_err"])
        return

    db = load_db()
    if is_duplicate(db, text, data.get("exam_date", ""), data.get("module", "")):
        await message.answer(T[lang]["duplicate"])
        return

    await state.update_data(passport=text)
    await state.set_state(Reg.phone)
    await message.answer(
        f"{step(lang, 6)}\n\n{T[lang]['phone']}",
        reply_markup=kb_phone(lang),
    )

# ── Phone ──────────────────────────────────────────────────────────────────────
@dp.message(Reg.phone)
async def on_phone(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data["lang"]
    if message.contact:
        phone = message.contact.phone_number.replace("+", "").replace(" ", "")
    else:
        phone = (message.text or "").replace("+", "").replace(" ", "").strip()
    if not RE_PHONE.match(phone):
        await message.answer(T[lang]["phone_err"], reply_markup=kb_phone(lang))
        return
    await state.update_data(phone=phone)
    await state.set_state(Reg.email)
    await message.answer(
        f"{step(lang, 7)}\n\n{T[lang]['email']}",
        reply_markup=ReplyKeyboardRemove(),
    )

# ── Email ──────────────────────────────────────────────────────────────────────
@dp.message(Reg.email)
async def on_email(message: types.Message, state: FSMContext):
    data  = await state.get_data()
    lang  = data["lang"]
    email = (message.text or "").strip()
    if not RE_EMAIL.match(email):
        await message.answer(T[lang]["email_err"])
        return
    await state.update_data(email=email)
    await state.set_state(Reg.confirm)
    all_data = await state.get_data()
    await message.answer(
        confirm_text(lang, all_data),
        reply_markup=kb_confirm(lang),
        parse_mode="HTML",
    )

# ── Confirm ────────────────────────────────────────────────────────────────────
@dp.callback_query(Reg.confirm, F.data == "confirm_yes")
async def on_confirm(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data["lang"]
    await state.set_state(Reg.photo)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(T[lang]["photo"])
    await cb.answer()

@dp.callback_query(Reg.confirm, F.data == "confirm_restart")
async def on_confirm_restart(cb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(Reg.language)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(
        "Tilni tanlang / Выберите язык / Select Language:",
        reply_markup=kb_lang(),
    )
    await cb.answer()

# ── Photo & save ───────────────────────────────────────────────────────────────
@dp.message(Reg.photo)
async def on_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data["lang"]

    if not message.photo and not message.document:
        await message.answer(T[lang]["photo_err"])
        return

    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    ts      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db     = load_db()
    reg_id = next_reg_id(db)
    record = {
        "reg_id":    reg_id,
        "timestamp": ts,
        "full_name": data.get("full_name", ""),
        "exam_date": data.get("exam_date", ""),
        "module":    data.get("module", ""),
        "passport":  data.get("passport", ""),
        "phone":     "+" + data.get("phone", ""),
        "email":     data.get("email", ""),
        "lang":      lang.upper(),
        "tg_id":     str(message.from_user.id),
        "username":  message.from_user.username or "",
    }
    db["registrations"].append(record)
    save_db(db)

    username_str = (
        f"@{message.from_user.username}"
        if message.from_user.username
        else f'<a href="tg://user?id={message.from_user.id}">Profile</a>'
    )
    admin_caption = (
        f"📋 <b>New Registration</b>  •  <code>{reg_id}</code>\n\n"
        f"👤 <b>Name:</b> {data.get('full_name','')}\n"
        f"📅 <b>Exam Date:</b> {data.get('exam_date','')}\n"
        f"📚 <b>Module:</b> {data.get('module','')}\n"
        f"🪪 <b>Passport/ID:</b> {data.get('passport','')}\n"
        f"📞 <b>Phone:</b> +{data.get('phone','')}\n"
        f"📧 <b>Email:</b> {data.get('email','')}\n"
        f"🌐 <b>Language:</b> {lang.upper()}\n"
        f"🆔 <b>Telegram:</b> {username_str}\n"
        f"🕐 <b>Time:</b> {ts}"
    )
    try:
        for admin_id in ADMIN_IDS:
            await bot.send_photo(
                chat_id=admin_id,
                photo=file_id,
                caption=admin_caption,
                parse_mode="HTML",
            )
    except Exception as exc:
        logging.error("Admin notification error: %s", exc)

    exam_time = MODULE_TIMES.get(data.get("module", ""), "")
    thank_you_text = (
        f"{T[lang]['thank_you']}\n\n"
        f"🎫 <b>Registration ID: {reg_id}</b>\n\n"
        f"📋 <b>{T[lang]['exam_details']}</b>\n"
        f"👤 <b>{T[lang]['name_label']}:</b> {data.get('full_name','')}\n"
        f"📚 <b>{T[lang]['module_label']}:</b> {data.get('module','')}\n"
        f"📅 <b>{T[lang]['date_label']}:</b> {data.get('exam_date','')}\n"
        f"⏰ <b>{T[lang]['time_label']}:</b> {exam_time}\n"
        f"📍 <b>{T[lang]['location_label']}:</b> Samarkand city, Gagarin street, 95A\n"
        f"💰 <b>{T[lang]['fee_label']}:</b> 686,000 so'm\n\n"
        f"❓ <b>{T[lang]['contact_label']}:</b> @innovative_exam | +998 55 701 01 06"
    )
    await message.answer(
        thank_you_text,
        reply_markup=kb_reg_another(lang),
        parse_mode="HTML",
    )
    if PAYMENT_PDF_PATH.exists():
        await message.answer_document(
            BufferedInputFile(
                PAYMENT_PDF_PATH.read_bytes(),
                filename="TKT_Payment_Instructions.pdf",
            ),
            caption=(
                "💳 Imtihon uchun to'lovni <b>Click</b> yoki <b>Payme</b> ilovalari orqali amalga oshirish mumkin.\n\n"
                "Qidiruvda <b>«Innovative Exams»</b> yozing, ma'lumotlarni kiritib, TKT Modulini tanlang."
            ),
            parse_mode="HTML",
        )
    await state.clear()

# ── Register another candidate ─────────────────────────────────────────────────
@dp.callback_query(F.data == "reg_another")
async def on_reg_another(cb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(Reg.language)
    await cb.message.answer(
        "Tilni tanlang / Выберите язык / Select Language:",
        reply_markup=kb_lang(),
    )
    await cb.answer()

# ── Admin: /stats ──────────────────────────────────────────────────────────────
@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if str(message.from_user.id) not in ADMIN_IDS:
        return
    db   = load_db()
    regs = db["registrations"]
    if not regs:
        await message.answer("No registrations yet.")
        return

    by_module = {}
    by_date   = {}
    for r in regs:
        by_module[r["module"]]    = by_module.get(r["module"], 0) + 1
        by_date[r["exam_date"]]   = by_date.get(r["exam_date"], 0) + 1

    module_lines = "\n".join(f"  • {k}: <b>{v}</b>" for k, v in sorted(by_module.items()))
    date_lines   = "\n".join(f"  • {k}: <b>{v}</b>" for k, v in sorted(by_date.items()))

    await message.answer(
        f"📊 <b>TKT Registration Stats</b>\n\n"
        f"Total registrations: <b>{len(regs)}</b>\n\n"
        f"<b>By Module:</b>\n{module_lines}\n\n"
        f"<b>By Exam Date:</b>\n{date_lines}",
        parse_mode="HTML",
    )

# ── Admin: /export ─────────────────────────────────────────────────────────────
@dp.message(Command("export"))
async def cmd_export(message: types.Message):
    if str(message.from_user.id) not in ADMIN_IDS:
        return
    db   = load_db()
    regs = db["registrations"]
    if not regs:
        await message.answer("No registrations to export.")
        return

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=regs[0].keys())
    writer.writeheader()
    writer.writerows(regs)
    csv_bytes = output.getvalue().encode("utf-8-sig")  # utf-8-sig opens correctly in Excel

    await message.answer_document(
        BufferedInputFile(
            csv_bytes,
            filename=f"tkt_registrations_{datetime.now().strftime('%Y%m%d')}.csv",
        ),
        caption=f"📁 {len(regs)} registrations exported.",
    )

# ── Admin panel keyboard ───────────────────────────────────────────────────────
def kb_admin_panel():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Stats",      callback_data="ap_stats"),
            InlineKeyboardButton(text="📁 Export CSV", callback_data="ap_export"),
        ],
        [
            InlineKeyboardButton(text="📣 Broadcast",  callback_data="ap_broadcast"),
            InlineKeyboardButton(text="🔍 Search",     callback_data="ap_search"),
        ],
        [
            InlineKeyboardButton(text="🔒 Close date", callback_data="ap_close"),
            InlineKeyboardButton(text="🔓 Open date",  callback_data="ap_open"),
        ],
    ])

def kb_dates_toggle(action: str):
    rows = []
    db     = load_db()
    closed = set(db.get("closed_dates", []))
    for month, dates in EXAM_DATES.items():
        for d in dates:
            if action == "close" and d not in closed:
                rows.append([InlineKeyboardButton(text=d, callback_data=f"toggle_{action}_{d}")])
            elif action == "open" and d in closed:
                rows.append([InlineKeyboardButton(text=f"🔓 {d}", callback_data=f"toggle_{action}_{d}")])
    rows.append([InlineKeyboardButton(text="❌ Cancel", callback_data="ap_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ── /admin ─────────────────────────────────────────────────────────────────────
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if str(message.from_user.id) not in ADMIN_IDS:
        return
    db     = load_db()
    closed = db.get("closed_dates", [])
    closed_str = "\n".join(f"🔒 {d}" for d in closed) if closed else "None"
    await message.answer(
        f"⚙️ <b>Admin Panel</b>\n\n"
        f"👥 Total registrations: <b>{len(db['registrations'])}</b>\n"
        f"🔒 Closed dates:\n{closed_str}",
        reply_markup=kb_admin_panel(),
        parse_mode="HTML",
    )

@dp.callback_query(F.data == "ap_stats")
async def ap_stats(cb: types.CallbackQuery):
    if str(cb.from_user.id) not in ADMIN_IDS:
        return
    db   = load_db()
    regs = db["registrations"]
    if not regs:
        await cb.answer("No registrations yet.", show_alert=True)
        return
    by_module = {}
    by_date   = {}
    for r in regs:
        by_module[r["module"]]  = by_module.get(r["module"], 0) + 1
        by_date[r["exam_date"]] = by_date.get(r["exam_date"], 0) + 1
    module_lines = "\n".join(f"  • {k}: <b>{v}</b>" for k, v in sorted(by_module.items()))
    date_lines   = "\n".join(f"  • {k}: <b>{v}</b>" for k, v in sorted(by_date.items()))
    await cb.message.answer(
        f"📊 <b>TKT Registration Stats</b>\n\n"
        f"Total: <b>{len(regs)}</b>\n\n"
        f"<b>By Module:</b>\n{module_lines}\n\n"
        f"<b>By Exam Date:</b>\n{date_lines}",
        parse_mode="HTML",
    )
    await cb.answer()

@dp.callback_query(F.data == "ap_export")
async def ap_export(cb: types.CallbackQuery):
    if str(cb.from_user.id) not in ADMIN_IDS:
        return
    db   = load_db()
    regs = db["registrations"]
    if not regs:
        await cb.answer("No registrations to export.", show_alert=True)
        return
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=regs[0].keys())
    writer.writeheader()
    writer.writerows(regs)
    csv_bytes = output.getvalue().encode("utf-8-sig")
    await cb.message.answer_document(
        BufferedInputFile(csv_bytes, filename=f"tkt_{datetime.now().strftime('%Y%m%d')}.csv"),
        caption=f"📁 {len(regs)} registrations exported.",
    )
    await cb.answer()

@dp.callback_query(F.data == "ap_broadcast")
async def ap_broadcast_prompt(cb: types.CallbackQuery, state: FSMContext):
    if str(cb.from_user.id) not in ADMIN_IDS:
        return
    await state.set_state(Admin.broadcast_input)
    await cb.message.answer("📣 Enter the message to broadcast to all candidates:")
    await cb.answer()

@dp.message(Admin.broadcast_input)
async def ap_broadcast_send(message: types.Message, state: FSMContext):
    if str(message.from_user.id) not in ADMIN_IDS:
        return
    text    = message.text or ""
    db      = load_db()
    user_ids = list({r["tg_id"] for r in db["registrations"] if r.get("tg_id")})
    sent = failed = 0
    for uid in user_ids:
        try:
            await bot.send_message(chat_id=uid, text=text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
    await message.answer(
        f"📣 <b>Broadcast complete</b>\n\n✅ Sent: <b>{sent}</b>\n❌ Failed: <b>{failed}</b>",
        parse_mode="HTML",
    )
    await state.clear()

@dp.callback_query(F.data == "ap_search")
async def ap_search_prompt(cb: types.CallbackQuery, state: FSMContext):
    if str(cb.from_user.id) not in ADMIN_IDS:
        return
    await state.set_state(Admin.search_input)
    await cb.message.answer("🔍 Enter passport/ID number to search (e.g. AA1234567):")
    await cb.answer()

@dp.message(Admin.search_input)
async def ap_search_result(message: types.Message, state: FSMContext):
    if str(message.from_user.id) not in ADMIN_IDS:
        return
    query = (message.text or "").strip().upper()
    db    = load_db()
    found = [r for r in db["registrations"] if r.get("passport","").upper() == query]
    if not found:
        await message.answer(f"❌ No registration found for <code>{query}</code>.", parse_mode="HTML")
    else:
        for r in found:
            await message.answer(
                f"🔍 <b>Found:</b>\n\n"
                f"🎫 <b>ID:</b> {r['reg_id']}\n"
                f"👤 <b>Name:</b> {r['full_name']}\n"
                f"📅 <b>Date:</b> {r['exam_date']}\n"
                f"📚 <b>Module:</b> {r['module']}\n"
                f"🪪 <b>Passport:</b> {r['passport']}\n"
                f"📞 <b>Phone:</b> {r['phone']}\n"
                f"📧 <b>Email:</b> {r['email']}\n"
                f"🕐 <b>Time:</b> {r['timestamp']}",
                parse_mode="HTML",
            )
    await state.clear()

@dp.callback_query(F.data == "ap_close")
async def ap_close_prompt(cb: types.CallbackQuery):
    if str(cb.from_user.id) not in ADMIN_IDS:
        return
    kb = kb_dates_toggle("close")
    if not kb.inline_keyboard[:-1]:
        await cb.answer("No open dates to close.", show_alert=True)
        return
    await cb.message.answer("🔒 Select a date to close:", reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data == "ap_open")
async def ap_open_prompt(cb: types.CallbackQuery):
    if str(cb.from_user.id) not in ADMIN_IDS:
        return
    kb = kb_dates_toggle("open")
    if not kb.inline_keyboard[:-1]:
        await cb.answer("No closed dates to open.", show_alert=True)
        return
    await cb.message.answer("🔓 Select a date to open:", reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data.startswith("toggle_close_"))
async def toggle_close(cb: types.CallbackQuery):
    if str(cb.from_user.id) not in ADMIN_IDS:
        return
    date = cb.data.removeprefix("toggle_close_")
    db   = load_db()
    if "closed_dates" not in db:
        db["closed_dates"] = []
    if date not in db["closed_dates"]:
        db["closed_dates"].append(date)
        save_db(db)
        await cb.message.edit_text(f"🔒 <b>{date}</b> has been closed.", parse_mode="HTML")
    await cb.answer()

@dp.callback_query(F.data.startswith("toggle_open_"))
async def toggle_open(cb: types.CallbackQuery):
    if str(cb.from_user.id) not in ADMIN_IDS:
        return
    date = cb.data.removeprefix("toggle_open_")
    db   = load_db()
    if "closed_dates" not in db:
        db["closed_dates"] = []
    if date in db["closed_dates"]:
        db["closed_dates"].remove(date)
        save_db(db)
        await cb.message.edit_text(f"🔓 <b>{date}</b> has been reopened.", parse_mode="HTML")
    await cb.answer()

@dp.callback_query(F.data == "ap_cancel")
async def ap_cancel(cb: types.CallbackQuery):
    await cb.message.delete()
    await cb.answer()

# ── Admin: /broadcast ─────────────────────────────────────────────────────────
@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message):
    if str(message.from_user.id) not in ADMIN_IDS:
        return

    text = message.text.removeprefix("/broadcast").strip()
    if not text:
        await message.answer(
            "Usage:\n<code>/broadcast Your message here</code>\n\n"
            "You can also send a photo with /broadcast as the caption.",
            parse_mode="HTML",
        )
        return

    db   = load_db()
    regs = db["registrations"]
    if not regs:
        await message.answer("No registered candidates yet.")
        return

    # Get unique Telegram IDs
    user_ids = list({r["tg_id"] for r in regs if r.get("tg_id")})

    sent = 0
    failed = 0
    for uid in user_ids:
        try:
            await bot.send_message(chat_id=uid, text=text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1

    await message.answer(
        f"📣 <b>Broadcast complete</b>\n\n"
        f"✅ Sent: <b>{sent}</b>\n"
        f"❌ Failed: <b>{failed}</b>\n"
        f"👥 Total: <b>{len(user_ids)}</b>",
        parse_mode="HTML",
    )

# ── Run ────────────────────────────────────────────────────────────────────────
async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
