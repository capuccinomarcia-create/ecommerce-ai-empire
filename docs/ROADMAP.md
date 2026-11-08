# Progresso por etapa

## ETAPA 1 — Repositório, estrutura, núcleo e painel ✅
- Estrutura completa, `requirements.txt`, `.env.example`, `.gitignore`.
- `core/config.py` (settings tipados, `.env` opcional), `core/utils.py`.
- Painel Streamlit com navegação e 20 páginas, todas ligadas ao backend.

## ETAPA 2 — CEO AI, orquestração e agentes ✅
- `core/planner.py` (intenção determinística + planos com dependências).
- `core/orchestrator.py` (execução, blackboard, validação, relatório).
- 12 agentes com lógica própria em `agents/`.

## ETAPA 3 — Banco, memória e histórico ✅
- SQLite transacional com 20 tabelas; `database/schema.sql` para Supabase.
- `core/memory.py` persistente (sobrevive a reinício).
- `tasks`, `task_events`, `approvals`, `audit_logs`, `reports`.

## ETAPA 4 — Pesquisa, concorrência e pontuação ✅
- `analytics/product_score.py` com pesos, confiança e limites.
- `analytics/competitors.py` (mediana, posição, diferenciais).
- Product Hunter ranqueando e explicando cada nota.

## ETAPA 5 — Calculadora financeira ✅
- `analytics/profitability.py` com margem, ROI, preço mínimo, equilíbrio.
- Comparação entre canais; alertas de prejuízo e margem crítica.

## ETAPA 6 — Conectores e importação ✅ (aguardando credenciais)
- Shopee, Mercado Livre, TikTok Shop, Instagram, WooCommerce com assinatura
  própria; todos "Não conectado" por padrão.
- CSV completo para cinco entidades, com rejeição motivada.

## ETAPA 7 — Marketing, SEO e roteiros ✅
- Campanhas orgânicas, calendário, copy por canal.
- SEO por n-gramas com limite por marketplace e detecção de repetição.
- Roteiros 15/30/60s, cenas, prompts e CTA.

## ETAPA 8 — Automações e relatórios ✅
- `automation` agent: overview, register_defaults, toggle, report.
- Scripts diário e semanal + workflows do GitHub Actions.

## ETAPA 9 — Testes e correções ✅
- 85 testes, 1 skip condicional. Nenhuma chamada de rede.
- Correções feitas: decodificação de JSON na leitura do banco, vínculo de
  concorrente por nome de produto, expectativa de desconto vs anúncio.

## ETAPA 10 — Implantação e operação ✅
- `docs/IMPLANTACAO.md` com limites gratuitos e checklist.

## Backlog priorizado (próximas execuções)
1. Conectar Mercado Livre real (busca pública primeiro, depois OAuth).
2. Ligar Supabase para histórico persistente no GitHub Actions.
3. Publicação assistida no WooCommerce após aprovação (primeiro canal com
   escrita real end-to-end).
4. Métricas pós-publicação importadas por CSV para fechar o ciclo de aprendizado.
5. Fila assíncrona (worker) para ciclos longos, mantendo o mesmo contrato de
   tarefas.
