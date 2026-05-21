import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageSendMessage
)
import google.generativeai as genai

app = Flask(__name__)

# --- 設定（Renderの環境変数と一致している前提） ---
line_bot_api = LineBotApi(os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# Gemini 2.5
model = genai.GenerativeModel("gemini-2.5-flash")

# ネコシェフURL
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
    # 【重要】これが返信の鍵です
    tk = event.reply_token 

    if msg not in ["メニュー", "最初から", "⚙️再設定"]:
        try:
            # Takashiさんこだわりのトリプルクォート形式
            prompt = f"""
あなたは元ラーメン店長の献立アドバイザーです。
食材「{msg}」を使ったプロ直伝の献立を1つ提案してください。

【ルール】
・300文字以内、職人気質だけど優しい口調で。
・最後に必ず実在するレシピURLを1つ載せること。
"""
            response = model.generate_content(prompt)
            
            # まとめて1回の「返信(reply)」で送る。これが一番確実です！
            messages = [
                TextSendMessage(text="オーダー入りました！ねこシェフ調理中...🐾"),
                ImageSendMessage(original_content_url=GIF_URL, preview_image_url=GIF_URL),
                TextSendMessage(text=f"チン！完成です！✨\n\n{response.text}")
            ]
            
            # pushではなくreplyを使うのがLINE公式の推奨です
            line_bot_api.reply_message(tk, messages)

        except Exception as e:
            # ログで200が出ているのに返信がない場合、ここが実行されます
            print(f"Error detail: {e}")
            line_bot_api.reply_message(tk, TextSendMessage(text=f"店長エラー: {str(e)[:50]}"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
