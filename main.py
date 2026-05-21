import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, FollowEvent,
    QuickReply, QuickReplyButton, MessageAction, ImageSendMessage
)

# インポートエラー対策
try:
    from linebot.models.responses import ShowLoadingAnimationRequest
except ImportError:
    try:
        from linebot.models import ShowLoadingAnimationRequest
    except ImportError:
        ShowLoadingAnimationRequest = None

import google.generativeai as genai

app = Flask(__name__)

# --- 環境設定 ---
line_bot_api = LineBotApi(os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("models/gemini-2.0-flash")

# --- 演出用GIF ---
# Japandiな雰囲気に合う、シンプルな調理GIF（サンプル）
GIF_URL = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExNHJid3R3bmZyZzR4bmZ4bmZ4bmZ4bmZ4bmZ4bmZ4bmZ4bmZ4JmVwPXYxX2ludGVybmFsX2dpZl9ieV9pZCZjdD1n/l0HlUUxwYvSJy05JS/giphy.gif"

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
    line_bot_api.reply_message(event.reply_token, TextSendMessage(
        text="友だち追加ありがとうございます！Takashiです😊\n献立作りのサポートのため、まずは【男性の人数】を教えてください👇",
        quick_reply=create_qr(["男性0人", "男性1人", "男性2人", "男性3人以上"])
    ))

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text
    user_id = event.source.user_id

    # 1. 基本メニュー
    if user_message in ["メニュー", "最初から", "戻る", "↩️戻る"]:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="こんにちは！今からどんなご飯にしますか？😊",
            quick_reply=create_qr(["☀️朝ごはん", "🍱お昼ご飯", "🌙晩ご飯", "⚙️再設定"])
        ))
        return

    # 2. 家族構成ヒアリング
    if "男性" in user_message:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="ありがとうございます！次は【女性の人数】を教えてください✨",
            quick_reply=create_qr(["女性0人", "女性1人", "女性2人", "女性3人以上"])
        ))
        return
    elif "女性" in user_message:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="お子さん（中学生以下）はいらっしゃいますか？👶",
            quick_reply=create_qr(["いない", "乳幼児", "幼児", "小学生", "中学生"])
        ))
        return
    elif user_message in ["いない", "乳幼児", "幼児", "小学生", "中学生"]:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="最後にご年配の方（65歳以上）はいらっしゃいますか？👵",
            quick_reply=create_qr(["ご年配あり", "ご年配なし"])
        ))
        return
    elif "ご年配" in user_message:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="登録完了！😊\nさっそく、今はどのタイミングのご飯ですか？👇",
            quick_reply=create_qr(["☀️朝ごはん", "🍱お昼ご飯", "🌙晩ご飯"])
        ))
        return

    # 3. タイミング ➔ ジャンル
    elif user_message in ["☀️朝ごはん", "🍱お昼ご飯", "🌙晩ご飯"]:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="ジャンルはどうしますか？🇯🇵🇨🇳🇫🇷",
            quick_reply=create_qr(["和食", "洋食", "中華", "イタリアン", "お任せ"])
        ))
        return

    # 4. ジャンル ➔ 気分
    elif user_message in ["和食", "洋食", "中華", "イタリアン", "お任せ"]:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="今の気分に近いのは？🍳",
            quick_reply=create_qr(["🥗ヘルシー", "🧀コッテリ", "🍖ガッツリ", "🍵あっさり"])
        ))
        return

    # 5. 気分 ➔ 冷蔵庫ヒアリング
    elif user_message in ["🥗ヘルシー", "🧀コッテリ", "🍖ガッツリ", "🍵あっさり"]:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text=f"【{user_message}】ですね！了解です👍\n最後に、冷蔵庫の「使いたい食材」を教えてください。（例：鶏肉、玉ねぎ、豆腐）"
        ))
        return

    # 6. 再設定
    elif user_message == "⚙️再設定":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="家族構成を再登録します。まずは【男性の人数】を教えてください👇",
            quick_reply=create_qr(["男性0人", "男性1人", "男性2人", "男性3人以上"])
        ))
        return

    # 7. 最終ステップ：自由入力（食材） ➔ AI生成
    else:
        # アニメーション開始
        if ShowLoadingAnimationRequest:
            try:
                line_bot_api.show_loading_animation(ShowLoadingAnimationRequest(chat_id=user_id, loading_seconds=60))
            except: pass
        
        # 調理GIFを送信
        try:
            line_bot_api.push_message(user_id, ImageSendMessage(original_content_url=GIF_URL, preview_image_url=GIF_URL))
        except: pass

        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="オーダー入りました！👨‍🍳\nただいまレンジで加熱中です。完成まで1分ほどお待ちください..."
        ))
        
        # AI生成
        prompt = f"家族構成と食材（{user_message}）に合わせ、元ラーメン店長の視点で、300文字以内の簡潔なレシピとプロのコツを提案してください。"
        response = model.generate_content(prompt)

        # チン！の通知演出
        line_bot_api.push_message(user_id, TextSendMessage(text="🔔 ピーッ！ピーッ！ ＼ チン！ ／"))
        
        # レシピ表示
        line_bot_api.push_message(user_id, TextSendMessage(text=f"お待たせしました！本日の特製メニューです✨\n\n{response.text}"))
        return

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
