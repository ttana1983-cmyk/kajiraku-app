import os
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from google import genai

app = Flask(__name__)

# 環境変数
conf = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    
    # 1. 署名検証だけ先に行う
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    # 2. ここが重要：何はともあれ「200 OK」を先にLINEに返してタイムアウトを防ぐ
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    msg = event.message.text
    tk = event.reply_token

    try:
        # AIの処理（ここが少し遅くても、上のcallbackが先にOKを返しているので大丈夫）
        response = client.models.generate_content(
            model="gemini-2.0-flash", 
            contents=f"食材「{msg}」の献立とURLを1つ教えて"
        )
        
        with ApiClient(conf) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=tk,
                    messages=[TextMessage(text=response.text)]
                )
            )
    except Exception as e:
        # エラーが起きた時だけLINEに通知
        with ApiClient(conf) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=tk,
                    messages=[TextMessage(text=f"エラー: {str(e)[:50]}")]
                )
            )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
