import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageSendMessage
)
import google.generativeai as genai

app = Flask(__name__)

# --- 設定（RenderのEnvironment Variablesと名前が一致しているか確認！） ---
line_bot_api = LineBotApi(os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# 2.5-flashを使用
model = genai.GenerativeModel("gemini-2.5-flash")

# あなたのリポジトリ上のchef.gif
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

    # デバッグログ（RenderのLogs画面でこれが出るか見てください）
    print(f"--- 受信メッセージ: {msg} ---")

    if msg not in ["メニュー", "最初から", "⚙️再設定"]:
        try:
            # Gemini 2.5 へのプロンプト
            prompt = f"元ラーメン店長として、食材「{msg}」に合う献立を1つ提案し、最後に実在するクックパッド等のURLを1つ載せて。300文字以内。"
            response = model.generate_content(prompt)
            
            # 正常時の返信（ネコシェフ付き）
            messages = [
                TextSendMessage(text="オーダー入りました！ねこシェフ調理中...🐾"),
                ImageSendMessage(original_content_url=GIF_URL, preview_image_url=GIF_URL),
                TextSendMessage(text=f"チン！完成です！✨\n\n{response.text}")
            ]
            line_bot_api.reply_message(token, messages)
            print("--- 返信完了 ---")

        except Exception as e:
            # エラーが出た場合、その内容をLINEに直接報告させる
            error_msg = f"【デバッグ】店長エラーだ！\n内容: {str(e)}"
            print(f"--- エラー発生: {error_msg} ---")
            line_bot_api.reply_message(token, TextSendMessage(text=error_msg))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
