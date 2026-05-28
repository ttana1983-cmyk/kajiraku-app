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
    
    # --- リッチメニュー連動ロジック ---
    if msg == "レシピのご提案":
        show_meal_selection(tk)
    
    elif msg == "レシピ検索":
        send_reply(tk, "どんなお料理をお知りになりたいですか？✨\n料理名（例：ハンバーグ）を入力してください。")
        user_temp_data[u_id] = {"mode": "search"} # 検索モードにセット
        
    elif msg == "食材変更":
        # 最後に選んだ「時間帯」が残っていればそこから再開、なければ最初から
        meal = user_temp_data.get(f"{u_id}_meal", "夜")
        send_reply(tk, f"【{meal}】の食材を変更しますね。新しい食材を教えてください。")
        
    elif msg == "人数変更":
        start_registration(u_id, tk, is_edit=True)
        
    # --- 通常フロー ---
    elif msg in ["メニュー", "スタート"]:
        show_meal_selection(tk)
    elif u_id in user_temp_data and user_temp_data[u_id].get("step") == "waiting_free_input":
        register_new_user(event, msg)
    else:
        handle_free_consultation(event)

# --- 判定・生成ロジック ---
def handle_free_consultation(event):
    msg, u_id, tk = event.message.text, event.source.user_id, event.reply_token
    
    # 検索モード、または明らかに料理名っぽい場合
    is_search_mode = user_temp_data.get(u_id, {}).get("mode") == "search"
    
    try:
        judge_prompt = f"判定：A(特定の料理名のレシピ希望) B(食材相談)。『{msg}』はどっち？"
        res = model.generate_content(judge_prompt).text.strip()
        
        if "A" in res or is_search_mode:
            # 検索モードのリセット
            if u_id in user_temp_data: user_temp_data[u_id].pop("mode", None)
            
            variation_prompt = f"『{msg}』のバリエーションを5つ、短い名称で改行区切りで出してください。"
            vars_res = model.generate_content(variation_prompt).text.strip()
            options = vars_res.split('\n')
            items = [QuickReplyItem(action=PostbackAction(label=opt[:20], data=f"genre={opt}")) for opt in options if opt]
            send_reply(tk, f"『{msg}』ですね！今日はどんな気分で作りますか？✨", QuickReply(items=items))
            user_temp_data[f"{u_id}_last_food"] = msg
        else:
            send_reply(tk, "献立を考えています。少々お待ちくださいませ。")
            user_temp_data[f"{u_id}_last_food"] = msg
            handle_ai_generation(event, get_sheet(), get_row_idx(u_id))
    except:
        send_reply(tk, "すみません、少し考え込んでしまいました。")

def handle_ai_generation(event, sheet, row_idx, is_retry=False):
    u_id = event.source.user_id
    row = sheet.row_values(row_idx) if row_idx else ["", "", "設定なし", "設定なし"]
    fam, ng_all = row[2], row[3]
    food = user_temp_data.get(f"{u_id}_last_food", "あるもの")
    meal = user_temp_data.get(f"{u_id}_meal", "今日")
    gen = user_temp_data.get(f"{u_id}_genre", "お任せ")
    
    retry_inst = "※前回とは別の味付けや調理法で提案してください。" if is_retry else ""
    
    try:
        prompt = f"""家事ラクコンシェルジュとして提案。
        家族:{fam}/時間:{meal}/気分:{gen}/食材:{food}/制限:{ng_all}
        【ルール】料理名指定ならそのレシピ、食材なら最高の1つを選び他は温存。15分150円目安。URL禁止。{retry_inst}"""
        
        res = model.generate_content(prompt)
        qr = QuickReply(items=[
            QuickReplyItem(action=PostbackAction(label="🔄 別の提案", data="step=retry")),
            QuickReplyItem(action=PostbackAction(label="🏠 戻る", data="step=reset_meal"))
        ])
        push_text(u_id, f"家事ラクコンシェルジュです。\n\n{res.text}", qr)
    except:
        push_text(u_id, "失敗しました。再度お試しください。")

# --- 以降、登録フロー等は前回同様（省略せず含めてください） ---
def get_row_idx(u_id):
    try: return get_sheet().find(u_id).row
    except: return None

