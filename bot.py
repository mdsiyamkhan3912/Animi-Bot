import os
import asyncio
import threading
import requests
import json

from flask import Flask

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# ======================================================
# BOT TOKEN
# ======================================================

BOT_TOKEN ="8963746331:AAE_1Ej_BthpXDNG737xrEHsDRoSYOx7S8E"

# ======================================================
# ADMIN IDS
# ======================================================

ADMIN_IDS = [
    5084280631
]

# ======================================================
# FLASK KEEP ALIVE
# ======================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Running"

def run_web():
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )

# ======================================================
# BOT SETUP
# ======================================================

bot = Bot(token=BOT_TOKEN)

dp = Dispatcher(
    storage=MemoryStorage()
)

# ======================================================
# STATES
# ======================================================

class PaymentState(StatesGroup):

    waiting_for_eiin = State()

    waiting_for_student = State()

# ======================================================
# BUTTONS
# ======================================================

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(
                text="EIIN Number"
            )
        ]
    ],
    resize_keyboard=True
)

# ======================================================
# GET STUDENT
# ======================================================

def get_student(eiin, student_id):

    url = "https://api.eims.live/api/payment-portal/student-login"

    payload = {
        "institute_id": eiin,
        "custom_student_id": student_id
    }

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:

        r = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=20
        )

        data = r.json()

        student = data["payload"]["data"]["student"]

        token = data["payload"]["data"]["authorization"]["access_token"]

        return {
            "valid": True,
            "internal_id": student["id"],
            "student_id": student["student_id"],
            "name": student["student_name"],
            "class": student["class_name"],
            "shift": student["shift"],
            "department": student["department_name"],
            "academic_year": student["academic_year"],
            "roll": student["roll"],
            "academic_year_id": student["academic_year_list"][0]["id"],
            "token": token
        }

    except Exception as e:

        print(e)

        return {
            "valid": False
        }

# ======================================================
# GET INVOICE
# ======================================================

def get_invoice(student_internal_id, academic_year_id, token):

    url = "https://api.eims.live/api/payment-portal/payment-invoice-show"

    params = {
        "academic_year_id": academic_year_id,
        "student_id": student_internal_id
    }

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Authorization": f"Bearer {token}"
    }

    try:

        r = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=20
        )

        data = r.json()

        invoices = data["payload"]["data"]["enlistment_list"]["data"]

        if len(invoices) == 0:

            return {
                "valid": False
            }

        inv = invoices[0]

        invoice_number = inv.get("invoice", "N/A")

        # ==========================================
        # FULL INVOICE DETAILS
        # ==========================================

        details_url = f"https://api.eims.live/api/invoice-details?invoice={invoice_number}"

        details = requests.get(
            details_url,
            headers=headers,
            timeout=20
        ).json()

        invoice = details["payload"]["data"]["invoice"]

        payee = json.loads(
            invoice["payee_info"]
        )

        return {
            "valid": True,
            "invoice": invoice.get("invoice", "N/A"),
            "payment_date": invoice.get("payment_date", "N/A"),
            "phone": payee.get("contact", "N/A")
        }

    except Exception as e:

        print(e)

        return {
            "valid": False
        }

# ======================================================
# START
# ======================================================

@dp.message(CommandStart())
async def start(message: Message):

    if message.from_user.id not in ADMIN_IDS:

        await message.answer(
            "❌ Access Denied"
        )

        return

    await message.answer(
        "✅ Welcome To Student Payment Bot",
        reply_markup=main_keyboard
    )

# ======================================================
# EIIN BUTTON
# ======================================================

@dp.message(F.text == "EIIN Number")
async def eiin_button(message: Message, state: FSMContext):

    await message.answer(
        "📚 Send Institute EIIN Number"
    )

    await state.set_state(
        PaymentState.waiting_for_eiin
    )

# ======================================================
# SAVE EIIN
# ======================================================

@dp.message(PaymentState.waiting_for_eiin)
async def save_eiin(message: Message, state: FSMContext):

    eiin = message.text.strip()

    await state.update_data(
        eiin=eiin
    )

    await message.answer(
        f"✅ Institute Saved : {eiin}\n\n"
        f"Now Send Student ID OR Range\n\n"
        f"Example:\n"
        f"10032566\n\n"
        f"OR\n\n"
        f"10032566-10032666"
    )

    await state.set_state(
        PaymentState.waiting_for_student
    )

