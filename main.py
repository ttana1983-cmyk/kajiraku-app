import os, json, threading, requests, google.genai as genai
from flask import Flask, request, abort, render_template, jsonify
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest,
    TextMessage, QuickReply, QuickReplyItem, MessageAction, URIAction
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from google.genai import types

base_dir = os.path.dirname(os.path.abspath(__file__))
template_dir = os.path.join(base_dir, 'templates')
app = Flask(__name__, template_folder=template_dir)

# 環境設定
conf = Configuration(access_token=os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

def wake_up_render():
    try: requests.get(f"https://{request.host}/", timeout=1)
    except: pass

# 🚀 案内用ページ：UptimeRobotやブラウザがアクセスした時は、LINEチェックを通さず即200（成功）を返す
@app.route("/")
def top_page():
    return "カジラク・コンシェルジュ サーバー稼働中！🍳", 200

# 🍳 アプリ画面用ページ（ハッシュ切り替えのベース）
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

    if "今日のレシピ" in raw_txt or "コンシェルジュと相談" in raw_txt:
        send_quick(tk, "カジラク・コンシェルジュです🍳\nいつのご飯を考えましょうか？", ["朝ごはん", "昼ごはん", "夜ごはん"])
    
    elif raw_txt in ["朝ごはん", "昼ごはん", "夜ごはん"]:
        send_quick(tk, f"{raw_txt}ですね！ジャンルはどうしますか？", 
                   [f"{raw_txt}/和風", f"{raw_txt}/洋風", f"{raw_txt}/中華", f"{raw_txt}/お任せ"])
    
    elif "/" in raw_txt and any(g in raw_txt for g in ["和風", "洋風", "中華", "お任せ"]):
        meal, genre = raw_txt.split('/')
        msg = f"【{meal} × {genre}】ですね。承りました。\n\n冷蔵庫の中で優先的に使いたい食材を教えてください！（例：鶏もも肉、玉ねぎ）"
        send_reply(tk, msg)
        
    else:
        msg = (
            "入力ありがとうございます！\n"
            "今からコンシェルジュがレシピを考えますので、下のボタンからレシピを受け取ってくださいね。🍳"
        )
        encoded_query = requests.utils.quote(raw_txt)
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

# 🧠 AIレシピ生成API（本物のガチレシピ生成・寄り添う一言アドバイス・JSON構造完全固定版）
@app.route("/api/generate-recipe")
def generate():
    query = request.args.get('query', 'おまかせ')
    family = request.args.get('family', '大人2人分')
    allergy = request.args.get('allergy', 'なし')
    dislike = request.args.get('dislike', 'なし')
    
    p = (
        f"あなたはプロの料理家であり、主婦・主夫の毎日の家事を劇的に楽にする、時短節約レシピの専門コンシェルジュ『カジラク』です。\n"
        f"以下の条件を完璧に満たす、15分で作れる具体的で美味しいオリジナルレシピを1つ提案してください。\n\n"
        f"【ユーザーからの要望】\n"
        f"・使いたい食材: {query}\n"
        f"・指定の家族構成: {family}\n"
        f"・絶対に使えないアレルギー食材: {allergy}\n"
        f"・レシピに入れないもの・嫌いな食材: {dislike}\n\n"
        f"【調理・分量ルール】\n"
        f"1. アレルギー食材（{allergy}）とレシピに入れないもの（{dislike}）は、調味料や出汁の隠し味を含め一切使用を禁止します。\n"
        f"2. 食材の分量は、「適量」などの曖昧な表現を一切禁止し、指定された家族構成（{family}）全員がお腹いっぱいになる正確なグラム数、個数、大さじ・小さじの量で具体的に計算してください。\n"
        f"3. 作り方の手順（steps）は、「適当に味付けする」などの丸投げは禁止し、「醤油大さじ2を入れて中火で3分炒める」のように、誰でも失敗せず15分で作れる具体的な調理アクションを詳しく書いてください。\n\n"
        f"【🌟コンシェルジュの一言アドバイス（tip）の絶対ルール】\n"
        f"入力された家族構成（{family}）や嫌いなもの（{dislike}）をプロの目線でよく分析し、主婦・主夫が泣いて喜ぶような、家族みんなが笑顔になれる温かいアドバイスを書いてください。\n"
        f"（例1：お子様がいるのに『野菜が嫌い・除外』とある場合 ➡️ 『野菜嫌いなお子様には、野菜を合わせる前にお肉だけ先に取り出して味付けしてあげると、パクパク食べてくれますよ！』など）\n"
        f"（例2：小さいお子様がいる場合 ➡️ 『小さなお子様用には、お肉を細かくハサミで切ってあげると食べやすくなります！』など）\n"
        f"（例3：大人数でお肉料理の場合 ➡️ 『大人数分を一気に炒めると水気が出やすいので、2回に分けるか強火で一気に仕上げるのがお肉を柔らかく保つコツです！』など）"
    )

    json_schema = {
        "type": "OBJECT",
        "properties": {
            "name": {"type": "STRING", "description": "具体的で美味しそうなオリジナル料理名"},
            "time": {"type": "STRING", "description": "調理時間（例：15分）"},
            "cost": {"type": "STRING", "description": "家族構成に合わせた目安の総材料費（例：約600円）"},
            "tip": {"type": "STRING", "description": "【絶対必須】指定された家族構成やアレルギー・嫌いなものに優しく寄り添った、コンシェルジュからの温かいワンポイントアドバイス"},
            "ingredients": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "name": {"type": "STRING", "description": "食材名または調味料名"},
                        "amount": {"type": "STRING", "description": "家族の人数にぴったり合わせた具体的な分量（適量は禁止）"}
                    },
                    "required": ["name", "amount"]
                }
            },
            "steps": {
                "type": "ARRAY",
                "items": {"type": "STRING", "description": "具体的な調理手順（加熱時間、火加減、投入する調味料を明記）"}
            }
        },
        "required": ["name", "time", "cost", "tip", "ingredients", "steps"]
    }

    try:
        res = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=p,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=json_schema,
                temperature=0.3
            )
        )
        return jsonify(json.loads(res.text.strip()))
        
    except Exception as e:
        print(f"Gemini/Parsing Error: {e}")
        fallback = {
            "name": f"{query}の特製スピード炒め",
            "time": "15分",
            "cost": "約600円",
            "tip": "お子様や苦手な方がいる場合は、調味料を絡める前に取り分けてケチャップなどで味付けアレンジするのもおすすめですよ！",
            "ingredients": [
                {"name": f"{query}", "amount": "家族人数分（目安500g）"},
                {"name": "醤油・みりん・酒", "amount": "各大さじ2"}
            ],
            "steps": [
                f"{query}を食べやすい大きさに切り、下ごしらえをします。",
                "フライパンに油を熱し、強火で肉に完全に火が通るまで炒めます。",
                "合わせておいた調味料を回し入れ、全体にタレがよく絡むまで中火で1分ほど炒め合わせます。"
            ]
        }
        return jsonify(fallback)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
