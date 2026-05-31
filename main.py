@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    txt = event.message.text
    tk = event.reply_token

    # 1. 最初の入り口
    if txt == "今日のレシピ提案" or txt == "今日のレシピを教えて":
        send_quick(tk, "カジラク・コンシェルジュです🍳\nいつのご飯を考えましょうか？", ["朝ごはん", "昼ごはん", "夜ごはん"])

    # 2. 時間帯の選択
    elif txt in ["朝ごはん", "昼ごはん", "夜ごはん"]:
        send_quick(tk, f"{txt}ですね！ジャンルはどうしますか？", 
                   [f"{txt}/和風", f"{txt}/洋風", f"{txt}/中華", f"{txt}/お任せ"])

    # 3. ジャンルの確定（スラッシュがある場合）
    elif "/" in txt and any(word in txt for word in ["和風", "洋風", "中華", "お任せ"]):
        msg = f"【{txt.replace('/', ' ')}】ですね。承りました。\n\n冷蔵庫の中で優先的に使いたい食材はありますか？\n（例：鶏肉、キャベツ、特になし）"
        send_reply(tk, msg)

    # 4. 食材の入力（それ以外のテキストはすべて「食材」として扱う）
    else:
        # ここが店長のこだわりのメッセージ
        msg = (
            "入力ありがとうございます。\n"
            "今からコンシェルジュがレシピを考えますので、下のボタンからレシピを受け取ってくださいね。\n\n"
            "買い物リストやレシピの画像保存もできますので、ぜひご利用ください！"
        )
        
        # LIFF URLへ飛ばす
        liff_url = f"https://liff.line.me/2010225388-rXh2LiOR?query={txt}"
        qr = QuickReply(items=[
            QuickReplyItem(action=URIAction(label="🍳 レシピを表示", uri=liff_url))
        ])
        
        send_reply(tk, msg, qr)
