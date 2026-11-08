# Rodar 24h de graça no Hugging Face Spaces

O Space roda o `Dockerfile` deste repositório: um processo com o bot do Telegram e
(o ciclos autônomos, se você quiser). Sem cartão de crédito.

1. Crie conta em https://huggingface.co (grátis).
2. Crie um Space: New Space -> SDK **Docker** -> template **Blank** -> visibilidade
   **Private**.
3. No Space, aba **Settings -> Variables and secrets**, adicione como *secret*:
   - `TELEGRAM_BOT_TOKEN` (obtido com o @BotFather no Telegram)
   - `TELEGRAM_ALLOWED_CHAT_IDS` (seu id, para o bot não ficar aberto)
   - opcional: `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`
4. Envie este repositório para o Space:
   ```
   git remote add space https://huggingface.co/spaces/SEU_USUARIO/ecommerce-ai-empire
   git push space main
   ```
5. Abra a aba **Logs** e confira `agente no ar: mande mensagem no Telegram`.
6. Fale com o seu bot no Telegram.

## Dois detalhes que importam

**O Space hiberna** depois de um tempo sem visitas. O bot sozinho não conta como
visita. Solução gratuita: um monitor de URL (UptimeRobot, gratuito) batendo no
endereço do Space a cada 5 minutos. Isso mantém o Space acordado.

**O disco é temporário**: a cada reinício o SQLite volta ao que está no repositório.
Para dados que não podem se perder (produtos, vendas, aprovações), use o Supabase
gratuito: basta definir `SUPABASE_URL` e `SUPABASE_KEY` nos secrets. O sistema já
sabe gravar nele.
