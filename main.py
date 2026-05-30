import os, json, google.genai as genai
from flask import Flask, request, abort, render_template, jsonify
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest,
    TextMessage, QuickReply, QuickReplyItem, MessageAction, URIAction
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

app = Flask(__name__)

# 環境設定
conf = Configuration(access_token=os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/callback", methods=['POST'])
def callback():
    sig = request.headers.get('x-line-signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, sig)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    txt = event.message.text
    tk = event.reply_token

    # 1. 時間帯の選択
    if txt in ["メニュー提案", "献立", "スタート"]:
        send(tk, "カジラク・コンシェルジュです🍳\\nいつのご飯を作りましょうか？", ["朝ごはん", "昼ごはん", "夜ごはん"])

    # 2. ジャンルの選択
    elif txt in ["朝ごはん", "昼ごはん", "夜ごはん"]:
        send(tk, f"{txt}ですね！ジャンルはどうしますか？", 
             [f"{txt}/和風", f"{txt}/洋風", f"{txt}/中華", f"{txt}/お任せ"])

    # 3. 食材のヒアリング
    elif "/" in text:
        send(tk, f"【{txt}】で承りました。\\n優先的に使いたい食材を入力してください。\\n（例：鶏肉、キャベツ、特になし）", None)

    # 4. 最終誘導（LIFFへ）
    else:
        liff_url = f"https://liff.line.me/2010225388-rXh2LiOR?query={txt}"
        qr = QuickReply(items=[QuickReplyItem(action=URIAction(label="🍳 レシピを表示", uri=liff_url))])
        send(tk, f"「{txt}」を優先したレシピを考えました！\\n下のボタンから確認して、画像を保存してくださいね。", None, qr)

def send(tk, msg, opts, qr=None):
    if opts:
        items = [QuickReplyItem(action=MessageAction(label=o.split('/')[-1], text=o)) for o in opts]
        qr = QuickReply(items=items)
    with ApiClient(conf) as api:
        line_api = MessagingApi(api)
        line_api.reply_message(ReplyMessageRequest(
            reply_token=tk,
            messages=[TextMessage(text=msg, quick_reply=qr)]
        ))

# --- レシピ生成API（Gemini 3.5 Flash 呼び出し） ---
@app.route("/api/generate-recipe")
def generate():
    query = request.args.get('query', 'おまかせ')
    
    # ユーザー要望に基づいたプロンプト
    prompt = f"""
    あなたは優秀な家事のコンシェルジュです。
    要望: {query}。
    15分以内で作れる節約レシピを提案してください。
    回答は必ず以下のJSON形式のみとし、他は一切含めないでください。
    {{
      "name": "料理名", 
      "time": "〇分", 
      "cost": "約〇円", 
      "tip": "コンシェルジュからのコツ",
      "ingredients": [{{"name": "食材名", "amount": "分量"}}],
      "steps": ["手順1", "手順2", "手順3"]
    }}
    """
    
    try:
        # モデルを gemini-3.5-flash に修正
        response = client.models.generate_content(
            model='gemini-3.5-flash', 
            contents=prompt
        )
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        return jsonify(json.loads(clean_json))
    except Exception as e:
        print(f"AI Error: {e}")
        return jsonify({
            "name": "申し訳ありません", 
            "time": "-", "cost": "-", "tip": "現在混み合っております。",
            "ingredients": [{"name": "再試行してください", "amount": "-"}], 
            "steps": ["もう一度お試しいただけますか？"]
        })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
