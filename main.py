import os
import json
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage, QuickReply, QuickReplyItem, PostbackAction, PushMessageRequest
from linebot.v3.webhooks import MessageEvent, TextMessageContent, PostbackEvent
import google.generativeai as genai

app = Flask(__name__)
user_temp_data = {}

# --- 設定 ---
conf = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-3.5-flash')

def get_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(os.environ["SPREADSHEET_ID"]).sheet1

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
    if msg in ["メニュー", "スタート"]:
        show_meal_selection(tk)
    elif msg == "設定変更":
        start_registration(u_id, tk, is_edit=True)
    elif u_id in user_temp_data and user_temp_data[u_id].get("step") == "waiting_free_input":
        register_new_user(event, msg)
    else:
        handle_free_consultation(event)

# --- 登録フロー ---
def start_registration(u_id, tk, is_edit=False):
    user_temp_data[u_id] = {
        "counts": {"男性": 0, "女性": 0, "お子様": 0, "ご年配": 0},
        "child_detail": "", "ng_items": [], "is_edit": is_edit, "step": "member_select"
    }
    show_main_category_selector(tk)

def show_main_category_selector(tk):
    items = [
        QuickReplyItem(action=PostbackAction(label="👨 男性の人数を設定する", data="select=男性")),
        QuickReplyItem(action=PostbackAction(label="👩 女性の人数を設定する", data="select=女性")),
        QuickReplyItem(action=PostbackAction(label="👶 お子様の人数を設定する", data="select=お子様")),
        QuickReplyItem(action=PostbackAction(label="👵 ご年配の人数を設定する", data="select=ご年配")),
        QuickReplyItem(action=PostbackAction(label="✨ 設定を完了して次へ進む ✅", data="select=DONE"))
    ]
    send_reply(tk, "【家族構成の設定】\n該当する項目を選んでください。", QuickReply(items=items))

@handler.add(PostbackEvent)
def handle_postback(event):
    data, tk, u_id = event.postback.data, event.reply_token, event.source.user_id
    params = dict(item.split('=') for item in data.split('&'))
    
    if params.get('step') == "edit_force":
        start_registration(u_id, tk, is_edit=True); return

    if "select" in params:
        sel = params.get("select")
        if sel == "DONE": show_ng_selector(tk)
        elif sel == "お子様":
            items = [QuickReplyItem(action=PostbackAction(label=f"🧒 お子様：{i}名", data=f"child_num={i}")) for i in range(1, 4)]
            send_reply(tk, "お子様は何名ですか？", QuickReply(items=items))
        else:
            items = [QuickReplyItem(action=PostbackAction(label=f"👥 {sel}：{i}名", data=f"m_type={sel}&num={i}")) for i in range(1, 4)]
            send_reply(tk, f"【{sel}】の人数を選んでください。", QuickReply(items=items))

    elif "m_type" in params:
        user_temp_data[u_id]["counts"][params['m_type']] = params['num']
        show_main_category_selector(tk)

    elif "child_num" in params:
        user_temp_data[u_id]["counts"]["お子様"] = params['child_num']
        items = [QuickReplyItem(action=PostbackAction(label=a, data=f"c_age={a}")) for a in ["🍼 離乳食（ドロドロ）", "🥣 幼児食（パクパク）", "🍱 小学生以上（大人近い）"]]
        send_reply(tk, "お子様の今の状態は？", QuickReply(items=items))

    elif "c_age" in params:
        user_temp_data[u_id]["child_detail"] = params['c_age']
        show_main_category_selector(tk)

    elif "ng" in params:
        ng = params.get("ng")
        if ng == "DONE": register_new_user(event, "特になし")
        elif ng == "生もの":
            items = [
                QuickReplyItem(action=PostbackAction(label="🍣 マグロは食べられる", data="exc=マグロ")),
                QuickReplyItem(action=PostbackAction(label="🍣 サーモンは食べられる", data="exc=サーモン")),
                QuickReplyItem(action=PostbackAction(label="🚫 生ものは一切NG", data="exc=全てNG"))
            ]
            send_reply(tk, "生もの（刺身・寿司）の例外はありますか？", QuickReply(items=items))
        elif ng == "OTHER":
            user_temp_data[u_id]["step"] = "waiting_free_input"
            send_reply(tk, "アレルギーやその他のNG事項を教えてください。")
        else:
            user_temp_data[u_id]["ng_items"].append(ng); show_ng_selector(tk)

    elif "exc" in params:
        res = f"生ものNG(例外:{params['exc']})" if params['exc'] != "全てNG" else "生もの完全NG"
        user_temp_data[u_id]["ng_items"].append(res); show_ng_selector(tk)

    elif params.get('step') == "reset_meal":
        user_temp_data.pop(u_id, None); show_meal_selection(tk)
    elif params.get('meal'):
        user_temp_data[f"{u_id}_meal"] = {"morning": "朝ごはん", "lunch": "昼ごはん", "dinner": "夜ごはん"}.get(params.get('meal'))
        show_genre_selection(tk, user_temp_data[f"{u_id}_meal"])
    elif params.get('genre'):
        user_temp_data[f"{u_id}_genre"] = params.get('genre')
        send_reply(tk, f"【{params.get('genre')}】で承りました。食材を教えてください🍳")
    elif params.get('step') == "retry":
        try:
            sheet = get_sheet(); cell = sheet.find(u_id); handle_ai_generation(event, sheet, cell.row, is_retry=True)
        except: send_reply(tk, "申し訳ありません。もう一度食材を教えていただけますか？")

