# E-COMMERCE AI EMPIRE

Centro de inteligência comercial multiagente para operar Shopee, Mercado Livre,
TikTok Shop, Instagram, loja própria e WooCommerce.

Não é um chatbot: é um sistema que pesquisa, calcula, pontua, redige, registra
histórico e **bloqueia ações de risco até a sua aprovação**. Todo número vem de
código determinístico; a IA só explica o resultado.

- Idioma: português brasileiro · Moeda: BRL · Fuso: America/Sao_Paulo
- Orçamento de operação: **R$ 0** (SQLite local, IA opcional, CSV no lugar de API)
- Python 3.11 · FastAPI · Streamlit · Pydantic · SQLite/Supabase · pytest
- Licença MIT

---

## 1. O que já está implementado

| Módulo | Estado | Observação |
|---|---|---|
| Orquestrador (CEO AI) | ✅ funcionando | plano → tarefas → execução → validação → relatório |
| 12 agentes independentes | ✅ funcionando | responsabilidades e ferramentas distintas |
| Product Opportunity Score | ✅ funcionando | 0–100, pesos do projeto, explicação por critério |
| Calculadora financeira | ✅ funcionando | margem, ROI, preço mínimo, ponto de equilíbrio |
| Banco + memória + histórico | ✅ funcionando | SQLite persistente; esquema Supabase pronto |
| Tarefas com estados e retentativa | ✅ funcionando | pendente/em execução/concluída/falhou/aguardando aprovação |
| Aprovações e auditoria | ✅ funcionando | 9 ações protegidas, histórico de quem autorizou |
| Painel Streamlit (20 páginas) | ✅ funcionando | todas as páginas ligadas a dados reais |
| API REST (FastAPI) | ✅ funcionando | `/docs` com todos os endpoints |
| Importação/exportação CSV | ✅ funcionando | produtos, concorrentes, fornecedores, vendas, oportunidades |
| Conectores Shopee/ML/TikTok/Instagram/Woo | ✅ código pronto, **não conectados** | exigem credenciais suas |
| Marketing, SEO, roteiros, conteúdo | ✅ funcionando | texto em pt-BR, prioriza orgânico |
| Automações diária/semanal | ✅ funcionando | GitHub Actions + scripts prontos |
| IA generativa | ⚙️ opcional | Gemini/OpenAI-compatible; modo offline completo |
| Custo por token | ⚙️ informativo | sem preço configurado o custo fica 0 |

**Depende de configuração externa (sua parte):** credenciais das APIs de
marketplace, chave de IA (opcional) e, se quiser nuvem, um projeto Supabase.

---

## 2. Arquitetura

```
                        ┌──────────────────────────────┐
   você  ── comando ──▶ │  CEO AI  (core/orchestrator) │
                        └──────────────┬───────────────┘
                                       │ core/planner.py
                                       ▼
             ┌───────────────────────────────────────────────┐
             │ Task manager: fila, estados, retentativa,     │
             │ deduplicação, timeout, eventos                │
             └───────┬───────────────────────────────────────┘
                     ▼
   ┌─────────────── 12 especialistas ────────────────────────┐
   │ product_hunter   market_analyst   marketplace_manager   │
   │ financial        marketing        video_creator         │
   │ seo              supplier_hunter  customer              │
   │ automation       content_intelligence                   │
   └───────┬──────────────────────────────┬──────────────────┘
           │ cálculos determinísticos     │ texto (IA opcional)
           ▼                              ▼
  analytics/ (profitability,      core/ai_provider.py
  product_score, competitors,     gemini → openai-compatible → offline
  reports)
           │
           ▼
  database/ (SQLite ou Supabase) ←→ core/memory.py (histórico)
           │
           ▼
  core/permissions.py  ──▶  aprovação humana obrigatória
```

Regras que o código garante:

1. **Nada de taxa inventada.** Comissão e taxa fixa começam em 0% com fonte
   explícita "não informado"; o relatório avisa.
2. **Nada de dado inventado.** Critério sem informação fica `None`, é listado em
   "dados que faltam" e reduz a confiança da nota.
3. **Nada de ação de risco sem aprovação.** Compra, pagamento, preço,
   publicação, exclusão, mensagem em massa, campanha e operação financeira.
4. **Toda execução é auditável.** `tasks`, `task_events`, `approvals`,
   `audit_logs` e `reports` ficam no banco.

---

## 3. Os 12 agentes

