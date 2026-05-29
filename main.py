import os
import sys
from flask import Flask, request, abort
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

# --- Webhookの入り口 ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['x-line-signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- メッセージを受け取った時の処理 ---
@handler.add(MessageEvent, content_type=TextMessageContent)
def handle_message(event):
    text = event.message.text
    tk = event.reply_token

    # 「今日のレシピ提案」ボタンなどが押された時の判定
    if "レシピ" in text or "献立" in text:
        handle_recipe_induction(event, tk)
    else:
        # その他のメッセージへの返信
        send_reply(tk, "コンシェルジュです。左下のメニューからレシピの提案ができますよ！")

# --- LIFFへの誘導ロジック (ここがキモ！) ---
def handle_recipe_induction(event, tk):
    """
    ユーザーをLIFFへ誘導する。
    リプライを即座に完了させることで、400エラーを防ぎ、メッセージ数を節約する。
    """
    # 店長のLIFF URL
    base_url = "https://liff.line.me/2010225388-rXh2LiOR"
    
    # ユーザーが入力した言葉をパラメータとして渡す（LIFF側で解析するため）
    # 空白や特殊文字を考慮して本当はURLエンコードが必要ですが、まずはシンプルに。
    target_url = f"{base_url}?query={event.message.text}"

    message_text = (
        "ありがとうございます！コンシェルジュが今の気分にぴったりの献立を検討中です。\n\n"
        "準備が整い次第、以下のページでレシピを表示します。足りない食材のチェックもこちらからどうぞ！"
    )

    # クイックリプライにLIFFを開くアクションを設定
    quick_reply = QuickReply(items=[
        QuickReplyItem(
            action=URIAction(label="🍳 レシピを確認する", uri=target_url)
        )
    ])

    send_reply(tk, message_text, quick_reply=quick_reply)

# --- 返信用共通関数 ---
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
