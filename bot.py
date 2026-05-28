import os
import threading
import cv2

from flask import Flask

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# TOKEN
BOT_TOKEN ="8626630085:AAHh6GY6zvYWuO0p5b7GPrD8bOakVMjHzao"

# FLASK
web_app = Flask(__name__)

@web_app.route("/")
def home():
    return "Anime Bot Running 🔥"

# STORE USER IMAGE
user_images = {}

# START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🔥 Send me a photo"
    )

# PHOTO RECEIVE
async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    photo_file = await update.message.photo[-1].get_file()

    file_path = f"{update.message.chat_id}.jpg"

    await photo_file.download_to_drive(file_path)

    user_images[update.message.chat_id] = file_path

    keyboard = [
        [
            InlineKeyboardButton(
                "🎨 Cartoon",
                callback_data="cartoon"
            ),

            InlineKeyboardButton(
                "🌸 Anime",
                callback_data="anime"
            )
        ],

        [
            InlineKeyboardButton(
                "🏯 Ghibli",
                callback_data="ghibli"
            ),

            InlineKeyboardButton(
                "✏ Sketch",
                callback_data="sketch"
            )
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Choose Style 👇",
        reply_markup=reply_markup
    )

# BUTTON CLICK
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    style = query.data

    chat_id = query.message.chat_id

    input_path = user_images.get(chat_id)

    if not input_path:

        await query.message.reply_text(
            "❌ No image found"
        )

        return

    try:

        img = cv2.imread(input_path)

        if img is None:

            await query.message.reply_text(
                "❌ Failed to load image"
            )

            return

        output_path = f"output_{chat_id}.jpg"

        # CARTOON
        if style == "cartoon":

            gray = cv2.cvtColor(
                img,
                cv2.COLOR_BGR2GRAY
            )

            gray = cv2.medianBlur(gray, 5)

            edges = cv2.adaptiveThreshold(
                gray,
                255,
                cv2.ADAPTIVE_THRESH_MEAN_C,
                cv2.THRESH_BINARY,
                9,
                9
            )

            color = cv2.bilateralFilter(
                img,
                9,
                250,
                250
            )

            result = cv2.bitwise_and(
                color,
                color,
                mask=edges
            )

        # ANIME
        elif style == "anime":

            result = cv2.stylization(
                img,
                sigma_s=60,
                sigma_r=0.45
            )

        # GHIBLI
        elif style == "ghibli":

            result = cv2.detailEnhance(
                img,
                sigma_s=12,
                sigma_r=0.15
            )

        # SKETCH
        elif style == "sketch":

            gray, result = cv2.pencilSketch(
                img,
                sigma_s=60,
                sigma_r=0.07,
                shade_factor=0.05
            )

        else:

            result = img

        cv2.imwrite(output_path, result)

        await query.message.reply_photo(
            photo=open(output_path, "rb"),
            caption=f"✅ {style.upper()} Done"
        )

    except Exception as e:

        await query.message.reply_text(
            f"❌ Error:\n{e}"
        )

# TELEGRAM BOT
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

telegram_app.add_handler(
    CommandHandler("start", start)
)

telegram_app.add_handler(
    MessageHandler(filters.PHOTO, photo)
)

telegram_app.add_handler(
    CallbackQueryHandler(button)
)

# RUN BOT
def run_bot():

    print("🔥 Telegram Bot Started")

    telegram_app.run_polling()

# MAIN
if __name__ == "__main__":

    threading.Thread(
        target=run_bot
    ).start()

    port = int(
        os.environ.get("PORT", 10000)
    )

    web_app.run(
        host="0.0.0.0",
        port=port
    )
