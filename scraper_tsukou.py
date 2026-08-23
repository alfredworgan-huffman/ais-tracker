"""
scraper_tsukou.py
----------------------------------------------------------------
海上保安庁 各海上交通センターの「大型船入航予定情報」ページを取得し、
表から船名・船種・予定時刻を抽出、登録船と名前が一致すればアラートを出す。

GitHub Actionsから毎時1回実行される想定。

対象: 東京湾・伊勢湾・大阪湾・備讃瀬戸・来島海峡・関門海峡 の6箇所
  (名古屋港は表に「船種」列が無いため、船種フィルタが必要な場合は対象外にしている)

必要な環境変数:
  SUPABASE_URL
  SUPABASE_SERVICE_KEY
----------------------------------------------------------------
"""

import os
import re
import unicodedata
import requests
import pandas as pd
from datetime import datetime, timezone
from notify import send_discord_alert

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

# center名 -> URL (24時間表示のページ)
CENTERS = {
    "tokyowan": "https://www6.kaiho.mlit.go.jp/tokyowan/schedule/URAGA/schedule_1.html",
    "isewan":   "https://www6.kaiho.mlit.go.jp/isewan/schedule/IRAGO/schedule_1.html",
    "osakawan": "https://www6.kaiho.mlit.go.jp/osakawan/schedule/AKASHI/schedule_1.html",
    "bisan":    "https://www6.kaiho.mlit.go.jp/bisan/schedule/BISANHIGASHI/schedule_1.html",
    "kurushima":"https://www6.kaiho.mlit.go.jp/kurushima/schedule/KURUSHIMA/schedule_1.html",
    "kanmon":   "https://www6.kaiho.mlit.go.jp/kanmon/schedule/KANMON/schedule_1.html",
}

# 対象を絞りたい船種があればここに書く(空リストなら全船種を対象)
# 例: TARGET_SHIP_TYPES = ["タンカー", "油槽船", "LPG・LNG船"]
TARGET_SHIP_TYPES: list[str] = []


def normalize_name(name: str) -> str:
    """船名の表記ゆれを吸収するための正規化。
    全角/半角統一、前後の空白除去、大文字化を行う。"""
    name = unicodedata.normalize("NFKC", name)
    name = re.sub(r"\s+", "", name)
    return name.upper()


def fetch_registered_vessels() -> dict[str, int]:
    """vesselsテーブルから {正規化した船名: mmsi} の辞書を作る"""
    url = f"{SUPABASE_URL}/rest/v1/vessels?select=mmsi,name&active=eq.true"
    res = requests.get(url, headers=HEADERS, timeout=30)
    res.raise_for_status()
    return {normalize_name(row["name"]): row["mmsi"] for row in res.json()}


def parse_center_page(center: str, url: str) -> pd.DataFrame:
    """1センター分のページから表を抽出し、船名・船種・列を持つDataFrameを返す"""
    res = requests.get(url, timeout=30)
    res.raise_for_status()
    tables = pd.read_html(res.text)  # ページ内の<table>を全部拾う

    rows = []
    for table in tables:
        cols = [str(c) for c in table.columns]
        if "船名" not in cols or ("船種" not in cols and "種別" not in cols):
            continue  # 目的の表でなければスキップ(メニュー等の表を除外)
        type_col = "船種" if "船種" in cols else "種別"
        for _, r in table.iterrows():
            ship_name = str(r.get("船名", "")).strip()
            if not ship_name or ship_name.lower() == "nan":
                continue
            rows.append({
                "center": center,
                "ship_name": ship_name,
                "ship_type": str(r.get(type_col, "")).strip(),
                "scheduled_time_raw": str(r.get("入航予定時刻", r.get("日時", ""))).strip(),
            })
    return pd.DataFrame(rows)


def build_alert(mmsi: int, ship_name: str, center: str) -> dict:
    return {
        "mmsi": mmsi,
        "alert_type": "tsukou",
        "message": f"登録船「{ship_name}」が{center}の通峡予告情報に掲載されました。",
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def main():
    registered = fetch_registered_vessels()
    print(f"登録船: {len(registered)}隻")

    notice_rows = []
    alert_rows = []

    for center, url in CENTERS.items():
        try:
            df = parse_center_page(center, url)
        except Exception as e:
            print(f"[{center}] 取得/パース失敗: {e}")
            continue

        if TARGET_SHIP_TYPES:
            df = df[df["ship_type"].isin(TARGET_SHIP_TYPES)]

        for _, row in df.iterrows():
            norm = normalize_name(row["ship_name"])
            matched_mmsi = registered.get(norm)

            notice_rows.append({
                "center": center,
                "ship_name": row["ship_name"],
                "ship_type": row["ship_type"],
                "matched_mmsi": matched_mmsi,
                "raw_row": row.to_dict(),
            })

            if matched_mmsi:
                alert_rows.append(build_alert(matched_mmsi, row["ship_name"], center))

        print(f"[{center}] {len(df)}件取得")

    if notice_rows:
        res = requests.post(f"{SUPABASE_URL}/rest/v1/tsukou_notices",
                             headers=HEADERS, json=notice_rows, timeout=30)
        res.raise_for_status()
        print(f"通峡予告情報 {len(notice_rows)}件を保存しました。")

    if alert_rows:
        res = requests.post(f"{SUPABASE_URL}/rest/v1/alerts",
                             headers=HEADERS, json=alert_rows, timeout=30)
        res.raise_for_status()
        print(f"アラート {len(alert_rows)}件を発報しました。")
        for a in alert_rows:
            send_discord_alert(a["message"])
    else:
        print("登録船と一致する通峡予告はありませんでした。")


if __name__ == "__main__":
    main()
