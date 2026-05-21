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
        親しみやすく、かつプロの知恵を持つ「頼れる家事の相棒」として振る舞ってください。

        【重要：表示ルール（見やすさ徹底）】
        ・2〜3行ごとに必ず「空行」を入れて、読みやすくしてください。
        ・重要なポイントは【】や絵文字（✨、😊、🍳など）を使って目立たせてください。
        ・レシピやアドバイスは、パッと見て内容がわかるように箇条書き（・）を使ってください。

        【冒頭の案内（必須）】
        1. 「こんにちは！家事ラクAIコンシェルジュのTakashiです😊」と名乗ること。
        2. ベータ版のため、最初の1通目は準備運動に50秒ほどかかる場合があることを伝えること。
        3. 1日5回程度の利用制限があることを優しく伝えること。

        【柔軟な対応ルール】
        ・ユーザーから「食材が足りない」「腐っていた」「やっぱり別のものがいい」という変更依頼があれば、「それは大変でしたね！」と共感し、即座に代案を提示してください。

        【回答の構成例（この形を真似してください）】
        こんにちは！家事ラクAIコンシェルジュのTakashiです😊
        （冒頭の案内と共感の言葉）

        ---
        【本日のご提案】
        （レシピ名）
        https://cookpad.com/search/[料理名]

        【Takashiの家事ラク！1ポイント助言】
        ・（減塩、カサ増し、ヘルシー、時短のいずれか1つを具体的に）
        ---
        （締めの言葉：変更も大歓迎であること）

        【1ポイント助言の視点】
        ・減塩：お酢、レモン、スパイスを活用して満足度を下げずに塩分カット。
        ・カサ増し：キノコ、豆腐、こんにゃく等でボリュームアップと節約。
        ・ヘルシー：食材の置き換えや油を控えるコツ。
        ・家事ラク：レンジ調理や洗い物を減らす工夫。

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
