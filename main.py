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

# --- 1. メッセージ受付（「メニュー」への反応） ---
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    msg = event.message.text
    tk = event.reply_token

    if msg in ["メニュー", "最初から", "スタート", "献立"]:
        show_time_selection(tk)
    else:
        # 自由入力は食材としてAIへ
        handle_ai_generation(tk, msg)

# 時間選択（朝・昼・夜）を表示
def show_time_selection(tk):
    quick_reply = QuickReply(items=[
        QuickReplyItem(action=PostbackAction(label="朝ごはん", data="step=mood&time=朝", display_text="朝ごはん")),
        QuickReplyItem(action=PostbackAction(label="昼ごはん", data="step=mood&time=昼", display_text="昼ごはん")),
        QuickReplyItem(action=PostbackAction(label="夜ごはん", data="step=mood&time=夜", display_text="夜ごはん"))
    ])
    send_reply(tk, "いつのごはんにしますか？", quick_reply)

# --- 2. ボタン操作（ここがループの原因でした。修正済み！） ---
@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    tk = event.reply_token
    # データを解析
    params = dict(item.split('=') for item in data.split('&'))
    step = params.get('step')

    try:
        if step == "mood":
            # 気分・ジャンル選択
            moods = ["ヘルシー", "コッテリ", "ガッツリ", "さっぱり", "時短", "和食", "中華", "洋食", "お菓子", "お任せ"]
            items = [QuickReplyItem(action=PostbackAction(label=m, data=f"step=ask_fridge&time={params.get('time')}&mood={m}", display_text=m)) for m in moods]
            
            # 再設定と戻るボタンを追加
            items.append(QuickReplyItem(action=PostbackAction(label="最初から（再設定）", data="step=restart", display_text="最初からやり直す")))
            
            send_reply(tk, "今の気分は？", QuickReply(items=items))

        elif step == "ask_fridge":
            # 冷蔵庫の確認（戻るボタン付き）
            items = [QuickReplyItem(action=PostbackAction(label="戻る", data=f"step=mood&time={params.get('time')}", display_text="気分を選び直す"))]
            send_reply(tk, f"【{params.get('time')}/{params.get('mood')}】ですね！\n\n冷蔵庫の食材は何がありますか？\n(例：鶏肉、卵、しなびた小松菜)", QuickReply(items=items))

        elif step == "restart":
            show_time_selection(tk)

    except Exception as e:
        send_error_to_line(tk, e)

# --- 共通返信関数 ---
def send_reply(tk, text, quick_reply=None):
    with ApiClient(conf) as api_client:
        line_api = MessagingApi(api_client)
        line_api.reply_message(ReplyMessageRequest(
            reply_token=tk,
            messages=[TextMessage(text=text, quick_reply=quick_reply)]
        ))

# --- 3. AI生成 ---
def handle_ai_generation(tk, msg):
    try:
        prompt = f"プロの料理研究家として提案してください。食材「{msg}」を使い、実在するレシピを検索して1つ教えて。必ず有効なURLを載せて。家事を楽にするコツも添えて。"
        response = model.generate_content(
            prompt,
            safety_settings=[{"category": c, "threshold": "BLOCK_NONE"} for c in ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
        )
        send_reply(tk, response.text)
    except Exception as e:
        send_error_to_line(tk, e)

def send_error_to_line(tk, e):
    error_msg = f"⚠️詳細エラー:\n{str(e)[:200]}"
    send_reply(tk, error_msg)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