| # | Agente | Arquivo | Responsabilidade real | Ferramentas |
|---|---|---|---|---|
| 1 | CEO AI | `agents/ceo.py` | interpreta, distribui, valida e consolida | plan, consolidate, request_approval |
| 2 | Product Hunter | `agents/product_hunter.py` | ranqueia candidatos por score | research, score |
| 3 | Market Analyst | `agents/market_analyst.py` | compara preço/avaliação coletados | competitor_scan, differentials |
| 4 | Marketplace Manager | `agents/marketplace.py` | status de canal, auditoria, rascunho | channel_status, audit_listings, prepare_listing |
| 5 | Financial AI | `agents/financial.py` | margem, ROI, preço mínimo, equilíbrio | evaluate, compare_channels, price_floor |
| 6 | Marketing AI | `agents/marketing.py` | campanha orgânica, copy, calendário | campaign_plan, copy, content_calendar |
| 7 | Video Creator | `agents/video_creator.py` | roteiros 15/30/60s, prompts | scripts, video_prompts |
| 8 | SEO Specialist | `agents/seo.py` | palavras-chave, título, descrição | keywords, title, audit |
| 9 | Supplier Hunter | `agents/supplier.py` | custo total de aquisição, risco | compare, risk |
| 10 | Customer AI | `agents/customer.py` | FAQ, pós-venda, políticas | faq, templates, escalation |
| 11 | Automation AI | `agents/automation.py` | rotinas, falhas, relatórios | overview, register_defaults, toggle, report |
| 12 | Content Intelligence | `agents/content_intelligence.py` | pauta, calendário, desempenho | plan, performance, repurpose |

Cada agente tem `execute()` próprio. Não são doze nomes para a mesma chamada de
IA: o cálculo acontece antes e a IA recebe fatos prontos.

---

## 4. Product Opportunity Score

Pesos: demanda **25**, margem **25**, concorrência **15**, tendência **15**,
logística **10**, tráfego orgânico **10**.

Classificação: 90–100 prioritária · 75–89 interessante · 60–74 análise
adicional · <60 não recomendar.

Regras de honestidade aplicadas em `analytics/product_score.py`:

- normalização pelo peso **disponível**;
- limite duro por confiança (100% → sem limite; ≥50% → 84; ≥25% → 74; <25% → 59);
- margem < 40 pontos limita a nota a **74**, porque popularidade não é lucro;
- cada critério sai com nota, peso, contribuição, **fonte** e "sem dado";
- nenhum critério é preenchido por estimativa da IA.

## 5. Financeiro determinístico

```
receita      = preço × qtd − desconto × qtd
custos_bens  = (compra + frete_aquisição + embalagem + outros) × qtd
taxas        = receita × comissão% + taxa_fixa × qtd + frete_subsidiado × qtd
impostos     = receita × imposto%
lucro_bruto  = receita − custos_bens
lucro_líquido= receita − (custos_bens + taxas + impostos + anúncios)
margem%      = lucro_líquido / receita
ROI%         = lucro_líquido / (custos_bens + anúncios)
preço_mínimo = custo_fixo_unitário / (1 − comissão% − imposto% − margem_alvo%)
equilíbrio   = ceil(custos_fixos_mensais / lucro_por_unidade)
```

## 6. IA: opcional, trocável, com fallback

Ordem configurável em `AI_PROVIDERS`:

1. `gemini` (camada gratuita, exige `GEMINI_API_KEY`);
2. `openai_compatible` (Ollama, llama.cpp, LM Studio, Groq, OpenRouter…);
3. `offline` (sempre disponível: monta a redação local a partir dos fatos).

Limites: `AI_MAX_CALLS_PER_TASK` por tarefa, timeout por chamada, registro em
`ai_usage` (tokens, latência, erro). Se um provedor falha, o próximo assume.
**Sem nenhuma chave o sistema continua funcionando**: cálculos, scores,
relatórios e painel são locais.

## 7. Segurança e autorizações

- Ações protegidas: `purchase`, `payment`, `price_change`, `publish_listing`,
  `delete_product`, `bulk_message`, `campaign_change`, `financial_transaction`,
  `connector_write`.
- Fluxo: agente pede → registro em `approvals` (pendente) → você aprova em
  **Configurações → Aprovações** → só então `execute_guarded` libera.
- Auditoria: `audit_logs` guarda ator, ação, recurso, detalhes e horário.
- Senhas: hash **scrypt** com sal (`core/auth.py`); nenhum token no código.
- Segredos: apenas `.env` local ou *secrets* do GitHub Actions. `.gitignore`
  bloqueia `.env`, `*.pem`, `*.key`, bancos e logs.

## 8. Banco de dados

- Padrão: **SQLite** em `data/empire.db` (gratuito, zero configuração,
  persistente entre reinícios).
