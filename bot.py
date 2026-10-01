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
    return "GSSMC eShiksha Bot is Online!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

def keep_alive():
    Thread(target=run_flask).start()

# ----------- ২. কনফিগারেশন -----------
BOT_TOKEN = "8925175381:AAEWjpK81PHubS7NWi_IswXyK_f7iIKLK_4"
CHANNEL_ID = "@amir_test_cnle"  # আপনার চ্যানেলের ইউজারনেম

bot = telebot.TeleBot(BOT_TOKEN)

user_modes = {}       # chat_id -> 'eshiksha' অথবা 'master'
active_tasks = {}     # chat_id -> True/False


# =======================================================
#          ১ম অংশ: 1️⃣ eShiksha Result
# =======================================================

BASE_URL_ESHIKSHA = "https://gssmc.eshiksabd.com"
LOGIN_URL_ESHIKSHA = f"{BASE_URL_ESHIKSHA}/Authentication"
DATA_URL_ESHIKSHA = f"{BASE_URL_ESHIKSHA}/controller_student_module.php"

def get_eshiksha_session():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0 Mobile Safari/537.36',
        'Referer': f"{BASE_URL_ESHIKSHA}/Result-Enquiry-Center",
        'X-Requested-With': 'XMLHttpRequest'
    })
    login_payload = {
        'username': 'gssmcstudent',
        'password': 'gssmcstudent',
        'submit': 'Sign In'
    }
    try:
        session.post(LOGIN_URL_ESHIKSHA, data=login_payload, timeout=15)
    except Exception:
        pass
    return session

def fetch_eshiksha_slip_details(session, roll, student_name):
    slip_info = {
        "father": "N/A", "mother": "N/A", "phone": "N/A",
        "adm_roll": "N/A", "reg_no": "N/A"
    }
    try:
        tx_res = session.post(
            DATA_URL_ESHIKSHA,
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
            DATA_URL_ESHIKSHA,
            data={'rootData': target_receipt_id, 'flagreq': 'ajaxEncryption'},
            timeout=12
        )
        if enc_res.status_code != 200:
            return slip_info

        xx_code = enc_res.text.strip().strip('"\'')
        pdf_url = f"{BASE_URL_ESHIKSHA}/std_coll_slip.php?xxCode={quote(xx_code)}"
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

