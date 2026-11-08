-- ============================================================================
-- E-COMMERCE AI EMPIRE - esquema oficial (PostgreSQL / Supabase, plano free)
-- ============================================================================
-- Como usar no Supabase:
--   1. Crie um projeto gratuito em https://supabase.com
--   2. SQL Editor -> cole este arquivo -> Run
--   3. Copie "Project URL" e a chave "anon/service_role" para o seu .env:
--        DATABASE_BACKEND=supabase
--        SUPABASE_URL=...
--        SUPABASE_KEY=...
--   4. Nunca versione essas chaves. O .env está no .gitignore.
--
-- O SQLite local (padrão) cria as mesmas tabelas automaticamente em
-- database/repository.py, sem necessidade de nenhum serviço externo.
-- ============================================================================

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------- usuários --
create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  email text unique not null,
  full_name text,
  role text not null default 'owner' check (role in ('owner','admin','analyst','viewer')),
  password_hash text,               -- scrypt/bcrypt; nunca senha em texto puro
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ----------------------------------------------------------------- agentes --
create table if not exists agents (
  id uuid primary key default gen_random_uuid(),
  name text unique not null,
  role text not null,
  description text,
  status text not null default 'ativo',
  capabilities jsonb not null default '[]'::jsonb,
  instructions text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ------------------------------------------------------------------ tarefas --
create table if not exists tasks (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid references tasks(id) on delete set null,
  agent text not null,
  task_type text not null,
  title text not null,
  status text not null default 'pendente'
    check (status in ('pendente','em_execucao','concluida','falhou','aguardando_aprovacao','cancelada')),
  priority int not null default 3,
  payload jsonb not null default '{}'::jsonb,
  result jsonb,
  error text,
  attempts int not null default 0,
  max_attempts int not null default 3,
  dedupe_key text,
  timeout_seconds int not null default 300,
  requested_by text,
  is_demo boolean not null default false,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz
);
create index if not exists idx_tasks_status on tasks(status);
create index if not exists idx_tasks_dedupe on tasks(dedupe_key);

create table if not exists task_events (
  id uuid primary key default gen_random_uuid(),
  task_id uuid references tasks(id) on delete cascade,
  event text not null,
  message text,
  created_at timestamptz not null default now()
);

-- ----------------------------------------------------------------- memórias --
create table if not exists memories (
  id uuid primary key default gen_random_uuid(),
  scope text not null default 'global',
  key text not null,
  value jsonb not null,
  tags text[] default '{}',
  importance int not null default 3,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (scope, key)
);

-- ---------------------------------------------------------------- aprovações --
create table if not exists approvals (
  id uuid primary key default gen_random_uuid(),
  action text not null,
  risk_level text not null default 'alto',
  resource_type text,
  resource_id text,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'pendente'
    check (status in ('pendente','aprovado','rejeitado','cancelado','expirado')),
  requested_by_agent text,
  requested_by text,
  decided_by text,
  decided_at timestamptz,
  note text,
  created_at timestamptz not null default now()
);
create index if not exists idx_approvals_status on approvals(status);

-- -------------------------------------------------------------------- logs --
create table if not exists audit_logs (
  id uuid primary key default gen_random_uuid(),
  actor text not null,
  action text not null,
  resource_type text,
  resource_id text,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_audit_created on audit_logs(created_at desc);

-- --------------------------------------------------------------- catálogo --
create table if not exists categories (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  parent_id uuid references categories(id) on delete set null,
  created_at timestamptz not null default now()
);

create table if not exists suppliers (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  contact text,
  url text,
  min_qty int not null default 1,
  unit_price numeric(12,2) not null default 0,
  lead_time_days int not null default 0,
  shipping_cost numeric(12,2) not null default 0,
  pickup_available boolean not null default false,
  same_day_pickup boolean not null default false,
  city text,
  state text,
  notes text,
  risk_notes text,
  is_demo boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists products (
  id uuid primary key default gen_random_uuid(),
  sku text,
  name text not null,
  category text,
  description text,
  purchase_price numeric(12,2) not null default 0,
  extra_cost numeric(12,2) not null default 0,
  sale_price numeric(12,2) not null default 0,
  supplier_id uuid references suppliers(id) on delete set null,
  marketplace text,
  status text not null default 'ativo',
  source text default 'manual',
  is_demo boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_products_marketplace on products(marketplace);

create table if not exists competitors (
  id uuid primary key default gen_random_uuid(),
  product_id uuid references products(id) on delete cascade,
  name text not null,
  marketplace text,
  price numeric(12,2),
  url text,
  rating numeric(3,2),
  reviews int,
  differentials text,
  source text,
  collected_at timestamptz not null default now(),
  is_demo boolean not null default false
);

create table if not exists listings (
  id uuid primary key default gen_random_uuid(),
  product_id uuid references products(id) on delete cascade,
  marketplace text not null,
  external_id text,
  title text,
  description text,
  price numeric(12,2),
  status text not null default 'rascunho',
  score numeric(5,2),
  url text,
  is_demo boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists marketplaces (
  id uuid primary key default gen_random_uuid(),
  slug text unique not null,
  name text not null,
  commission_pct numeric(6,3) not null default 0,
  fixed_fee numeric(12,2) not null default 0,
  handling_days int not null default 0,
  delivery_days int not null default 0,
  sla_source text,
  notes text,
  source text,
  updated_at timestamptz not null default now()
);

create table if not exists costs (
  id uuid primary key default gen_random_uuid(),
  product_id uuid references products(id) on delete cascade,
  kind text not null,
  amount numeric(12,2) not null default 0,
  note text,
  created_at timestamptz not null default now()
);

create table if not exists sales (
  id uuid primary key default gen_random_uuid(),
  product_id uuid references products(id) on delete set null,
  listing_id uuid references listings(id) on delete set null,
  marketplace text,
  quantity int not null default 1,
  unit_price numeric(12,2) not null default 0,
  fees numeric(12,2) not null default 0,
  shipping numeric(12,2) not null default 0,
  taxes numeric(12,2) not null default 0,
  total numeric(12,2) not null default 0,
  sold_at timestamptz not null default now(),
  is_demo boolean not null default false
);

-- --------------------------------------------------------- oportunidades --
create table if not exists stock_movements (
  id text primary key, product_id text not null, kind text not null default 'entrada',
  quantity integer not null default 0, note text, reference text,
  created_at timestamptz not null default now(), is_demo boolean not null default false
);

create table if not exists opportunities (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  category text,
  marketplace text,
  price_found numeric(12,2),
  source text,
  consulted_at timestamptz not null default now(),
  cost_estimate numeric(12,2),
  margin_estimate numeric(6,2),
  score numeric(5,2),
  recommendation text,
  breakdown jsonb not null default '{}'::jsonb,
  risks text,
  is_demo boolean not null default false,
  created_at timestamptz not null default now()
);

-- ------------------------------------------------- relatórios/automações --
create table if not exists reports (
  id uuid primary key default gen_random_uuid(),
  kind text not null,
  title text not null,
  body text not null,
  period_start timestamptz,
  period_end timestamptz,
  is_demo boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists automations (
  id uuid primary key default gen_random_uuid(),
  name text unique not null,
  schedule_cron text,
  job text not null,
  enabled boolean not null default true,
  last_run_at timestamptz,
  next_run_at timestamptz,
  config jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists ai_usage (
  id uuid primary key default gen_random_uuid(),
  provider text not null,
  model text,
  task_id uuid,
  agent text,
  prompt_tokens int default 0,
  completion_tokens int default 0,
  cost_usd numeric(10,6) default 0,
  latency_ms int default 0,
  ok boolean not null default true,
  error text,
  created_at timestamptz not null default now()
);

create table if not exists settings_kv (
  id uuid default gen_random_uuid(),
  key text primary key,
  value jsonb not null,
  updated_at timestamptz not null default now()
);

-- ============================================================================
-- Row Level Security: cada usuário só vê os próprios registros.
-- O papel 'owner' (service_role no backend) mantém acesso total.
-- ============================================================================
do $$
declare t text;
begin
  foreach t in array array[
    'products','competitors','listings','suppliers','costs','sales','tasks',
    'task_events','memories','approvals','audit_logs','reports','automations',
    'opportunities','categories','marketplaces','ai_usage'
  ]
  loop
    execute format('alter table %I enable row level security', t);
  end loop;
end $$;

-- Exemplo de política (repita para cada tabela de dados do usuário):
-- create policy "own rows" on products
--   for all using (auth.uid() = created_by) with check (auth.uid() = created_by);
-- Observação: no SQLite local (single-tenant) o controle de acesso é feito
-- pela camada de permissões (core/permissions.py) e pelo login do painel.
