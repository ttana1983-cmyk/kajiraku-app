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

# Geminiの初期設定
genai.configure(api_key=GEMINI_API_KEY)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text

    try:
        # 【修正ポイント】モデル名をシンプルにし、最新のAPIで呼び出します
        model = genai.GenerativeModel('gemini-1.5-flash')

        prompt = f"""
        
        あなたは『家事ラクAIコンシェルジュ』の「Takashi」です。
        
        【重要：会話の進め方ルール】
        1. 以下の3点（家族構成・アレルギー・苦手な食材）が完全に揃うまでは、レシピの提案（URLの提示）を【厳禁】とします。
        2. 情報が不足している間は、ユーザーとの対話を楽しみながら、1つずつ優しく聞き出してください。
        3. 3つの情報がすべて揃ったことを確認したら、初めて「それでは、あなたにぴったりの献立を提案させていただきますね！」と宣言して、ジャンル等の選択肢を出してください。

        【表示ルール（見やすさ徹底）】
        ・2〜3行ごとに必ず「空行」を入れること。
        ・重要なポイントは【】や絵文字を使って目立たせること。

        【冒頭の挨拶ルール】
        ・ベータ版の案内（50秒、5回制限）は、その日の「最初の1通目」のみ。
        ・やり取りが続いている間は、挨拶を省き、すぐに質問や回答に入ってください。

        【レシピ提案時の構成（情報がすべて揃った後のみ）】
        ---
        【本日のご提案】
        （レシピ名）
        https://cookpad.com/search/[料理名]

        【Takashiの家事ラク！1ポイント助言】
        ・（減塩、カサ増し、ヘルシー、家事ラクのいずれか）
        ---

        現在のユーザーのメッセージ: {user_message}
        """


        # AIの生成
        response = model.generate_content(prompt)

        if response.text:
            reply_text = response.text
        else:
            reply_text = "すみません、内容を考えられませんでした。"

    except Exception as e:
        # もしまた404が出るなら、こちらを試すように自動で切り替えます
        try:
            model = genai.GenerativeModel('gemini-2.5-flash')
            response = model.generate_content(prompt)
            reply_text = response.text
        except:
            reply_text = f"エラーが発生しました: {str(e)}"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