def fetch_eshiksha_single(session, roll):
    try:
        data_payload = {'rootData': str(roll).strip(), 'flagreq': 'profileRollCheck'}
        res = session.post(DATA_URL_ESHIKSHA, data=data_payload, timeout=12)
        if res.status_code != 200 or "Student Info" not in res.text:
            return None, None

        soup = BeautifulSoup(res.text, 'html.parser')
        img_url = None
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if 'image/student' in src:
                img_url = urljoin(BASE_URL_ESHIKSHA, src)
                break

        full_text = soup.get_text()
        name_m = re.search(r"Name\s*:\s*(.*?)(?=\n|Department)", full_text)
        dept_m = re.search(r"Department\s*:\s*(.*?)(?=\n|Session)", full_text)
        sess_m = re.search(r"Session\s*:\s*(.*?)(?=\n|Academic)", full_text)
        year_m = re.search(r"Academic\s*Year\s*:\s*(\d+)", full_text)

        student_name = name_m.group(1).strip() if name_m else "N/A"
        slip = fetch_eshiksha_slip_details(session, roll, student_name)

        data = {
            "roll": roll, "name": student_name,
            "dept": dept_m.group(1).strip() if dept_m else "N/A",
            "session": sess_m.group(1).strip() if sess_m else "N/A",
            "year": year_m.group(1).strip() if year_m else "N/A",
            "father": slip["father"], "mother": slip["mother"],
            "phone": slip["phone"], "adm_roll": slip["adm_roll"],
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

def format_eshiksha_caption(data):
    return (
        f"🏛️ *সরকারি সুন্দর সুন্দরী মহিলা কলেজ*\n"
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

def run_eshiksha_range_search(chat_id, start_roll, end_roll):
    total_to_search = end_roll - start_roll + 1
    active_tasks[chat_id] = True
    bot.send_message(chat_id, f"🔄 ই-শিক্ষা অটো সার্চ শুরু: `{start_roll}` - `{end_roll}`", parse_mode='Markdown')

    stop_markup = InlineKeyboardMarkup()
    stop_markup.add(InlineKeyboardButton("🔴 Stop Search", callback_data="stop_search"))
    status_msg = bot.send_message(chat_id, "⏳ সার্চ শুরু হচ্ছে...", reply_markup=stop_markup)

    session = get_eshiksha_session()
    found_count = 0

    for idx, r in enumerate(range(start_roll, end_roll + 1), start=1):
        if not active_tasks.get(chat_id, False):
            bot.send_message(chat_id, "🛑 সার্চ থামানো হয়েছে!")
            break

        data, photo = fetch_eshiksha_single(session, r)
        if data and data['name'] != "N/A":
            found_count += 1
            caption = format_eshiksha_caption(data)
            action_markup = InlineKeyboardMarkup()
            if data['phone'] and data['phone'] != "N/A" and len(data['phone']) >= 10:
                clean_num = data['phone'][-11:]
                if len(clean_num) == 10: clean_num = "0" + clean_num
                action_markup.row(
                    InlineKeyboardButton("🟢 WhatsApp ↗", url=f"https://wa.me/88{clean_num}"),
                    InlineKeyboardButton("🔵 Telegram ↗", url=f"https://t.me/+88{clean_num}")
                )
            try:
                if photo:
                    bot.send_photo(chat_id, photo, caption=caption, parse_mode='Markdown', reply_markup=action_markup)
                    bot.send_photo(CHANNEL_ID, photo, caption=caption, parse_mode='Markdown', reply_markup=action_markup)
                else:
                    bot.send_message(chat_id, caption, parse_mode='Markdown', reply_markup=action_markup)
                    bot.send_message(CHANNEL_ID, caption, parse_mode='Markdown', reply_markup=action_markup)
            except Exception:
                pass

        status_text = f"⌛ Processing...\n🔢 Roll: {r}\n📊 Found: {found_count}\n✅ Progress: {idx}/{total_to_search}"
        try:
            bot.edit_message_text(status_text, chat_id, status_msg.message_id, reply_markup=stop_markup)
        except Exception:
            pass
        time.sleep(1)

    try:
        bot.delete_message(chat_id, status_msg.message_id)
    except Exception:
        pass
    
    bot.send_message(chat_id, f"✅ ই-শিক্ষা সার্চ সম্পন্ন হয়েছে!\n📊 মোট পাওয়া গেছে: {found_count}")

    next_start = end_roll + 1
    next_end = next_start + 499
    next_markup = InlineKeyboardMarkup()
    next_markup.add(InlineKeyboardButton("➡️ Next 500", callback_data=f"eshiksha_next_{next_start}_{next_end}"))
    bot.send_message(chat_id, "👉 পরবর্তী ব্যাচ খুঁজতে চান?", reply_markup=next_markup)

    active_tasks[chat_id] = False


# =======================================================
#          ২য় অংশ: 2️⃣ Master Information
# =======================================================

BASE_URL_MASTER = "https://gssmc.eshiksabd.com"
LOGIN_URL_MASTER = f"{BASE_URL_MASTER}/Authentication"
DATA_URL_MASTER = f"{BASE_URL_MASTER}/controller_student_module.php"

def get_master_session():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
        'Referer': f"{BASE_URL_MASTER}/Result-Enquiry-Center",
        'X-Requested-With': 'XMLHttpRequest'
    })
    login_payload = {
        'username': 'gssmcstudent',
        'password': 'gssmcstudent',
        'submit': 'Sign In'
    }
    try:
        session.post(LOGIN_URL_MASTER, data=login_payload, timeout=15)
    except Exception:
        pass
    return session

