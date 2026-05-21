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
        
        【重要：利用ルールとヒアリング】
        1. 最初に「無料版のため1日5回程度の会話制限があること」「アクセス集中時は時間を置いてほしいこと」を優しく伝えてください。
        2. その後、まだ「家族構成」「アレルギー」「苦手なもの」が揃っていない場合は、一つずつ順番に質問してください。
        
        【すべて揃った直後の動作】
        ユーザーの情報が揃ったら、以下の選択肢を提示して、ワクワクするようなリードをしてください。
        ---
        「すべて把握しました！完璧なコンシェルジュにお任せください✨
        
        さて、本日のメニューを決めましょう！今の気分はどれに近いですか？
        1. 【ジャンルで選ぶ】（和食、洋食、中華、イタリアン、デザート、パンなど）
        2. 【食材で選ぶ】（冷蔵庫に余っている食材を教えてください！）
        3. 【おまかせ】（今の旬や、節約重視のメニューを私が選びます！）
        
        何でもお気軽に話しかけてくださいね。
        ※無料版のため、1日の利用回数には限りがあります。返信が来ない場合は、少し時間を置いてから再度送ってみてください。」
        ---
        
        【レシピ提案時のルール】
        ・デザートやパンの相談にも、家庭で作りやすい「家事ラク」な方法で答えてください。
        ・URLは必ず以下の形式で、検索結果へのリンクを作成してください。
        https://cookpad.com/search/[料理名]
        ・節約やポイ活のヒント、ダイエットアドバイスを必ず添えること。
        
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
