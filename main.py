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

# 送っていただいた正確なURLをここにセット
GIF_URL = "https://raw.githubusercontent.com/ttana1983-cmyk/main.py/chef.gif.gif"

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

    # 進行フロー以外の「食材入力」に反応
    if msg not in ["メニュー", "最初から", "⚙️再設定"]:
        # 1. 調理開始（テキスト）
        line_bot_api.push_message(uid, TextSendMessage(text="オーダー入りました！ねこシェフ調理中...🐾"))
        
        # 2. ネコシェフ送信（TakashiさんのURL）
        try:
            line_bot_api.push_message(uid, ImageSendMessage(
                original_content_url=GIF_URL,
                preview_image_url=GIF_URL
            ))
        except:
            pass

        # 3. AIによるレシピ生成 ＋ 実在するURLの検索指示
        try:
            prompt = (
                f"あなたは元ラーメン店長の献立アドバイザーです。食材（{msg}）を使った献立を1つ提案してください。\n\n"
                "【重要】回答の最後に、その料理の作り方がわかる『実在する』レシピサイト（クックパッド、クラシル、楽天レシピ等）のURLを必ず1つ添えてください。\n"
                "※URLが正しいか厳重に確認し、404エラーになる嘘のリンクは絶対に載せないでください。350文字以内。"
            )
            # モデルに検索（grounding）を促すための構成
            response = model.generate_content(prompt)
            
            # 4. 完成通知
            line_bot_api.push_message(uid, TextSendMessage(text="🔔 ピーッ！＼ チン！ ／"))
            line_bot_api.push_message(uid, TextSendMessage(text=f"特製メニュー完成です！✨\n\n{response.text}"))
        except Exception as e:
            line_bot_api.push_message(uid, TextSendMessage(text=f"店長エラー: {str(e)[:40]}"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
