import os
import io
import re
import time
import requests
import urllib3
from threading import Thread
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote
from pypdf import PdfReader
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ----------- ১. ফ্লাস্ক সার্ভার -----------
app = Flask('')

@app.route('/')
def home():
    return "BBGGC Scanner is Online!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

def keep_alive():
    Thread(target=run_flask).start()

# ----------- ২. কনফিগারেশন -----------
BOT_TOKEN = "8692377700:AAHUQ1NB3MbeyRNr8GSdbbsdDDNxYne8MXg"
bot = telebot.TeleBot(BOT_TOKEN)

user_modes = {}       # chat_id -> 'sonali' অথবা 'eshiksha'
active_tasks = {}     # chat_id -> True/False
user_context = {}     # Sonali রেঞ্জ ট্র্যাকিং

# =======================================================
#               ১ম কোড: 1️⃣ Sonali Result (BBGGC)
# =======================================================

headers_sonali = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
}

def get_data(tid):
    url = f"https://billpay.sonalibank.com.bd/SevenCollege/Home/Voucher/{tid}"
    try:
        r = requests.get(url, headers=headers_sonali, timeout=15, verify=False)
        soup = BeautifulSoup(r.text, "html.parser")
        html_text = r.text
        
        d = {
            "id": tid, "college": "N/A", "name": "N/A", "mobile": "N/A", 
            "roll": "N/A", "class_roll": "N/A", "reg": "N/A", 
            "group": "N/A", "subject": "N/A", "year": "N/A", 
            "session": "N/A", "amount": "0.00", "date": "N/A"
        }
        
        tds = soup.find_all("td")
        for i, td in enumerate(tds):
            txt = td.get_text(strip=True).replace(":", "")
            val = tds[i+1].get_text(strip=True) if i+1 < len(tds) else "N/A"
            
            if "Transaction Id" == txt: d["id"] = val
            elif "College" == txt: d["college"] = val
            elif "Name" == txt: d["name"] = val
            elif "Mobile" == txt: d["mobile"] = val
            elif "Roll/Reg" == txt:
                if "/" in val:
                    p = val.split("/")
                    d["roll"], d["reg"] = p[0].strip(), p[1].strip()
                else: d["roll"] = val
            elif "Class Roll" == txt: d["class_roll"] = val
            elif "Group" == txt: d["group"] = val
            elif "Subject" == txt: d["subject"] = val
            elif "Year" == txt: d["year"] = val
            elif "Session" == txt: d["session"] = val
            elif "Amount" in txt: d["amount"] = val
            elif "Date" == txt: d["date"] = val

        if d["date"] == "N/A":
            match = re.search(r'(\d{2}/\d{2}/\d{4})', html_text)
            if match: d["date"] = match.group(1)
        
        return d
    except:
        return None

def process_student_results(chat_id, data_list):
    final_output = "🏛️ <b>BBGGC Payment Result</b>\n\n"
    phones = []
    
    for i, data in enumerate(data_list, 1):
        final_output += (
            f"🎯 Result {i}\n"
            f"<pre>"
            f"🆔 Transaction Id: {data['id']}\n"
            f"🏫 College: {data['college']}\n"
            f"👤 Name: {data['name']}\n"
            f"📳 Mobile: {data['mobile']}\n"
            f"🔢 Roll: {data['roll']}\n"
            f"📇 Class Roll: {data['class_roll']}\n"
            f"🪪 Reg: {data['reg']}\n"
            f"🔬 Group: {data['group']}\n"
            f"🩺 Subject: {data['subject']}\n"
            f"​​📆 Year: {data['year']}\n"
            f"​​📅Session: {data['session']}\n"
            f"💰 Amount(BDT): {data['amount']}\n"
            f"🗓️ Date: {data['date']}"
            f"</pre>\n\n"
        )
        
        p = data["mobile"].strip()[-11:]
        if len(p) >= 11 and p not in phones:
            phones.append(p)

    markup = InlineKeyboardMarkup()
    for ph in phones:
        markup.row(
            InlineKeyboardButton("📱 WhatsApp", url=f"https://wa.me/88{ph}"),
            InlineKeyboardButton("✈️ Telegram", url=f"https://t.me/+88{ph}")
        )
    
    bot.send_message(chat_id, final_output, parse_mode="HTML", reply_markup=markup if phones else None)

