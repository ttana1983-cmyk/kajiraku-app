import os
import traceback  # エラー詳細表示用
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

# Geminiクライアント
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    msg = event.message.text
    tk = event.reply_token

    try:
        # AIの処理
        response = client.models.generate_content(
            model="models/gemini-1.5-flash",  # ここに models/ を追加
            contents=f"食材「{msg}」の献立とURLを1つ教えて"
        )

        
        # あらゆる角度からテキストを絞り出す書き方
        try:
            ai_text = response.text
        except:
            # textで取れない場合、構造を分解して直接取りに行く
            ai_text = response.candidates[0].content.parts[0].text
        
        # それでも空なら警告を出す
        if not ai_text:
            raise ValueError("Geminiからの返答が空でした")


        with ApiClient(conf) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=tk,
                    messages=[TextMessage(text=ai_text)]
                )
            )
            
    except Exception:
        # ログにエラーの全容を強制的に表示させる
        print("--- !!! ERROR START !!! ---")
        print(traceback.format_exc())
        print("--- !!! ERROR END !!! ---")
        
        with ApiClient(conf) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=tk,
                    messages=[TextMessage(text="システム内でエラーが起きました。ログを確認してください。")]
                )
            )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
