import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, FollowEvent,
    QuickReply, QuickReplyButton, MessageAction, ImageSendMessage
)
import google.generativeai as genai

# アニメーション機能の読み込み
try:
    from linebot.models.responses import ShowLoadingAnimationRequest
except:
    ShowLoadingAnimationRequest = None

app = Flask(__name__)

# --- 設定 ---
line_bot_api = LineBotApi(os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# Takashiさんの環境で動作実績のある「2.5」を固定
model = genai.GenerativeModel("gemini-2.5-flash")

# ねこシェフGIF（確実に表示されるようプレビューも共通化）
GIF_URL = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExOHR0ZnIydmZ6ZnB6YmZ6ZnB6YmZ6ZnB6YmZ6ZnB6YmZ6ZnB6JmVwPXYxX2ludGVybmFsX2dpZl9ieV9pZCZjdD1n/C21GGDOpKT6Z4CX9oY/giphy.gif"

def create_qr(options):
    return QuickReply(items=[QuickReplyButton(action=MessageAction(label=opt, text=opt)) for opt in options])

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(FollowEvent)
def handle_follow(event):
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="友だち追加ありがとうございます！Takashiです😊\nまずは【男性の人数】を教えてください👇", quick_reply=create_qr(["男性0人", "男性1人", "男性2人", "男性3人以上"])))

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    uid = event.source.user_id

    # 進行フロー
    if msg in ["メニュー", "最初から", "戻る", "↩️戻る"]:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="こんにちは！今からどんなご飯にしますか？😊", quick_reply=create_qr(["☀️朝ごはん", "🍱お昼ご飯", "🌙晩ご飯", "⚙️再設定"])))
    elif "男性" in msg:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="次は【女性の人数】を教えてください✨", quick_reply=create_qr(["女性0人", "女性1人", "女性2人", "女性3人以上"])))
    elif "女性" in msg:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="お子さんは？👶", quick_reply=create_qr(["いない", "乳幼児", "幼児", "小学生", "中学生"])))
    elif msg in ["いない", "乳幼児", "幼児", "小学生", "中学生"]:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ご年配の方は？👵", quick_reply=create_qr(["ご年配あり", "ご年配なし"])))
    elif "ご年配" in msg:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="登録完了！😊\nタイミングを選んでください👇", quick_reply=create_qr(["☀️朝ごはん", "🍱お昼ご飯", "🌙晩ご飯"])))
    elif msg in ["☀️朝ごはん", "🍱お昼ご飯", "🌙晩ご飯"]:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ジャンルは？🇯🇵🇨🇳", quick_reply=create_qr(["和食", "洋食", "中華", "イタリアン", "お任せ"]) ))
    elif msg in ["和食", "洋食", "中華", "イタリアン", "お任せ"]:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="今の気分に近いのは？🍳", quick_reply=create_qr(["🥗ヘルシー", "🧀コッテリ", "🍖ガッツリ", "🍵あっさり"])))
    elif msg in ["🥗ヘルシー", "🧀コッテリ", "🍖ガッツリ", "🍵あっさり"]:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"【{msg}】ですね！了解です👍\n最後に、冷蔵庫の「使いたい食材」を入力してください。"))
    elif msg == "⚙️再設定":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="再設定します。まずは【男性の人数】を教えてください👇", quick_reply=create_qr(["男性0人", "男性1人", "男性2人", "男性3人以上"])))
    
    # AI生成部分
    else:
        # 入力中アニメーション（三点リーダー）
        if ShowLoadingAnimationRequest:
            try: line_bot_api.show_loading_animation(ShowLoadingAnimationRequest(chat_id=uid, loading_seconds=30))
            except: pass
        
        # 1. 調理開始テキスト
        line_bot_api.push_message(uid, TextSendMessage(text="オーダー入りました！ねこシェフ調理中...🐾"))

        # 2. ねこシェフGIFの送信
        try:
            line_bot_api.push_message(uid, ImageSendMessage(original_content_url=GIF_URL, preview_image_url=GIF_URL))
        except: pass

        # 3. AIによるレシピ生成
        try:
            prompt = f"元ラーメン店長として、食材({msg})に合う献立を1つ提案してください。レシピとコツを300文字以内で。"
            response = model.generate_content(prompt)
            
            # 4. 「チン！」の通知演出
            line_bot_api.push_message(uid, TextSendMessage(text="🔔 ピーッ！＼ チン！ ／"))
            # 5. レシピ送信
            line_bot_api.push_message(uid, TextSendMessage(text=f"特製メニュー完成です！✨\n\n{response.text}"))
        except Exception as e:
            # エラーの詳細をそのままLINEに出して特定しやすくします
            line_bot_api.push_message(uid, TextSendMessage(text=f"AIエラー発生: {str(e)}"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
