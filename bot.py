import os
import sys
import logging
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from PIL import Image, ImageDraw, ImageFont

# --- [CRITICAL FIX] MoviePy-এর ভেতরের ANTIALIAS এরর চিরতরে দূর করার ম্যাজিক লজিক ---
# কোডটি রান হওয়া মাত্রই গ্লোবালি এবং moviepy-এর ভেতরের মডিউলে ANTIALIAS ফিক্স করে দেবে
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.Resampling.LANCZOS
    
# moviepy যেখানে ইমেজ প্রসেস করে, সেখানে জোরপূর্বক এটি ইমপোর্ট করিয়ে দেওয়া
try:
    import moviepy.video.fx.all as mv_fx
    import moviepy.video.VideoClip as mv_clip
    mv_clip.Image.ANTIALIAS = Image.Resampling.LANCZOS
except Exception:
    pass

# এবার সেফলি moviepy ইমপোর্ট করা হচ্ছে
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
# ---------------------------------------------------------------------------------

# লগিং সেটআপ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# তোমার দেওয়া টেস্ট টোকেন
TOKEN = "8716578947:AAG1tliMeUj78ZsYBEvi1YI8I1GhIpuV2B4"

DOWNLOAD_DIR = "bot_files"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ----------------- FLASK SERVER -----------------
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "বট একদম লাইভ আছে ভাই! 😎", 200

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host='0.0.0.0', port=port)
# ------------------------------------------------

# Pillow দিয়ে হলুদ টেক্সট ব্যানার তৈরি করার ফাংশন
def create_text_banner(width, text, font_size=32):
    banner = Image.new("RGBA", (width, 150), (255, 255, 255, 0))
    draw = ImageDraw.Draw(banner)
    try:
        font = ImageFont.load_default()
    except:
        font = None
        
    w, h = width * 0.5, 60
    position = ((width - w) // 2, (150 - h) // 2)
    draw.text(position, text, fill="yellow", font=font)
    
    banner_path = os.path.join(DOWNLOAD_DIR, "temp_banner.png")
    banner.save(banner_path)
    return banner_path

# /start কমান্ড হ্যান্ডলার
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "হ্যালো ভাই! ভিডিও এডিটিং বটে স্বাগতম। 😎\n\n"
        "👉 কাজ শুরু করতে প্রথমে আপনার **ভিডিওটি** পাঠান।"
    )

# ভিডিও হ্যান্ডলার (ধাপ ১)
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video_file = await update.message.video.get_file()
    video_path = os.path.join(DOWNLOAD_DIR, f"{update.effective_user.id}_input.mp4")
    
    await update.message.reply_text("⏳ ভিডিওটি ডাউনলোড হচ্ছে, দয়া করে একটু অপেক্ষা করুন...")
    await video_file.download_to_drive(video_path)
    
    context.user_data['video_path'] = video_path
    await update.message.reply_text("✅ ভিডিও পেয়েছি ভাই! এবার আপনার **ছবিটি** পাঠান।")

# ফটো হ্যান্ডলার এবং ভিডিও এডিটিং (ধাপ ২)
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'video_path' not in context.user_data:
        await update.message.reply_text("⚠️ ভাই, আগে ভিডিও পাঠান, তারপর ছবি দিবেন।")
        return

    status_message = await update.message.reply_text("⏳ ছবি পাওয়া গেছে। প্রসেসিং এবং রেন্ডারিং শুরু হচ্ছে ভাই, একটু সময় লাগবে...")
    
    photo_file = await update.message.photo[-1].get_file()
    photo_path = os.path.join(DOWNLOAD_DIR, f"{update.effective_user.id}_user_photo.png")
    await photo_file.download_to_drive(photo_path)
    
    video_path = context.user_data['video_path']
    output_path = os.path.join(DOWNLOAD_DIR, f"{update.effective_user.id}_output.mp4")

    try:
        # --- MoviePy ভিডিও এডিটিং শুরু ---
        video = VideoFileClip(video_path)
        
        # ১. ইউজারের পাঠানো ছবি পজিশন (মাথার ওপরের এরিয়া)
        user_image = (ImageClip(photo_path)
                      .set_duration(video.duration)
                      .resize(width=video.w * 0.35)
                      .set_position(("center", int(video.h * 0.18))))

        # ২. নিচের ফিক্সড হলুদ টেক্সট ব্যানার জেনারেশন
        text_str = "নিঊ কালেকশন 👻👀\n🥵 লিংক কমেন্টে ✅"
        generated_banner_path = create_text_banner(video.w, text_str, font_size=int(video.w * 0.045))
        
        banner_image = (ImageClip(generated_banner_path)
                        .set_duration(video.duration)
                        .set_position(("center", int(video.h * 0.75))))

        # ৩. লেয়ারগুলো একসাথে কম্বাইন করা
        final_video = CompositeVideoClip([video, user_image, banner_image])
        
        await status_message.edit_text("🎬 ভিডিও রেন্ডারিং হচ্ছে ভাই...")
        
        # ক্লাউড সার্ভার রেন্ডারিং ফাস্ট করার জন্য কনফিগারেশন
        final_video.write_videofile(
            output_path, 
            codec="libx264", 
            audio_codec="aac", 
            preset="ultrafast", 
            threads=4
        )
        
        # ফাইল রিসোর্স রিলিজ করা
        video.close()
        final_video.close()

        # ৪. ইউজারকে ফাইনাল ভিডিও পাঠানো
        await status_message.edit_text("🚀 রেন্ডারিং শেষ! ভিডিও আপলোড হচ্ছে...")
        await update.message.reply_video(video=open(output_path, 'rb'), caption="ভাই, আপনার এডিটেড ভিডিও রেডি! 😎")
        
        # স্টোরেজ খালি করতে ফাইলগুলো ডিলিট করা
        os.remove(video_path)
        os.remove(output_path)
        os.remove(photo_path)
        if os.path.exists(generated_banner_path): os.remove(generated_banner_path)
            
        context.user_data.clear()
        await status_message.delete()
        
    except Exception as e:
        logging.error(f"Error: {e}")
        await status_message.edit_text(f"❌ এরর হয়েছে ভাই: {str(e)[:50]}")
        # এরর হলেও ফাইল সেফটি ক্লিনআপ
        if os.path.exists(video_path): os.remove(video_path)
        if os.path.exists(output_path): os.remove(output_path)
        if os.path.exists(photo_path): os.remove(photo_path)

def main():
    # ব্যাকগ্রাউন্ড থ্রেডে Flask রান করা যাতে Render ওয়েব সার্ভিস এরর না দেয়
    threading.Thread(target=run_flask, daemon=True).start()

    # টেলিগ্রাম বট অ্যাপ্লিকেশন চালু করা
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    print("বট সফলভাবে চালু হয়েছে ভাই... Render-এ পুশ করে দিন!")
    app.run_polling()

if __name__ == '__main__':
    main()
