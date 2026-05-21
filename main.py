import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, 
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

@app.route("/callback", method=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text
    user_id = event.source.user_id

    # 1. 【初回ヒアリング】男性の人数
    if user_message in ["0人", "1人", "2人", "3人以上"]:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="ありがとうございます！次は【女性の人数】を教えてください✨",
            quick_reply=create_qr(["0人", "1人", "2人", "3人以上"])
        ))
        return

    # 2. 【リピート：タイミング選択】
    elif user_message in ["☀️朝ごはん", "🍱お昼ご飯", "🌙晩ご飯"]:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="料理のジャンルは何がよろしいですか？😊",
            quick_reply=create_qr(["和食", "中華", "洋食", "イタリアン", "お任せ", "甘いもの"])
        ))
        return

    # 3. 【リピート：ジャンル選択】
    elif user_message in ["和食", "中華", "洋食", "イタリアン", "お任せ", "甘いもの"]:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="今の気分はどれに近いですか？🍳",
            quick_reply=create_qr(["🥗ヘルシー", "🧀コッテリ", "🍖ガッツリ", "🍵あっさり"])
        ))
        return

    # 4. 【最終ステップ：気分選択】→ ここでAI起動！
    elif user_message in ["🥗ヘルシー", "🧀コッテリ", "🍖ガッツリ", "🍵あっさり"]:
        # ローディングアニメーション（50秒稼ぐ）
        try:
            line_bot_api.show_loading_animation(ShowLoadingAnimationRequest(chat_id=user_id, loading_seconds=60))
        except: pass
        
        # 応援メッセージを即レス（これで安心感を与える）
        line_bot_api.push_message(user_id, TextSendMessage(text=f"【{user_message}】ですね！了解です！\nTakashiが最高のレシピを今から50秒で考えます。少しだけお待ちくださいね🍳"))

        # AIへの蓄積プロンプト
        prompt = f"""
        あなたは『家事ラクAIコンシェルジュ』の「Takashi」です。
        元ラーメン店店長の経験を活かし、時短・節約・プロの知恵を伝えてください。

        【ユーザーの希望】: {user_message} を中心としたメニュー

        【ルール】
        ・2〜3行ごとに「空行」を入れ、めちゃくちゃ見やすくすること。
        ・レシピ名とCookpadのURL（https://cookpad.com/search/料理名）をセットで出す。
        ・最後に「Takashiの1ポイント助言」として、減塩・カサ増し・家事ラクのいずれかのプロ技を添えること。

        まずは「お疲れ様です✨」と共感から始めてください。
        """
        
        response = model.generate_content(prompt)
        line_bot_api.push_message(user_id, TextSendMessage(text=response.text))
        return

    # それ以外の自由入力
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="「献立を考えて」や、メニューのボタンを押してみてくださいね😊"))

if __name__ == "__main__":
    app.run()