# ======================================================
# SEARCH SYSTEM
# ======================================================

@dp.message(PaymentState.waiting_for_student)
async def search_student(message: Message, state: FSMContext):

    text_input = message.text.strip()

    data = await state.get_data()

    eiin = data.get("eiin")

    if not eiin:

        await message.answer(
            "❌ First Set EIIN Number"
        )

        return

    # ==================================================
    # RANGE SEARCH
    # ==================================================

    if "-" in text_input:

        try:

            start, end = map(
                int,
                text_input.split("-")
            )

            total = end - start + 1

            if total > 2000:

                await message.answer(
                    "❌ Maximum 2000 IDs Allowed"
                )

                return

            await message.answer(
                f"🔍 Scanning {total} IDs..."
            )

            found = 0

            for sid in range(start, end + 1):

                student = get_student(
                    eiin,
                    str(sid)
                )

                if not student["valid"]:
                    continue

                invoice = get_invoice(
                    student["internal_id"],
                    student["academic_year_id"],
                    student["token"]
                )

                if not invoice["valid"]:
                    continue

                found += 1

                phone = invoice["phone"]

                if phone.startswith("0"):

                    whatsapp = "88" + phone

                else:

                    whatsapp = phone

                buttons = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="WhatsApp",
                                url=f"https://wa.me/{whatsapp}"
                            ),

                            InlineKeyboardButton(
                                text="Telegram",
                                url="https://t.me/Automate_IT_Ltd_Bot"
                            )
                        ]
                    ]
                )

                text = f"""
━━━━━━━━━━━━━━
🎓 STUDENT PAYMENT INFO
━━━━━━━━━━━━━━

🧾 Invoice Number : {invoice['invoice']}
👤 Name : {student['name']}
🆔 Student ID : {student['student_id']}
📞 Phone Number : {phone}

🏫 Department : {student['department']}
📚 Class : {student['class']}
🌅 Shift : {student['shift']}

📖 Academic Year : {student['academic_year']}
🎯 Student Roll : {student['roll']}

💳 Payment Date : {invoice['payment_date']}
"""

                await message.answer(
                    text,
                    reply_markup=buttons
                )

            await message.answer(
                f"✅ Scan Completed\n\nFound : {found}"
            )

        except Exception as e:

            print(e)

            await message.answer(
                "❌ Invalid Range Format"
            )

    # ==================================================
    # SINGLE SEARCH
    # ==================================================

    else:

        student = get_student(
            eiin,
            text_input
        )

        if not student["valid"]:

            await message.answer(
                "❌ Student Not Found"
            )

            return

        invoice = get_invoice(
            student["internal_id"],
            student["academic_year_id"],
            student["token"]
        )

        if not invoice["valid"]:

            await message.answer(
                "❌ Invoice Not Found"
            )

            return

        phone = invoice["phone"]

        if phone.startswith("0"):

            whatsapp = "88" + phone

        else:

            whatsapp = phone

        buttons = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="WhatsApp",
                        url=f"https://wa.me/{whatsapp}"
                    ),

                    InlineKeyboardButton(
                        text="Telegram",
                        url="https://t.me/new_bd_test_bot"
                    )
                ]
            ]
        )

        text = f"""
━━━━━━━━━━━━━━
🎓 STUDENT PAYMENT INFO
━━━━━━━━━━━━━━

🧾 Invoice Number : {invoice['invoice']}
👤 Name : {student['name']}
🆔 Student ID : {student['student_id']}
📞 Phone Number : {phone}

🏫 Department : {student['department']}
📚 Class : {student['class']}
🌅 Shift : {student['shift']}

📖 Academic Year : {student['academic_year']}
🎯 Student Roll : {student['roll']}

💳 Payment Date : {invoice['payment_date']}
"""

        await message.answer(
            text,
            reply_markup=buttons
        )

    await state.set_state(
        PaymentState.waiting_for_student
    )

# ======================================================
# MAIN
# ======================================================

async def main():

    print("Bot Started")

    threading.Thread(
        target=run_web
    ).start()

    await dp.start_polling(bot)

if __name__ == "__main__":

    asyncio.run(main())