- Opcional: **Supabase** (`DATABASE_BACKEND=supabase`). Aplique
  `database/schema.sql`, que já cria as 20 tabelas, índices e RLS.
- 20 tabelas: users, agents, tasks, task_events, memories, approvals,
  audit_logs, categories, suppliers, products, competitors, listings,
  marketplaces, costs, sales, opportunities, reports, automations, ai_usage,
  settings_kv.

---

## 9. Instalação (3 comandos)

```bash
git clone <seu-repo> && cd ecommerce-ai-empire
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Configuração (opcional — o sistema roda sem nada disso):

```bash
cp .env.example .env   # preencha só o que tiver
```

Rodar o painel:

```bash
streamlit run dashboard/streamlit_app.py
```

Rodar a API:

```bash
uvicorn app:app --reload --port 8000   # http://localhost:8000/docs
```

Carregar dados de demonstração (marcados como **DEMO**):

```bash
python -m scripts.seed_demo
```

## 10. Como usar

1. Abra **Dashboard**, clique em **Carregar dados DEMO** (ou importe seus CSV).
2. Vá em **Configurações → Marketplaces** e informe comissão/taxa fixa reais.
3. Abra **CEO AI** e escreva, por exemplo:

> CEO, encontre 10 produtos com potencial de venda na Shopee, Mercado Livre e
> TikTok Shop. Analise concorrência, preços, custos, tendências e lucro. Depois
> me apresente as cinco melhores oportunidades.

O CEO identifica a intenção, monta o plano, executa `product_hunter` →
`market_analyst` → `financial` → `seo` → consolidação, valida a consistência dos
números e devolve relatório em Markdown (também salvo no histórico).

Outro exemplo:

> Analise meus anúncios e identifique quais precisam de melhorias para conseguir
> mais visualizações e vendas sem aumentar meus gastos com anúncios.

## 11. Páginas do painel (20)

Dashboard · CEO AI · Central de agentes · Pesquisa de produtos · Concorrentes ·
Calculadora financeira · Shopee · Mercado Livre · TikTok Shop · Instagram ·
Loja própria · Marketing · Criador de vídeos · Fornecedores · Clientes ·
Relatórios · Automações · Configurações · Catálogo · Vendas

Cada botão executa ação real: cria tarefa, roda agente, grava no banco, abre
aprovação ou gera arquivo. Não há elemento decorativo fingindo funcionar.

## 12. Testes

```bash
pytest -q
```

**85 testes** cobrindo cálculo financeiro, pontuação, orquestração, memória,
tarefas, permissões, conectores (assinaturas incluídas) e importação CSV.
Nenhum teste usa rede. Licença MIT.

## 13. Integrações

Todas começam **"Não conectado"** e caem para CSV. Documentado em
[`docs/INTEGRACOES.md`](docs/INTEGRACOES.md): permissões, variáveis e limites de
cada canal. Nada é simulado: sem credencial, o botão "Testar conexão" diz
exatamente o que falta.

## 14. Automações

| Rotina | Script | Cron (UTC) | Hora em São Paulo |
|---|---|---|---|
| Diária | `python -m scripts.daily_analysis` | `0 11 * * *` | 08:00 |
| Semanal | `python -m scripts.weekly_report` | `0 12 * * 1` | segunda 09:00 |
| Testes | `.github/workflows/tests.yml` | push/PR | — |

## 15. Implantação gratuita

Limites verificados em novembro de 2026 (confirme antes, pois mudam):

- **Streamlit Community Cloud**: grátis, 1 app por repositório, ~1 GB de memória
  por app, hiberna por inatividade. Serve para o painel.
- **GitHub Actions (plano Free)**: minutos ilimitados em repositório público;
  ~2.000 minutos/mês em repositório privado. Suficiente para 2 rotinas/dia.
- **Supabase Free**: projeto gratuito com limite de banco e pausa por inatividade.
- **Render/Fly/Railway**: camadas gratuitas instáveis; a API é opcional.

Passo a passo completo em [`docs/IMPLANTACAO.md`](docs/IMPLANTACAO.md).

## 16. Limitações conhecidas (sem maquiagem)

1. **Não há dados de mercado sem fonte.** Demanda, concorrência e tendência
   precisam vir de CSV, API autorizada ou Google Trends manual. O sistema não
   raspa sites, não burla CAPTCHA e não inventa volume de busca.
2. **Nada é publicado automaticamente.** Shopee/ML/TikTok/Instagram/Woo só
   executam escrita após aprovação; hoje os métodos de escrita são rascunho e
   atualização de preço no WooCommerce.
3. **O Video Creator não gera arquivo de vídeo** — não há gerador integrado.
4. **Ponto de equilíbrio** usa apenas custos fixos que você informar.
5. **Impostos** dependem do seu regime; o campo é manual.
6. **GitHub Actions é efêmero**: histórico só persiste com Supabase ou artefato.

## 17. Estrutura do repositório

```
ecommerce-ai-empire/
├── app.py                  # FastAPI (API + /docs)
├── requirements.txt  pytest.ini  README.md  .env.example  .gitignore
├── core/                   # config, IA, memória, tarefas, permissões, orquestrador, planner
├── agents/                 # 12 especialistas + base
├── analytics/              # profitability, product_score, competitors, reports
├── integrations/           # shopee, mercadolivre, tiktok, instagram, woocommerce, generic_csv
├── database/               # models, repository, schema.sql, supabase_repository
├── dashboard/              # 20 páginas Streamlit + common + streamlit_app
├── api/                    # rotas REST e dependências
├── scripts/                # seed_demo, daily_analysis, weekly_report
├── tests/                  # 10 arquivos, 85 testes
├── demo/                   # CSVs DEMO
├── docs/                   # arquitetura, integrações, implantação, segurança, roadmap
└── .github/workflows/      # daily_analysis, weekly_report, tests
```

## 18. Etapas do projeto

| Etapa | Conteúdo | Status |
|---|---|---|
| 1 | Repositório, estrutura, config, núcleo e painel | ✅ |
| 2 | CEO AI, orquestração e agentes | ✅ |
| 3 | Banco, memória e histórico | ✅ |
| 4 | Pesquisa, concorrência e pontuação | ✅ |
| 5 | Calculadora financeira | ✅ |
| 6 | Conectores e importação | ✅ (código pronto, aguardando credenciais) |
| 7 | Marketing, SEO e roteiros | ✅ |
| 8 | Automações e relatórios | ✅ |
| 9 | Testes e correções | ✅ 85 testes |
| 10 | Implantação e operação | ✅ documentado |

Próximos passos sugeridos: conectar a primeira API real (Mercado Livre é a mais
simples, tem busca pública) e ligar o Supabase para manter histórico no Actions.

## 19. Licença

MIT — use, modifique e venda o que construir com isso.

## Prazo de entrega (não perder tráfego)

Vender e não despachar no prazo da plataforma derruba o anúncio no ranking.
Por isso o sistema cruza o **prazo do canal** com o **prazo de cada fornecedor**
antes de recomendar um produto.

1. Abra a página do canal (Shopee, Mercado Livre, TikTok Shop...) e salve
   "Dias úteis para despachar" e "Dias úteis de entrega". O sistema não chuta
   esses números: sem eles o veredito é `indefinido`.
2. Em **Fornecedores**, importe o CSV com `lead_time_days`, `pickup_available`,
   `same_day_pickup`, `city` e `shipping_cost`.
3. O veredito por fornecedor é: `pode vender hoje`, `vende no limite`,
   `vende com risco`, `perde o prazo` ou `indefinido`.

Retirada no mesmo dia (`same_day_pickup=sim`) conta como despacho no dia 0.
O cálculo usa dias úteis e ignora feriados (o sistema não inventa calendário).

## Super agente autônomo

O agente que roda sozinho, com limites claros:

```bash
python -m core.autonomy --status     # como ele está agora
python -m core.autonomy --once       # um ciclo agora
python -m core.autonomy --loop       # roda continuamente (30 min por ciclo)
python -m core.autonomy --pause      # pausa
python -m core.autonomy --resume     # retoma
```

Guardas que ele respeita: janela de horário (7h-23h), máximo de 8 ciclos por dia,
intervalo mínimo entre ciclos, cooldown maior depois de falha, pausa automática
após 2 falhas seguidas e bloqueio quando há 25 aprovações pendentes. O estado fica
no banco: reiniciar não zera o histórico.

**O que ele faz sozinho:** pesquisa produto, calcula margem, confere prazo de
fornecedor, compara concorrente, escreve título, descrição e roteiro, e grava relatório.

**O que ele nunca faz sem você:** comprar, pagar, publicar anúncio, mudar preço,
excluir produto, mandar mensagem em massa e alterar campanha. Essas ações caem na
fila de aprovação.

Para 24 horas por dia ele precisa de um processo rodando. Opções gratuitas: seu
computador ligado, uma VM gratuita (Oracle Cloud Free Tier) ou um serviço de
container com plano free. Streamlit Community Cloud e GitHub Actions não servem
para processo contínuo (o primeiro dorme, o segundo tem limite de minutos e não
guarda o banco).
