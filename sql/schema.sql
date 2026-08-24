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
-- MODELO DE LIBRO DE OPERACIONES. `cartera_posiciones` es solo la CABECERA
-- de una operación completa (un "trade"): identidad, divisas y ciclo de
-- vida. NO guarda cifras: acciones vivas, precio medio y P&L se derivan
-- recorriendo `cartera_operaciones` en core/cartera.py. Es la única forma
-- de que las ventas parciales y las compras adicionales no destruyan el
-- historial (y lo que habilita el cálculo FIFO para fiscalidad).
--
-- `divisa` es la divisa del COSTE (el bróker liquida en EUR);
-- `divisa_cotizacion` es la divisa en que cotiza el valor en yfinance, para
-- poder convertir el precio de mercado antes de compararlo con el coste.
create table if not exists cartera_posiciones (
    id                bigint generated always as identity primary key,
    usuario_id        text        not null default 'local',
    ticker            text        not null,
    nombre            text,
    divisa            text        not null default 'EUR',
    divisa_cotizacion text,
    estado            text        not null default 'abierta'
                      check (estado in ('abierta', 'cerrada')),
    notas             text,
    abierta_en        date        not null default current_date,
    cerrada_en        date,
    creado_en         timestamptz not null default now()
);
create index if not exists idx_cartera_usuario on cartera_posiciones (usuario_id, estado);
-- Un ticker no puede tener dos posiciones abiertas a la vez: una compra sobre
-- un ticker sin posición viva abre una posición NUEVA (trade independiente),
-- y este índice lo garantiza a nivel de base de datos, no solo de código.
create unique index if not exists idx_cartera_abierta_unica
    on cartera_posiciones (usuario_id, ticker) where estado = 'abierta';

create table if not exists cartera_operaciones (
    id           bigint generated always as identity primary key,
    usuario_id   text        not null default 'local',
    posicion_id  bigint      not null references cartera_posiciones (id) on delete cascade,
    ticker       text        not null,
    tipo         text        not null check (tipo in ('compra', 'venta')),
    acciones     numeric     not null check (acciones > 0),
    precio       numeric     not null check (precio > 0),
    comisiones   numeric     not null default 0 check (comisiones >= 0),
    fecha        date        not null,
    notas        text,
    creado_en    timestamptz not null default now()
);
create index if not exists idx_cartera_ops_posicion on cartera_operaciones (posicion_id, fecha, id);
create index if not exists idx_cartera_ops_usuario on cartera_operaciones (usuario_id);

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

-- ---------------------------------------------------- caché L2 de la API ---
-- Respaldo persistente de lo que casi nunca cambia (estados financieros,
-- perfil de Finnhub, CIK de SEC), para sobrevivir al reinicio del
-- contenedor de Streamlit Community Cloud tras un periodo de inactividad,
-- que vacía por completo la caché en memoria (L1). Tabla genérica de
-- clave/valor: `clave` ya incluye el ticker y el tipo de dato (p. ej.
-- "estados:AAPL", "perfil_finnhub:AAPL"), así que no necesita columnas
-- propias por tipo. Sin usuario_id: el dato no depende de quién pregunta.
create table if not exists cache_api (
    clave        text        not null primary key,
    valor        jsonb       not null,
    guardado_en  timestamptz not null default now()
);

-- ------------------------------------------------------------------ RLS --
-- Con la clave anon y un solo usuario ('local') basta con políticas abiertas.
-- Si más adelante se activa Supabase Auth, sustituir 'local' por auth.uid()::text.
alter table favoritos                 enable row level security;
alter table analisis_historico        enable row level security;
alter table cartera_posiciones        enable row level security;
alter table cartera_operaciones       enable row level security;
alter table paper_trading_posiciones  enable row level security;
alter table paper_trading_niveles     enable row level security;
alter table descripciones_traducidas  enable row level security;
alter table cache_api                 enable row level security;

create policy "acceso_local_favoritos"  on favoritos                for all using (true) with check (true);
create policy "acceso_local_analisis"   on analisis_historico       for all using (true) with check (true);
create policy "acceso_local_cartera"    on cartera_posiciones       for all using (true) with check (true);
create policy "acceso_local_cartera_ops" on cartera_operaciones     for all using (true) with check (true);
create policy "acceso_local_paper"      on paper_trading_posiciones for all using (true) with check (true);
create policy "acceso_local_niveles"    on paper_trading_niveles    for all using (true) with check (true);
create policy "acceso_local_traducciones" on descripciones_traducidas for all using (true) with check (true);
create policy "acceso_local_cache_api"  on cache_api                for all using (true) with check (true);
