import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageSendMessage
)
import google.generativeai as genai

app = Flask(__name__)

# --- 【重要】ここが定義されていないとNameErrorになります ---
line_bot_api = LineBotApi(os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# Takashiさん指定の2.5モデル
model = genai.GenerativeModel("gemini-2.5-flash")

# 正確なネコURL
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

    # 特定のコマンド以外（食材入力）をレシピ生成とみなす
    if msg not in ["メニュー", "最初から", "⚙️再設定"]:
        try:
            # プロンプトの書き方を整理
    prompt = f"""
あなたは元ラーメン店長の献立アドバイザーです。
食材「{msg}」を使った、家庭で作りやすいプロ直伝の献立を1つ提案してください。

【ルール】
・語尾は少し職人気質だが、優しく親しみやすく
・回答は300文字程度にまとめること
・最後に必ず、その料理の作り方がわかる『実在する』レシピサイト（クックパッド、クラシル等）のURLを1つ載せること
"""
            response = model.generate_content(prompt)
            recipe_text = response.text

            # まとめて1回の「返信」で送る（これが一番エラーに強い！）
            messages = [
                TextSendMessage(text="オーダー入りました！ねこシェフ調理中...🐾"),
                ImageSendMessage(original_content_url=GIF_URL, preview_image_url=GIF_URL),
                TextSendMessage(text=f"🔔 ピーッ！＼ チン！ ／\n\n{recipe_text}")
            ]
            
            line_bot_api.reply_message(token, messages)

        except Exception as e:
            # AI側のエラーが出た場合も返信で伝える
            error_msg = f"わりぃ、店長ちょっと今手が離せねえ！\n(Error: {str(e)[:20]})"
            line_bot_api.reply_message(token, TextSendMessage(text=error_msg))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
