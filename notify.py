"""
notify.py
----------------------------------------------------------------
Discord Webhookへアラートメッセージを送るための共通関数。

事前準備(Discord側):
  1. 通知を受け取りたいDiscordサーバーのテキストチャンネルを開く
  2. チャンネル設定 → 連携サービス → Webhook → 「新しいウェブフック」を作成
  3. 発行された「ウェブフックURL」をコピー
  4. GitHub Secretsに DISCORD_WEBHOOK_URL として登録する

環境変数 DISCORD_WEBHOOK_URL が未設定の場合は、送信をスキップする
(Discordを使わない場合でも他の処理が止まらないようにするため)。
----------------------------------------------------------------
"""

import os
import requests

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")


def send_discord_alert(message: str) -> None:
    if not DISCORD_WEBHOOK_URL:
        print("DISCORD_WEBHOOK_URL未設定のため通知をスキップ:", message)
        return
    try:
        res = requests.post(DISCORD_WEBHOOK_URL, json={"content": message}, timeout=15)
        if res.status_code >= 300:
            print("Discord通知失敗:", res.status_code, res.text)
    except Exception as e:
        print("Discord通知でエラー:", e)