def send_reply(tk, text, quick_reply=None):
    with ApiClient(conf) as c:
        MessagingApi(c).reply_message(ReplyMessageRequest(reply_token=tk, messages=[TextMessage(text=text, quick_reply=quick_reply)]))

def push_text(u_id, text, quick_reply=None):
    with ApiClient(conf) as c:
        MessagingApi(c).push_message(PushMessageRequest(to=u_id, messages=[TextMessage(text=text, quick_reply=quick_reply)]))

def show_meal_selection(tk):
    items = [
        QuickReplyItem(action=PostbackAction(label="☀️ 朝ごはん", data="meal=morning")),
        QuickReplyItem(action=PostbackAction(label="🕛 昼ごはん", data="meal=lunch")),
        QuickReplyItem(action=PostbackAction(label="🌙 夜ごはん", data="meal=dinner")),
        QuickReplyItem(action=PostbackAction(label="⚙️ 設定変更", data="step=edit_force"))
    ]
    send_reply(tk, "家事ラク・コンシェルジュです。今日のご予定は？✨", QuickReply(items=items))

def show_genre_selection(tk, meal_type):
    items = [
        QuickReplyItem(action=PostbackAction(label="🍱 和風", data="genre=和風")),
        QuickReplyItem(action=PostbackAction(label="🍝 洋風", data="genre=洋風")),
        QuickReplyItem(action=PostbackAction(label="🥟 中華", data="genre=中華")),
        QuickReplyItem(action=PostbackAction(label="🤝 お任せ", data="genre=お任せ"))
    ]
    send_reply(tk, f"【{meal_type}】ですね。今の気分は？", QuickReply(items=items))

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
        handle_ai_generation(event, get_sheet(), get_row_idx(u_id))
    elif params.get('step') == "retry":
        handle_ai_generation(event, get_sheet(), get_row_idx(u_id), is_retry=True)

def start_registration(u_id, tk, is_edit=False):
    user_temp_data[u_id] = {"counts": {"男性": 0, "女性": 0, "お子様": 0, "ご年配": 0}, "child_detail": "", "ng_items": [], "is_edit": is_edit, "step": "member_select"}
    show_main_category_selector(tk)

def show_main_category_selector(tk):
    items = [QuickReplyItem(action=PostbackAction(label="👨 男性", data="select=男性")), QuickReplyItem(action=PostbackAction(label="👩 女性", data="select=女性")), QuickReplyItem(action=PostbackAction(label="👶 お子様", data="select=お子様")), QuickReplyItem(action=PostbackAction(label="👵 ご年配", data="select=ご年配")), QuickReplyItem(action=PostbackAction(label="✅ 設定完了", data="select=DONE"))]
    send_reply(tk, "家族構成を設定してください。", QuickReply(items=items))

def show_ng_selector(tk):
    items = [QuickReplyItem(action=PostbackAction(label="🙅 生ものNG", data="ng=生もの")), QuickReplyItem(action=PostbackAction(label="🍋 酸味NG", data="ng=酸味")), QuickReplyItem(action=PostbackAction(label="⚠️ その他", data="ng=OTHER")), QuickReplyItem(action=PostbackAction(label="✅ 完了", data="ng=DONE"))]
    send_reply(tk, "苦手なものはありますか？", QuickReply(items=items))

def register_new_user(event, other_msg):
    u_id = event.source.user_id; data = user_temp_data[u_id]; c = data["counts"]
    summary = f"男{c.get('男性',0)}女{c.get('女性',0)}子{c.get('お子様',0)}({data.get('child_detail','')})年{c.get('ご年配',0)}"
    ng_list = ",".join(data.get("ng_items",[])) + f" その他:{other_msg}"
    user_temp_data.pop(u_id, None)
    try:
        sheet = get_sheet()
        try: cell = sheet.find(u_id); sheet.update_cell(cell.row, 3, summary); sheet.update_cell(cell.row, 4, ng_list)
        except: sheet.append_row([u_id, "ユーザー", summary, ng_list, "", "Free", datetime.date.today().strftime("%Y/%m/%d")])
        send_reply(event.reply_token, "設定を保存しました！"); show_meal_selection(event.reply_token)
    except: send_reply(event.reply_token, "保存失敗...")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