def run_sonali_search(chat_id, s_r, e_r):
    active_tasks[chat_id] = True
    status_text = (
        f"⏳ <b>Processing BBGGC</b>\n"
        f"🔢 Reg/Roll: {s_r}\n"
        f"📊 Found: 0\n"
        f"✅ Progress: 0/{e_r - s_r + 1}"
    )
    status_msg = bot.send_message(chat_id, status_text, parse_mode="HTML")
    
    user_context[chat_id] = e_r
    found_students = 0
    total_range = e_r - s_r + 1
    
    for i, roll in enumerate(range(s_r, e_r + 1), 1):
        if not active_tasks.get(chat_id, True):
            break
        try:
            url = f"https://billpay.sonalibank.com.bd/SevenCollege/Home/Search?searchStr={roll}"
            r = requests.get(url, headers=headers_sonali, timeout=10, verify=False)
            if "Voucher" in r.text:
                ids = re.findall(r'Voucher/(\d+)', r.text)
                v_list = []
                for tid in set(ids):
                    d = get_data(tid)
                    if d and d["name"] != "N/A":
                        v_list.append(d)
                
                if v_list:
                    student_map = {}
                    for v in v_list:
                        key = f"{v['name']}_{v['roll']}".upper()
                        if key not in student_map:
                            student_map[key] = []
                        student_map[key].append(v)
                    
                    for key in student_map:
                        found_students += 1
                        process_student_results(chat_id, student_map[key])

            if i % 5 == 0 or i == total_range:
                new_status = (
                    f"⏳ <b>Processing BBGGC</b>\n"
                    f"🔢 Reg/Roll: {roll}\n"
                    f"📊 Found: {found_students}\n"
                    f"✅ Progress: {i}/{total_range}"
                )
                try:
                    bot.edit_message_text(new_status, chat_id, status_msg.message_id, parse_mode="HTML")
                except:
                    pass
            time.sleep(0.05)
        except:
            continue

    try:
        bot.delete_message(chat_id, status_msg.message_id)
    except:
        pass

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("👉 Next 500?", callback_data="sonali_next_500"))
    bot.send_message(chat_id, f"✅ Done!\n📊 Found Students: {found_students}", reply_markup=markup)
    active_tasks[chat_id] = False


# =======================================================
#               ২য় কোড: 2️⃣ eShiksha Result (BBGGC)
# =======================================================

BASE_URL = "https://bbggc.eshiksaems.com"
LOGIN_URL = f"{BASE_URL}/Authentication"
DATA_URL = f"{BASE_URL}/controller_student_module.php"

def get_session():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0 Mobile Safari/537.36',
        'Referer': f"{BASE_URL}/Result-Enquiry-Center",
        'X-Requested-With': 'XMLHttpRequest'
    })
    login_payload = {
        'username': 'bbggcstudent',
        'password': 'bbggcstudent',
        'submit': 'Sign In'
    }
    try:
        session.post(LOGIN_URL, data=login_payload, timeout=15)
    except Exception:
        pass
    return session

