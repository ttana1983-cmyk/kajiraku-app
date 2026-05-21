import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import google.generativeai as genai

app = Flask(__name__)

# --- 設定（Renderの環境変数から読み込みます） ---
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['x-line-signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text
    
    # AIへの指示（コンシェルジュの性格付け・ダイエット・ポイ活等のビジョンを含む）
    prompt = f"""
    あなたは月収1000万を目指す事業の柱となる『家事ラクAIコンシェルジュ』です。
    
    【基本方針】
    1. 冷蔵庫の食材、人数、アレルギー、辛さの好み（取り分け調理）を考慮したレシピ提案。
    2. ダイエット目標に合わせたカロリー計算と、モチベーション維持のアドバイス。
    3. ポイ活や節約、使い切りプランの提示。
    4. 親しみやすく、かつプロフェッショナルなコンシェルジュとして振る舞ってください。
    
    ユーザーのメッセージ: {user_message}
    """
    
    response = model.generate_content(prompt)
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=response.text)
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
