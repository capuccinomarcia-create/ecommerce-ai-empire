# Arquitetura

## Camadas

| Camada | Pasta | Papel | Pode chamar |
|---|---|---|---|
| Interface | `dashboard/`, `api/` | painel Streamlit e REST | core, analytics, integrations |
| Coordenação | `core/` | orquestrador, planner, tarefas, permissões, memória, IA | agents, database, analytics |
| Especialistas | `agents/` | 12 agentes com lógica própria | analytics, integrations, database |
| Cálculo | `analytics/` | matemática pura, sem IA | — |
| Integração | `integrations/` | APIs oficiais + CSV | core/config |
| Dados | `database/` | repositório e esquema | core/utils |

Dependência aponta sempre para baixo. `analytics/` nunca importa `agents/`.

## Fluxo de um comando

1. `Orchestrator.handle(command)`
2. `core/planner.detect_intent` — classificação determinística por sinais
   (palavras-chave normalizadas), com confiança proporcional aos sinais.
3. `core/planner.build_plan` — lista de passos com `depends_on`. Extrai
   quantidade do texto ("10 produtos" → `limit=10`, `top=5`).
4. Para cada passo: `TaskManager.create` (com `dedupe_key`), `start`,
   `AgentContext`, `agent.run`, `complete`/`fail`.
5. Resultados vão para um blackboard (`shared`) com chave `agente.task_type`;
   passo com dependência falha é cancelado, não executado às cegas.
6. `Orchestrator._validate` confere `receita − custo = lucro` e margem.
7. `analytics/reports.orchestration_report` monta o Markdown, salvo em `reports`.
8. `MemoryStore.log_decision` + `PermissionGate.audit` fecham o ciclo.

## Estados de tarefa

```
pendente ──start──▶ em_execucao ──complete──▶ concluida
   ▲                    │
   │                    ├─fail (attempts < max)──▶ pendente (retentativa)
   │                    └─fail (attempts = max)──▶ falhou
   │
   └──resume── aguardando_aprovacao ◀──await_approval
                        │
                        └──cancel──▶ cancelada
```

## Deduplicação

`dedupe_key = sha256(comando + agente + tipo)`. Uma tarefa com a mesma chave em
`pendente`, `em_execucao` ou `aguardando_aprovacao` dentro da janela
(`TASK_DEDUPE_WINDOW_MINUTES`, padrão 30) bloqueia a criação duplicada e registra
o evento `duplicada`. Tarefa já concluída não bloqueia reexecução.

## Timeout e orçamento

Cada tarefa tem `timeout_seconds`. O orquestrador mede a duração de cada etapa e
marca aviso quando excede; o ciclo inteiro tem orçamento
`task_timeout_seconds × max(2, passos)` e cancela o restante ao estourar. Chamadas
de IA têm seu próprio `AI_TIMEOUT_SECONDS`.

## Determinismo

- `analytics/profitability.py` e `analytics/product_score.py` não importam IA.
- A ordem de execução é topológica e estável.
- Testes fixam os números esperados com `pytest.approx`.

## Extensões previstas

- Novo marketplace: crie `integrations/<canal>.py` herdando
  `MarketplaceConnector`, registre em `CONNECTOR_CLASSES` e em
  `DEFAULT_MARKETPLACES`.
- Novo agente: crie `agents/<nome>.py` herdando `BaseAgent`, registre em
  `AGENT_CLASSES` e use em `core/planner.build_plan`.
- Novo provedor de IA: implemente `generate`/`status` e registre em
  `PROVIDER_CLASSES`.
