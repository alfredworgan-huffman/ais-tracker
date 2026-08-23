# AIS船舶監視・ロギングアプリ (無料枠〜低コスト構成)

登録した最大500隻程度の船をAISで監視・ロギングし、ジオフェンスや通峡予告情報と
組み合わせてアラートを出す構成の最小サンプルです。自宅サーバーは不要で、
すべてクラウドの無料枠〜低コストプランで動かせる想定です。

## 構成

| 役割 | 使用サービス | 料金目安 |
|---|---|---|
| データベース | [Supabase](https://supabase.com/) (PostgreSQL + PostGIS) | 無料枠: 500MBまで無料 |
| 定期実行(スクレイピング) | GitHub Actions | 無料枠: パブリックリポジトリは実質無制限 |
| AIS位置情報取得 | [aisstream.io](https://aisstream.io/) | 無料登録でAPIキー取得可 |
| 地図表示 | Leaflet + OpenStreetMap | 完全無料 |
| フロント配信 | GitHub Pages | 無料 |

## セットアップ手順

1. **Supabaseプロジェクトを作成**
   - https://supabase.com/ で無料アカウント登録 → 新規プロジェクト作成
   - ダッシュボードの `SQL Editor` を開き、`schema.sql` の中身を貼り付けて実行
   - `Project Settings > API` から以下をメモ:
     - `Project URL`
     - `anon public key` (フロント用・読み取り専用)
     - `service_role key` (スクレイピングの書き込み用・**絶対に公開しないこと**)

2. **登録船を追加**
   - Supabaseの `Table Editor` から `vessels` テーブルを開き、監視したい船を
     MMSI・船名付きで登録(最大500行)

3. **aisstream.ioのAPIキーを取得**
   - https://aisstream.io/ で無料登録し、APIキーを発行

4. **このリポジトリをGitHubにアップロード**
   - `Settings > Secrets and variables > Actions` で以下をSecretsに登録:
     - `SUPABASE_URL`
     - `SUPABASE_SERVICE_KEY`
     - `AISSTREAM_API_KEY`
   - `Settings > Actions > General` でワークフローの実行を許可
   - これで `scraper_ais.py` が10分おき、`scraper_tsukou.py` が毎時、
     自動的に実行されます

5. **フロントエンドを公開**
   - `frontend/index.html` の `SUPABASE_URL` / `SUPABASE_ANON_KEY` を
     書き換える(**anonキーのみ**。service_roleキーは使わない)
   - GitHub Pagesを有効化するか、Vercel/Netlifyの無料プランにドラッグ&ドロップで公開

## ジオフェンスの追加方法

`geofences` テーブルに、監視したいエリアのポリゴンを追加します。例:

```sql
insert into geofences (name, polygon)
values (
  'テスト海域',
  st_geographyfromtext('POLYGON((133.9 34.1, 134.1 34.1, 134.1 34.3, 133.9 34.3, 133.9 34.1))')
);
```

ジオフェンスの出入り判定・アラート発報の処理は、このサンプルにはまだ含めていません。
`scraper_ais.py` で位置を保存した後、`st_within` などで `geofences` と照合する処理を
追加すると実装できます(必要であれば別途コードを用意します)。

## コスト概算(500隻・10分間隔・7海域毎時アクセスの場合)

- ログデータ: 年間 約5.5〜7GB → Supabase無料枠(500MB)は数ヶ月で超える見込み
  - 対策1: 古いログ(例: 3ヶ月以上前)を間引いて要約保存する
  - 対策2: Supabaseの有料プラン(Pro: 月$25、8GBまで)に上げる
- GitHub Actions: パブリックリポジトリなら実行時間の制限は事実上なし
  (プライベートリポジトリの場合は無料枠 月2,000分、この構成なら十分収まる想定)
- aisstream.io / 地図表示: 無料枠の範囲内で運用可能

**結論**: 立ち上げ〜数ヶ月程度の検証運用であれば、ほぼ無料で動かせます。
本格運用でログを長期保存し続ける場合は、Supabaseの有料プラン移行
(月$25程度)を見込んでおくと安心です。

## 今回のサンプルに含まれていないもの(今後の拡張)

- ジオフェンスの出入り判定・アラート発報処理
- アラートの通知手段(LINE Notify、メール、Discord Webhookなど)
- 認証機能(現状は誰でも位置情報を閲覧できる設計)
- 名古屋港(船種列が無い)の船種フィルタ対応
