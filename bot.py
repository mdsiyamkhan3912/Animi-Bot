import os
import io
import re
import time
import requests
import urllib3
from threading import Thread
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote, unquote
from pypdf import PdfReader
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ----------- ১. ফ্লাস্ক সার্ভার -----------
app = Flask('')

@app.route('/')
def home():
    return "BBGGC Combined Final Bot is Online!"

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
#               ১ম অংশ: 1️⃣ Sonali Result (BBGGC)
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
#          ২য় অংশ: 2️⃣ eShiksha Result (অটো চেইন)
# =======================================================

BASE_URL = "https://bbggc.eshiksaems.com"
LOGIN_URL = f"{BASE_URL}/Authentication"
DATA_URL = f"{BASE_URL}/controller_student_module.php"

def get_session():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
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

def extract_adm_roll_photo_and_session(session, class_roll):
    adm_roll = None
    photo_bytes = None
    session_id = "22"  # ডিফল্ট সেশন আইডি

    try:
        payload = {
            'rootData': str(class_roll).strip(),
            'flagreq': 'transactionCheck'
        }
        tx_res = session.post(DATA_URL, data=payload, timeout=12)
        
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
                enc_res = session.post(
                    DATA_URL,
                    data={'rootData': target_receipt_id, 'flagreq': 'ajaxEncryption'},
                    timeout=10
                )
                if enc_res.status_code == 200:
                    xx_code = enc_res.text.strip().strip('"\'')
                    pdf_url = f"{BASE_URL}/std_coll_slip.php?xxCode={quote(xx_code)}"
                    pdf_res = session.get(pdf_url, timeout=15)

                    if pdf_res.status_code == 200 and len(pdf_res.content) > 500:
                        reader = PdfReader(io.BytesIO(pdf_res.content))
                        slip_text = ""
                        for page in reader.pages:
                            slip_text += (page.extract_text() or "") + "\n"

                        adm_m = re.search(r"Admission\s*Roll\s*:\s*(\d{5,8})", slip_text, re.I)
                        if adm_m:
                            adm_roll = adm_m.group(1).strip()

        p_res = session.post(DATA_URL, data={'rootData': str(class_roll).strip(), 'flagreq': 'profileRollCheck'}, timeout=10)
        if p_res.status_code == 200:
            soup = BeautifulSoup(p_res.text, 'html.parser')
            for img in soup.find_all('img'):
                src = img.get('src', '')
                if 'image/student' in src:
                    ir = session.get(f"{BASE_URL}/{src.lstrip('/')}", timeout=10)
                    if ir.status_code == 200:
                        photo_bytes = ir.content
                    break
            
            if not adm_roll:
                p_rolls = re.findall(r"\b2\d{5}\b", p_res.text)
                if p_rolls:
                    adm_roll = p_rolls[0]

    except Exception:
        pass

    return adm_roll, photo_bytes, session_id