def extract_master_adm_roll_photo_and_session(session, class_roll):
    adm_roll = None
    photo_bytes = None
    session_id = "22"
    try:
        payload = {'rootData': str(class_roll).strip(), 'flagreq': 'transactionCheck'}
        tx_res = session.post(DATA_URL_MASTER, data=payload, timeout=12)
        
        if tx_res.status_code == 200:
            soup_tx = BeautifulSoup(tx_res.text, 'html.parser')
            sess_select = soup_tx.find('select', {'id': 'sessionID'}) or soup_tx.find('select', {'name': 'sessionID'})
            if sess_select:
                opt = sess_select.find('option', selected=True) or sess_select.find('option')
                if opt and opt.has_attr('value'):
                    session_id = opt['value'].strip()

            all_btns = re.findall(r"printReceipts\s*\(\s*['\"]?(\d+)['\"]?\s*\)", tx_res.text)
            if all_btns:
                target_receipt_id = all_btns[-1]
                enc_res = session.post(DATA_URL_MASTER, data={'rootData': target_receipt_id, 'flagreq': 'ajaxEncryption'}, timeout=10)
                if enc_res.status_code == 200:
                    xx_code = enc_res.text.strip().strip('"\'')
                    pdf_url = f"{BASE_URL_MASTER}/std_coll_slip.php?xxCode={quote(xx_code)}"
                    pdf_res = session.get(pdf_url, timeout=15)

                    if pdf_res.status_code == 200 and len(pdf_res.content) > 500:
                        reader = PdfReader(io.BytesIO(pdf_res.content))
                        slip_text = ""
                        for page in reader.pages:
                            slip_text += (page.extract_text() or "") + "\n"
                        adm_m = re.search(r"Admission\s*Roll\s*:\s*(\d{5,8})", slip_text, re.I)
                        if adm_m:
                            adm_roll = adm_m.group(1).strip()

        p_res = session.post(DATA_URL_MASTER, data={'rootData': str(class_roll).strip(), 'flagreq': 'profileRollCheck'}, timeout=10)
        if p_res.status_code == 200:
            soup = BeautifulSoup(p_res.text, 'html.parser')
            for img in soup.find_all('img'):
                src = img.get('src', '')
                if 'image/student' in src:
                    ir = session.get(f"{BASE_URL_MASTER}/{src.lstrip('/')}", timeout=10)
                    if ir.status_code == 200:
                        photo_bytes = ir.content
                    break
            if not adm_roll:
                p_rolls = re.findall(r"\b2\d{5}\b", p_res.text)
                if p_rolls:
                    adm_roll = p_rolls[0]
    except Exception:
        pass
    if not adm_roll:
        adm_roll = str(class_roll).strip()
    return adm_roll, photo_bytes, session_id