# --- UI ---
def show_ng_selector(tk):
    items = [
        QuickReplyItem(action=PostbackAction(label="🙅 生ものが苦手", data="ng=生もの")),
        QuickReplyItem(action=PostbackAction(label="🌶️ 強い香辛料が苦手", data="ng=スパイス")),
        QuickReplyItem(action=PostbackAction(label="🍋 強い酸味が苦手", data="ng=酸味")),
        QuickReplyItem(action=PostbackAction(label="⚠️ その他（文字入力）", data="ng=OTHER")),
        QuickReplyItem(action=PostbackAction(label="✨ 設定完了 ✅", data="ng=DONE"))
    ]
    send_reply(tk, "【苦手・こだわり】\n当てはまる項目を選択してください。", QuickReply(items=items))

def show_meal_selection(tk):
    items = [
        QuickReplyItem(action=PostbackAction(label="☀️ 朝ごはんを作る", data="meal=morning")),
        QuickReplyItem(action=PostbackAction(label="🕛 昼ごはんを作る", data="meal=lunch")),
        QuickReplyItem(action=PostbackAction(label="🌙 夜ごはんを作る", data="meal=dinner")),
        QuickReplyItem(action=PostbackAction(label="⚙️ 設定を変更する", data="step=edit_force"))
    ]
    send_reply(tk, "カジラク・コンシェルジュです。今日のご予定はいかがいたしますか？✨", QuickReply(items=items))

def show_genre_selection(tk, meal_type):
    items = [
        QuickReplyItem(action=PostbackAction(label="🍱 和風な気分", data="genre=和風")),
        QuickReplyItem(action=PostbackAction(label="🍝 洋風な気分", data="genre=洋風")),
        QuickReplyItem(action=PostbackAction(label="🥟 中華な気分", data="genre=中華")),
        QuickReplyItem(action=PostbackAction(label="🤝 コンシェルジュにお任せ", data="genre=お任せ"))
    ]
    send_reply(tk, f"【{meal_type}】ですね。今の気分を教えてください。", QuickReply(items=items))

def register_new_user(event, other_msg):
    u_id = event.source.user_id; data = user_temp_data[u_id]; c = data["counts"]
    summary = f"男{c['男性']}女{c['女性']}子{c['お子様']}({data['child_detail']})年{c['ご年配']}"
    ng_list = ",".join(data["ng_items"]) + f" その他:{other_msg}"
    user_temp_data.pop(u_id, None)
    try:
        sheet = get_sheet()
        try:
            cell = sheet.find(u_id)
            sheet.update_cell(cell.row, 3, summary); sheet.update_cell(cell.row, 4, ng_list)
        except gspread.exceptions.CellNotFound:
            sheet.append_row([u_id, "ユーザー", summary, ng_list, "", "Free", datetime.date.today().strftime("%Y/%m/%d")])
        send_reply(event.reply_token, "家族設定を保存しました。"); show_meal_selection(event.reply_token)
    except: send_reply(event.reply_token, "データの保存に失敗しました。")

def handle_free_consultation(event):
    msg, u_id, tk = event.message.text, event.source.user_id, event.reply_token
    try:
        sheet = get_sheet()
        try:
            cell = sheet.find(u_id)
            res = model.generate_content(f"分類：A(食材) B(質問) C(挨拶)。判定せよ：{msg}").text.strip()
            if "C" in res: show_meal_selection(tk)
            elif "A" in res: user_temp_data[f"{u_id}_last_food"] = msg; handle_ai_generation(event, sheet, cell.row)
            else:
                answer = model.generate_content(f"コンシェルジュとして回答：{msg}").text
                send_reply(tk, answer)
        except gspread.exceptions.CellNotFound:
            start_registration(u_id, tk)
    except: send_reply(tk, "エラーが発生しました。時間を置いてお試しください。")

def handle_ai_generation(event, sheet, row_idx, is_retry=False):
    tk, u_id = event.reply_token, event.source.user_id
    row = sheet.row_values(row_idx); fam, ng_all = row[2], row[3]
    food = user_temp_data.get(f"{u_id}_last_food", "あるもの")
    meal = user_temp_data.get(f"{u_id}_meal", "夜ごはん"); gen = user_temp_data.get(f"{u_id}_genre", "お任せ")
    
    # 最初の返信で「考え中」を伝える
    send_reply(tk, "献立を構築しています。少々お待ちくださいませ。")
    
    try:
        prompt = f"""あなたはプロの家事コンシェルジュです。家族構成:{fam}、時間帯:{meal}、気分:{gen}、食材:{food}、制限:{ng_all}に基づき、15分で完成する引き算レシピを1つ提案してください。
        【指針】丁寧で安心感のある言葉遣い。冒頭で必ず衛生管理への注意を促す。URLは含めない。プレーンテキストで。"""
        res = model.generate_content(prompt)
        qr = QuickReply(items=[
            QuickReplyItem(action=PostbackAction(label="🔄 別のレシピを提案", data="step=retry")),
            QuickReplyItem(action=PostbackAction(label="🏠 メニューに戻る", data="step=reset_meal"))
        ])
        with ApiClient(conf) as c:
            MessagingApi(c).push_message(PushMessageRequest(to=u_id, messages=[TextMessage(text=res.text, quick_reply=qr)]))
    except:
        with ApiClient(conf) as c:
            MessagingApi(c).push_message(PushMessageRequest(to=u_id, messages=[TextMessage(text="申し訳ありません、献立の作成に失敗しました。")]))

def send_reply(tk, text, quick_reply=None):
    with ApiClient(conf) as c: MessagingApi(c).reply_message(ReplyMessageRequest(reply_token=tk, messages=[TextMessage(text=text, quick_reply=quick_reply)]))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
