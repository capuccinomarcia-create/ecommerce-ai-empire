"""Agente conversacional: você escreve o comando, ele entende e executa.

Fica em cima do Orchestrator, então o que ele executa é exatamente o mesmo motor
dos 12 agentes, com as mesmas travas de aprovação. Serve para terminal
(`python -m core.chat`) e para Telegram (`python -m scripts.telegram_bot`).

Frases entendidas sem IA nenhuma (rápido e determinístico):
    "status"                 situação da operação
    "pendentes"              o que espera sua aprovação
    "aprovar 2" / "rejeitar 2"
    "pausar" / "retomar"     autonomia
    "produtos"               catálogo com margem
    "ajuda"                  lista de comandos
Qualquer outra coisa vira um comando para o CEO AI:
    "analise o livro de colorir e veja se vale a pena na shopee"
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core import data_mode
from core.autonomy import AutonomousSuperAgent
from core.config import get_settings
from core.orchestrator import Orchestrator
from core.utils import now_iso

HISTORY_KEY = "chat_history"
HISTORY_LIMIT = 40
TELEGRAM_CHUNK = 3800

AJUDA = """Comandos que eu executo:

*Operação*
• status — como está a operação agora
• rotinas — o que roda sozinho e quando
• vendas — plano de venda: preço, estoque e anúncio
• produtos — catálogo com margem calculada
• relatório — último relatório do CEO
• pendentes — o que espera sua aprovação
• aprovar 1 / rejeitar 1 — decide uma pendência

*Agentes* (fale em português normal)
• "analise o caderno de caligrafia na shopee e veja a margem"
• "compare meu preço com os concorrentes"
• "escreva o título e a descrição do livro de colorir"
• "monte o roteiro de vídeo para o TikTok"
• "quais fornecedores entregam em 7 dias?"

