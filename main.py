import os
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, 
    ReplyMessageRequest, TextMessage, ImageMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

# 最新のGoogle GenAIライブラリを使用
from google import genai
from google.genai import types

app = Flask(__name__)

# --- 設定 ---
access_token = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
channel_secret = os.environ["LINE_CHANNEL_SECRET"]
configuration = Configuration(access_token=access_token)
handler = WebhookHandler(channel_secret)

# 最新のクライアント初期化
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

GIF_URL = "https://raw.githubusercontent.com/ttana1983-cmyk/main.py/main/chef.gif"

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

    if msg not in ["メニュー", "最初から", "⚙️再設定"]:
        try:
            # プロンプト（最新モデル gemini-2.0-flash 等も指定可能ですが、一旦 2.5 で）
            prompt = f"""
あなたは元ラーメン店長の献立アドバイザーです。食材「{msg}」を使った献立を1つ提案してください。
【重要】実在するレシピURL（クックパッド等）を必ず載せ、300文字以内の職人気質な口調で。
"""
            # 最新の生成メソッドを使用
            response = client.models.generate_content(
                model="gemini-2.0-flash", # 最新の高速モデルを推奨
                contents=prompt
            )
            recipe_text = response.text

            # LINE返信
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=tk,
                        messages=[
                            TextMessage(text="オーダー入りました！ねこシェフ調理中...🐾"),
                            ImageMessage(original_content_url=GIF_URL, preview_image_url=GIF_URL),
                            TextMessage(text=f"チン！完成だ！✨\n\n{recipe_text}")
                        ]
                    )
                )
        except Exception as e:
            print(f"Error detail: {e}")
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=tk,
                        messages=[TextMessage(text=f"すまねえ、店長エラーだ：{str(e)[:50]}")]
                    )
                )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