def fetch_master_admission_form(session, adm_roll, session_id="22"):
    possible_sessions = [str(session_id), "22", "21", "20", "19", "18", "23", "24"]
    for sid in possible_sessions:
        try:
            tx_payload = {'rootData': str(adm_roll).strip(), 'sessionID': str(sid), 'flagreq': 'checkTransaction'}
            res_tx = session.post(DATA_URL_MASTER, data=tx_payload, timeout=12)
            if res_tx.status_code != 200 or not res_tx.text.strip():
                continue

            raw_query = res_tx.text.strip().strip('"\'')
            if len(raw_query) < 10 or "<html" in raw_query.lower():
                continue

            if "xxCode=" in raw_query:
                pdf_url = f"{BASE_URL_MASTER}/Student-Admission?{raw_query}"
            else:
                pdf_url = f"{BASE_URL_MASTER}/Student-Admission?xxCode={raw_query}"
                if "yyCode" not in pdf_url: pdf_url += "&yyCode=1"

            pdf_headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
                'Referer': f"{BASE_URL_MASTER}/Result-Enquiry-Center",
                'Accept': 'application/pdf,text/html,*/*'
            }
            pdf_res = session.get(pdf_url, headers=pdf_headers, timeout=20)
            if pdf_res.status_code != 200 or len(pdf_res.content) < 500:
                continue

            pdf_bytes = pdf_res.content
            reader = PdfReader(io.BytesIO(pdf_bytes))
            full_text = ""
            for page in reader.pages:
                full_text += (page.extract_text() or "") + "\n"

            def get_match(pat, def_val=""):
                m = re.search(pat, full_text, re.I | re.M)
                return m.group(1).strip() if m else def_val

            def extract_bd_phone(section_pattern):
                sec = re.search(section_pattern, full_text, re.I | re.M)
                if sec:
                    num_match = re.search(r"(?:88)?(01[3-9]\d{8})", sec.group(1))
                    if num_match: return num_match.group(1)
                return ""

            student_phone = extract_bd_phone(r"Student'?s\s*Phone\s*:\s*([^\n\r]+)")
            father_phone = extract_bd_phone(r"Father'?s/Guardian'?s\s*Phone\s*:\s*([^\n\r]+)")
            mother_phone = extract_bd_phone(r"Mother'?s\s*Phone\s*:\s*([^\n\r]+)")

            dob = get_match(r"Date\s*of\s*Birth\s*:\s*([0-9]{1,2}-[A-Za-z]{3}-[0-9]{4})")
            if not dob: dob = get_match(r"Date\s*of\s*Birth\s*:\s*([^\n\r]+?)(?=\s*\d{1,2}\.|\s*Quota|$)")

            email_match = re.search(r"Student'?s\s*E-?mail\s*:\s*([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", full_text, re.I)
            s_name = get_match(r"Student\s*Name\s*\(English\)\s*:\s*([A-Za-z\s\.]+?)(?=\(বাংলায়\)|\n|$)")
            
            if not s_name: continue

            data = {
                "class_roll": get_match(r"Class\s*Roll\s*:\s*(\d+)"),
                "adm_roll": str(adm_roll),
                "reg_no": get_match(r"Reg\s*No[\s\S]*?(\d{8,15})"),
                "student_name": s_name,
                "student_nid": get_match(r"Student'?s\s*NID/Birth\s*Reg\.?\s*:\s*([0-9]+)"),
                "gender": get_match(r"Gender\s*:\s*([A-Za-z]+)") or "Female",
                "student_phone": student_phone, "dob": dob,
                "religion": get_match(r"Religion\s*:\s*([A-Za-z]+)"),
                "blood": get_match(r"Blood\s*Group\s*:\s*([A-Za-z+-]+)"),
                "student_email": email_match.group(1).strip() if email_match else "",
                "father_name": get_match(r"Father'?s\s*Name\s*:\s*([A-Za-z\s\.]+?)(?=\(বাংলায়\)|\n|$)"),
                "father_nid": get_match(r"Father'?s/Guardian'?s\s*NID\s*:\s*([0-9]+)"),
                "father_phone": father_phone,
                "mother_name": get_match(r"Mother'?s\s*Name\s*:\s*([A-Za-z\s\.]+?)(?=\(বাংলায়\)|\n|$)"),
                "mother_nid": get_match(r"Mother'?s\s*NID\s*:\s*([0-9]+)"),
                "mother_phone": mother_phone,
                "permanent_address": get_match(r"Permanent\s*Address\s*:\s*([^\n\r]+?)(?=\n|Present|$)"),
                "present_address": get_match(r"Present\s*Address\s*:\s*([^\n\r]+?)(?=\n|Permanent|$)"),
                "dept": get_match(r"Group\s*:\s*([^\n\r]+?)(?=\n|Session)"),
                "board": get_match(r"Board/Instit\.?[\s\S]*?([A-Za-z]+)\s+\d\.\d{2}"),
                "gpa": get_match(r"(\d\.\d{2})\s*$"),
                "session": get_match(r"Session\s*:\s*([^\n\r]+?)(?=\n|$)", def_val="2026-2027")
            }
            return pdf_bytes, data
        except Exception:
            continue
    return None, None

