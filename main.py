import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageSendMessage
)
import google.generativeai as genai

app = Flask(__name__)

# --- 設定：Renderの環境変数と連携 ---
line_bot_api = LineBotApi(os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# 最新の Gemini 2.5 モデルを指定
model = genai.GenerativeModel("gemini-2.5-flash")

# あなたのGitHubから提供された正確なネコURL
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

    # 特定の挨拶以外（食材入力）をレシピ生成とみなす
    if msg not in ["メニュー", "最初から", "⚙️再設定"]:
        try:
            # Takashiさんこだわりのトリプルクォートによる詳細指示
            prompt = f"""
あなたは元ラーメン店長の献立アドバイザーです。
食材「{msg}」を使った、プロ直伝の献立を1つ提案してください。

【厳格なルール】
1. まずGoogle検索等の最新情報を参照し、提案する料理の実在するレシピURL（クックパッド、クラシル等）を特定してください。
2. そのURLが現在も有効（404エラーでないこと）であることを厳重に確認してください。
3. 回答の最後は必ず『詳しいレシピはこちら：[URL]』という形式で締めてください。
4. 語尾は職人気質だが親しみやすい口調で、300文字以内にまとめること。
"""
            # Gemini 2.5 での生成
            response = model.generate_content(prompt)
            recipe_text = response.text

            # LINEへの返信メッセージ作成（1セットで送ることで安定性を最大化）
            messages = [
                TextSendMessage(text="オーダー入りました！ねこシェフ調理中...🐾"),
                ImageSendMessage(original_content_url=GIF_URL, preview_image_url=GIF_URL),
                TextSendMessage(text=f"🔔 チン！完成したぜ！✨\n\n{recipe_text}")
            ]
            
            line_bot_api.reply_message(token, messages)

        except Exception as e:
            # エラー発生時のデバッグ用返信
            error_msg = f"店長、ちょっと今手が離せねえ！\n(内容: {str(e)[:50]})"
            line_bot_api.reply_message(token, TextSendMessage(text=error_msg))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