def fetch_slip_details(session, roll, student_name):
    slip_info = {
        "father": "N/A",
        "mother": "N/A",
        "phone": "N/A",
        "adm_roll": "N/A",
        "reg_no": "N/A"
    }
    try:
        tx_res = session.post(
            DATA_URL,
            data={'rootData': str(roll).strip(), 'flagreq': 'transactionCheck'},
            timeout=12
        )
        if tx_res.status_code != 200:
            return slip_info

        soup = BeautifulSoup(tx_res.text, 'html.parser')
        target_receipt_id = None

        clean_target_name = re.sub(r'[^a-zA-Z]', '', student_name).lower()
        rows = soup.find_all('tr')

        for row in rows:
            row_text = row.get_text()
            clean_row_text = re.sub(r'[^a-zA-Z]', '', row_text).lower()
            if clean_target_name and (clean_target_name in clean_row_text or any(part in clean_row_text for part in clean_target_name.split() if len(part) > 3)):
                btn_match = re.search(r"printReceipts\s*\(\s*['\"]?(\d+)['\"]?\s*\)", str(row))
                if btn_match:
                    target_receipt_id = btn_match.group(1)
                    break

        if not target_receipt_id:
            all_btns = re.findall(r"printReceipts\s*\(\s*['\"]?(\d+)['\"]?\s*\)", tx_res.text)
            if all_btns:
                target_receipt_id = all_btns[-1]

        if not target_receipt_id:
            return slip_info

        enc_res = session.post(
            DATA_URL,
            data={'rootData': target_receipt_id, 'flagreq': 'ajaxEncryption'},
            timeout=12
        )
        if enc_res.status_code != 200:
            return slip_info

        xx_code = enc_res.text.strip().strip('"\'')

        pdf_url = f"{BASE_URL}/std_coll_slip.php?xxCode={quote(xx_code)}"
        pdf_res = session.get(pdf_url, timeout=15)

        if pdf_res.status_code == 200 and len(pdf_res.content) > 500:
            reader = PdfReader(io.BytesIO(pdf_res.content))
            full_pdf_text = ""
            for page in reader.pages:
                full_pdf_text += (page.extract_text() or "") + "\n"

            f_m = re.search(r"Father'?s\s*Name\s*:\s*([^\n\r]+?)(?=\s{2,}|Class\s*Roll|\n|$)", full_pdf_text, re.I)
            m_m = re.search(r"Mother'?s\s*Name\s*:\s*([^\n\r]+?)(?=\s{2,}|Student\s*Phone|SSC|\n|$)", full_pdf_text, re.I)
            p_m = re.search(r"Student\s*Phone\s*:\s*([0-9\s\-]{10,14})", full_pdf_text, re.I)
            adm_m = re.search(r"Admission\s*Roll\s*:\s*(\d+)", full_pdf_text, re.I)
            reg_m = re.search(r"(?:SSC/HSC\s*Reg|Reg)\.?\s*No\.?\s*:\s*(\d+)", full_pdf_text, re.I)

            if f_m: slip_info["father"] = f_m.group(1).strip()
            if m_m: slip_info["mother"] = m_m.group(1).strip()
            
            if p_m:
                raw_phone = re.sub(r"\D", "", p_m.group(1))
                if len(raw_phone) == 10 and raw_phone.startswith("1"):
                    raw_phone = "0" + raw_phone
                slip_info["phone"] = raw_phone

            if adm_m: slip_info["adm_roll"] = adm_m.group(1).strip()
            if reg_m: slip_info["reg_no"] = reg_m.group(1).strip()

    except Exception:
        pass

    return slip_info

def fetch_single(session, roll):
    try:
        data_payload = {'rootData': str(roll).strip(), 'flagreq': 'profileRollCheck'}
        res = session.post(DATA_URL, data=data_payload, timeout=12)
        if res.status_code != 200 or "Student Info" not in res.text:
            return None, None

        soup = BeautifulSoup(res.text, 'html.parser')

        img_url = None
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if 'image/student' in src:
                img_url = urljoin(BASE_URL, src)
                break

        full_text = soup.get_text()
        name_m = re.search(r"Name\s*:\s*(.*?)(?=\n|Department)", full_text)
        dept_m = re.search(r"Department\s*:\s*(.*?)(?=\n|Session)", full_text)
        sess_m = re.search(r"Session\s*:\s*(.*?)(?=\n|Academic)", full_text)
        year_m = re.search(r"Academic\s*Year\s*:\s*(\d+)", full_text)

        student_name = name_m.group(1).strip() if name_m else "N/A"
        slip = fetch_slip_details(session, roll, student_name)

        data = {
            "roll": roll,
            "name": student_name,
            "dept": dept_m.group(1).strip() if dept_m else "N/A",
            "session": sess_m.group(1).strip() if sess_m else "N/A",
            "year": year_m.group(1).strip() if year_m else "N/A",
            "father": slip["father"],
            "mother": slip["mother"],
            "phone": slip["phone"],
            "adm_roll": slip["adm_roll"],
            "reg_no": slip["reg_no"]
        }

        photo_bytes = None
        if img_url:
            img_res = session.get(img_url, timeout=12)
            if img_res.status_code == 200:
                photo_bytes = img_res.content

        return data, photo_bytes
    except Exception:
        return None, None

