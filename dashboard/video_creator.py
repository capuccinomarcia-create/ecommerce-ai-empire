"""Página 13 - Criador de vídeos (roteiros e prompts)."""

from __future__ import annotations

import streamlit as st

from dashboard.common import notice, orch, page_header, render_result, run_agent, table


def render() -> None:
    o = orch()
    page_header("Criador de vídeos", "Roteiros de 15, 30 e 60 segundos e prompts por cena.")
    notice("info", "Este módulo escreve texto. Nenhum arquivo de vídeo é gerado: não há gerador "
                   "integrado, e não usamos vídeos de terceiros.")

    products = o.repo.find("products", {}, limit=100)
    options = ["(produto de melhor score)"] + [p["name"] for p in products]
    focus = st.selectbox("Produto", options)
    if st.button("Gerar roteiros", type="primary"):
        payload = {} if focus.startswith("(") else {"product": focus}
        st.session_state["video"] = run_agent("video_creator", "scripts",
                                              "Escrever roteiros de vídeo", payload)

    result = st.session_state.get("video")
    if result and result["ok"]:
        data = result["result"]["data"]
        st.subheader(f"Roteiros para {data.get('product')}")
        tabs = st.tabs(["15s", "30s", "60s"])
        for tab, key in zip(tabs, ["15s", "30s", "60s"]):
            with tab:
                script = data["scripts"][key]
                st.markdown(f"**Gancho:** {script['gancho']}")
                st.markdown(f"**CTA:** {script['cta']}")
                table(script["cenas"], key=f"scenes_{key}")
                st.code(script["roteiro"], language="text")
        st.subheader("Prompts para geração de vídeo")
        for prompt in data["prompts"]:
            st.code(prompt["prompt"], language="text")
        st.caption("Hashtags: " + " ".join(data.get("hashtags", [])))
        st.download_button(
            "Baixar roteiros (.txt)",
            "\n\n".join(f"[{k}]\n{v['roteiro']}" for k, v in data["scripts"].items()),
            file_name="roteiros_video.txt", mime="text/plain",
        )
    elif result:
        notice("bad", result.get("error", "falha"))
    render_result(result) if result and result.get("ok") else None
