import os, json, threading, requests, google.genai as genai
from flask import Flask, request, abort, render_template, jsonify
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest,
    TextMessage, QuickReply, QuickReplyItem, MessageAction, URIAction
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

# --- 🚀 修正ポイント：物理パスを絶対に見失わない設定 ---
# 実行ファイル(main.py)がある場所を「基準点」として固定します
base_dir = os.path.dirname(os.path.abspath(__file__))
# templatesフォルダの場所を「絶対パス」で指定します
template_dir = os.path.join(base_dir, 'templates')

app = Flask(__name__, template_folder=template_dir)

# 環境設定（RenderのEnvironment Variablesから取得）
conf = Configuration(access_token=os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

# Renderのスリープ対策
def wake_up_render():
    try:
        # 自分のURLを叩いて起こし続ける
        requests.get(f"https://{request.host}/", timeout=1)
    except:
        pass

@app.route("/")
def index():
    # 物理パスを指定して直接ファイルを読み込み、render_templateのバグを回避します
    try:
        return render_template("index.html")
    except:
        # 万が一失敗した時の予備（力技読み込み）
        path = os.path.join(template_dir, "index.html")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

@app.route("/callback", methods=['POST'])
def callback():
    sig = request.headers.get('x-line-signature')
    body = request.get_data(as_text=True)
    threading.Thread(target=wake_up_render).start()
    try:
        handler.handle(body, sig)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    txt = event.message.text
    tk = event.reply_token

    if txt == "今日のレシピ提案":
        send_quick(tk, "カジラク・コンシェルジュです🍳\nいつのご飯を考えましょうか？", ["朝ごはん", "昼ごはん", "夜ごはん"])
    elif txt in ["朝ごはん", "昼ごはん", "夜ごはん"]:
        send_quick(tk, f"{txt}ですね！ジャンルはどうしますか？", 
                   [f"{txt}/和風", f"{txt}/洋風", f"{txt}/中華", f"{txt}/お任せ"])
    elif "/" in txt and "優先" not in txt:
        msg = f"【{txt}】で承りました。\n優先的に使いたい食材を入力してください。\n（例：鶏肉、キャベツ、特になし）"
        send_reply(tk, msg)
    else:
        # 最終誘導（LIFFへ）
        liff_url = f"https://liff.line.me/2010225388-rXh2LiOR?query={txt}"
        qr = QuickReply(items=[QuickReplyItem(action=URIAction(label="🍳 レシピを表示", uri=liff_url))])
        msg = f"「{txt}」を優先したレシピを考えました！\n下のボタンから確認して、画像を保存してくださいね。"
        send_reply(tk, msg, qr)

def send_quick(tk, msg, opts):
    items = [QuickReplyItem(action=MessageAction(label=o.split('/')[-1], text=o)) for o in opts]
    send_reply(tk, msg, QuickReply(items=items))

def send_reply(tk, msg, qr=None):
    with ApiClient(conf) as api_client:
        line_api = MessagingApi(api_client)
        line_api.reply_message(ReplyMessageRequest(
            reply_token=tk,
            messages=[TextMessage(text=msg, quick_reply=qr)]
        ))

# --- レシピ生成API（Gemini 3.5 Flash） ---
@app.route("/api/generate-recipe")
def generate():
    query = request.args.get('query', 'おまかせ')
    # AIへの指示
    p = f"要望:{query}。15分節約レシピをJSON形式で。{{'name':'','time':'','cost':'','tip':'','ingredients':[{{'name':'','amount':''}}],'steps':[]}}"
    try:
        # 3.5-flash を指定
        res = client.models.generate_content(model='gemini-1.5-flash', contents=p) # 3.5-flashがエラーなら1.5-flashが確実です
        clean = res.text.replace('```json', '').replace('```', '').strip()
        return jsonify(json.loads(clean))
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"name": "準備中...", "steps": ["もう一度お試しください"]})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
