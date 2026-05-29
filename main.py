import os
import sys
import json
import google.genai as genai # 変更点1: 新しいパッケージをインポート
from flask import Flask, request, abort, render_template, jsonify
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest,
    TextMessage, QuickReply, QuickReplyItem, URIAction
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

app = Flask(__name__)

# --- 環境設定 ---
channel_secret = os.getenv('LINE_CHANNEL_SECRET')
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
gemini_api_key = os.getenv('GEMINI_API_KEY')

# 変更点2: 新しいSDKでの初期化
client = genai.Client(api_key=gemini_api_key)
model_id = 'gemini-1.5-flash'

configuration = Configuration(access_token=channel_access_token)
handler = WebhookHandler(channel_secret)

# --- 1. LIFF表示用 ---
@app.route("/")
def index():
    return render_template("index.html")

# --- 2. AIレシピ生成 (新しいSDKへ対応) ---
@app.route("/api/generate-recipe")
def generate_recipe():
    query = request.args.get('query', 'おまかせ')
    
    # 徹底したJSON形式での指示
    prompt = f"""
    あなたは家事の負担を減らす「カジラク・コンシェルジュ」です。
    ユーザーの要望: 「{query}」
    
    以下の条件でレシピを1つ提案してください：
    1. 15分以内で作れる時短レシピ。
    2. 安価な食材を使った節約レシピ。
    3. 初心者でも迷わない簡潔な工程。

    回答は必ず以下のJSON形式のみとし、他の文章は一切含めないでください。
    {{
      "name": "料理名",
      "time": "〇分",
      "cost": "約〇円",
      "main": "主な食材",
      "tip": "プロの時短コツを一言",
      "ingredients": [
        {{"name": "食材1", "amount": "分量"}},
        {{"name": "食材2", "amount": "分量"}}
      ],
      "steps": [
        "1. 〇〇をカットする",
        "2. 〇〇を炒める",
        "3. 味付けして完成"
      ]
    }}
    """

    try:
        # 変更点3: 新しいSDKでの生成処理
        response = client.models.generate_content(
            model=model_id,
            contents=prompt
        )
        
        # AIの回答からJSONを抽出
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        return jsonify(json.loads(clean_text))
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return jsonify({
            "name": "申し訳ありません", "time": "-", "cost": "-", "main": "-", "tip": "再試行してください",
            "ingredients": [{"name": "エラー", "amount": "-"}],
            "steps": ["レシピの生成に失敗しました。もう一度お試しください。"]
        })

# --- 3. 買い物リスト保存用API ---
@app.route("/api/add-to-cart", methods=['POST'])
def add_to_cart():
    data = request.get_json()
    items = data.get('items', [])
    print(f"買い物リストに追加: {items}")
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
        send_reply(tk, "コンシェルジュです。左下のメニューからレシピ提案をどうぞ！")

# --- 6. LIFFへの誘導ロジック ---
def handle_recipe_induction(event, tk):
    base_url = "https://liff.line.me/2010225388-rXh2LiOR"
    target_url = f"{base_url}?query={event.message.text}"
    msg = "コンシェルジュが献立を検討中です。\n準備ができたら、下のボタンから確認してくださいね。"
    quick_reply = QuickReply(items=[
        QuickReplyItem(action=URIAction(label="🍳 レシピを確認する", uri=target_url))
    ])
    send_reply(tk, msg, quick_reply=quick_reply)

# --- 7. 返信用共通関数 ---
def send_reply(tk, text, quick_reply=None):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(ReplyMessageRequest(
            reply_token=tk,
            messages=[TextMessage(text=text, quick_reply=quick_reply)]
        ))

if __name__ == "__main__":
    # 本番環境（Render）ではFlaskの開発サーバーではなく、Gunicornなどを使うことが推奨されますが、
    # 警告を解消するためにデバッグモードを明示的にOFFにします。
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
