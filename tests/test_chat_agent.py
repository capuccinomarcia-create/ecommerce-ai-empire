"""Testes do agente conversacional: comandos rápidos, execução e aprovações."""

from __future__ import annotations

import pytest

from core.chat_agent import ChatAgent, chunk_text


class FakePermissions:
    def __init__(self, repo) -> None:
        self.repo = repo
        self.eventos: list[tuple] = []

    def pending(self, limit: int = 50) -> list[dict]:
        return self.repo.find("approvals", {"status": "pendente"}, limit=limit)

    def approve(self, approval_id: str, decided_by: str = "proprietario", note: str = "") -> dict:
        self.eventos.append(("aprovar", approval_id))
        return self.repo.update("approvals", approval_id,
                                {"status": "aprovado", "decided_by": decided_by})

    def reject(self, approval_id: str, decided_by: str = "proprietario", note: str = "") -> dict:
        self.eventos.append(("rejeitar", approval_id))
        return self.repo.update("approvals", approval_id,
                                {"status": "rejeitado", "decided_by": decided_by})

    def audit(self, *args, **kwargs) -> None:
        pass


class FakeTasks:
    def pending_approvals_count(self) -> int:
        return 0


class FakeOrchestrator:
    def __init__(self, repo, ok: bool = True) -> None:
        self.repo = repo
        self.tasks = FakeTasks()
        self.permissions = FakePermissions(repo)
        self.ok = ok
        self.comandos: list[str] = []

    def handle(self, command: str, requested_by: str = "proprietario") -> dict:
        self.comandos.append(command)
        if not self.ok:
            return {"ok": False, "error": "fornecedor de IA fora do ar"}
        return {
            "ok": True,
            "run_id": "run_1",
            "intent": {"code": "product_research", "label": "Pesquisa de produtos"},
            "report": "Relatório: 3 oportunidades analisadas.",
            "steps": [{"agent": "product_hunter", "status": "concluida"},
                      {"agent": "financial", "status": "concluida"}],
            "pending_approvals": [],
        }


def criar(repo, ok: bool = True) -> tuple[ChatAgent, FakeOrchestrator]:
    fake = FakeOrchestrator(repo, ok=ok)
    return ChatAgent(orchestrator=fake), fake


def test_ajuda_lista_comandos(repo):
    agente, _ = criar(repo)
    resposta = agente.handle_message("ajuda")
    assert "status" in resposta.reply and "aprovar" in resposta.reply


def test_status_mostra_operacao(repo):
    agente, _ = criar(repo)
    resposta = agente.handle_message("status")
    assert "Operação agora" in resposta.reply
    assert "Produtos: 0" in resposta.reply
    assert "Modo:" in resposta.reply


def test_frase_livre_executa_o_ceo(repo):
    agente, fake = criar(repo)
    resposta = agente.handle_message("analise o livro de colorir na shopee")
    assert fake.comandos == ["analise o livro de colorir na shopee"]
    assert "Pesquisa de produtos" in resposta.reply
    assert "2/2 etapas" in resposta.reply
    assert "Relatório" in resposta.reply


def test_falha_do_motor_nao_derruba_o_chat(repo):
    agente, _ = criar(repo, ok=False)
    resposta = agente.handle_message("faça qualquer coisa")
    assert resposta.kind == "erro"
    assert "fora do ar" in resposta.reply


def test_pendentes_e_aprovacao_por_numero(repo):
    agente, fake = criar(repo)
    repo.insert("approvals", {"id": "apr_1", "action": "publicar_anuncio",
                              "risk_level": "alto", "status": "pendente",
                              "resource_id": "prod_1"})
    repo.insert("approvals", {"id": "apr_2", "action": "comprar_estoque",
                              "risk_level": "alto", "status": "pendente",
                              "resource_id": "prod_2"})
    lista = agente.handle_message("pendentes")
    assert "publicar anuncio" in lista.reply
    assert "1." in lista.reply and "2." in lista.reply

    decidido = agente.handle_message("aprovar 2")
    assert "Aprovado" in decidido.reply
    assert ("aprovar", "apr_2") in fake.permissions.eventos
    assert repo.get("approvals", "apr_2")["status"] == "aprovado"
    # a que sobrou continua pendente
    assert [a["id"] for a in fake.permissions.pending()] == ["apr_1"]


def test_aprovar_sem_pendencia_avisa(repo):
    agente, _ = criar(repo)
    assert "Não há nada" in agente.handle_message("aprovar 1").reply


def test_produtos_vazio_orienta(repo):
    agente, _ = criar(repo)
    assert "Nenhum produto cadastrado" in agente.handle_message("produtos").reply


def test_produtos_com_margem(repo):
    agente, _ = criar(repo)
    repo.insert("products", {"id": "p1", "name": "Livro de Colorir", "purchase_price": 18.5,
                             "sale_price": 39.9, "marketplace": "shopee", "is_demo": 0})
    resposta = agente.handle_message("produtos")
    assert "Livro de Colorir" in resposta.reply
    assert "margem" in resposta.reply


def test_historico_guarda_conversa(repo):
    agente, _ = criar(repo)
    agente.handle_message("status")
    agente.handle_message("ajuda")
    historico = agente.historico(10)
    assert [h["role"] for h in historico] == ["user", "agent", "user", "agent"]
    agente.limpar_historico()
    assert agente.historico() == []


def test_historico_nao_cresce_sem_limite(repo):
    from core.chat_agent import HISTORY_LIMIT

    agente, _ = criar(repo)
    for _ in range(HISTORY_LIMIT):
        agente.handle_message("ajuda")
    assert len(agente.historico(HISTORY_LIMIT * 2)) <= HISTORY_LIMIT


def test_pausar_e_retomar_pelo_chat(repo):
    agente, _ = criar(repo)
    assert "pausada" in agente.handle_message("pausar").reply
    assert "retomada" in agente.handle_message("retomar").reply


def test_chunk_text_respeita_limite():
    texto = ("linha de teste com acentuação ção\n" * 400).strip()
    pedacos = chunk_text(texto, limite=500)
    assert all(len(p) <= 500 for p in pedacos)
    assert "".join(pedacos).replace("\n", "") == texto.replace("\n", "")