*Automação*
• pausar / retomar — liga e desliga a autonomia
• modo — mostra se está em modo real ou demo
• ajuda — esta mensagem"""


def _fmt_money(valor: Any) -> str:
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "R$ 0,00"


def chunk_text(text: str, limite: int = TELEGRAM_CHUNK) -> list[str]:
    """Quebra mensagens longas sem cortar palavra no meio."""
    pedacos: list[str] = []
    resto = (text or "").strip()
    while len(resto) > limite:
        corte = resto.rfind("\n", 0, limite)
        if corte < limite // 2:
            corte = resto.rfind(" ", 0, limite)
        if corte < limite // 2:
            corte = limite
        pedacos.append(resto[:corte].strip())
        resto = resto[corte:].strip()
    if resto:
        pedacos.append(resto)
    return pedacos


@dataclass
class Resposta:
    reply: str
    kind: str = "texto"          # texto | relatorio | lista | erro
    wait_for_approval: bool = False
    data: Any = None


class ChatAgent:
    def __init__(self, orchestrator: Orchestrator | None = None, user: str = "proprietario") -> None:
        self.orchestrator = orchestrator or Orchestrator()
        self.settings = get_settings()
        self.user = user

    # --------------------------------------------------------------- histórico --
    def _historico(self) -> list[dict]:
        salvo = self.orchestrator.repo.get_setting(HISTORY_KEY, []) or []
        return salvo if isinstance(salvo, list) else []

    def _registrar(self, papel: str, texto: str) -> None:
        entrada = {"at": now_iso(), "role": papel, "text": texto[:4000]}
        historico = (self._historico() + [entrada])[-HISTORY_LIMIT:]
        self.orchestrator.repo.set_setting(HISTORY_KEY, historico)

    def historico(self, limite: int = 10) -> list[dict]:
        return self._historico()[-limite:]

    def limpar_historico(self) -> None:
        self.orchestrator.repo.set_setting(HISTORY_KEY, [])

    # --------------------------------------------------------------- comandos --
    def _pendentes(self) -> list[dict]:
        permissoes = getattr(self.orchestrator, "permissions", None)
        if permissoes is not None:
            return permissoes.pending(limit=10)
        return self.orchestrator.repo.find(
            "approvals", {"status": "pendente"}, order_by="-created_at", limit=10
        )

    def _lista_pendentes(self) -> str:
        pendentes = self._pendentes()
        if not pendentes:
            return "Não há nada esperando sua aprovação."
        linhas = ["Esperando sua aprovação:", ""]
        for indice, item in enumerate(pendentes, start=1):
            acao = str(item.get("action") or "").replace("_", " ")
            risco = str(item.get("risk_level") or "")
            linha = f"{indice}. {acao} (risco {risco})"
            if item.get("resource_id"):
                linha += f" — {item['resource_id']}"
            linhas.append(linha)
        linhas += ["", 'Para decidir: "aprovar 1" ou "rejeitar 1".']
        return "\n".join(linhas)

    def _decidir(self, arg: str, decisao: str) -> Resposta:
        pendentes = self._pendentes()
        if not pendentes:
            return Resposta("Não há nada pendente para decidir.", kind="texto")
        alvo = (arg or "").strip()
        escolhido: dict | None = None
        if alvo.isdigit():
            indice = int(alvo)
            if 1 <= indice <= len(pendentes):
                escolhido = pendentes[indice - 1]
        else:
            for item in pendentes:
                if item.get("id") == alvo:
                    escolhido = item
        if not escolhido:
            return Resposta(f'Não achei a pendência "{alvo}". Manda "pendentes" para ver a lista.',
                            kind="erro")

        alvo_id = escolhido["id"]
        permissoes = getattr(self.orchestrator, "permissions", None)
        if decisao == "aprovar":
            if permissoes is not None:
                permissoes.approve(alvo_id, self.user, "aprovado pelo chat")
            else:
                self.orchestrator.repo.update("approvals", alvo_id,
                                              {"status": "aprovado", "decided_by": self.user})
            return Resposta(f"Aprovado: {str(escolhido.get('action','')).replace('_',' ')}.",
                            kind="texto")
        if permissoes is not None:
            permissoes.reject(alvo_id, self.user, "rejeitado pelo chat")
        else:
            self.orchestrator.repo.update("approvals", alvo_id,
                                          {"status": "rejeitado", "decided_by": self.user})
        return Resposta(f"Rejeitado: {str(escolhido.get('action','')).replace('_',' ')}.", kind="texto")

    def _status(self) -> Resposta:
        repo = self.orchestrator.repo
        produtos = repo.find("products", {}, limit=500)
        oportunidades = repo.find("opportunities", {}, limit=500)
        pendentes = self._pendentes()
        agentes = AutonomousSuperAgent(orchestrator=self.orchestrator).status()
        modo = data_mode.get_mode(repo)
        config = data_mode.resumo(repo, self.settings)
        linhas = [
            "*Operação agora*",
            f"Modo: {modo.upper()} ({config['prontos']}/{config['total']} itens prontos)",
            f"Produtos: {len(produtos)} · Oportunidades: {len(oportunidades)}",
            f"Aprovações pendentes: {len(pendentes)}",
            f"Autonomia: {'pausada' if agentes['paused'] else ('ligada' if agentes['enabled'] else 'manual')}"
            f" · ciclos hoje {agentes['cycles_today']}/{agentes['limites']['ciclos_por_dia']}",
        ]
        if agentes.get("last_status"):
            linhas.append(f"Último ciclo: {agentes['last_status']}"
                          f" ({str(agentes.get('last_cycle_at') or '')[:16]})")
        faltando = [i["item"] for i in config["itens"] if not i["ok"]]
        if faltando:
            linhas += ["", "Ainda falta: " + ", ".join(faltando)]
        return Resposta("\n".join(linhas), kind="texto", data=agentes)

    def _produtos(self) -> Resposta:
        from analytics.profitability import calculate

        repo = self.orchestrator.repo
        produtos = repo.find("products", {}, order_by="-created_at", limit=50)
        if not produtos:
            return Resposta("Nenhum produto cadastrado ainda. Me manda nome, custo e preço "
                            "que eu cadastro.", kind="texto")
        linhas = ["*Produtos*", ""]
        for produto in produtos:
            regra = repo.find_one("marketplaces",
                                  {"slug": produto.get("marketplace") or "shopee"}) or {}
            resultado = calculate({
                "product_name": produto.get("name"),
                "marketplace": produto.get("marketplace") or "shopee",
                "costs": {"purchase_price": float(produto.get("purchase_price") or 0),
                          "other_costs": float(produto.get("extra_cost") or 0)},
                "terms": {"sale_price": float(produto.get("sale_price") or 1),
                          "commission_pct": float(regra.get("commission_pct") or 0),
                          "fixed_fee": float(regra.get("fixed_fee") or 0)},
            })
            linhas.append(
                f"• {produto.get('name')} — {_fmt_money(produto.get('sale_price'))} "
                f"· margem {resultado.margin_pct:.1f}% · lucro {_fmt_money(resultado.net_profit)}"
            )
        return Resposta("\n".join(linhas), kind="lista", data=produtos)


    def _rotinas(self) -> Resposta:
        from core.scheduler import Agendador

        agendador = Agendador(self.orchestrator.repo)
        rotinas = agendador.rotinas()
        filtro = getattr(self.orchestrator, "agent_filter", None)
        if filtro:
            rotinas = [r for r in rotinas if filtro in str(r.get("job") or "")]
        if not rotinas:
            return Resposta(
                "Nenhuma rotina cadastrada. Diga \"cadastrar rotinas\" que eu crio as de venda.",
                kind="texto", data={"automations": []},
            )
        linhas = ["*Rotinas automáticas*", ""]
        for rotina in rotinas:
            estado = "ativa" if rotina.get("enabled") else "pausada"
            linhas.append(f"• {rotina.get('name')} · {rotina.get('schedule_cron')} · {estado}"
                          f" · próxima: {rotina.get('next_run_at') or '—'}")
        linhas += ["", "Tudo isso roda no agendador; publicar e pagar seguem com aprovação."]
        return Resposta("\n".join(linhas), kind="lista", data={"automations": rotinas})

    def _relatorio(self) -> Resposta:
        ultimo = self.orchestrator.repo.find("reports", {}, order_by="-created_at", limit=1)
        if not ultimo:
            return Resposta('Nenhum relatório ainda. Peça, por exemplo: "analise minhas '
                            'oportunidades e me diga o que fazer".', kind="texto")
        corpo = str(ultimo[0].get("body") or "").strip()
        return Resposta(corpo[:3500] or "Relatório vazio.", kind="relatorio", data=ultimo[0])

    # ---------------------------------------------------------------- mensagem --
    def handle_message(self, texto: str) -> Resposta:
        texto = (texto or "").strip()
        if not texto:
            return Resposta("Manda o comando.", kind="erro")

        self._registrar("user", texto)
        resposta = self._route(texto)
        self._registrar("agent", resposta.reply)
        return resposta

    def _route(self, texto: str) -> Resposta:
        baixo = re.sub(r"\s+", " ", texto.lower()).strip()

        if baixo in {"ajuda", "/ajuda", "help", "/help", "comandos", "o que voce faz"}:
            return Resposta(AJUDA)

        if baixo in {"status", "/status", "como esta", "como está", "situacao", "situação"}:
            return self._status()

        if baixo in {"pendentes", "/pendentes", "aprovacoes", "aprovações", "fila"}:
            return Resposta(self._lista_pendentes(), wait_for_approval=bool(self._pendentes()))

        match = re.match(r"^(aprovar|aprova|rejeitar|rejeita|cancelar)\s+(.+)$", baixo)
        if match:
            decisao = "aprovar" if match.group(1).startswith("aprova") else "rejeitar"
            return self._decidir(match.group(2).strip(), decisao)

        if baixo in {"produtos", "/produtos", "catalogo", "catálogo", "meus produtos"}:
            return self._produtos()

        if baixo in {"vendas", "venda", "/vendas", "plano de vendas", "plano de venda",
                     "o que fazer para vender", "como vender"}:
            from core.sales_ops import SalesOperator, resumo_texto

            plano = SalesOperator(self.orchestrator.repo).plano()
            return Resposta(resumo_texto(plano), kind="lista", data=plano)

        if baixo in {"cadastrar rotinas", "criar rotinas", "configurar rotinas",
                     "ativar rotinas", "tarefas automaticas de venda"}:
            from scripts.setup_rotinas import sincronizar

            resultado = sincronizar(self.orchestrator.repo, ativar=True)
            return Resposta(
                f"Rotinas de venda prontas: {len(resultado['criadas'])} criadas, "
                f"{len(resultado['atualizadas'])} atualizadas, {resultado['total']} no total. "
                "Diga \"rotinas\" para ver quando cada uma roda.",
                kind="texto", data=resultado,
            )

        if baixo in {"rotinas", "automacoes", "automações", "/rotinas",
                     "tarefas automaticas", "tarefas automáticas"}:
            return self._rotinas()

        if baixo in {"relatorio", "relatório", "/relatorio", "ultimo relatorio"}:
            return self._relatorio()

        if baixo in {"modo", "/modo", "modo real", "modo demo"}:
            config = data_mode.resumo(self.orchestrator.repo, self.settings)
            if "real" in baixo and baixo != "modo":
                data_mode.set_mode(self.orchestrator.repo, data_mode.REAL)
                return Resposta("Modo alterado para REAL.", data=config)
            if baixo == "modo demo":
                data_mode.set_mode(self.orchestrator.repo, data_mode.DEMO)
                return Resposta("Modo alterado para DEMO.", data=config)
            linhas = [f"Modo atual: *{config['mode'].upper()}*",
                      f"{config['prontos']}/{config['total']} itens prontos"]
            for item in config["itens"]:
                linhas.append(f"{'✔' if item['ok'] else '—'} {item['item']}: {item['detalhe']}")
            return Resposta("\n".join(linhas), data=config)

        agente = AutonomousSuperAgent(orchestrator=self.orchestrator)
        if baixo in {"pausar", "/pausar", "para", "parar", "pausa"}:
            agente.pause("pausado pelo chat")
            return Resposta("Autonomia pausada. Nada roda sozinho até você mandar retomar.")
        if baixo in {"retomar", "/retomar", "continuar", "voltar"}:
            agente.resume()
            return Resposta("Autonomia retomada, dentro dos limites: 7h-23h e 8 ciclos por dia.")

        # qualquer outra frase vira comando para o CEO AI
        try:
            resultado = self.orchestrator.handle(texto, requested_by=self.user)
        except Exception as exc:  # nunca deixa o chat cair
            return Resposta(f"Não consegui executar: {exc}", kind="erro")

        if not resultado.get("ok"):
            erro = resultado.get("error") or "o plano não completou"
            return Resposta(f"Tentei executar e falhou: {erro}", kind="erro", data=resultado)

        etapas = resultado.get("steps") or []
        feitas = [s for s in etapas if s.get("status") == "concluida"]
        cabeca = f"✅ Intenção: {resultado['intent']['label']}"
        cabeca += f" · {len(feitas)}/{len(etapas)} etapas concluídas"
        corpo = str(resultado.get("report") or "").strip()
        extra = ""
        if resultado.get("pending_approvals"):
            extra = f"\n\n⏳ {len(resultado['pending_approvals'])} ação(ões) esperando sua aprovação. Manda \"pendentes\"."
        return Resposta(f"{cabeca}\n\n{corpo[:3200]}{extra}", kind="relatorio",
                        wait_for_approval=bool(resultado.get("pending_approvals")),
                        data=resultado)
