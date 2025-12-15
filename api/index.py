from flask import Flask, request, jsonify
import requests
import os
import redis
import json
import traceback

app = Flask(__name__)

# --- الدادات (تؤخذ من متغيرات البيئة) ---
# احصل عليها من موقع Upstash.com (مجاني)
REDIS_URL = os.environ.get('rediss://default:AUgwAAIncDExZDk4NjZmM2YyY2Q0YzI0YjFmZjk0NjBkNDg3NDA3MnAxMTg0ODA@neutral-muskox-18480.upstash.io:6379') 
# توكن البوت الأساسي (المضيف)
ADMIN_BOT_TOKEN = os.environ.get('8352316200:AAHujChoBx7shlgBXJrOTLB7i9h9qtq_cMI')

# الاتصال بقاعدة البيانات السريعة
r = redis.from_url(REDIS_URL) if REDIS_URL else None

TELEGRAM_API = "https://api.telegram.org/bot"

# --- دوال المساعدة ---
def set_webhook(token, host_url):
    """ربط البوت المستضاف بسيرفرنا"""
    webhook_url = f"{host_url}/webhook/{token}"
    url = f"{TELEGRAM_API}{token}/setWebhook"
    try:
        requests.post(url, json={"url": webhook_url})
        return True
    except:
        return False

def delete_webhook(token):
    url = f"{TELEGRAM_API}{token}/deleteWebhook"
    requests.post(url)

# --- واجهة تنفيذ الكود (Sandbox) ---
def execute_bot_logic(token, code, update):
    """
    هنا السحر: نقوم بتنفيذ كود المستخدم ونمرر له أدوات جاهزة
    بما في ذلك كائن Redis ليتمكن من صنع بوتات دردشة عشوائية
    """
    try:
        # دوال مساعدة تحقن داخل كود المستخدم
        def send_msg(chat_id, text, reply_markup=None):
            payload = {"chat_id": chat_id, "text": text}
            if reply_markup: payload["reply_markup"] = reply_markup
            requests.post(f"{TELEGRAM_API}{token}/sendMessage", json=payload)
        
        # بيئة العمل للكود المستضاف
        context = {
            "update": update,
            "requests": requests,
            "json": json,
            "redis_db": r,  # إعطاء البوت إمكانية استخدام قاعدة البيانات!
            "token": token,
            "send_msg": send_msg,
            "message": update.get('message', {}),
            "chat_id": update.get('message', {}).get('chat', {}).get('id')
        }
        
        # تنفيذ الكود
        exec(code, context)
        return True
    except Exception as e:
        print(f"Error in user bot {token}: {e}")
        return False

# --- المسارات (Routes) ---

@app.route('/api/control', methods=['POST'])
def control_panel():
    """API للتحكم من التطبيق المصغر (رفع، إيقاف، حذف)"""
    data = request.json
    action = data.get('action') # upload, start, stop, delete
    token = data.get('token')
    
    if not token or not r:
        return jsonify({"status": "error", "msg": "Database Error or Missing Token"})

    key_code = f"bot:{token}:code"
    key_status = f"bot:{token}:status"

    if action == "upload":
        code = data.get('code')
        # حفظ الكود في Redis (سريع جداً)
        r.set(key_code, code)
        r.set(key_status, "active")
        # تفعيل الويب هوك
        set_webhook(token, f"https://{request.host}")
        return jsonify({"status": "success", "msg": "تم رفع البوت وتشغيله!"})

    elif action == "stop":
        r.set(key_status, "stopped")
        delete_webhook(token)
        return jsonify({"status": "success", "msg": "تم إيقاف البوت مؤقتاً"})

    elif action == "start":
        r.set(key_status, "active")
        set_webhook(token, f"https://{request.host}")
        return jsonify({"status": "success", "msg": "تم إعادة تشغيل البوت"})

    elif action == "delete":
        r.delete(key_code)
        r.delete(key_status)
        delete_webhook(token)
        return jsonify({"status": "success", "msg": "تم حذف البوت نهائياً"})

    return jsonify({"status": "error", "msg": "Invalid Action"})

@app.route('/webhook/<path:subpath>', methods=['POST'])
def handle_bot_webhook(subpath):
    """المسار الذي يستقبل تحديثات كل البوتات المستضافة"""
    user_token = subpath
    update = request.json
    
    if not r:
        return "DB Error", 500

    # 1. التحقق هل البوت موجود ونشط؟
    status = r.get(f"bot:{user_token}:status")
    if not status or status.decode('utf-8') != "active":
        return "Bot Stopped", 200

    # 2. جلب الكود من الذاكرة (سريع جداً - مللي ثانية)
    code = r.get(f"bot:{user_token}:code")
    if not code:
        return "No Code", 200

    # 3. تشغيل الكود
    execute_bot_logic(user_token, code.decode('utf-8'), update)
    
    return "OK", 200

@app.route('/')
def home():
    return "🚀 Telegram Bot Hosting Engine is Running (Vercel + Redis)"
