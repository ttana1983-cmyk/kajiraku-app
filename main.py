import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageSendMessage
)
import google.generativeai as genai

app = Flask(__name__)

# --- 環境設定 ---
line_bot_api = LineBotApi(os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# Takashiさんこだわりの 2.5 モデル
model = genai.GenerativeModel("gemini-2.5-flash")

# あなたが設定した chef.gif の直リンク
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

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    token = event.reply_token 

    if msg not in ["メニュー", "最初から", "⚙️再設定"]:
        try:
            # 1. Gemini 2.5 でレシピ生成
            prompt = f"食材「{msg}」を使った献立を1つ提案してください。"
            response = model.generate_content(prompt)
            
            # 2. ネコとレシピをセットで返信
            messages = [
                TextSendMessage(text="オーダー入りました！ねこシェフ調理中...🐾"),
                ImageSendMessage(original_content_url=GIF_URL, preview_image_url=GIF_URL),
                TextSendMessage(text=f"完成です！✨\n\n{response.text}")
            ]
            line_bot_api.reply_message(token, messages)

        except Exception as e:
            # 万が一の時はエラー内容をLINEに送る
            line_bot_api.reply_message(token, TextSendMessage(text=f"エラー発生：{str(e)[:50]}"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
