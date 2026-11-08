# Rodar 24h de graça numa VM (sem hibernar)

Opção mais estável e sem truque de "manter acordado": a VM fica ligada de verdade.

## Oracle Cloud Always Free (grátis para sempre, pede cartão só para verificação)

1. Crie a conta em https://www.oracle.com/cloud/free/ e escolha a região mais próxima
   (ex.: São Paulo).
2. Crie uma instância **Ampere A1 (ARM)** com Ubuntu 22.04, 1 OCPU e 6 GB já basta.
3. Libere SSH, entre e instale:
   ```
   sudo apt update && sudo apt install -y python3-venv git
   git clone https://github.com/capuccinomarcia-create/ecommerce-ai-empire.git
   cd ecommerce-ai-empire
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   ```
4. Crie o `.env` (nunca comite esse arquivo):
   ```
   TELEGRAM_BOT_TOKEN=123456:ABC...
   TELEGRAM_ALLOWED_CHAT_IDS=seu_id
   GEMINI_API_KEY=opcional
   SUPABASE_URL=opcional
   SUPABASE_KEY=opcional
   ```
5. Teste antes de deixar rodando: `.venv/bin/python -m scripts.run_agent --check`
6. Instale como serviço para subir junto com a máquina:
   ```
   sudo cp deploy/vm/empire-agent.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now empire-agent
   sudo systemctl status empire-agent
   ```
7. Veja os logs: `journalctl -u empire-agent -f`

## Alternativa: seu computador

`python -m scripts.run_agent` funciona igual, mas só enquanto o PC estiver ligado.
