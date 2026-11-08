"""AGENTE 7 - VIDEO CREATOR: roteiros e prompts (não gera arquivos de vídeo)."""

from __future__ import annotations

from typing import Any

from agents.base import AgentContext, AgentResult, BaseAgent, MarketContext


class VideoCreatorAgent(BaseAgent):
    name = "video_creator"
    role = "Video Creator"
    description = (
        "Escreve roteiros de 15, 30 e 60 segundos com gancho, cenas, fala e CTA, além de "
        "prompts para geradores de vídeo. Não produz o arquivo de vídeo."
    )
    capabilities = ["roteiro_15s", "roteiro_30s", "roteiro_60s", "sequencia_de_cenas",
                    "prompts_de_video", "legendas"]
    tools = [
        {"name": "scripts", "description": "Gera roteiros nos três formatos."},
        {"name": "video_prompts", "description": "Cria prompts de geração por cena."},
    ]

    DISCLAIMER = (
        "Este agente entrega texto. Nenhum arquivo de vídeo é gerado porque não há gerador "
        "integrado; os prompts abaixo servem para qualquer ferramenta que você usar."
    )

    def execute(self) -> AgentResult:
        payload = self.ctx.payload()
        market = MarketContext(self.ctx)
        scored = market.scored_products()
        product = payload.get("product") or (scored[0]["name"] if scored else "")
        row = next((r for r in scored if r["name"] == product), scored[0] if scored else None)
        if not row:
            return AgentResult(
                summary="Sem produto para roteirizar.",
                data_gaps=["Cadastre um produto para gerar roteiros."],
            )

        scripts = {f"{sec}s": self._script(row, sec) for sec in (15, 30, 60)}
        prompts = [
            {
                "scene": scene["cena"],
                "prompt": (
                    f"Vertical 9:16, produto: {row['name']}, {scene['visual']}, "
                    "luz natural, câmera na mão, estilo UGC brasileiro, sem texto na imagem"
                ),
            }
            for scene in scripts["15s"]["cenas"]
        ]

        findings = [
            f"Roteiros criados para {row['name']} (15s, 30s e 60s).",
            f"Gancho 15s: {scripts['15s']['gancho']}",
            f"CTA: {scripts['15s']['cta']}",
        ]
        narrative, provider = self.narrate(
            f"Roteiros de vídeo curto para {row['name']}.",
            [scripts["15s"]["roteiro"][:400]],
        )
        return AgentResult(
            summary=f"3 roteiros + {len(prompts)} prompts de vídeo para {row['name']}.",
            data={
                "product": row["name"],
                "scripts": scripts,
                "prompts": prompts,
                "hashtags": self._hashtags(row),
                "demo_mode": row.get("is_demo", False),
            },
            findings=findings,
            warnings=[self.DISCLAIMER],
            data_gaps=[
                "Sem vídeo original gravado: o conteúdo depende da sua gravação.",
                "Não reutilize vídeos de terceiros nem remova marca d'água.",
            ],
            next_actions=[
                "Gravar as cenas na ordem indicada.",
                "Publicar o corte de 15s primeiro e testar o gancho.",
            ],
            narrative=narrative,
            ai_provider=provider,
        )

    def _script(self, row: dict, seconds: int) -> dict[str, Any]:
        name = row["name"]
        if seconds == 15:
            scenes = [
                {"cena": 1, "tempo": "0-3s", "visual": "produto na mão, close", "fala": f"Olha esse {name}."},
                {"cena": 2, "tempo": "3-9s", "visual": "produto em uso", "fala": "Resolve o problema em segundos."},
                {"cena": 3, "tempo": "9-15s", "visual": "tela com preço e link", "fala": "Tá no carrinho, corre."},
            ]
            gancho = f"Olha esse {name}."
            cta = "Toque no carrinho antes que acabe."
        elif seconds == 30:
            scenes = [
                {"cena": 1, "tempo": "0-4s", "visual": "close no problema", "fala": f"Cansado de não achar {name} bom?"},
                {"cena": 2, "tempo": "4-12s", "visual": "produto em uso", "fala": "Esse aqui resolve: simples e rápido."},
                {"cena": 3, "tempo": "12-22s", "visual": "detalhe de qualidade", "fala": "Veja o acabamento e o tamanho."},
                {"cena": 4, "tempo": "22-30s", "visual": "preço na tela", "fala": "Link no carrinho, frete rápido."},
            ]
            gancho = f"Cansado de não achar {name} bom?"
            cta = "Link no carrinho."
        else:
            scenes = [
                {"cena": 1, "tempo": "0-5s", "visual": "contexto do problema", "fala": "Se você já passou por isso, presta atenção."},
                {"cena": 2, "tempo": "5-15s", "visual": "produto e embalagem", "fala": f"Esse {name} chegou para resolver."},
                {"cena": 3, "tempo": "15-30s", "visual": "demonstração", "fala": "Mostrando passo a passo como usar."},
                {"cena": 4, "tempo": "30-45s", "visual": "detalhes e comparação", "fala": "Compare com o que você já usa."},
                {"cena": 5, "tempo": "45-55s", "visual": "depoimento curto", "fala": "Quem já comprou recomenda."},
                {"cena": 6, "tempo": "55-60s", "visual": "oferta final", "fala": "Aproveita que o estoque é limitado."},
            ]
            gancho = "Se você já passou por isso, presta atenção."
            cta = "Aproveita o link no carrinho."
        roteiro = "\n".join(f"[{s['tempo']}] {s['fala']} ({s['visual']})" for s in scenes)
        return {"duracao": f"{seconds}s", "gancho": gancho, "cenas": scenes,
                "roteiro": roteiro, "cta": cta}

    def _hashtags(self, row: dict) -> list[str]:
        from core.utils import slugify

        base = [slugify(row.get("name", "")).replace("-", ""), "achadinhos", "shopee"]
        if row.get("category"):
            base.append(slugify(row["category"]).replace("-", ""))
        return [f"#{tag}" for tag in dict.fromkeys(base) if tag][:6]
