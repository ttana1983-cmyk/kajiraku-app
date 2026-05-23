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

# --- 一時記憶用（家族構成を保持） ---
user_temp_data = {}

# --- 設定 ---
conf = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-3.5-flash')

# Google Sheets 連携
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

# --- 1. メッセージ受付 ---
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    msg = event.message.text
    tk = event.reply_token
    user_id = event.source.user_id

    if msg in ["メニュー", "スタート", "設定変更"]:
        show_family_selection(tk)
    
    # 登録フローの途中（アレルギー入力待ち）
    elif user_id in user_temp_data:
        register_new_user(event, msg)
        
    else:
        # 通常のレシピ検索（シートを確認）
        try:
            sheet = get_sheet()
            cell = sheet.find(user_id)
            if not cell:
                send_reply(tk, "まずは「メニュー」と送って、登録をお願いしますね！")
            else:
                handle_ai_generation(event, sheet, cell.row, "指定なし")
        except Exception as e:
            print(f"Error: {e}")
            send_reply(tk, "通信エラーが発生しました。設定を確認してください。")

# 家族構成の選択
def show_family_selection(tk):
    quick_reply = QuickReply(items=[
        QuickReplyItem(action=PostbackAction(label="1人", data="step=dislike&family=1人")),
        QuickReplyItem(action=PostbackAction(label="2人", data="step=dislike&family=2人")),
        QuickReplyItem(action=PostbackAction(label="3人", data="step=dislike&family=3人")),
        QuickReplyItem(action=PostbackAction(label="4人以上", data="step=dislike&family=4人以上"))
    ])
    send_reply(tk, "何人分のごはんを作ることが多いですか？👪", quick_reply)

# --- 2. ボタン操作（Postback処理） ---
@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    tk = event.reply_token
    user_id = event.source.user_id
    params = dict(item.split('=') for item in data.split('&'))
    
    # アレルギー入力へ誘導
    if params.get('step') == "dislike":
        user_temp_data[user_id] = params.get('family')
        send_reply(tk, f"{params.get('family')}分ですね！\n次に【苦手なものやアレルギー】を教えてください。\n（なければ「なし」でOK！）")
    
    # 朝・昼・夜の選択後の食材入力誘導
    elif params.get('meal'):
        meal_type = {"morning": "朝ごはん", "lunch": "昼ごはん", "dinner": "夜ごはん"}.get(params.get('meal'))
        send_reply(tk, f"{meal_type}ですね！承知いたしました。\n\n今、使いたい食材（例：鶏肉、卵、余っている野菜など）を教えてください🍳")

# --- 3. 顧客登録処理 ---
def register_new_user(event, dislike_msg):
    user_id = event.source.user_id
    family = user_temp_data.pop(user_id, "不明")
    today = datetime.date.today().strftime("%Y/%m/%d")
    
    try:
        sheet = get_sheet()
        cell = sheet.find(user_id)
        if cell:
            sheet.update_cell(cell.row, 3, family)
            sheet.update_cell(cell.row, 4, dislike_msg)
        else:
            sheet.append_row([user_id, "ユーザー", family, dislike_msg, "Free", today])
        
        # 登録完了直後に「何ごはんか」を聞く（店長のこだわり！）
        quick_reply = QuickReply(items=[
            QuickReplyItem(action=PostbackAction(label="朝ごはん ☀️", data="meal=morning", display_text="朝ごはん")),
            QuickReplyItem(action=PostbackAction(label="昼ごはん 🕛", data="meal=lunch", display_text="昼ごはん")),
            QuickReplyItem(action=PostbackAction(label="夜ごはん 🌙", data="meal=dinner", display_text="夜ごはん"))
        ])
        
        send_reply(event.reply_token, 
                   f"ご登録ありがとうございます！✨\n{family}分の献立、バッチリ覚えました。\n\nさて、今日のごはんは何にしましょうか？", 
                   quick_reply)

    except Exception as e:
        print(f"Register Error: {e}")
        send_reply(event.reply_token, "登録中にエラーが発生しました。設定を確認してください。")

# --- 4. AI生成処理 ---
def handle_ai_generation(event, sheet, row_idx, meal_context):
    msg = event.message.text
    tk = event.reply_token
    user_id = event.source.user_id
    
    row_data = sheet.row_values(row_idx)
    family = row_data[2] if len(row_data) > 2 else "不明"
    dislike = row_data[3] if len(row_data) > 3 else "特になし"

    send_reply(tk, "今からピッタリのレシピを考えますね。少々お待ちください。🍳")

    try:
        prompt = f"プロの料理研究家として提案してください。{meal_context}の献立です。食材「{msg}」を使い、{family}分で、{dislike}を避けた実在するレシピをURL付きで教えて。時短テクも1つ添えて。"
        response = model.generate_content(prompt)
        
        with ApiClient(conf) as api_client:
            line_api = MessagingApi(api_client)
            line_api.push_message(PushMessageRequest(
                to=user_id, messages=[TextMessage(text=response.text)]
            ))
    except Exception as e:
        print(f"AI Error: {e}")

def send_reply(tk, text, quick_reply=None):
    with ApiClient(conf) as api_client:
        line_api = MessagingApi(api_client)
        line_api.reply_message(ReplyMessageRequest(
            reply_token=tk, messages=[TextMessage(text=text, quick_reply=quick_reply)]
        ))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
