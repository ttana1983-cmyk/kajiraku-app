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

# 環境設定
conf = Configuration(access_token=os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

# Renderのスリープを叩き起こす空撃ち関数
def wake_up_render():
    try: requests.get(f"https://{request.host}/", timeout=1)
    except: pass

# 🚀 どのパスでアクセスされてもHTML（枠組み）を確実に表示
@app.route("/")
@app.route("/recipe")
def index():
    try: 
        return render_template("index.html")
    except:
        path = os.path.join(template_dir, "index.html")
        with open(path, "r", encoding="utf-8") as f: 
            return f.read()

@app.route("/callback", methods=['POST'])
def callback():
    sig = request.headers.get('x-line-signature')
    body = request.get_data(as_text=True)
    # トークが進んでいる間に裏でサーバーを起こす仕込み
    threading.Thread(target=wake_up_render).start()
    try: 
        handler.handle(body, sig)
    except InvalidSignatureError: 
        abort(400)
    return 'OK'

# 🍳 LINE上での「コンシェルジュと相談」ヒアリングルート
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    raw_txt = event.message.text.strip()
    tk = event.reply_token

    # 1. スタート（朝・昼・夜の選択）
    if "今日のレシピ" in raw_txt or "コンシェルジュと相談" in raw_txt:
        send_quick(tk, "カジラク・コンシェルジュです🍳\nいつのご飯を考えましょうか？", ["朝ごはん", "昼ごはん", "夜ごはん"])
    
    # 2. 時間帯の選択（ジャンルの選択へ）
    elif raw_txt in ["朝ごはん", "昼ごはん", "夜ごはん"]:
        send_quick(tk, f"{raw_txt}ですね！ジャンルはどうしますか？", 
                   [f"{raw_txt}/和風", f"{raw_txt}/洋風", f"{raw_txt}/中華", f"{raw_txt}/お任せ"])
    
    # 3. ジャンルの選択（食材入力の催促へ）
    elif "/" in raw_txt and any(g in raw_txt for g in ["和風", "洋風", "中華", "お任せ"]):
        meal, genre = raw_txt.split('/')
        msg = f"【{meal} × {genre}】ですね。承りました。\n\n冷蔵庫の中で優先的に使いたい食材を教えてください！（例：鶏もも肉、玉ねぎ）"
        send_reply(tk, msg)
        
    # 4. 食材の入力（それ以外の自由入力テキストはすべて食材とみなす）
    else:
        msg = (
            "入力ありがとうございます！\n"
            "今からコンシェルジュがレシピを考えますので、下のボタンからレシピを受け取ってくださいね。🍳"
        )
        encoded_query = requests.utils.quote(raw_txt)
        # URLに食材データを乗せてブラウザへ引き継ぎ
        safe_url = f"https://kajiraku-ai.onrender.com/recipe?openExternalBrowser=1#query={encoded_query}"
        
        qr = QuickReply(items=[
            QuickReplyItem(action=URIAction(label="🍳 レシピを表示する", uri=safe_url))
        ])
        send_reply(tk, msg, qr)

def send_quick(tk, msg, opts):
    items = [QuickReplyItem(action=MessageAction(label=o.split('/')[-1], text=o)) for o in opts]
    send_reply(tk, msg, QuickReply(items=items))

def send_reply(tk, msg, qr=None):
    with ApiClient(conf) as api_client:
        line_api = MessagingApi(api_client)
        line_api.reply_message(ReplyMessageRequest(reply_token=tk, messages=[TextMessage(text=msg, quick_reply=qr)]))

# 🧠 AIレシピ生成API（豆腐などのシンプル食材・崩れJSON対策済みの完全版）
@app.route("/api/generate-recipe")
def generate():
    query = request.args.get('query', 'おまかせ')
    family = request.args.get('family', '大人2人分')
    allergy = request.args.get('allergy', 'なし')
    dislike = request.args.get('dislike', 'なし')
    
    p = (
        f"要望:{query}。家族構成:{family}。アレルギー食材:{allergy}。嫌いなもの・入れない食材:{dislike}。\n"
        f"【絶対厳守】アレルギー食材（{allergy}）と、レシピに入れないもの（{dislike}）は、隠し味や出汁を含め一切使用しないでください。\n"
        f"【絶対厳守】分量は必ず指定された家族構成（{family}）にぴったりな量で計算してください。\n"
        f"15分で完成する節約レシピを1つ提案してください。毎回違う調理法や味付けを意識してバリエーション豊かにしてください。\n"
        f"出力形式は必ず以下のピュアなJSON形式のみとし、前後に『はい、どうぞ』などの挨拶や説明文、```json などのマークアップは一切含めないでください。:\n"
        f"{{\n"
        f"  \"name\": \"料理名\",\n"
        f"  \"time\": \"15分\",\n"
        f"  \"cost\": \"目安の金額\",\n"
        f"  \"tip\": \"料理のコツ\",\n"
        f"  \"ingredients\": [\n"
        f"    {{\"name\": \"食材名\", \"amount\": \"分量\"}}\n"
        f"  ],\n"
        f"  \"steps\": [\n"
        f"    \"ステップ1\",\n"
        f"    \"ステップ2\"\n"
        f"  ]\n"
        f"}}"
    )
    try:
        res = client.models.generate_content(model='gemini-3.5-flash', contents=p)
        
        # 💡 AIが余計な挨拶やマークアップをつけても、JSONの「{ }」だけを力づくで抜き出す安全ガード
        raw_text = res.text.strip()
        if "{" in raw_text and "}" in raw_text:
            start_idx = raw_text.find("{")
            end_idx = raw_text.rfind("}") + 1
            clean = raw_text[start_idx:end_idx]
        else:
            clean = raw_text.replace('
```json', '').replace('```', '').strip()
            
        return jsonify(json.loads(clean))
        
    except Exception as e:
        print(f"Gemini/Parsing Error: {e}")
        # 💡 万が一データが砕けてパースエラーになっても、画面を止めず最低限動くダミーで救済するフォールバック
        fallback = {
            "name": f"美味しいスピード料理 ({query})",
            "time": "12分",
            "cost": "お財布に優しい安心価格",
            "tip": "火通りを均一にするため、食材の大きさを揃えて手早く調理するのがコツです。",
            "ingredients": [{"name": f"{query}", "amount": "適量"}, {"name": "お好みの調味料", "amount": "適量"}],
            "steps": ["食材を適切な大きさに切り、下ごしらえをします。", "フライパンまたはレンジで手早く熱を通します。", "お好みの味付けをして、器に盛り付けたら完成です！"]
        }
        return jsonify(fallback)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
