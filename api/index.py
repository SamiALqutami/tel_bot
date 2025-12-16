from flask import Flask, request, jsonify
import requests
import os
import redis
import json
import traceback
from flask_cors import CORS # 👈 1. استيراد مكتبة CORS

app = Flask(__name__)
CORS(app) # 👈 2. تفعيل CORS على مستوى التطبيق

# --- الدادات (تؤخذ من متغيرات البيئة) ---
# ملاحظة: يجب تعريف هذه المتغيرات (UPSTASH_REDIS_URL و ADMIN_BOT_TOKEN) في إعدادات Vercel (Environment Variables)

REDIS_URL = os.environ.get('UPSTASH_REDIS_URL') # 👈 تم تغيير القيمة إلى اسم المفتاح
ADMIN_BOT_TOKEN = os.environ.get('ADMIN_BOT_TOKEN') # 👈 تم تغيير القيمة إلى اسم المفتاح

# الاتصال بقاعدة البيانات السريعة
r = redis.from_url(REDIS_URL) if REDIS_URL else None

TELEGRAM_API = "https://api.telegram.org/bot"

# --- دوال المساعدة ---
def set_webhook(token, host_url):
    """ربط البوت المستضاف بسيرفرنا"""
    webhook_url = f"{host_url}/webhook/{token}"
    url = f"{TELEGRAM_API}{token}/setWebhook"
    try:
        # إرسال طلب Webhook
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
    تنفيذ كود المستخدم بأمان وتمرير أدوات جاهزة
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
        # يمكنك هنا إضافة لوج (Log) إلى قاعدة البيانات أو نظام مراقبة
        return False

# --- المسارات (Routes) ---

@app.route('/api/control', methods=['POST'])
def control_panel():
    """API للتحكم من التطبيق المصغر (رفع، إيقاف، حذف)"""
    data = request.json
    action = data.get('action') # upload, start, stop, delete
    token = data.get('token')
    
    # تم تغيير التحقق الأولي ليكون أوضح
    if not token:
        return jsonify({"status": "error", "msg": "Missing Bot Token"})
    if not r:
        return jsonify({"status": "error", "msg": "Database Connection Error (Check UPSTASH_REDIS_URL)"})

    key_code = f"bot:{token}:code"
    key_status = f"bot:{token}:status"

    # ... (بقية منطق التحكم لم يتغير) ...

    if action == "upload":
        code = data.get('code')
        r.set(key_code, code)
        r.set(key_status, "active")
        # استخدام طلب.المضيف (request.host) لضمان استخدام النطاق الصحيح
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
        # رسالة خطأ واضحة في حالة عدم اتصال Redis
        return "DB Error", 500 

    # 1. التحقق هل البوت موجود ونشط؟
    status = r.get(f"bot:{user_token}:status")
    # يجب التحقق من حالة البايت ثم فك التشفير
    if not status or status.decode('utf-8') != "active":
        return "Bot Stopped", 200

    # 2. جلب الكود من الذاكرة
    code = r.get(f"bot:{user_token}:code")
    if not code:
        return "No Code", 200

    # 3. تشغيل الكود
    execute_bot_logic(user_token, code.decode('utf-8'), update)
    
    return "OK", 200

@app.route('/')
def home():
    # هذا المسار يثبت أن التطبيق يعمل
    return "🚀 Telegram Bot Hosting Engine is Running (Vercel + Redis)"

# إذا كنت تستخدم gunicorn أو Vercel في وضع التطوير المحلي
if __name__ == '__main__':
    app.run(debug=True)
