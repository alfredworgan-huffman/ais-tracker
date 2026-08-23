-- ============================================================
-- ジオフェンス判定 追加分
-- Supabaseの SQL Editor に貼り付けて実行してください
-- (schema.sql を実行済みであることが前提です)
-- ============================================================

-- ----------------------------------------------------------
-- 1. 船ごと・ジオフェンスごとの「現在の状態(中/外)」を覚えておくテーブル
--    前回との比較で「入った/出た」を判定するために使う
-- ----------------------------------------------------------
create table if not exists vessel_geofence_state (
    mmsi         bigint not null references vessels(mmsi),
    geofence_id  bigint not null references geofences(id),
    inside       boolean not null,
    updated_at   timestamptz not null default now(),
    primary key (mmsi, geofence_id)
);

-- ----------------------------------------------------------
-- 2. 「ある緯度経度が、どのジオフェンスに含まれるか」を返す関数
--    Pythonからは /rest/v1/rpc/point_in_geofences として呼び出す
-- ----------------------------------------------------------
create or replace function point_in_geofences(p_lat double precision, p_lon double precision)
returns table(geofence_id bigint, geofence_name text)
language sql stable
as $$
    select id, name
    from geofences
    where active = true
      and st_covers(polygon, st_setsrid(st_makepoint(p_lon, p_lat), 4326)::geography)
$$;
