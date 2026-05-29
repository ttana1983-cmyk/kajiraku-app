import os
import sys
from flask import Flask, request, abort, render_template, jsonify
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    QuickReply,
    QuickReplyItem,
    URIAction
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

app = Flask(__name__)

# --- 環境設定 (Renderの環境変数から取得) ---
channel_secret = os.getenv('LINE_CHANNEL_SECRET')
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')

if channel_secret is None or channel_access_token is None:
    print('Specify LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN as environment variables.')
    sys.exit(1)

configuration = Configuration(access_token=channel_access_token)
handler = WebhookHandler(channel_secret)

# --- 1. LIFFページ（トップ画面）を表示する設定 ---
@app.route("/")
def index():
    # templatesフォルダの中のindex.htmlを表示します
    return render_template("index.html")

# --- 2. レシピ生成API（LIFFから呼ばれる処理） ---
@app.route("/api/generate-recipe")
def generate_recipe():
    query = request.args.get('query', '')
    
    # 本来はここでAI（Gemini等）を動かしますが、まずはテスト用にデータを返します
    # 店長、ここを後ほどAI連携に書き換えましょう！
    recipe_data = {
        "name": f"{query}で作る！コンシェルジュ特製メニュー",
        "time": "15分",
        "cost": "約250円",
        "main": "メイン食材",
        "tip": "強火でサッと！",
        "ingredients": [
            {"name": "メイン食材", "amount": "200g"},
            {"name": "付け合わせ野菜", "amount": "1/2個"},
            {"name": "調味料セット", "amount": "少々"}
        ],
        "steps": [
            "1. 食材を一口大に切り、下味をつけます。",
            "2. フライパンを熱し、焼き色がつくまで炒めます。",
            "3. 最後に調味料を絡めて完成です！"
        ]
    }
    return jsonify(recipe_data)

# --- 3. 買い物リスト保存API ---
@app.route("/api/add-to-cart", methods=['POST'])
def add_to_cart():
    data = request.get_json()
    items = data.get('items', [])
    print(f"買い物リストに追加: {items}")
    # ここでスプレッドシート等に保存する処理を入れます
    return jsonify({"status": "success"})

# --- 4. LINE Webhookの入り口 ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['x-line-signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 5. LINEメッセージを受け取った時の処理 ---
@handler.add(MessageEvent, content_type=TextMessageContent)
def handle_message(event):
    text = event.message.text
    tk = event.reply_token

    if "レシピ" in text or "献立" in text:
        handle_recipe_induction(event, tk)
    else:
        send_reply(tk, "コンシェルジュです。左下のメニューからレシピの提案ができますよ！")

# --- 6. LIFFへの誘導ロジック ---
def handle_recipe_induction(event, tk):
    base_url = "https://liff.line.me/2010225388-rXh2LiOR"
    # ユーザーが送ったテキストをそのままパラメータにしてLIFFへ送る
    target_url = f"{base_url}?query={event.message.text}"

    message_text = (
        "ありがとうございます！今の気分にぴったりの献立を検討中です。\n\n"
        "準備が整い次第、以下のページでレシピを表示します。足りない食材のチェックもこちらからどうぞ！"
    )

    quick_reply = QuickReply(items=[
        QuickReplyItem(
            action=URIAction(label="🍳 レシピを確認する", uri=target_url)
        )
    ])
    send_reply(tk, message_text, quick_reply=quick_reply)

# --- 7. 返信用共通関数 ---
def send_reply(tk, text, quick_reply=None):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=tk,
                messages=[TextMessage(text=text, quick_reply=quick_reply)]
            )
        )

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
