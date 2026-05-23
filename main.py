import os
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from google import genai

app = Flask(__name__)

# 環境変数
conf = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])

# Geminiクライアントの初期化（最新の書き方）
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    msg = event.message.text
    tk = event.reply_token

    try:
        # AIの処理：最新のライブラリ（google-genai）の書き方に統一しました
        # モデル名は確実に存在する「gemini-1.5-flash」に変更しています
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=f"食材「{msg}」の献立とURLを1つ教えて"
        )
        
        with ApiClient(conf) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=tk,
                    messages=[TextMessage(text=response.text)]
                )
            )
    except Exception as e:
        with ApiClient(conf) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=tk,
                    messages=[TextMessage(text=f"エラーが発生しました。時間を置いてお試しください。")]
                )
            )
        # ログに詳細なエラー内容を出す（デバッグ用）
        print(f"Error: {e}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
