import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, FollowEvent,
    QuickReply, QuickReplyButton, MessageAction, 
    ShowLoadingAnimationRequest
)
import google.generativeai as genai

app = Flask(__name__)

# --- 環境設定 ---
line_bot_api = LineBotApi(os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
model = genai.GenerativeModel("models/gemini-2.0-flash")

# --- 便利関数：ボタン（クイックリプライ）作成 ---
def create_qr(options):
    return QuickReply(items=[QuickReplyButton(action=MessageAction(label=opt, text=opt)) for opt in options])

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 友だち追加された時の最初の質問 ---
@handler.add(FollowEvent)
def handle_follow(event):
    line_bot_api.reply_message(event.reply_token, TextSendMessage(
        text="友だち追加ありがとうございます！Takashiです😊\n献立作りのサポートのため、まずは【男性の人数】を教えてください👇",
        quick_reply=create_qr(["男性0人", "男性1人", "男性2人", "男性3人以上"])
    ))

# --- メッセージを受け取った時の処理（しりとりロジック） ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text
    user_id = event.source.user_id

    # 1. 男性の回答が来たら → 女性を聞く
    if "男性" in user_message:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="ありがとうございます！次は【女性の人数】を教えてください✨",
            quick_reply=create_qr(["女性0人", "女性1人", "女性2人", "女性3人以上"])
        ))
        return

    # 2. 女性の回答が来たら → お子さんを聞く
    elif "女性" in user_message:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="お子さん（中学生以下）はいらっしゃいますか？👶",
            quick_reply=create_qr(["いない", "乳幼児", "幼児", "小学生", "中学生"])
        ))
        return

    # 3. お子さんの回答が来たら → ご年配を聞く
    elif user_message in ["いない", "乳幼児", "幼児", "小学生", "中学生"]:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="最後にご年配の方（65歳以上）はいらっしゃいますか？👵",
            quick_reply=create_qr(["ご年配あり", "ご年配なし"])
        ))
        return

    # 4. ご年配の回答（初回登録完了） → 最初の献立を出す（ここでAI起動！）
    elif "ご年配" in user_message:
        line_bot_api.show_loading_animation(ShowLoadingAnimationRequest(chat_id=user_id, loading_seconds=60))
        line_bot_api.push_message(user_id, TextSendMessage(text="情報をありがとうございます！バッチリ把握しました😊\n今から50秒ほどで、最初のおすすめ献立を考えますね！"))
        
        prompt = f"家族構成（{user_message}）に合わせた、Takashi流の丁寧な最初のおすすめ献立を1つ提案してください。" # 詳細は省略
        response = model.generate_content(prompt)
        line_bot_api.push_message(user_id, TextSendMessage(text=response.text))
        return

    # --- 2回目以降のメニュー選び ---
    elif user_message in ["☀️朝ごはん", "🍱お昼ご飯", "🌙晩ご飯"]:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="料理のジャンルは何がよろしいですか？😊",
            quick_reply=create_qr(["和食", "中華", "洋食", "イタリアン", "お任せ", "甘いもの"])
        ))
        return

    elif user_message in ["和食", "中華", "洋食", "イタリアン", "お任せ", "甘いもの"]:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="今の気分はどれに近いですか？🍳",
            quick_reply=create_qr(["🥗ヘルシー", "🧀コッテリ", "🍖ガッツリ", "🍵あっさり"])
        ))
        return

    # 最後の「気分」が選ばれたらAI起動
    elif user_message in ["🥗ヘルシー", "🧀コッテリ", "🍖ガッツリ", "🍵あっさり"]:
        line_bot_api.show_loading_animation(ShowLoadingAnimationRequest(chat_id=user_id, loading_seconds=60))
        prompt = f"条件：{user_message}。これまでの蓄積プロンプトに従い、レシピとプロの助言を出してください。"
        response = model.generate_content(prompt)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response.text))
        return

if __name__ == "__main__":
    app.run()