def format_master_caption(data):
    return (
        f"🏛️ সরকারি সারদা সুন্দরী মহিলা কলেজ (Master Info)\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔢 Class Roll : `{data['class_roll']}`\n"
        f"🎫 Adm Roll : `{data['adm_roll']}`\n"
        f"📝 Reg No : `{data['reg_no']}`\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 Name : {data['student_name']}\n"
        f"🆔 Student NID : `{data['student_nid']}`\n"
        f"⚥ Gender : {data['gender']}\n"
        f"📞 Std Phone : `{data['student_phone']}`\n"
        f"🎂 DOB : `{data['dob']}`\n"
        f"☪️ Religion : {data['religion']}\n"
        f"🩸 Blood : {data['blood']}\n"
        f"📧 Email : {data['student_email']}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👨‍🦱 Father : {data['father_name']}\n"
        f"🪪 Father NID : `{data['father_nid']}`\n"
        f"☎️ Father Phone : `{data['father_phone']}`\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👩‍🦰 Mother : {data['mother_name']}\n"
        f"🪪 Mother NID : `{data['mother_nid']}`\n"
        f"☎️ Mother Phone : `{data['mother_phone']}`\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🏠 Permanent : {data['permanent_address']}\n"
        f"🏠 Present : {data['present_address']}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🏫 Dept: {data['dept']}\n"
        f"🏢 Board: {data['board']}\n"
        f"🎰 GPA: {data['gpa']}\n"
        f"📆 Session: {data['session']}"
    )

def process_master_student(chat_id, user_input, next_start=None, next_end=None):
    session = get_master_session()
    adm_roll, photo_bytes, extracted_session_id = extract_master_adm_roll_photo_and_session(session, user_input)

    if not adm_roll:
        bot.send_message(chat_id, f"❌ রোল `{user_input}`-এর কোনো তথ্য পাওয়া যায়নি!", parse_mode='Markdown')
        return

    pdf_bytes, data = fetch_master_admission_form(session, adm_roll, extracted_session_id)
    if not data or not pdf_bytes:
        bot.send_message(chat_id, f"❌ রোল `{adm_roll}`-এর মূল আবেদন ফর্ম পাওয়া যায়নি!", parse_mode='Markdown')
        return

    if not data["class_roll"] or data["class_roll"] == "N/A":
        data["class_roll"] = str(user_input)

    caption = format_master_caption(data)
    action_markup = InlineKeyboardMarkup()
    if data['student_phone']:
        action_markup.row(InlineKeyboardButton("🟢 Std WA", url=f"https://wa.me/88{data['student_phone']}"), InlineKeyboardButton("🔵 Std TG", url=f"https://t.me/+88{data['student_phone']}"))
    if data['father_phone']:
        action_markup.row(InlineKeyboardButton("🟢 Fat WA", url=f"https://wa.me/88{data['father_phone']}"), InlineKeyboardButton("🔵 Fat TG", url=f"https://t.me/+88{data['father_phone']}"))
    if data['mother_phone']:
        action_markup.row(InlineKeyboardButton("🟢 Mot WA", url=f"https://wa.me/88{data['mother_phone']}"), InlineKeyboardButton("🔵 Mot TG", url=f"https://t.me/+88{data['mother_phone']}"))
    
    if next_start and next_end:
        action_markup.add(InlineKeyboardButton("➡️ Next 500", callback_data=f"master_next_{next_start}_{next_end}"))

    pdf_file = io.BytesIO(pdf_bytes)
    pdf_file.name = f"Admission_Form_{data['adm_roll']}.pdf"
    bot.send_document(chat_id, pdf_file, caption=f"📄 *মূল আবেদন ফর্ম (Admission Form)*\n🎫 Adm Roll: `{data['adm_roll']}`", parse_mode='Markdown')

    pdf_file_channel = io.BytesIO(pdf_bytes)
    pdf_file_channel.name = f"Admission_Form_{data['adm_roll']}.pdf"
    bot.send_document(CHANNEL_ID, pdf_file_channel, caption=f"📄 *মূল আবেদন ফর্ম (Admission Form)*\n🎫 Adm Roll: `{data['adm_roll']}`", parse_mode='Markdown')

    if photo_bytes:
        try:
            bot.send_photo(chat_id, photo_bytes, caption=caption, parse_mode='Markdown', reply_markup=action_markup)
            bot.send_photo(CHANNEL_ID, photo_bytes, caption=caption, parse_mode='Markdown', reply_markup=action_markup)
            return
        except Exception:
            pass
            
    bot.send_message(chat_id, caption, parse_mode='Markdown', reply_markup=action_markup)
    bot.send_message(CHANNEL_ID, caption, parse_mode='Markdown', reply_markup=action_markup)

