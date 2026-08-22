-- =====================================================================
-- StockScanner · esquema Supabase (PostgreSQL)
-- Ejecutar en el SQL Editor del proyecto Supabase.
-- Diseñado para escalar a multiusuario: cada tabla lleva `usuario_id`.
-- =====================================================================

-- ----------------------------------------------------------- favoritos --
create table if not exists favoritos (
    id          bigint generated always as identity primary key,
    usuario_id  text        not null default 'local',
    ticker      text        not null,
    nombre      text,
    sector      text,
    creado_en   timestamptz not null default now(),
    unique (usuario_id, ticker)
);
create index if not exists idx_favoritos_usuario on favoritos (usuario_id);

-- ------------------------------------------- histórico de análisis ------
create table if not exists analisis_historico (
    id                  bigint generated always as identity primary key,
    usuario_id          text        not null default 'local',
    ticker              text        not null,
    precio              numeric,
    fair_value          numeric,
    upside_pct          numeric,
    puntuacion_calidad  numeric,
    puntuacion_timing   numeric,
    senal_timing        text,
    veredicto           text,
    payload             jsonb,
    creado_en           timestamptz not null default now()
);
create index if not exists idx_analisis_ticker on analisis_historico (usuario_id, ticker, creado_en desc);

-- ------------------------------------------------------------- cartera --
create table if not exists cartera_posiciones (
    id              bigint generated always as identity primary key,
    usuario_id      text        not null default 'local',
    ticker          text        not null,
    acciones        numeric     not null,
    precio_compra   numeric     not null,
    fecha_compra    date,
    divisa          text        default 'USD',
    comisiones      numeric     default 0,
    estado          text        not null default 'abierta',
    precio_venta    numeric,
    fecha_venta     date,
    notas           text,
    creado_en       timestamptz not null default now()
);
create index if not exists idx_cartera_usuario on cartera_posiciones (usuario_id, estado);

-- ------------------------------------------------------- paper trading --
create table if not exists paper_trading_posiciones (
    id                        bigint generated always as identity primary key,
    usuario_id                text        not null default 'local',
    ticker                    text        not null,
    estado                    text        not null default 'abierta',
    precio_apertura           numeric,
    precio_medio_estimado     numeric,
    objetivo_medio_estimado   numeric,
    stop_loss                 numeric,
    puntuacion_calidad        numeric,
    puntuacion_timing         numeric,
    veredicto                 text,
    precio_cierre             numeric,
    motivo_cierre             text,
    abierta_en                timestamptz not null default now(),
    cerrada_en                timestamptz
);
create index if not exists idx_paper_usuario on paper_trading_posiciones (usuario_id, estado);

create table if not exists paper_trading_niveles (
    id            bigint generated always as identity primary key,
    posicion_id   bigint      not null references paper_trading_posiciones (id) on delete cascade,
    tipo          text        not null check (tipo in ('entrada', 'salida', 'stop')),
    nivel         int         not null,
    precio        numeric     not null,
    peso          numeric,
    ejecutado     boolean     not null default false,
    ejecutado_en  timestamptz,
    motivos       text
);
create index if not exists idx_niveles_posicion on paper_trading_niveles (posicion_id);

-- ------------------------------------------- descripciones traducidas ---
-- Caché de la traducción al español de `longBusinessSummary` (yfinance,
-- siempre en inglés). No lleva usuario_id: la traducción no depende del
-- usuario, es la misma para todos y se comparte. `hash_original` es un
-- hash corto del texto en inglés: si yfinance actualiza la descripción
-- (cambio de negocio, adquisición, etc.), el hash deja de coincidir y se
-- vuelve a traducir en vez de servir una traducción obsoleta desde caché.
create table if not exists descripciones_traducidas (
    ticker          text        not null primary key,
    hash_original   text        not null,
    texto_original  text        not null,
    texto_traducido text        not null,
    traducido_en    timestamptz not null default now()
);

-- ------------------------------------------------------------------ RLS --
-- Con la clave anon y un solo usuario ('local') basta con políticas abiertas.
-- Si más adelante se activa Supabase Auth, sustituir 'local' por auth.uid()::text.
alter table favoritos                 enable row level security;
alter table analisis_historico        enable row level security;
alter table cartera_posiciones        enable row level security;
alter table paper_trading_posiciones  enable row level security;
alter table paper_trading_niveles     enable row level security;
alter table descripciones_traducidas  enable row level security;

create policy "acceso_local_favoritos"  on favoritos                for all using (true) with check (true);
create policy "acceso_local_analisis"   on analisis_historico       for all using (true) with check (true);
create policy "acceso_local_cartera"    on cartera_posiciones       for all using (true) with check (true);
create policy "acceso_local_paper"      on paper_trading_posiciones for all using (true) with check (true);
create policy "acceso_local_niveles"    on paper_trading_niveles    for all using (true) with check (true);
create policy "acceso_local_traducciones" on descripciones_traducidas for all using (true) with check (true);
