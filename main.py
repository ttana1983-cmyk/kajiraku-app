import os
import traceback
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent
import google.generativeai as genai

app = Flask(__name__)

# --- 1. 環境設定 ---
# LINE側
line_access_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
line_secret = os.environ.get("LINE_CHANNEL_SECRET")
gemini_key = os.environ.get("GEMINI_API_KEY")

conf = Configuration(access_token=line_access_token)
handler = WebhookHandler(line_secret)

# Gemini側（安定版の設定）
genai.configure(api_key=gemini_key)
# モデル名を最も無難な 'gemini-1.5-flash' に固定
model = genai.GenerativeModel('gemini-1.5-flash')

# --- 2. Webhook受付 ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 3. メッセージ処理 ---
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    msg = event.message.text
    tk = event.reply_token

    try:
        # AIで献立を生成（安全設定を最小限にしてブロックを防ぐ設定を追加）
        response = model.generate_content(
            f"食材「{msg}」の献立とURLを1つ教えて",
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
        )
        
        # テキストの取り出し
        ai_text = response.text

        # LINE返信
        with ApiClient(conf) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=tk,
                    messages=[TextMessage(text=ai_text)]
                )
            )
            
    except Exception as e:
        # エラーが起きた場合は、ログに詳細を出しつつLINEに「正体」を返させる
        error_detail = traceback.format_exc()
        print(f"--- ERROR ---\n{error_detail}")
        
        with ApiClient(conf) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=tk,
                    messages=[TextMessage(text=f"AIエラー: {str(e)[:100]}")]
                )
            )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