def fetch_admission_form_by_adm_roll(session, adm_roll, session_id="22"):
    possible_sessions = [str(session_id), "22", "21", "20", "19", "18", "23", "24"]
    
    for sid in possible_sessions:
        try:
            tx_payload = {
                'rootData': str(adm_roll).strip(),
                'sessionID': str(sid),
                'flagreq': 'checkTransaction'
            }
            res_tx = session.post(DATA_URL, data=tx_payload, timeout=12)
            if res_tx.status_code != 200 or not res_tx.text.strip():
                continue

            raw_query = res_tx.text.strip().strip('"\'')
            if len(raw_query) < 10 or "<html" in raw_query.lower():
                continue

            if "xxCode=" in raw_query:
                pdf_url = f"{BASE_URL}/Student-Admission?{raw_query}"
            else:
                pdf_url = f"{BASE_URL}/Student-Admission?xxCode={raw_query}"
                if "yyCode" not in pdf_url:
                    pdf_url += "&yyCode=1"

            pdf_headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
                'Referer': f"{BASE_URL}/Result-Enquiry-Center",
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
                    if num_match:
                        return num_match.group(1)
                return ""

            student_phone = extract_bd_phone(r"Student'?s\s*Phone\s*:\s*([^\n\r]+)")
            father_phone = extract_bd_phone(r"Father'?s/Guardian'?s\s*Phone\s*:\s*([^\n\r]+)")
            mother_phone = extract_bd_phone(r"Mother'?s\s*Phone\s*:\s*([^\n\r]+)")

            dob = get_match(r"Date\s*of\s*Birth\s*:\s*([0-9]{1,2}-[A-Za-z]{3}-[0-9]{4})")
            if not dob:
                dob = get_match(r"Date\s*of\s*Birth\s*:\s*([^\n\r]+?)(?=\s*\d{1,2}\.|\s*Quota|$)")

            rel = get_match(r"Religion\s*:\s*([A-Za-z]+)")

            email_match = re.search(r"Student'?s\s*E-?mail\s*:\s*([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", full_text, re.I)
            student_email = email_match.group(1).strip() if email_match else ""

            s_name = get_match(r"Student\s*Name\s*\(English\)\s*:\s*([A-Za-z\s\.]+?)(?=\(বাংলায়\)|\n|$)")
            f_name = get_match(r"Father'?s\s*Name\s*:\s*([A-Za-z\s\.]+?)(?=\(বাংলায়\)|\n|$)")
            m_name = get_match(r"Mother'?s\s*Name\s*:\s*([A-Za-z\s\.]+?)(?=\(বাংলায়\)|\n|$)")

            if not s_name:
                continue

            gender = get_match(r"Gender\s*:\s*([A-Za-z]+)") or "Female"
            blood = get_match(r"Blood\s*Group\s*:\s*([A-Za-z+-]+)")

            data = {
                "class_roll": get_match(r"Class\s*Roll\s*:\s*(\d+)"),
                "adm_roll": str(adm_roll),
                "reg_no": get_match(r"Reg\s*No[\s\S]*?(\d{8,15})"),
                "student_name": s_name,
                "student_nid": get_match(r"Student'?s\s*NID/Birth\s*Reg\.?\s*:\s*([0-9]+)"),
                "gender": gender,
                "student_phone": student_phone,
                "dob": dob,
                "religion": rel,
                "blood": blood,
                "student_email": student_email,
                "father_name": f_name,
                "father_nid": get_match(r"Father'?s/Guardian'?s\s*NID\s*:\s*([0-9]+)"),
                "father_phone": father_phone,
                "mother_name": m_name,
                "mother_nid": get_match(r"Mother'?s\s*NID\s*:\s*([0-9]+)"),
                "mother_phone": mother_phone,
                "permanent_address": get_match(r"Permanent\s*Address\s*:\s*([^\n\r]+?)(?=\n|Present|$)"),
                "present_address": get_match(r"Present\s*Address\s*:\s*([^\n\r]+?)(?=\n|Permanent|$)"),
                "dept": get_match(r"Group\s*:\s*([^\n\r]+?)(?=\n|Session)"),
                "board": get_match(r"Board/Instit\.?[\s\S]*?([A-Za-z]+)\s+\d\.\d{2}"),
                "gpa": get_match(r"(\d\.\d{2})\s*$"),
                "session": get_match(r"Session\s*:\s*([^\n\r]+?)(?=\n|$)", def_val="2026-2027"),
                "year": "1"
            }

            return pdf_bytes, data
        except Exception:
            continue

    return None, None