def format_caption(data):
    return (
        f"🏛️ *বেগম বদরুন্নেসা সরকারি মহিলা কলেজ*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 *নাম :* {data['name']}\n"
        f"🔢 *Class Roll :* `{data['roll']}`\n"
        f"🎫 *Adm Roll :* `{data['adm_roll']}`\n"
        f"📝 *Reg No :* `{data['reg_no']}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👨‍🦱 *পিতার নাম :* {data['father']}\n"
        f"👩‍🦰 *মাতার নাম :* {data['mother']}\n"
        f"📞 *মোবাইল :* `{data['phone']}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🏫 *বিভাগ :* {data['dept']}\n"
        f"📆 *সেশন :* {data['session']}\n"
        f"📚 *শিক্ষাবর্ষ :* {data['year']}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

def create_action_keyboard(phone, next_start=None, next_end=None):
    markup = InlineKeyboardMarkup()
    buttons = []

    if phone and phone != "N/A" and len(phone) >= 10:
        clean_num = phone[-11:]
        if len(clean_num) == 10:
            clean_num = "0" + clean_num
            
        wa_url = f"https://wa.me/88{clean_num}"
        tg_url = f"https://t.me/+88{clean_num}"

        buttons.append(InlineKeyboardButton("🟢 WhatsApp ↗", url=wa_url))
        buttons.append(InlineKeyboardButton("🔵 Telegram ↗", url=tg_url))
        markup.row(*buttons)

    if next_start and next_end:
        markup.add(InlineKeyboardButton("➡️ Next 500", callback_data=f"eshiksha_next_{next_start}_{next_end}"))

    return markup

def run_range_search(chat_id, start_roll, end_roll):
    total_to_search = end_roll - start_roll + 1
    active_tasks[chat_id] = True

    bot.send_message(chat_id, f"🔄 অটো সার্চ শুরু: `{start_roll}` - `{end_roll}`", parse_mode='Markdown')

    stop_markup = InlineKeyboardMarkup()
    stop_markup.add(InlineKeyboardButton("🔴 Stop Search", callback_data="stop_search"))

    status_msg = bot.send_message(chat_id, "⏳ সার্চ শুরু হচ্ছে...", reply_markup=stop_markup)

    session = get_session()
    found_count = 0

    for idx, r in enumerate(range(start_roll, end_roll + 1), start=1):
        if not active_tasks.get(chat_id, False):
            bot.send_message(chat_id, "🛑 সার্চ থামানো হয়েছে!")
            break

        data, photo = fetch_single(session, r)

        if data and data['name'] != "N/A":
            found_count += 1
            caption = format_caption(data)
            action_markup = create_action_keyboard(data['phone'])
            try:
                if photo:
                    bot.send_photo(chat_id, photo, caption=caption, parse_mode='Markdown', reply_markup=action_markup)
                else:
                    bot.send_message(chat_id, caption, parse_mode='Markdown', reply_markup=action_markup)
            except Exception:
                pass

        status_text = (
            f"⌛ Processing...\n"
            f"🔢 Roll: {r}\n"
            f"📊 Found: {found_count}\n"
            f"✅ Progress: {idx}/{total_to_search}"
        )
        try:
            bot.edit_message_text(status_text, chat_id, status_msg.message_id, reply_markup=stop_markup)
        except Exception:
            pass

        time.sleep(1)

    try:
        bot.delete_message(chat_id, status_msg.message_id)
    except Exception:
        pass

    bot.send_message(chat_id, f"✅ সার্চ সম্পন্ন হয়েছে!\n📊 মোট পাওয়া গেছে: {found_count}")

    next_start = end_roll + 1
    next_end = next_start + 499
    next_markup = InlineKeyboardMarkup()
    next_markup.add(InlineKeyboardButton("➡️ Next 500", callback_data=f"eshiksha_next_{next_start}_{next_end}"))

    bot.send_message(chat_id, "👉 পরবর্তী ব্যাচ খুঁজতে চান?", reply_markup=next_markup)
    active_tasks[chat_id] = False


# =======================================================
#               ৩. মেনু ও হ্যান্ডলার কন্ট্রোল
# =======================================================

def main_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("1️⃣ Sonali Result", callback_data="mode_sonali"),
        InlineKeyboardButton("2️⃣ eShiksha Result", callback_data="mode_eshiksha")
    )
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(
        message.chat.id,
        "👋 **কোন অপশনটি ব্যবহার করতে চান নির্বাচন করুন:**",
        parse_mode='Markdown',
        reply_markup=main_menu()
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id

    if call.data == "mode_sonali":
        user_modes[chat_id] = "sonali"
        bot.answer_callback_query(call.id, "1️⃣ Sonali Result সিলেক্ট করা হয়েছে!")
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("Start Search", callback_data="btn_ready")]])
        bot.send_message(chat_id, "বেগম বদরুন্নেসা কলেজ পেমেন্ট বট!", reply_markup=markup)

    elif call.data == "mode_eshiksha":
        user_modes[chat_id] = "eshiksha"
        bot.answer_callback_query(call.id, "2️⃣ eShiksha Result সিলেক্ট করা হয়েছে!")
        bot.send_message(
            chat_id,
            "স্বাগতম!\n\n"
            "• রোল নম্বর দিন (যেমন: `233115`)\n"
            "• অথবা রেঞ্জ দিন (যেমন: `233115-233200`)",
            parse_mode='Markdown'
        )

    elif call.data == "btn_ready":
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, "🚀 রোল বা রেঞ্জ পাঠান।")

    elif call.data == "sonali_next_500":
        bot.answer_callback_query(call.id)
        le = user_context.get(chat_id, 0)
        if le > 0:
            run_sonali_search(chat_id, le + 1, le + 500)

    elif call.data == "stop_search":
        active_tasks[chat_id] = False
        bot.answer_callback_query(call.id, "সার্চ থামানো হচ্ছে...")

    elif call.data.startswith("eshiksha_next_"):
        parts = call.data.split("_")
        s_roll = int(parts[2])
        e_roll = int(parts[3])
        bot.answer_callback_query(call.id)
        run_range_search(chat_id, s_roll, e_roll)

