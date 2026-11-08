"""E-COMMERCE AI EMPIRE - aplicação FastAPI.

    uvicorn app:app --reload --port 8000
    # documentação automática: http://localhost:8000/docs

O painel visual (Streamlit) roda separado:
    streamlit run dashboard/streamlit_app.py
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from api.routes import router
from core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "Centro de inteligência comercial multiagente. Todos os números são "
        "calculados por código; a IA apenas explica. Ações de risco exigem aprovação."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return f"""
    <html lang="pt-BR"><head><meta charset="utf-8">
    <title>{settings.app_name}</title>
    <style>
      body {{ font-family: system-ui, sans-serif; margin: 0; background: #0f1115; color: #e8eaf0; }}
      main {{ max-width: 760px; margin: 8vh auto; padding: 0 24px; }}
      h1 {{ font-size: 26px; margin-bottom: 4px; }}
      p {{ color: #9aa3b2; }}
      a {{ color: #7cc4ff; }}
      code {{ background: #1a1e27; padding: 2px 6px; border-radius: 4px; }}
      li {{ margin: 6px 0; }}
    </style></head>
    <body><main>
      <h1>{settings.app_name}</h1>
      <p>v{settings.version} · {settings.timezone} · {settings.currency}</p>
      <ul>
        <li><a href="/docs">Documentação interativa da API</a></li>
        <li><a href="/api/health">/api/health</a></li>
        <li><a href="/api/status">/api/status</a></li>
        <li><a href="/api/connectors">/api/connectors</a> (status real de cada canal)</li>
      </ul>
      <p>Painel: <code>streamlit run dashboard/streamlit_app.py</code></p>
    </main></body></html>
    """


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
