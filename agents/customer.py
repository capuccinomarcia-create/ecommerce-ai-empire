"""AGENTE 10 - CUSTOMER AI: atendimento, FAQ e pós-venda."""

from __future__ import annotations

from typing import Any

from agents.base import AgentContext, AgentResult, BaseAgent, MarketContext


class CustomerAgent(BaseAgent):
    name = "customer"
    role = "Customer AI"
    description = (
        "Prepara respostas, mensagens de pós-venda e FAQ. Nunca envia mensagens "
        "automaticamente: envio em massa exige aprovação do proprietário."
    )
    capabilities = ["faq", "resposta_cliente", "pos_venda", "padrao_atendimento"]
    tools = [
        {"name": "faq", "description": "Gera perguntas frequentes a partir do catálogo."},
        {"name": "templates", "description": "Cria modelos de resposta por situação."},
        {"name": "escalation", "description": "Define quando chamar um humano." },
    ]

    def execute(self) -> AgentResult:
        payload = self.ctx.payload()
        market = MarketContext(self.ctx)
        products = market.products()
        focus = payload.get("product") or (products[0].get("name") if products else "produto")
        product = next((p for p in products if p.get("name") == focus), products[0] if products else {})

        prazo = payload.get("handling_days") or 3
        faq = [
            {
                "pergunta": "Quando meu pedido será enviado?",
                "resposta": (
                    f"Olá! O envio é feito em até {prazo} dias úteis após a confirmação do "
                    "pagamento. Assim que postado, o código de rastreio aparece no pedido."
                ),
            },
            {
                "pergunta": "O produto é igual ao da foto?",
                "resposta": (
                    f"Sim. As fotos são do {product.get('name', focus)} original. Pequenas variações "
                    "de tom podem ocorrer por causa da iluminação."
                ),
            },
            {
                "pergunta": "E se chegar com defeito?",
                "resposta": (
                    "Você pode abrir a solicitação de devolução dentro do prazo do marketplace. "
                    "Enviamos as instruções e acompanhamos o caso até o fim."
                ),
            },
            {
                "pergunta": "Faz desconto para mais de uma unidade?",
                "resposta": (
                    "Consulte a quantidade disponível no anúncio. Descontos só são oferecidos "
                    "quando a margem permite, sem prometer o que não está configurado."
                ),
            },
        ]
        templates = {
            "duvida_preco": "Olá, {nome}! O valor atual é o que aparece no anúncio. "
                            "Se houver promoção ativa, ela já está aplicada.",
            "pedido_atrasado": "Olá, {nome}! Estou verificando o rastreio do seu pedido agora "
                               "e te retorno com a posição exata em alguns minutos.",
            "pos_venda": "Olá, {nome}! Seu pedido foi entregue. Se puder avaliar, ajuda muito. "
                         "Qualquer dúvida, estou aqui.",
            "avaliacao_negativa": "Olá, {nome}! Sinto muito pela experiência. Quero resolver: "
                                  "me conta o que aconteceu que eu encaminho a solução hoje.",
            "troca": "Olá, {nome}! Para troca, abra a solicitação no marketplace e me avise "
                     "o número do caso. Acompanho do início ao fim.",
        }
        policy_notes = [
            "Nunca prometa prazo que você não controla.",
            "Nunca peça pagamento fora do marketplace (viola as políticas e expõe o cliente).",
            "Não ofereça brinde/desconto sem checar a margem calculada pelo Financial AI.",
            "Dados pessoais do cliente não saem do canal de atendimento.",
        ]
        narrative, provider = self.narrate(
            f"Padrão de atendimento para {focus}.", [f["pergunta"] for f in faq]
        )
        return AgentResult(
            summary=f"FAQ com {len(faq)} perguntas e {len(templates)} modelos de resposta.",
            data={
                "product": product.get("name", focus),
                "faq": faq,
                "templates": templates,
                "policy_notes": policy_notes,
                "auto_send": False,
                "demo_mode": bool(product.get("is_demo")),
            },
            findings=[f"P: {f['pergunta']}" for f in faq],
            warnings=[
                "Envio em massa de mensagens exige aprovação (ação bulk_message).",
                "Nada é enviado automaticamente por este agente.",
            ],
            data_gaps=["Sem histórico real de mensagens: o FAQ cobre o que é comum no nicho."],
            next_actions=[
                "Revisar os textos e colar no padrão de respostas do canal.",
                "Ajustar o prazo de envio informado para o real da sua operação.",
            ],
            narrative=narrative,
            ai_provider=provider,
        )
