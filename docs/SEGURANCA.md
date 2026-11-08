# Segurança e autorizações

## Princípio

O proprietário tem controle absoluto. O sistema foi desenhado para que a IA
**não possa** gastar dinheiro, mudar preço ou publicar nada sozinha.

## Ações que exigem aprovação

| Ação | Risco | Onde aparece |
|---|---|---|
| `purchase` | crítico | compra de produto/insumo |
| `payment` | crítico | pagamento/transferência |
| `financial_transaction` | crítico | qualquer operação financeira |
| `price_change` | alto | alteração de preço |
| `publish_listing` | alto | publicação de anúncio |
| `delete_product` | alto | exclusão de produto |
| `bulk_message` | alto | mensagem em massa |
| `campaign_change` | alto | alteração de campanha |
| `connector_write` | médio | escrita em API externa |

Fluxo: `PermissionGate.request()` grava em `approvals` (pendente) →
`approve/reject/cancel` registra quem decidiu e quando → `execute_guarded()`
confirma a existência da aprovação antes de executar.

## Auditoria

`audit_logs` registra ator, ação, recurso, detalhes e horário para: pedido de
aprovação, decisão, execução liberada, importação CSV, alteração de regra de
marketplace, criação/exclusão de produto, cancelamento de tarefa e cada ciclo do
orquestrador. Visível em Configurações → Auditoria.

## Credenciais

- Só em variáveis de ambiente (`.env` local ou Secrets do GitHub/Streamlit).
- `.gitignore` bloqueia `.env`, `.env.*`, `*.pem`, `*.key`, `secrets*`,
  bancos SQLite, logs e exports.
- `.env.example` existe para documentar **nomes**, nunca valores.
- Nenhuma chave é impressa em log, resposta de API ou relatório.
- `credential_report()` informa apenas *configurado/não configurado*.

## Senhas

`core/auth.py` usa **scrypt** (N=2^14, r=8, p=1) com sal aleatório de 16 bytes,
comparação em tempo constante (`hmac.compare_digest`) e formato versionado
`scrypt$n$r$p$salt$hash`. `password_hash` nunca sai do banco: `authenticate()`
devolve o usuário sem esse campo.

## Limites de execução

- `TASK_MAX_ATTEMPTS` (padrão 3) antes de marcar falha.
- `TASK_TIMEOUT_SECONDS` por tarefa e orçamento por ciclo.
- `AI_MAX_CALLS_PER_TASK` por tarefa.
- Deduplicação por janela evita execução repetida acidental.
- Cancelamento de tarefa pendente pelo painel, com registro de auditoria.

## Boas práticas embutidas

1. Nenhum conector faz scraping agressivo, burla CAPTCHA ou ignora limites.
2. Nada de pagamento fora do marketplace nos textos de atendimento.
3. Dados de cliente não saem do canal de atendimento.
4. Conteúdo de terceiros não é reutilizado nem tem marca d'água removida.
5. Números nunca são apresentados como estatística real quando são estimativa.

## Se algo der errado

1. `Configurações → Aprovações`: cancele o que estiver pendente.
2. `Automações`: desative as rotinas e cancele tarefas em andamento.
3. Rotacione as chaves no provedor e atualize o `.env`/Secrets.
4. Leia `audit_logs` e `task_events` para reconstruir o que aconteceu.
