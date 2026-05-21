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
        あなたは『家事ラクAIコンシェルジュ』です。
        
        【重要：会話のルール】
        1. ユーザーとの最初の会話では、まず「家族構成」だけを聞いてください。
        2. 家族構成を教えてもらったら、次に「アレルギー」を確認してください。
        3. アレルギーを確認できたら、最後に「苦手なもの」を聞いてください。
        4. すべて揃ったら「承知しました！完璧にメモしました」と伝え、以降はそれらを考慮して献立を提案してください。
        5. すでに食材などの具体的な相談がある場合は、質問は後回しにして、まずはレシピを提案してください。
        
        【方針】
        ・家族構成に合わせた分量で提案。
        ・アレルギーは絶対回避。
        ・最後にクックパッドのURLを1つ載せる。
        
        ユーザーのメッセージ: {user_message}
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
