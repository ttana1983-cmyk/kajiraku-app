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

    # 修正ポイント：モデルの呼び出しを最新の1.5-flashに最適化
    try:
        model = genai.GenerativeModel('models/gemini-1.5-flash')

        prompt = f"""
        あなたは『家事ラクAIコンシェルジュ』です。
        【方針】
        1. 食材、人数、取り分けを考慮したレシピ。
        2. ダイエットのアドバイス。
        3. ポイ活や節約の提示。
        ユーザーのメッセージ: {user_message}
        """

        response = model.generate_content(prompt)

        # 安全策：AIの返答が空の場合の処理
        reply_text = response.text if response.text else "申し訳ありません、うまく献立が考えられませんでした。"

    except Exception as e:
        # 万が一AI側でエラーが出た場合、何が原因かLINEに表示させる（デバッグ用）
        reply_text = f"エラーが発生しました: {str(e)}"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    # RenderはPORT 10000を使うことが多いので修正
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
