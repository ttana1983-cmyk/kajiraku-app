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

# --- 1. LINEからの信号を受け取る窓口（ここが抜けていました！） ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 2. 設定 ---
conf = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-3.5-flash')

# Google Sheets 連携用関数
def get_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(os.environ["SPREADSHEET_ID"]).sheet1

# --- 3. メッセージ受付（「メニュー」や「設定変更」への反応） ---
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    msg = event.message.text
    tk = event.reply_token
    user_id = event.source.user_id

    # 家族構成やアレルギーの「登録処理」か「献立相談」かを判別
    if msg in ["メニュー", "スタート", "設定変更"]:
        show_family_selection(tk)
    else:
        try:
            sheet = get_sheet()
            cell = sheet.find(user_id)
            
            # まだ名簿にいない場合は、まず登録を促す
            if not cell:
                send_reply(tk, "まずは「メニュー」と送って、家族構成などを教えてくださいね！")
            else:
                # 登録済みの場合は、食材として受け取ってレシピを生成
                handle_ai_generation(event, sheet, cell.row)
        except Exception as e:
            print(f"Error in message handler: {e}")
            send_reply(tk, "すみません、少し通信が不安定みたいです。時間を置いて試してみてね！")

# 家族構成の選択ボタンを表示
def show_family_selection(tk):
    quick_reply = QuickReply(items=[
        QuickReplyItem(action=PostbackAction(label="1人暮らし", data="step=dislike&family=1人", display_text="1人暮らし")),
        QuickReplyItem(action=PostbackAction(label="2人", data="step=dislike&family=2人", display_text="2人")),
        QuickReplyItem(action=PostbackAction(label="3人", data="step=dislike&family=3人", display_text="3人")),
        QuickReplyItem(action=PostbackAction(label="4人以上", data="step=dislike&family=4人以上", display_text="4人以上"))
    ])
    send_reply(tk, "まずは何人分のごはんを作ることが多いですか？👪", quick_reply)

# --- 4. ボタン操作（顧客情報の保存と更新） ---
@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    tk = event.reply_token
    user_id = event.source.user_id
    params = dict(item.split('=') for item in data.split('&'))
    
    if params.get('step') == "dislike":
        # 家族構成を保存（ここではまだ書き込まず、次にアレルギーを聞く）
        # ※本来はDBに保持しますが、簡易的に「メッセージを打って」と誘導
        send_reply(tk, f"{params.get('family')}分ですね！\n\n最後に【苦手な食材・アレルギー】を教えてください。\n（例：ピーマン、卵アレルギー、特になし）\n\nここに入力すると登録が完了します！")

# --- 5. AI生成（シートの名簿情報をプロンプトに注入） ---
def handle_ai_generation(event, sheet, row_idx):
    user_id = event.source.user_id
    msg = event.message.text
    tk = event.reply_token

    # スプレッドシートからその人の情報を読み出す
    try:
        row_data = sheet.row_values(row_idx)
        # シート構成: A:ID, B:名前, C:家族, D:苦手, E:ランク, F:日付
        user_name = row_data[1] if len(row_data) > 1 else "ユーザー"
        family = row_data[2] if len(row_data) > 2 else "不明"
        dislike = row_data[3] if len(row_data) > 3 else "特になし"

        # 即レスでお待たせさせない
        send_reply(tk, "ありがとうございます！条件に合わせたレシピを考えてくるので、少しお待ちくださいね。🍳")

        # AIへの命令
        prompt = f"""
        あなたはプロの料理研究家です。以下の顧客データを踏まえて回答してください。
        
        【顧客データ】
        - 家族構成: {family}
        - 苦手・アレルギー: {dislike}
        
        【今回のリクエスト】
        食材: {msg}
        
        【指示】
        - {family}に適した分量で提案。
        - {dislike}は絶対に使用しない。
        - 実在するレシピURLを必ず1つ載せる。
        - 家事の時短テクニックを1つ添える。
        """
        
        response = model.generate_content(prompt)
        
        # 回答をプッシュメッセージで送信
        with ApiClient(conf) as api_client:
            line_api = MessagingApi(api_client)
            line_api.push_message(PushMessageRequest(
                to=user_id,
                messages=[TextMessage(text=response.text)]
            ))
            
    except Exception as e:
        print(f"Error in AI generation: {e}")

# 共通返信関数
def send_reply(tk, text, quick_reply=None):
    with ApiClient(conf) as api_client:
        line_api = MessagingApi(api_client)
        line_api.reply_message(ReplyMessageRequest(
            reply_token=tk,
            messages=[TextMessage(text=text, quick_reply=quick_reply)]
        ))

if __name__ == "__main__":
    # Renderのポート設定に合わせて起動
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
