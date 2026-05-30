import os
import sys
import json
import google.genai as genai
from flask import Flask, request, abort, render_template, jsonify
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest,
    TextMessage, QuickReply, QuickReplyItem, URIAction
)
# ここが重要：メッセージ内容を判定するためのクラスをインポート
from linebot.v3.webhooks import MessageEvent, TextMessageContent

app = Flask(__name__)

# --- 環境設定 ---
channel_secret = os.getenv('LINE_CHANNEL_SECRET')
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
gemini_api_key = os.getenv('GEMINI_API_KEY')

client = genai.Client(api_key=gemini_api_key)
model_id = 'gemini-3.5-flash'

configuration = Configuration(access_token=channel_access_token)
handler = WebhookHandler(channel_secret)

# --- 1. LIFF表示用 ---
@app.route("/")
def index():
    return render_template("index.html")

# --- 2. AIレシピ生成 (LIFFから呼ばれる) ---
@app.route("/api/generate-recipe")
def generate_recipe():
    query = request.args.get('query', 'おまかせ')
    prompt = f"要望: {query}。15分以内の節約レシピをJSON形式のみで作成してください。"
    try:
        response = client.models.generate_content(model=model_id, contents=prompt)
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        return jsonify(json.loads(clean_text))
    except Exception as e:
        print(f"AI Error: {e}")
        return jsonify({"name": "エラー", "steps": ["もう一度お試しください"]})

# --- 3. Webhook ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('x-line-signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 4. メッセージ受信 (修正ポイント：引数の書き方を変えました) ---
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    tk = event.reply_token
    # 即座に誘導
    handle_recipe_induction(event, tk)

def handle_recipe_induction(event, tk):
    base_url = "https://liff.line.me/2010225388-rXh2LiOR"
    # メッセージテキストを取得する書き方も event.message.text に変更
    target_url = f"{base_url}?query={event.message.text}"
    
    msg = "カジラク・コンシェルジュが献立を考えています。\n下のボタンから確認してくださいね！"
    quick_reply = QuickReply(items=[
        QuickReplyItem(action=URIAction(label="🍳 レシピを確認する", uri=target_url))
    ])
    send_reply(tk, msg, quick_reply=quick_reply)

def send_reply(tk, text, quick_reply=None):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(ReplyMessageRequest(
            reply_token=tk,
            messages=[TextMessage(text=text, quick_reply=quick_reply)]
        ))

if __name__ == "__main__":
    # Renderのポート解決のため、環境変数PORTを優先
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
