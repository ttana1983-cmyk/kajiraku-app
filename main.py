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
model = genai.GenerativeModel('gemini-1.5-flash')

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

# --- 登録フロー（横幅を広げたデカボタン仕様） ---
def start_registration(u_id, tk, is_edit=False):
    user_temp_data[u_id] = {
        "counts": {"男性": 0, "女性": 0, "お子様": 0, "ご年配": 0},
        "child_detail": "", "ng_items": [], "is_edit": is_edit, "step": "member_select"
    }
    show_main_category_selector(tk)

def show_main_category_selector(tk):
    # 文字数を増やすことでボタンの横幅を最大化
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
                QuickReplyItem(action=PostbackAction(label="🍣 マグロだけは食べれる", data="exc=マグロ")),
                QuickReplyItem(action=PostbackAction(label="🍣 サーモンだけは食べれる", data="exc=サーモン")),
                QuickReplyItem(action=PostbackAction(label="🚫 生ものは一切食べられない", data="exc=全てNG"))
            ]
            send_reply(tk, "生もの（刺身・寿司）の例外は？", QuickReply(items=items))
        elif ng == "OTHER":
            user_temp_data[u_id]["step"] = "waiting_free_input"
            send_reply(tk, "アレルギーやその他のNGを文字で送ってください。")
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
        send_reply(tk, f"【{params.get('genre')}】で考えます！食材を教えてください🍳")
    elif params.get('step') == "retry":
        try:
            sheet = get_sheet(); cell = sheet.find(u_id); handle_ai_generation(event, sheet, cell.row, is_retry=True)
        except: send_reply(tk, "もう一度食材を教えてください。")

# --- UI：1つずつのボタンの横幅を最大化した設定 ---
def show_ng_selector(tk):
    items = [
        QuickReplyItem(action=PostbackAction(label="🙅 生もの（刺身等）が苦手", data="ng=生もの")),
        QuickReplyItem(action=PostbackAction(label="🌶️ 八角・花椒の香りが苦手", data="ng=スパイス")),
        QuickReplyItem(action=PostbackAction(label="🍋 強い酸味が苦手", data="ng=酸味")),
        QuickReplyItem(action=PostbackAction(label="⚠️ アレルギーを文字で入力", data="ng=OTHER")),
        QuickReplyItem(action=PostbackAction(label="✨ 設定を完了して登録！ ✅", data="ng=DONE"))
    ]
    send_reply(tk, "【苦手・こだわり】\n当てはまるものをタップしてください。", QuickReply(items=items))

def show_meal_selection(tk):
    items = [
        QuickReplyItem(action=PostbackAction(label="☀️ 朝ごはんの献立を作る", data="meal=morning")),
        QuickReplyItem(action=PostbackAction(label="🕛 昼ごはんの献立を作る", data="meal=lunch")),
        QuickReplyItem(action=PostbackAction(label="🌙 夜ごはんの献立を作る", data="meal=dinner")),
        QuickReplyItem(action=PostbackAction(label="⚙️ 登録内容を変更する", data="step=edit_force"))
    ]
    send_reply(tk, "今日のごはんは何にしましょうか？✨", QuickReply(items=items))

def show_genre_selection(tk, meal_type):
    items = [
        QuickReplyItem(action=PostbackAction(label="🍱 ほっこり和風な気分", data="genre=和風")),
        QuickReplyItem(action=PostbackAction(label="🍝 お洒落な洋風な気分", data="genre=洋風")),
        QuickReplyItem(action=PostbackAction(label="🥟 ガッツリ中華な気分", data="genre=中華")),
        QuickReplyItem(action=PostbackAction(label="🤝 今日はお任せしたい", data="genre=お任せ"))
    ]
    send_reply(tk, f"【{meal_type}】ですね！今の気分は？", QuickReply(items=items))

# --- データ処理・AI生成ロジック（安全管理を徹底） ---
def register_new_user(event, other_msg):
    u_id = event.source.user_id; data = user_temp_data[u_id]; c = data["counts"]
    summary = f"男{c['男性']}女{c['女性']}子{c['お子様']}({data['child_detail']})年{c['ご年配']}"
    ng_list = ",".join(data["ng_items"]) + f" その他:{other_msg}"
    user_temp_data.pop(u_id, None)
    try:
        sheet = get_sheet(); cell = sheet.find(u_id)
        if cell: sheet.update_cell(cell.row, 3, summary); sheet.update_cell(cell.row, 4, ng_list)
        else: sheet.append_row([u_id, "ユーザー", summary, ng_list, "", "Free", datetime.date.today().strftime("%Y/%m/%d")])
        send_reply(event.reply_token, "設定が完了しました！"); show_meal_selection(event.reply_token)
    except: send_reply(event.reply_token, "エラーです")

def handle_free_consultation(event):
    msg, u_id, tk = event.message.text, event.source.user_id, event.reply_token
    res = model.generate_content(f"「食材名(A)」か「質問(B)」か判断。挨拶はC：{msg}").text.strip()
    try:
        sheet = get_sheet(); cell = sheet.find(u_id)
        if "C" in res: show_meal_selection(tk)
        elif "A" in res: user_temp_data[f"{u_id}_last_food"] = msg; handle_ai_generation(event, sheet, cell.row)
        else: send_reply(tk, "ご質問ですね！お答えします。")
    except: send_reply(tk, "もう一度お願いします。")

def handle_ai_generation(event, sheet, row_idx, is_retry=False):
    tk, u_id = event.reply_token, event.source.user_id
    row = sheet.row_values(row_idx); fam, ng_all = row[2], row[3]
    food = user_temp_data.get(f"{u_id}_last_food", "あるもの")
    meal = user_temp_data.get(f"{u_id}_meal", "夜ごはん"); gen = user_temp_data.get(f"{u_id}_genre", "お任せ")
    send_reply(tk, f"【{fam}】向けのレシピを考え中...🍳")
    try:
        prompt = f"""料理研究家として提案。構成:{fam} / 時間:{meal} / ジャンル:{gen} / 食材:{food} / 制限:{ng_all}。
        【重要】
        1. 冒頭で「器具・食器の殺菌」を必ず促すこと。
        2. 低温調理は「63度で30分以上」等、文字化けしないプレーンテキストで。
        3. 法律制限の生食禁止。煮魚・焼き魚はOK。
        4. スパイス・酸味NG留意。再提案時は別の調理法で。URL禁止。"""
        res = model.generate_content(prompt)
        qr = QuickReply(items=[
            QuickReplyItem(action=PostbackAction(label="🔄 別のレシピ(同じ食材)を提案", data="step=retry")),
            QuickReplyItem(action=PostbackAction(label="🏠 最初（メニュー）に戻る", data="step=reset_meal"))
        ])
        with ApiClient(conf) as c: MessagingApi(c).push_message(PushMessageRequest(to=u_id, messages=[TextMessage(text=res.text, quick_reply=qr)]))
    except: print("AI Error")

def send_reply(tk, text, quick_reply=None):
    with ApiClient(conf) as c: MessagingApi(c).reply_message(ReplyMessageRequest(reply_token=tk, messages=[TextMessage(text=text, quick_reply=quick_reply)]))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
