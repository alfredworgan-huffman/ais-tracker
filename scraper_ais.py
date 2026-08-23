"""
scraper_ais.py
----------------------------------------------------------------
aisstream.io から登録船(最大500隻)のAIS位置情報を取得し、Supabaseに保存する。
GitHub Actionsから10分おきに実行される想定。

1回の実行で、指定した時間だけWebSocket接続を開いて位置情報を集め、
各MMSIごとに最新の1件だけをDBに書き込む(10分間隔ロギングのため)。

必要な環境変数:
  SUPABASE_URL          例: https://xxxx.supabase.co
  SUPABASE_SERVICE_KEY  Supabaseのservice_roleキー(書き込み権限が必要)
  AISSTREAM_API_KEY     aisstream.io のAPIキー(無料登録で取得)
  LISTEN_SECONDS        1回の接続で待ち受ける秒数(デフォルト90秒)
----------------------------------------------------------------
"""

import os
import json
import asyncio
import websockets
import requests
from datetime import datetime, timezone

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
AISSTREAM_API_KEY = os.environ["AISSTREAM_API_KEY"]
LISTEN_SECONDS = int(os.environ.get("LISTEN_SECONDS", "240"))

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


def fetch_registered_mmsi_list() -> list[int]:
    """vesselsテーブルから active=true の船のMMSI一覧を取得する"""
    url = f"{SUPABASE_URL}/rest/v1/vessels?select=mmsi&active=eq.true"
    res = requests.get(url, headers=HEADERS, timeout=30)
    res.raise_for_status()
    return [row["mmsi"] for row in res.json()]


async def collect_positions(mmsi_list: list[int]) -> dict[int, dict]:
    """aisstream.io に接続し、指定秒数だけ位置情報を集める。
    同じ船から複数報告があっても、最後に受信したものだけを残す。"""
    latest: dict[int, dict] = {}
    if not mmsi_list:
        return latest

    async with websockets.connect("wss://stream.aisstream.io/v0/stream") as ws:
        subscribe_msg = {
            "APIKey": AISSTREAM_API_KEY,
            "BoundingBoxes": [[[-90, -180], [90, 180]]],  # 全世界(MMSIで絞るため広域指定)
            "FiltersShipMMSI": [str(m) for m in mmsi_list],
            "FilterMessageTypes": ["PositionReport"],
        }
        await ws.send(json.dumps(subscribe_msg))

        try:
            async with asyncio.timeout(LISTEN_SECONDS):
                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("MessageType") != "PositionReport":
                        continue
                    report = msg["Message"]["PositionReport"]
                    mmsi = report["UserID"]
                    latest[mmsi] = {
                        "mmsi": mmsi,
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "lat": report["Latitude"],
                        "lon": report["Longitude"],
                        "sog": report.get("Sog"),
                        "cog": report.get("Cog"),
                    }
        except TimeoutError:
            pass  # 規定秒数経過したら正常終了

    return latest


def save_positions(positions: dict[int, dict]) -> None:
    """収集した位置情報をpositionsテーブルにまとめて書き込む"""
    if not positions:
        print("受信データなし。今回はスキップします。")
        return

    rows = list(positions.values())
    url = f"{SUPABASE_URL}/rest/v1/positions"
    res = requests.post(url, headers=HEADERS, json=rows, timeout=30)
    if res.status_code >= 300:
        print("書き込み失敗:", res.status_code, res.text)
        res.raise_for_status()
    print(f"{len(rows)}隻分の位置情報を保存しました。")


def main():
    mmsi_list = fetch_registered_mmsi_list()
    print(f"監視対象: {len(mmsi_list)}隻")
    positions = asyncio.run(collect_positions(mmsi_list))
    save_positions(positions)


if __name__ == "__main__":
    main()
