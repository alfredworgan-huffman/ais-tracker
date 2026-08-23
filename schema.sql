-- ============================================================
-- AIS船舶監視アプリ DBスキーマ (Supabase / PostgreSQL + PostGIS)
-- Supabaseのダッシュボード > SQL Editor に貼り付けて実行してください
-- ============================================================

-- PostGIS拡張を有効化 (Supabaseは標準でインストール済みのことが多い)
create extension if not exists postgis;

-- ----------------------------------------------------------
-- 1. 登録船マスタ (監視対象の最大500隻を登録する台帳)
-- ----------------------------------------------------------
create table if not exists vessels (
    id           bigserial primary key,
    mmsi         bigint unique not null,      -- AISの船舶識別番号
    imo          bigint,                      -- IMO番号(通峡情報には出ないが将来用)
    name         text not null,               -- 船名 (AIS上の表記)
    ship_type    text,                        -- 船種 (任意メモ)
    active       boolean not null default true,
    created_at   timestamptz not null default now()
);

-- ----------------------------------------------------------
-- 2. 位置ログ (10分おきに記録する航跡データ)
-- ----------------------------------------------------------
create table if not exists positions (
    id           bigserial primary key,
    mmsi         bigint not null references vessels(mmsi),
    ts           timestamptz not null,
    lat          double precision not null,
    lon          double precision not null,
    sog          double precision,            -- 対地速力(ノット)
    cog          double precision,            -- 対地針路
    geom         geography(Point, 4326) generated always as (
                     geography(st_setsrid(st_makepoint(lon, lat), 4326))
                 ) stored,
    created_at   timestamptz not null default now()
);
create index if not exists idx_positions_mmsi_ts on positions (mmsi, ts desc);
create index if not exists idx_positions_geom on positions using gist (geom);

-- ----------------------------------------------------------
-- 3. ジオフェンス (監視したいエリアのポリゴン)
-- ----------------------------------------------------------
create table if not exists geofences (
    id           bigserial primary key,
    name         text not null,
    polygon      geography(Polygon, 4326) not null,
    active       boolean not null default true
);

-- ジオフェンスの出入り状態の変化を記録
create table if not exists geofence_events (
    id           bigserial primary key,
    mmsi         bigint not null references vessels(mmsi),
    geofence_id  bigint not null references geofences(id),
    event_type   text not null check (event_type in ('enter', 'exit')),
    ts           timestamptz not null default now()
);

-- ----------------------------------------------------------
-- 4. 通峡予告情報 (海上交通センターの入航予定情報のスクレイピング結果)
-- ----------------------------------------------------------
create table if not exists tsukou_notices (
    id             bigserial primary key,
    center         text not null,             -- 例: 'kanmon', 'tokyowan' など
    ship_name      text not null,
    ship_type      text,
    scheduled_time timestamptz,
    direction      text,                       -- 東航/西航/北航/南航など
    matched_mmsi   bigint references vessels(mmsi),  -- 登録船と一致した場合のみ値が入る
    raw_row        jsonb,                       -- パースした行全体を保存(デバッグ用)
    created_at     timestamptz not null default now()
);
create index if not exists idx_tsukou_matched on tsukou_notices (matched_mmsi);

-- ----------------------------------------------------------
-- 5. アラート (ジオフェンス・通峡予告どちらの発報も一元管理)
-- ----------------------------------------------------------
create table if not exists alerts (
    id           bigserial primary key,
    mmsi         bigint not null references vessels(mmsi),
    alert_type   text not null,                -- 'geofence' or 'tsukou'
    message      text not null,
    ts           timestamptz not null default now(),
    acknowledged boolean not null default false
);

-- ----------------------------------------------------------
-- 6. Row Level Security (フロントから読み取り専用で使う場合の設定例)
-- ----------------------------------------------------------
alter table vessels enable row level security;
alter table positions enable row level security;
alter table alerts enable row level security;

create policy "public read positions" on positions for select using (true);
create policy "public read vessels" on vessels for select using (true);
create policy "public read alerts" on alerts for select using (true);
-- 書き込みはservice_role(GitHub Actions側)のみ許可されるため、
-- 上記のようにanonキーには select のみ与えるのが安全です。