@bot.message_handler(func=lambda msg: True)
def handle_message(message):
    chat_id = message.chat.id
    mode = user_modes.get(chat_id)
    text = message.text.strip()

    if not mode:
        bot.reply_to(message, "অনুগ্রহ করে প্রথমে একটি অপশন সিলেক্ট করুন:", reply_markup=main_menu())
        return

    # ১️⃣ Sonali Result এক্সিকিউশন
    if mode == "sonali":
        try:
            if "-" in text:
                s, e = map(int, text.split("-"))
                run_sonali_search(chat_id, s, e)
            else:
                run_sonali_search(chat_id, int(text), int(text))
        except:
            pass

    # 2️⃣ eShiksha Result এক্সিকিউশন
    elif mode == "eshiksha":
        if "-" in text:
            parts = text.split("-")
            if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                s = int(parts[0].strip())
                e = int(parts[1].strip())
                if e < s:
                    bot.reply_to(message, "ভুল রেঞ্জ! শুরুর রোল শেষের চেয়ে ছোট হতে হবে।")
                    return
                if (e - s + 1) > 500:
                    bot.reply_to(message, "⚠️ একসাথে সর্বোচ্চ ৫০০ রেঞ্জ দিতে পারবেন।")
                    return
                run_range_search(chat_id, s, e)
                return

        if text.isdigit():
            roll = int(text)
            wait_msg = bot.reply_to(message, f"রোল {roll}-এর বিস্তারিত তথ্য খোঁজা হচ্ছে...")
            session = get_session()
            data, photo = fetch_single(session, roll)

            try:
                bot.delete_message(chat_id, wait_msg.message_id)
            except Exception:
                pass

            if not data or data['name'] == "N/A":
                bot.reply_to(message, "❌ কোনো তথ্য পাওয়া যায়নি।")
                return

            caption = format_caption(data)
            action_markup = create_action_keyboard(data['phone'], next_start=roll+1, next_end=roll+500)

            if photo:
                bot.send_photo(chat_id, photo, caption=caption, parse_mode='Markdown', reply_markup=action_markup)
            else:
                bot.send_message(chat_id, caption, parse_mode='Markdown', reply_markup=action_markup)
            return

        bot.reply_to(message, "অনুগ্রহ করে সঠিক রোল নম্বর অথবা রেঞ্জ পাঠান।")

if __name__ == "__main__":
    keep_alive()
    print("🚀 বেগম বদরুন্নেসা কলেজ কম্বাইন্ড বট সফলভাবে চালু হয়েছে...")
    bot.infinity_polling()