def format_caption(data):
    return (
        f"🏛️ বেগম বদরুন্নেসা সরকারি মহিলা কলেজ\n"
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

def create_multi_phone_keyboard(std_phone, fat_phone, mot_phone, next_start=None, next_end=None):
    markup = InlineKeyboardMarkup()
    if std_phone:
        markup.row(
            InlineKeyboardButton("🟢 Std WA", url=f"https://wa.me/88{std_phone}"),
            InlineKeyboardButton("🔵 Std TG", url=f"https://t.me/+88{std_phone}")
        )
    if fat_phone:
        markup.row(
            InlineKeyboardButton("🟢 Fat WA", url=f"https://wa.me/88{fat_phone}"),
            InlineKeyboardButton("🔵 Fat TG", url=f"https://t.me/+88{fat_phone}")
        )
    if mot_phone:
        markup.row(
            InlineKeyboardButton("🟢 Mot WA", url=f"https://wa.me/88{mot_phone}"),
            InlineKeyboardButton("🔵 Mot TG", url=f"https://t.me/+88{mot_phone}")
        )
    
    if next_start and next_end:
        markup.add(InlineKeyboardButton("➡️ Next 500", callback_data=f"eshiksha_next_{next_start}_{next_end}"))

    return markup if len(markup.keyboard) > 0 else None

def process_full_student(chat_id, user_input, next_start=None, next_end=None):
    session = get_session()
    photo_bytes = None
    target_adm_roll = None
    extracted_session_id = "22"

    if len(str(user_input)) == 6:
        target_adm_roll = str(user_input)
    else:
        adm_roll, photo, sess_id = extract_adm_roll_photo_and_session(session, user_input)
        target_adm_roll = adm_roll
        photo_bytes = photo
        if sess_id:
            extracted_session_id = sess_id

    if not target_adm_roll:
        bot.send_message(chat_id, f"❌ রোল `{user_input}`-এর কোনো পেমেন্ট রিসিট বা এডমিশন রোল পাওয়া যায়নি!", parse_mode='Markdown')
        return

    pdf_bytes, data = fetch_admission_form_by_adm_roll(session, target_adm_roll, extracted_session_id)

    if not data or not pdf_bytes:
        bot.send_message(chat_id, f"❌ এডমিশন রোল `{target_adm_roll}`-এর মূল আবেদন ফর্ম পাওয়া যায়নি!", parse_mode='Markdown')
        return

    if not data["class_roll"] or data["class_roll"] == "N/A":
        data["class_roll"] = str(user_input)

    caption = format_caption(data)
    action_markup = create_multi_phone_keyboard(
        data['student_phone'],
        data['father_phone'],
        data['mother_phone'],
        next_start=next_start,
        next_end=next_end
    )

    pdf_file = io.BytesIO(pdf_bytes)
    pdf_file.name = f"Admission_Form_{data['adm_roll']}.pdf"
    doc_caption = f"📄 *মূল আবেদন ফর্ম (Admission Form)*\n🎫 Adm Roll: `{data['adm_roll']}`\n🔢 Class Roll: `{user_input if len(str(user_input)) > 6 else data['class_roll']}`"
    bot.send_document(chat_id, pdf_file, caption=doc_caption, parse_mode='Markdown')

    if photo_bytes:
        try:
            bot.send_photo(chat_id, photo_bytes, caption=caption, parse_mode='Markdown', reply_markup=action_markup)
            return
        except Exception:
            pass

    bot.send_message(chat_id, caption, parse_mode='Markdown', reply_markup=action_markup)

def run_eshiksha_range_search(chat_id, start_roll, end_roll):
    total_to_search = end_roll - start_roll + 1
    active_tasks[chat_id] = True

    bot.send_message(chat_id, f"🔄 অটো সার্চ শুরু: `{start_roll}` - `{end_roll}`", parse_mode='Markdown')

    stop_markup = InlineKeyboardMarkup()
    stop_markup.add(InlineKeyboardButton("🔴 Stop Search", callback_data="stop_search"))

    status_msg = bot.send_message(chat_id, "⏳ সার্চ শুরু হচ্ছে...", reply_markup=stop_markup)
    found_count = 0

    for idx, r in enumerate(range(start_roll, end_roll + 1), start=1):
        if not active_tasks.get(chat_id, False):
            bot.send_message(chat_id, "🛑 সার্চ থামানো হয়েছে!")
            break

        try:
            session = get_session()
            adm_roll, photo_bytes, sess_id = extract_adm_roll_photo_and_session(session, r)
            target_adm = adm_roll if adm_roll else (str(r) if len(str(r)) == 6 else None)

            if target_adm:
                pdf_bytes, data = fetch_admission_form_by_adm_roll(session, target_adm, sess_id)
                if data:
                    found_count += 1
                    if not data["class_roll"] or data["class_roll"] == "N/A":
                        data["class_roll"] = str(r)

                    caption = format_caption(data)
                    action_markup = create_multi_phone_keyboard(
                        data['student_phone'],
                        data['father_phone'],
                        data['mother_phone']
                    )

                    if pdf_bytes:
                        pdf_file = io.BytesIO(pdf_bytes)
                        pdf_file.name = f"Admission_Form_{data['adm_roll']}.pdf"
                        bot.send_document(chat_id, pdf_file, caption=f"📄 Admission Form: `{data['adm_roll']}`", parse_mode='Markdown')

                    if photo_bytes:
                        try:
                            bot.send_photo(chat_id, photo_bytes, caption=caption, parse_mode='Markdown', reply_markup=action_markup)
                            continue
                        except Exception:
                            pass

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
    except:
        pass

    bot.send_message(chat_id, f"✅ সার্চ সম্পন্ন হয়েছে!\n📊 মোট তথ্য পাওয়া গেছে: {found_count}")
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
            "স্বাগতম (বেগম বদরুন্নেসা কলেজ এডমিশন ও ফরম বট)!\n\n"
            "• ১৩ সংখ্যার **ক্লাস রোল** পাঠান (যেমন: `1202526033005`)\n"
            "• অথবা সরাসরি **এডমিশন রোল** পাঠান (যেমন: `547059`)\n"
            "• অথবা রেঞ্জ পাঠান",
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
        run_eshiksha_range_search(chat_id, s_roll, e_roll)

@bot.message_handler(func=lambda msg: True)
def handle_message(message):
    chat_id = message.chat.id
    mode = user_modes.get(chat_id)
    text = message.text.strip()

    if not mode:
        bot.reply_to(message, "অনুগ্রহ করে প্রথমে একটি অপশন সিলেক্ট করুন:", reply_markup=main_menu())
        return

    # ১️⃣ Sonali Result
    if mode == "sonali":
        try:
            if "-" in text:
                s, e = map(int, text.split("-"))
                run_sonali_search(chat_id, s, e)
            else:
                run_sonali_search(chat_id, int(text), int(text))
        except:
            pass

    # 2️⃣ eShiksha Result
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
                run_eshiksha_range_search(chat_id, s, e)
                return

        if text.isdigit():
            roll = int(text)
            wait_msg = bot.reply_to(message, f"🔍 রোল `{roll}`-এর পিডিএফ, তথ্য ও ছবি খোঁজা হচ্ছে...", parse_mode='Markdown')
            process_full_student(chat_id, roll, next_start=roll+1, next_end=roll+500)

            try:
                bot.delete_message(chat_id, wait_msg.message_id)
            except Exception:
                pass
            return

        bot.reply_to(message, "অনুগ্রহ করে সঠিক রোল নম্বর অথবা রেঞ্জ পাঠান।")

if __name__ == "__main__":
    keep_alive()
    print("🚀 বেগম বদরুন্নেসা কলেজ কম্বাইন্ড বট সফলভাবে চালু হয়েছে...")
    bot.infinity_polling()
