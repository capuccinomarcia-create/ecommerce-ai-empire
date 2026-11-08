"""Página de controle do bot: ligar, desligar, ver estado e log.

Aqui o botão faz algo de verdade, porque este painel roda na sua máquina ou VM
(Streamlit). O painel publicado no GitHub Pages é estático: lá o botão só explica
o que fazer.
"""

from __future__ import annotations

import streamlit as st

from dashboard.common import page_header
from scripts import bot_control


def _estado() -> bot_control.EstadoBot:
    return bot_control.status()


def render() -> None:
    page_header("Bot no celular", "Liga e desliga o agente que responde no Telegram")

    estado = _estado()
    colunas = st.columns(4)
    colunas[0].metric("Bot", estado.rotulo.upper())
    colunas[1].metric("PID", str(estado.pid or "—"))
    colunas[2].metric("Token", "configurado" if estado.token_configurado else "faltando")
    colunas[3].metric("Desde", (estado.desde or "—").replace("T", " "))

    if not estado.token_configurado:
        st.warning(
            "Falta o token do bot. No Telegram, fale com @BotFather, envie /newbot, "
            "copie o token e coloque no arquivo .env como TELEGRAM_BOT_TOKEN=123456:ABC..."
        )

    ligar, desligar, reiniciar = st.columns(3)
    if ligar.button("Ligar o bot", type="primary", width="stretch",
                    disabled=estado.rodando or not estado.token_configurado):
        ok, mensagem = bot_control.start()
        (st.success if ok else st.error)(mensagem)
        st.rerun()
    if desligar.button("Desligar", width="stretch", disabled=not estado.rodando):
        ok, mensagem = bot_control.parar()
        (st.success if ok else st.warning)(mensagem)
        st.rerun()
    if reiniciar.button("Reiniciar", width="stretch", disabled=not estado.rodando):
        bot_control.parar()
        ok, mensagem = bot_control.start()
        (st.success if ok else st.error)(mensagem)
        st.rerun()

    st.divider()
    st.markdown("**Como testar em 30 segundos**")
    st.markdown(
        "1. Ligue o bot aqui.\n"
        "2. Abra o Telegram, ache o seu bot pelo nome que você deu no @BotFather.\n"
        "3. Mande `status` — ele responde o estado da operação.\n"
        "4. Mande `vendas` — ele devolve o plano de venda.\n"
        "5. Mande `ajuda` — lista tudo que ele executa."
    )

    st.divider()
    st.markdown("**Log do bot**")
    log = bot_control.ultimas_linhas(60)
    st.code(log or "sem log ainda", language="text")
    if st.button("Atualizar estado"):
        st.rerun()
