import os
import traceback
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage, QuickReply, QuickReplyItem, PostbackAction
from linebot.v3.webhooks import MessageEvent, TextMessageContent, PostbackEvent
import google.generativeai as genai

app = Flask(__name__)

# --- 設定 ---
conf = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-3.5-flash')

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 1. メッセージ受付（「メニュー」や「最初から」への対応） ---
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    msg = event.message.text
    tk = event.reply_token

    # 【重要】もし「メニュー」や最初の挨拶、あるいは特定のキーワードが来たらボタンを出す
    if msg in ["メニュー", "最初から", "スタート", "献立"]:
        show_time_selection(tk)
    else:
        # それ以外は「冷蔵庫の食材」としてAIに投げる
        handle_ai_generation(tk, msg)

def show_time_selection(tk):
    quick_reply = QuickReply(items=[
        QuickReplyItem(action=PostbackAction(label="朝ごはん", data="step=mood&time=朝", display_text="朝ごはん")),
        QuickReplyItem(action=PostbackAction(label="昼ごはん", data="step=mood&time=昼", display_text="昼ごはん")),
        QuickReplyItem(action=PostbackAction(label="夜ごはん", data="step=mood&time=夜", display_text="夜ごはん"))
    ])
    with ApiClient(conf) as api_client:
        line_api = MessagingApi(api_client)
        line_api.reply_message(ReplyMessageRequest(
            reply_token=tk,
            messages=[TextMessage(text="いつのごはんにしますか？", quick_reply=quick_reply)]
        ))

# --- 2. ボタン操作（気分・冷蔵庫確認） ---
@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    tk = event.reply_token
    params = dict(item.split('=') for item in data.split('&'))
    step = params.get('step')

    try:
        if step == "mood":
            moods = ["ヘルシー", "コッテリ", "ガッツリ", "さっぱり", "時短", "和食", "中華", "洋食", "お菓子", "お任せ"]
            items = [QuickReplyItem(action=PostbackAction(label=m, data=f"step=ask_fridge&{data}&mood={m}", display_text=m)) for m in moods]
            with ApiClient(conf) as api_client:
                line_api = MessagingApi(api_client)
                line_api.reply_message(ReplyMessageRequest(
                    reply_token=tk,
                    messages=[TextMessage(text="今の気分は？", quick_reply=QuickReply(items=items))]
                ))
        elif step == "ask_fridge":
            with ApiClient(conf) as api_client:
                line_api = MessagingApi(api_client)
                line_api.reply_message(ReplyMessageRequest(
                    reply_token=tk,
                    messages=[TextMessage(text=f"【{params.get('time')}/{params.get('mood')}】ですね！\n\n冷蔵庫にある食材を教えてください。")]
                ))
    except Exception as e:
        send_error_to_line(tk, e)

# --- 3. AI生成ロジック ---
def handle_ai_generation(tk, msg):
    try:
        prompt = f"以下の食材で、実在するレシピを検索して提案して。URLも必ず1つ載せて。食材: {msg}"
        response = model.generate_content(
            prompt,
            safety_settings=[{"category": c, "threshold": "BLOCK_NONE"} for c in ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
        )
        with ApiClient(conf) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(ReplyMessageRequest(reply_token=tk, messages=[TextMessage(text=response.text)]))
    except Exception as e:
        send_error_to_line(tk, e)

def send_error_to_line(tk, e):
    error_msg = f"⚠️詳細エラー:\n{str(e)[:200]}"
    with ApiClient(conf) as api_client:
        line_api = MessagingApi(api_client)
        line_api.reply_message(ReplyMessageRequest(reply_token=tk, messages=[TextMessage(text=error_msg)]))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
