# Super agente 24h: bot do Telegram + ciclos autônomos no mesmo processo.
# Roda em qualquer host com Docker (Hugging Face Spaces, VM grátis, VPS, NAS).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=America/Sao_Paulo \
    SQLITE_PATH=/data/empire.db

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# dados persistentes em volume; em host sem volume, o banco fica no sistema de arquivos
RUN mkdir -p /data

# aquece importações para o primeiro comando responder rápido
RUN python -c "import core.chat_agent, scripts.run_agent" || true

CMD ["python", "-m", "scripts.run_agent"]
