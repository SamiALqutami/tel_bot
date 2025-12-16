from flask import Flask, request, jsonify
import requests
import os
import redis
import json
import traceback
import random
import time
from flask_cors import CORS

app = Flask(__name__)

# تفعيل CORS للسماح بالطلبات من أي مكان (لحل مشكلة Failed to fetch)
CORS(app, resources={r"/*": {"origins": "*"}})

# --- إعدادات Redis ---
REDIS_URL = os.environ.get('UPSTASH_REDIS_URL')
# إضافة ssl_cert_reqs=None لتجنب مشاكل شهادات SSL مع Upstash
r = redis.from_url(REDIS_URL, ssl_cert_reqs=None) if REDIS_URL else None

TELEGRAM_API = "https://api.telegram.org/bot"

# --- دوال المساعدة ---
def set_webhook(token, host_url):
    webhook_url = f"{host_url}/webhook/{token}"
    url = f"{TELEGRAM_API}{token}/setWebhook"
    try:
        requests.post(url, json={"url": webhook_url, "drop_pending_updates": True})
        return True
    except Exception as e:
        print(f"Webhook Error: {e}")
        return False

def delete_webhook(token):
    url = f"{TELEGRAM_API}{token}/deleteWebhook"
    try:
        requests.post(url)
    except:
        pass

# --- Sandbox (تنفيذ الكود) ---
def execute_bot_logic(token, code, update):
    try:
        def send_msg(chat_id, text, reply_markup=None, parse_mode=None):
            payload = {"chat_id": chat_id, "text": text}
            if reply_markup: payload["reply_markup"] = reply_markup
            if parse_mode: payload["parse_mode"] = parse_mode
            requests.post(f"{TELEGRAM_API}{token}/sendMessage", json=payload)
        
        # تحضير سياق التنفيذ (المكتبات المتاحة للمستخدم)
        context = {
            "update": update,
            "requests": requests,
            "json": json,
            "random": random,
            "time": time,
            "redis_db": r,
            "token": token,
            "send_msg": send_msg,
            # استخراج بيانات الرسالة بشكل آمن
            "message": update.get('message', {}),
            "chat_id": update.get('message', {}).get('chat', {}).get('id'),
            "text": update.get('message', {}).get('text', '')
        }
        
        # تنفيذ الكود
        exec(code, context)
        return True
    except Exception as e:
        err_msg = traceback.format_exc()
        print(f"User Code Error: {err_msg}")
        return False

# --- المسارات ---

@app.route('/api/control', methods=['POST'])
def control_panel():
    """API للتحكم: رفع، تشغيل، إيقاف"""
    if not r:
        return jsonify({"status": "error", "msg": "Database not connected. Check UPSTASH_REDIS_URL"}), 500

    data = request.json
    action = data.get('action')
    token = data.get('token')
    
    if not token:
        return jsonify({"status": "error", "msg": "No Token Provided"})

    key_code = f"bot:{token}:code"
    key_status = f"bot:{token}:status"

    try:
        if action == "upload":
            code = data.get('code')
            if not code: return jsonify({"status": "error", "msg": "No Code Provided"})
            
            r.set(key_code, code)
            r.set(key_status, "active")
            
            # ضبط الويب هوك على النطاق الحالي
            host = request.headers.get('Host') or request.host
            proto = "https" # Vercel دائما https
            set_webhook(token, f"{proto}://{host}")
            
            return jsonify({"status": "success", "msg": "✅ تم تفعيل البوت بنجاح!"})

        elif action == "stop":
            r.set(key_status, "stopped")
            delete_webhook(token)
            return jsonify({"status": "success", "msg": "⏸️ تم إيقاف البوت"})

        elif action == "start":
            r.set(key_status, "active")
            host = request.headers.get('Host') or request.host
            set_webhook(token, f"https://{host}")
            return jsonify({"status": "success", "msg": "▶️ تم إعادة التشغيل"})

        elif action == "delete":
            r.delete(key_code)
            r.delete(key_status)
            delete_webhook(token)
            return jsonify({"status": "success", "msg": "🗑️ تم حذف بيانات البوت"})

    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)})

    return jsonify({"status": "error", "msg": "Invalid Action"})

@app.route('/webhook/<token>', methods=['POST'])
def webhook_handler(token):
    """استقبال تحديثات تيليجرام"""
    if not r: return "DB Error", 500
    
    update = request.json
    if not update: return "No Data", 200

    # التحقق من الحالة
    status = r.get(f"bot:{token}:status")
    if not status or status.decode('utf-8') != "active":
        return "Stopped", 200

    # جلب الكود
    code = r.get(f"bot:{token}:code")
    if code:
        execute_bot_logic(token, code.decode('utf-8'), update)
    
    return "OK", 200

@app.route('/')
def home():
    return "🚀 Telegram Bot Engine Running. <br> use /api/control for commands."

# Vercel يتطلب هذا المتغير
app = app