def run_master_range_search(chat_id, start_roll, end_roll):
    total_to_search = end_roll - start_roll + 1
    active_tasks[chat_id] = True
    bot.send_message(chat_id, f"🔄 Master Info অটো সার্চ শুরু: `{start_roll}` - `{end_roll}`", parse_mode='Markdown')

    stop_markup = InlineKeyboardMarkup()
    stop_markup.add(InlineKeyboardButton("🔴 Stop Search", callback_data="stop_search"))
    status_msg = bot.send_message(chat_id, "⏳ সার্চ শুরু হচ্ছে...", reply_markup=stop_markup)

    session = get_master_session()
    found_count = 0

    for idx, r in enumerate(range(start_roll, end_roll + 1), start=1):
        if not active_tasks.get(chat_id, False):
            bot.send_message(chat_id, "🛑 সার্চ থামানো হয়েছে!")
            break

        adm_roll, photo_bytes, sess_id = extract_master_adm_roll_photo_and_session(session, r)
        if adm_roll:
            pdf_bytes, data = fetch_master_admission_form(session, adm_roll, sess_id)
            if data:
                found_count += 1
                if not data["class_roll"] or data["class_roll"] == "N/A":
                    data["class_roll"] = str(r)

                caption = format_master_caption(data)
                action_markup = InlineKeyboardMarkup()
                if data['student_phone']:
                    action_markup.row(InlineKeyboardButton("🟢 Std WA", url=f"https://wa.me/88{data['student_phone']}"), InlineKeyboardButton("🔵 Std TG", url=f"https://t.me/+88{data['student_phone']}"))
                if data['father_phone']:
                    action_markup.row(InlineKeyboardButton("🟢 Fat WA", url=f"https://wa.me/88{data['father_phone']}"), InlineKeyboardButton("🔵 Fat TG", url=f"https://t.me/+88{data['father_phone']}"))
                if data['mother_phone']:
                    action_markup.row(InlineKeyboardButton("🟢 Mot WA", url=f"https://wa.me/88{data['mother_phone']}"), InlineKeyboardButton("🔵 Mot TG", url=f"https://t.me/+88{data['mother_phone']}"))

                if pdf_bytes:
                    pdf_file = io.BytesIO(pdf_bytes)
                    pdf_file.name = f"Admission_Form_{data['adm_roll']}.pdf"
                    bot.send_document(chat_id, pdf_file, caption=f"📄 Admission Form: `{data['adm_roll']}`", parse_mode='Markdown')
                    
                    pdf_file_channel = io.BytesIO(pdf_bytes)
                    pdf_file_channel.name = f"Admission_Form_{data['adm_roll']}.pdf"
                    bot.send_document(CHANNEL_ID, pdf_file_channel, caption=f"📄 Admission Form: `{data['adm_roll']}`", parse_mode='Markdown')

                if photo_bytes:
                    try:
                        bot.send_photo(chat_id, photo_bytes, caption=caption, parse_mode='Markdown', reply_markup=action_markup)
                        bot.send_photo(CHANNEL_ID, photo_bytes, caption=caption, parse_mode='Markdown', reply_markup=action_markup)
                        continue
                    except Exception:
                        pass
                bot.send_message(chat_id, caption, parse_mode='Markdown', reply_markup=action_markup)
                bot.send_message(CHANNEL_ID, caption, parse_mode='Markdown', reply_markup=action_markup)

        status_text = f"⌛ Processing...\n🔢 Roll: {r}\n📊 Found: {found_count}\n✅ Progress: {idx}/{total_to_search}"
        try:
            bot.edit_message_text(status_text, chat_id, status_msg.message_id, reply_markup=stop_markup)
        except Exception:
            pass
        time.sleep(1)

    try:
        bot.delete_message(chat_id, status_msg.message_id)
    except Exception:
        pass
    
    bot.send_message(chat_id, f"✅ Master Info সার্চ সম্পন্ন হয়েছে!\n📊 মোট পাওয়া গেছে: {found_count}")

    next_start = end_roll + 1
    next_end = next_start + 499
    next_markup = InlineKeyboardMarkup()
    next_markup.add(InlineKeyboardButton("➡️ Next 500", callback_data=f"master_next_{next_start}_{next_end}"))
    bot.send_message(chat_id, "👉 পরবর্তী ব্যাচ খুঁজতে চান?", reply_markup=next_markup)

    active_tasks[chat_id] = False


