# Implantação gratuita

Limites conferidos em novembro de 2026. Planos gratuitos mudam: confirme nos
links oficiais antes de decidir.

## 1. Local (recomendado para começar) — custo R$ 0

```bash
pip install -r requirements.txt
cp .env.example .env
streamlit run dashboard/streamlit_app.py     # painel
uvicorn app:app --port 8000                  # API opcional
```

SQLite em `data/empire.db`. Backup = copiar o arquivo.

## 2. Painel no Streamlit Community Cloud

1. Suba o repositório no GitHub (privado ou público).
2. Em https://share.streamlit.io, conecte o GitHub e escolha o repositório.
3. Main file: `dashboard/streamlit_app.py`.
4. Em *Advanced settings → Secrets*, cole o conteúdo do seu `.env`
   (o Streamlit expõe os secrets como variáveis de ambiente na leitura, e o
   `core/config.py` já lê de `os.environ`).
5. Limites típicos do plano gratuito: ~1 GB de RAM por app, hibernação por
   inatividade, 1 app por repositório. Confirme em https://docs.streamlit.io.

Atenção: no Community Cloud o disco é efêmero. Para histórico permanente,
configure Supabase (item 4).

## 3. GitHub Actions (rotinas diária e semanal)

Já existem `.github/workflows/daily_analysis.yml`, `weekly_report.yml` e
`tests.yml`.

- Repositório **público**: minutos de Actions gratuitos e ilimitados.
- Repositório **privado**: ~2.000 minutos/mês no plano Free — as duas rotinas
  consomem cerca de 120 min/mês.
- Configure em *Settings → Secrets and variables → Actions*:
  `SUPABASE_URL`, `SUPABASE_KEY`, `GEMINI_API_KEY` (opcionais) e a variável
  `DATABASE_BACKEND` (`sqlite` ou `supabase`).
- Sem Supabase, cada execução começa com banco vazio: o workflow anexa o
  `data/empire.db` como artefato para você baixar.

## 4. Supabase (banco + autenticação) — plano gratuito

1. Crie o projeto em https://supabase.com.
2. SQL Editor → cole `database/schema.sql` → Run.
3. Copie *Project URL* e a chave `service_role` (ou `anon`, se for usar RLS com
   usuários reais) para `SUPABASE_URL` e `SUPABASE_KEY`.
4. `DATABASE_BACKEND=supabase`.
5. O plano gratuito limita armazenamento e pausa projetos ociosos; verifique em
   https://supabase.com/pricing.

O esquema já habilita Row Level Security nas tabelas de dados. Para multiusuário,
crie políticas por `auth.uid()` (há um exemplo comentado no final do arquivo).

## 5. API (opcional)

`app.py` é FastAPI puro, roda em qualquer host Python: Render free, Fly.io,
Railway, Hugging Face Spaces (Docker). Se o host hibernar, o painel continua
funcionando localmente. Não é necessário para operar.

## 6. Checklist pós-deploy

- [ ] `.env` preenchido apenas no host/Secrets, nunca no repositório
- [ ] `APP_REQUIRE_LOGIN=true` se o painel ficar exposto
- [ ] Senha do proprietário criada em Configurações → Segurança
- [ ] Comissões reais cadastradas em Configurações → Marketplaces
- [ ] Rotinas conferidas em Automações
- [ ] Primeira execução do CEO AI testada
