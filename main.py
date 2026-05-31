import os, json, threading, requests, google.genai as genai
from flask import Flask, request, abort, render_template, jsonify
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest,
    TextMessage, QuickReply, QuickReplyItem, MessageAction, URIAction
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

base_dir = os.path.dirname(os.path.abspath(__file__))
template_dir = os.path.join(base_dir, 'templates')
app = Flask(__name__, template_folder=template_dir)

conf = Configuration(access_token=os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

def wake_up_render():
    try: requests.get(f"https://{request.host}/", timeout=1)
    except: pass

@app.route("/")
def index():
    try: return render_template("index.html")
    except:
        path = os.path.join(template_dir, "index.html")
        with open(path, "r", encoding="utf-8") as f: return f.read()

@app.route("/callback", methods=['POST'])
def callback():
    sig = request.headers.get('x-line-signature')
    body = request.get_data(as_text=True)
    threading.Thread(target=wake_up_render).start()
    try: handler.handle(body, sig)
    except InvalidSignatureError: abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    raw_txt = event.message.text.strip()
    tk = event.reply_token

    if "今日のレシピ" in raw_txt:
        send_quick(tk, "カジラク・コンシェルジュです🍳\nいつのご飯を考えましょうか？", ["朝ごはん", "昼ごはん", "夜ごはん"])
    elif raw_txt in ["朝ごはん", "昼ごはん", "夜ごはん"]:
        send_quick(tk, f"{raw_txt}ですね！ジャンルはどうしますか？", 
                   [f"{raw_txt}/和風", f"{raw_txt}/洋風", f"{raw_txt}/中華", f"{raw_txt}/お任せ"])
    elif "/" in raw_txt and any(g in raw_txt for g in ["和風", "洋風", "中華", "お任せ"]):
        clean_text = raw_txt.replace('/', ' ')
        msg = f"【{clean_text}】ですね。承りました。\n\n冷蔵庫の中で優先的に使いたい食材はありますか？\n（例：鶏肉、キャベツ、特になし）"
        send_reply(tk, msg)
    else:
        msg = (
            "入力ありがとうございます。\n"
            "今からコンシェルジュがレシピを考えますので、下のボタンからレシピを受け取ってくださいね。\n\n"
            "買い物リストの画像保存やレシピの画像保存もできますのでご利用ください。"
        )
        encoded_query = requests.utils.quote(raw_txt)
        # 🚀 修正ポイント：直接RenderのURLを指定してSafariを強制起動
        liff_url = f"https://kajiraku-ai.onrender.com/?query={encoded_query}&openExternalBrowser=1"
        
        qr = QuickReply(items=[QuickReplyItem(action=URIAction(label="🍳 レシピを表示", uri=liff_url))])
        send_reply(tk, msg, qr)

def send_quick(tk, msg, opts):
    items = [QuickReplyItem(action=MessageAction(label=o.split('/')[-1], text=o)) for o in opts]
    send_reply(tk, msg, QuickReply(items=items))

def send_reply(tk, msg, qr=None):
    with ApiClient(conf) as api_client:
        line_api = MessagingApi(api_client)
        line_api.reply_message(ReplyMessageRequest(reply_token=tk, messages=[TextMessage(text=msg, quick_reply=qr)]))

@app.route("/api/generate-recipe")
def generate():
    query = request.args.get('query', 'おまかせ')
    p = f"要望:{query}。15分節約レシピをJSON形式で。{{'name':'','time':'','cost':'','tip':'','ingredients':[{{'name':'','amount':''}}],'steps':[]}}"
    try:
        res = client.models.generate_content(model='gemini-3.5-flash', contents=p)
        clean = res.text.replace('```json', '').replace('```', '').strip()
        return jsonify(json.loads(clean))
    except Exception as e:
        try:
            res = client.models.generate_content(model='gemini-1.5-flash', contents=p)
            clean = res.text.replace('```json', '').replace('```', '').strip()
            return jsonify(json.loads(clean))
        except: return jsonify({"name": "エラーが発生しました", "steps": ["もう一度お試しください"]})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
