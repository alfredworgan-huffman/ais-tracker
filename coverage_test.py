"""
coverage_test.py
----------------------------------------------------------------
登録船に限らず、指定した広い範囲(本州近海全体)で受信できる
「全ての」AIS位置情報を一時的に収集し、coverage_snapshotテーブルに保存する。

目的: aisstream.io(無料枠)の実際の受信カバレッジを検証するための、
一回限りの診断用スクリプト。普段の定期取得(scraper_ais.py)とは別物で、
継続的には実行しない想定(手動実行専用のワークフローから呼び出す)。

必要な環境変数:
  SUPABASE_URL
  SUPABASE_SERVICE_KEY
  AISSTREAM_API_KEY
  LISTEN_SECONDS  (デフォルト180秒。長くするほど多くの船を捕捉できるが、
                    その分メッセージ量も増える点に注意)
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
LISTEN_SECONDS = int(os.environ.get("LISTEN_SECONDS", "180"))

# 本州近海全体をざっくり覆う範囲(北海道南部〜九州北部、太平洋側・日本海側の沿岸を含む)
# 必要に応じて範囲を調整してください。広すぎるとメッセージ量が非常に多くなる点に注意。
BOUNDING_BOX = [[30.0, 128.0], [42.0, 143.0]]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


async def collect_all_positions() -> dict[int, dict]:
    """MMSIで絞り込まず、指定範囲内の全船の位置情報を集める。
    同じ船から複数報告があっても、最後に受信したものだけを残す。"""
    latest: dict[int, dict] = {}

    async with websockets.connect("wss://stream.aisstream.io/v0/stream") as ws:
        subscribe_msg = {
            "APIKey": AISSTREAM_API_KEY,
            "BoundingBoxes": [BOUNDING_BOX],
            "FilterMessageTypes": ["PositionReport"],
            # FiltersShipMMSIを指定しない = 範囲内の全船が対象
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
                        "lat": report["Latitude"],
                        "lon": report["Longitude"],
                        "sog": report.get("Sog"),
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }
        except TimeoutError:
            pass

    return latest


def save_snapshot(positions: dict[int, dict]) -> None:
    if not positions:
        print("受信データなし。")
        return

    run_label = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%MUTC")
    rows = [{**p, "run_label": run_label} for p in positions.values()]

    url = f"{SUPABASE_URL}/rest/v1/coverage_snapshot"
    res = requests.post(url, headers=HEADERS, json=rows, timeout=30)
    if res.status_code >= 300:
        print("書き込み失敗:", res.status_code, res.text)
        res.raise_for_status()
    print(f"{len(rows)}隻分のスナップショットを保存しました(run_label={run_label})。")


def main():
    print(f"範囲: {BOUNDING_BOX} / 受信時間: {LISTEN_SECONDS}秒")
    positions = asyncio.run(collect_all_positions())
    print(f"受信できたユニークMMSI数: {len(positions)}")
    save_snapshot(positions)


if __name__ == "__main__":
    main()
