import os
import json
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, request, abort, render_template_string
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage, QuickReply, QuickReplyItem, PostbackAction
from linebot.v3.webhooks import MessageEvent, TextMessageContent, PostbackEvent
import google.generativeai as genai

app = Flask(__name__)
user_temp_data = {}

# --- 環境変数設定 ---
conf = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# 【店長指定】モデル固定
model = genai.GenerativeModel('gemini-3.5-flash') 

def get_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(os.environ["SPREADSHEET_ID"]).sheet1

# --- 1. LIFF画面（買い物シート）の表示ルート ---
@app.route("/recipe")
def recipe_page():
    # 本来はDBから取得しますが、まずは店長のUIイメージを体験するための静的表示
    liff_id = os.environ.get("LIFF_ID", "")
    
    html_template = f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>カジラク・買い物シート</title>
        <script src="https://static.line-scdn.net/liff/edge/2/sdk.js"></script>
        <style>
            :root {{ --bg: #f9f7f2; --text: #4a4a4a; --accent: #8e9775; --card: #ffffff; }}
            body {{ font-family: sans-serif; background-color: var(--bg); color: var(--text); margin: 0; padding: 20px; }}
            .card {{ background: var(--card); border-radius: 15px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 20px; }}
            h1 {{ font-size: 1.1rem; border-bottom: 2px solid var(--accent); padding-bottom: 10px; margin-top: 0; }}
            .item {{ display: flex; align-items: center; padding: 12px 0; border-bottom: 1px solid #eee; cursor: pointer; }}
            .item input {{ margin-right: 15px; transform: scale(1.4); accent-color: var(--accent); }}
            .checked {{ text-decoration: line-through; color: #bbb; }}
            .btn-done {{ width: 100%; background: var(--accent); color: white; border: none; padding: 15px; border-radius: 30px; font-weight: bold; margin-top: 10px; cursor: pointer; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🍳 今日のレシピ</h1>
            <p>※ここにGeminiの回答が表示されます（現在開発中）</p>
        </div>
        <div class="card">
            <h1>🛒 お買い物チェックリスト</h1>
            <div class="item" onclick="this.classList.toggle('checked')"><input type="checkbox"> <span>メインの食材</span></div>
            <div class="item" onclick="this.classList.toggle('checked')"><input type="checkbox"> <span>野菜など</span></div>
        </div>
        <button class="btn-done" onclick="liff.closeWindow()">買い物完了！調理へ</button>

        <script>
            liff.init({{ liffId: "{liff_id}" }}).then(() => {{
                if (!liff.isLoggedIn()) {{ liff.login(); }}
            }});
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template)

# --- 2. LINE Webhook処理 ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    msg, tk, u_id = event.message.text, event.reply_token, event.source.user_id
    
    if msg == "レシピのご提案":
        show_meal_selection(tk)
    elif msg == "レシピ検索":
        send_reply(tk, "どんなお料理をお知りになりたいですか？✨")
        user_temp_data[u_id] = {"mode": "search"}
    elif msg == "食材変更":
        meal = user_temp_data.get(f"{u_id}_meal", "夜")
        send_reply(tk, f"【{meal}】の食材を変更しますね！新しい食材を教えてください。")
    elif msg == "人数変更":
        start_registration(u_id, tk, is_edit=True)
    elif u_id in user_temp_data and user_temp_data[u_id].get("step") == "waiting_free_input":
        register_new_user(event, msg)
    else:
        handle_free_consultation(event)

def handle_free_consultation(event):
    msg, u_id, tk = event.message.text, event.reply_token, event.source.user_id
    is_search_mode = user_temp_data.get(u_id, {}).get("mode") == "search"
    
    try:
        judge_prompt = f"判定：A(料理名) B(食材相談)。『{msg}』はどちら？Aならバリエーションを5つ、Bなら '食材' と返して。"
        res = model.generate_content(judge_prompt).text.strip()
        
        if "食材" in res or (not is_search_mode):
            user_temp_data[f"{u_id}_last_food"] = msg
            handle_ai_generation(event, tk)
        else:
            options = res.split('\n')
            items = [QuickReplyItem(action=PostbackAction(label=opt[:20], data=f"genre={opt}")) for opt in options if opt]
            send_reply(tk, f"『{msg}』ですね！今日はどんな気分で作りますか？✨", QuickReply(items=items))
            user_temp_data[f"{u_id}_last_food"] = msg
    except:
        send_reply(tk, "もう一度教えていただけますか？")

def handle_ai_generation(event, tk, is_retry=False):
    u_id = event.source.user_id
    liff_url = f"https://liff.line.me/{os.environ.get('LIFF_ID')}"
    
    try:
        sheet = get_sheet(); cell = sheet.find(u_id); row = sheet.row_values(cell.row)
        fam, ng_all = row[2], row[3]
    except: fam, ng_all = "未設定", "特になし"
    
    food = user_temp_data.get(f"{u_id}_last_food", "あるもの")
    meal = user_temp_data.get(f"{u_id}_meal", "今日")
    gen = user_temp_data.get(f"{u_id}_genre", "お任せ")
    
    try:
        prompt = f"家事ラクコンシェルジュ。構成:{fam}/{meal}/{gen}/食材:{food}/制限:{ng_all}。15分150円レシピ。簡潔に。"
        res = model.generate_content(prompt)
        
        # 買い物シート（LIFF）への誘導ボタンを追加
        qr = QuickReply(items=[
            QuickReplyItem(action=PostbackAction(label="🔄 別の提案", data="step=retry")),
            QuickReplyItem(action=PostbackAction(label="🏠 戻る", data="step=reset_meal"))
        ])
        
        # レシピ本文にLIFFへのリンクを添える
        reply_text = f"家事ラクコンシェルジュです✨\n\n{res.text}\n\n👇お買い物リストはこちら\n{liff_url}"
        send_reply(tk, reply_text, qr)
    except:
        send_reply(tk, "献立の作成に失敗しました。")

def send_reply(tk, text, quick_reply=None):
    with ApiClient(conf) as c:
        MessagingApi(c).reply_message(ReplyMessageRequest(reply_token=tk, messages=[TextMessage(text=text, quick_reply=quick_reply)]))

# --- 以下、設定フロー（省略せず維持） ---
def start_registration(u_id, tk, is_edit=False):
    user_temp_data[u_id] = {"counts": {"男性": 0, "女性": 0, "お子様": 0, "ご年配": 0}, "child_detail": "", "ng_items": [], "is_edit": is_edit, "step": "member_select"}
    show_main_category_selector(tk)

def show_main_category_selector(tk):
    items = [QuickReplyItem(action=PostbackAction(label="👨 男性", data="select=男性")), QuickReplyItem(action=PostbackAction(label="👩 女性", data="select=女性")), QuickReplyItem(action=PostbackAction(label="👶 お子様", data="select=お子様")), QuickReplyItem(action=PostbackAction(label="👵 ご年配", data="select=ご年配")), QuickReplyItem(action=PostbackAction(label="✅ 設定完了", data="select=DONE"))]
    send_reply(tk, "家族構成を設定してください。", QuickReply(items=items))

@handler.add(PostbackEvent)
def handle_postback(event):
    data, tk, u_id = event.postback.data, event.reply_token, event.source.user_id
    params = dict(item.split('=') for item in data.split('&'))
    if params.get('step') == "edit_force": start_registration(u_id, tk, is_edit=True)
    elif "select" in params:
        sel = params.get("select")
        if sel == "DONE": show_ng_selector(tk)
        elif sel == "お子様":
            items = [QuickReplyItem(action=PostbackAction(label=f"🧒 お子様：{i}名", data=f"child_num={i}")) for i in range(1, 4)]
            send_reply(tk, "お子様は何名ですか？", QuickReply(items=items))
        else:
            items = [QuickReplyItem(action=PostbackAction(label=f"👥 {sel}：{i}名", data=f"m_type={sel}&num={i}")) for i in range(1, 4)]
            send_reply(tk, f"【{sel}】の人数を選んでください。", QuickReply(items=items))
    elif "m_type" in params:
        if u_id not in user_temp_data: user_temp_data[u_id] = {"counts": {}}
        user_temp_data[u_id]["counts"][params['m_type']] = params['num']
        show_main_category_selector(tk)
    elif "child_num" in params:
        user_temp_data[u_id]["counts"]["お子様"] = params['child_num']
        items = [QuickReplyItem(action=PostbackAction(label=a, data=f"c_age={a}")) for a in ["🍼 離乳食", "🥣 幼児食", "🍱 小学生以上"]]
        send_reply(tk, "お子様の状態は？", QuickReply(items=items))
    elif "c_age" in params:
        user_temp_data[u_id]["child_detail"] = params['c_age']
        show_main_category_selector(tk)
    elif "ng" in params:
        ng = params.get("ng")
        if ng == "DONE": register_new_user(event, "特になし")
        elif ng == "OTHER":
            user_temp_data[u_id]["step"] = "waiting_free_input"
            send_reply(tk, "NG事項を教えてください。")
        else:
            user_temp_data[u_id]["ng_items"].append(ng); show_ng_selector(tk)
    elif params.get('step') == "reset_meal":
        user_temp_data.pop(u_id, None); show_meal_selection(tk)
    elif params.get('meal'):
        user_temp_data[f"{u_id}_meal"] = {"morning": "朝", "lunch": "昼", "dinner": "夜"}.get(params.get('meal'))
        show_genre_selection(tk, user_temp_data[f"{u_id}_meal"])
    elif params.get('genre'):
        user_temp_data[f"{u_id}_genre"] = params.get('genre')
        send_reply(tk, f"【{params.get('genre')}】ですね！使いたい食材を教えてください。入力後に少しお時間を下さいね✨")
    elif params.get('step') == "retry":
        handle_ai_generation(event, tk, is_retry=True)

def show_meal_selection(tk):
    items = [QuickReplyItem(action=PostbackAction(label="☀️ 朝", data="meal=morning")), QuickReplyItem(action=PostbackAction(label="🕛 昼", data="meal=lunch")), QuickReplyItem(action=PostbackAction(label="🌙 夜", data="meal=dinner")), QuickReplyItem(action=PostbackAction(label="⚙️ 設定", data="step=edit_force"))]
    send_reply(tk, "今日のご予定は？✨", QuickReply(items=items))

def show_genre_selection(tk, meal_type):
    items = [QuickReplyItem(action=PostbackAction(label="🍱 和風", data="genre=和風")), QuickReplyItem(action=PostbackAction(label="🍝 洋風", data="genre=洋風")), QuickReplyItem(action=PostbackAction(label="🥟 中華", data="genre=中華")), QuickReplyItem(action=PostbackAction(label="🤝 任せる", data="genre=お任せ"))]
    send_reply(tk, f"【{meal_type}】ですね。今の気分は？", QuickReply(items=items))

def register_new_user(event, other_msg):
    u_id = event.source.user_id; data = user_temp_data[u_id]; c = data["counts"]
    summary = f"男{c.get('男性',0)}女{c.get('女性',0)}子{c.get('お子様',0)}年{c.get('ご年配',0)}"
    ng_list = ",".join(data.get("ng_items",[])) + f" その他:{other_msg}"
    user_temp_data.pop(u_id,
