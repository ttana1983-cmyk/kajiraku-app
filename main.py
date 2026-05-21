import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageSendMessage
)
import google.generativeai as genai

app = Flask(__name__)

# --- 設定 ---
line_bot_api = LineBotApi(os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# Takashiさん指定の2.5モデル
model = genai.GenerativeModel("gemini-2.5-flash")

# 【ここを新しいURLに！】
# ttana1983-cmyk さんのリポジトリ名が main.py である前提です
GIF_URL = "https:///raw.githubusercontent.com/ttana1983-cmyk/main.py/main/chef.gif"

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
    uid = event.source.user_id

    # 進行フロー以外の入力に反応
    if msg not in ["メニュー", "最初から", "⚙️再設定"]:
        line_bot_api.push_message(uid, TextSendMessage(text="オーダー入りました！ねこシェフ調理中...🐾"))
        
        # ネコシェフ送信（preview_image_urlも同じURLを指定）
        try:
            line_bot_api.push_message(uid, ImageSendMessage(
                original_content_url=GIF_URL,
                preview_image_url=GIF_URL
            ))
        except:
            pass

        try:
            # 実在するレシピURLを出すためのプロンプト
            prompt = (
                f"あなたは元ラーメン店長です。食材（{msg}）を使った献立を1つ提案してください。\n\n"
                "【重要】回答の最後に、その料理の作り方がわかる『実在する』クックパッド等のレシピURLを必ず1つ添えてください。\n"
                "※存在しないURL（404）は絶対に載せないでください。350文字以内。"
            )
            response = model.generate_content(prompt)
            
            line_bot_api.push_message(uid, TextSendMessage(text="🔔 ピーッ！＼ チン！ ／"))
            line_bot_api.push_message(uid, TextSendMessage(text=f"特製メニュー完成です！✨\n\n{response.text}"))
        except Exception as e:
            line_bot_api.push_message(uid, TextSendMessage(text=f"AIエラー: {str(e)[:40]}"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