# =======================================================
#               ৩. মেনু ও হ্যান্ডলার কন্ট্রোল
# =======================================================

def main_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("1️⃣ eShiksha Result", callback_data="mode_eshiksha"),
        InlineKeyboardButton("2️⃣ Master Information", callback_data="mode_master")
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

    if call.data == "mode_eshiksha":
        user_modes[chat_id] = "eshiksha"
        bot.answer_callback_query(call.id, "1️⃣ eShiksha Result সিলেক্ট করা হয়েছে!")
        bot.send_message(chat_id, "ই-শিক্ষা মোড চালু হয়েছে। রোল নম্বর বা রেঞ্জ পাঠান (যেমন: `261001` বা `261001-261010`)।", parse_mode='Markdown')

    elif call.data == "mode_master":
        user_modes[chat_id] = "master"
        bot.answer_callback_query(call.id, "2️⃣ Master Information সিলেক্ট করা হয়েছে!")
        bot.send_message(chat_id, "📋 **Master Information** মোড চালু হয়েছে। রোল নম্বর বা রেঞ্জ পাঠান (যেমন: `261001` বা `261001-261010`)।", parse_mode='Markdown')

    elif call.data.startswith("eshiksha_next_"):
        parts = call.data.split("_")
        s_roll, e_roll = int(parts[2]), int(parts[3])
        bot.answer_callback_query(call.id)
        run_eshiksha_range_search(chat_id, s_roll, e_roll)

    elif call.data.startswith("master_next_"):
        parts = call.data.split("_")
        s_roll, e_roll = int(parts[2]), int(parts[3])
        bot.answer_callback_query(call.id)
        run_master_range_search(chat_id, s_roll, e_roll)

    elif call.data == "stop_search":
        active_tasks[chat_id] = False
        bot.answer_callback_query(call.id, "সার্চ থামানো হচ্ছে...")

