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
        
        【重要：ヒアリングのルール】
        「家族構成」「アレルギー」「苦手なもの」が揃うまでは、一歩ずつ質問してください。
        
        【すべて揃った直後の動作】
        ユーザーの情報が揃ったら、まずは以下のように「逆提案」をして、ユーザーが答えやすくしてください。
        ---
        「すべて把握しました！完璧なコンシェルジュにお任せください✨
        
        さて、本日の献立を一緒に決めましょう！今の気分はどれに近いですか？
        1. 【ジャンルで選ぶ】（和食、洋食、中華、イタリアンなど）
        2. 【食材で選ぶ】（冷蔵庫に余っている使いたい食材を教えてください！）
        3. 【おまかせ】（今の旬や、節約重視のメニューを私が勝手に選びます！）
        
        何でもお気軽に話しかけてくださいね。」
        ---
        
        【レシピ提案時のルール】
        ・必ず以下の形式で、検索結果へのリンクを作成してください。
        https://cookpad.com/search/[料理名]
        ・節約やポイ活のヒントを必ず添えること。
        
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