@bot.message_handler(func=lambda msg: True)
def handle_message(message):
    chat_id = message.chat.id
    mode = user_modes.get(chat_id)
    text = message.text.strip()

    if not mode:
        bot.reply_to(message, "অনুগ্রহ করে প্রথমে একটি অপশন সিলেক্ট করুন:", reply_markup=main_menu())
        return

    # 1️⃣ eShiksha Result
    if mode == "eshiksha":
        if "-" in text:
            parts = text.split("-")
            if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                s, e = int(parts[0].strip()), int(parts[1].strip())
                if e < s:
                    bot.reply_to(message, "ভুল রেঞ্জ! শুরুর রোল ছোট হতে হবে।")
                    return
                if (e - s + 1) > 500:
                    bot.reply_to(message, "⚠️ সর্বোচ্চ ৫০০ রেঞ্জ দিতে পারবেন।")
                    return
                run_eshiksha_range_search(chat_id, s, e)
                return

        if text.isdigit():
            roll = int(text)
            wait_msg = bot.reply_to(message, f"🔍 ই-শিক্ষা রোল `{roll}` খোঁজা হচ্ছে...", parse_mode='Markdown')
            session = get_eshiksha_session()
            data, photo = fetch_eshiksha_single(session, roll)
            try:
                bot.delete_message(chat_id, wait_msg.message_id)
            except Exception:
                pass

            if not data or data['name'] == "N/A":
                bot.reply_to(message, "❌ কোনো তথ্য পাওয়া যায়নি।")
                return

            caption = format_eshiksha_caption(data)
            action_markup = InlineKeyboardMarkup()
            if data['phone'] and data['phone'] != "N/A" and len(data['phone']) >= 10:
                clean_num = data['phone'][-11:]
                if len(clean_num) == 10: clean_num = "0" + clean_num
                action_markup.row(
                    InlineKeyboardButton("🟢 WhatsApp ↗", url=f"https://wa.me/88{clean_num}"),
                    InlineKeyboardButton("🔵 Telegram ↗", url=f"https://t.me/+88{clean_num}")
                )
            
            next_start = roll + 1
            next_end = next_start + 499
            action_markup.add(InlineKeyboardButton("➡️ Next 500", callback_data=f"eshiksha_next_{next_start}_{next_end}"))

            if photo:
                bot.send_photo(chat_id, photo, caption=caption, parse_mode='Markdown', reply_markup=action_markup)
                bot.send_photo(CHANNEL_ID, photo, caption=caption, parse_mode='Markdown', reply_markup=action_markup)
            else:
                bot.send_message(chat_id, caption, parse_mode='Markdown', reply_markup=action_markup)
                bot.send_message(CHANNEL_ID, caption, parse_mode='Markdown', reply_markup=action_markup)
            return
        bot.reply_to(message, "অনুগ্রহ করে সঠিক রোল নম্বর বা রেঞ্জ পাঠান।")

    # 2️⃣ Master Information
    elif mode == "master":
        if "-" in text:
            parts = text.split("-")
            if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                s, e = int(parts[0].strip()), int(parts[1].strip())
                if e < s:
                    bot.reply_to(message, "ভুল রেঞ্জ! শুরুর রোল ছোট হতে হবে।")
                    return
                run_master_range_search(chat_id, s, e)
                return

        if text.isdigit():
            roll = int(text)
            wait_msg = bot.reply_to(message, f"📋 Master Info রোল `{roll}`-এর ডেটা প্রসেস হচ্ছে...", parse_mode='Markdown')
            process_master_student(chat_id, roll, next_start=roll+1, next_end=roll+500)
            try:
                bot.delete_message(chat_id, wait_msg.message_id)
            except Exception:
                pass
            return
        bot.reply_to(message, "অনুগ্রহ করে সঠিক রোল নম্বর বা রেঞ্জ পাঠান।")

if __name__ == "__main__":
    keep_alive()
    print("🚀 সরকারি সারদা সুন্দরী মহিলা কলেজ বট সফলভাবে চালু হয়েছে...")
    bot.infinity_polling()
