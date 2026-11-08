"""Camada de IA independente de fornecedor.

Provedores suportados, em ordem de preferência (configurável em AI_PROVIDERS):
  gemini             -> Google Gemini (tem camada gratuita; exige GEMINI_API_KEY)
  openai_compatible  -> qualquer endpoint compatível com OpenAI (Ollama, llama.cpp,
                        LM Studio, Groq, OpenRouter...) via OPENAI_COMPATIBLE_BASE_URL
  offline            -> gera narrativa local determinística, sem rede e sem custo

Princípios:
- Nenhuma chave no código: só variáveis de ambiente.
- Se um provedor falhar, o próximo assume (fallback automático).
- Limite de chamadas por tarefa e controle de uso/custo (tabela ai_usage).
- O sistema é útil sem nenhuma IA paga: os agentes calculam primeiro e usam a
  IA apenas para redigir a explicação.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from core.config import Settings, get_settings

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


@dataclass
class AIResponse:
    text: str
    provider: str
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    ok: bool = True
    error: str = ""

    @property
    def used_ai(self) -> bool:
        return self.ok and self.provider not in {"offline", ""}


@dataclass
class AIStatus:
    name: str
    available: bool
    detail: str
    model: str = ""


def _post_json(url: str, payload: dict, headers: dict[str, str], timeout: int) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


class AIProvider:
    name = "base"

    def __init__(self, settings: Settings):
        self.settings = settings

    def status(self) -> AIStatus:  # pragma: no cover - sobrescrito
        raise NotImplementedError

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        facts: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AIResponse:  # pragma: no cover - sobrescrito
        raise NotImplementedError


class GeminiProvider(AIProvider):
    name = "gemini"

    def status(self) -> AIStatus:
        if not self.settings.gemini_api_key:
            return AIStatus(self.name, False, "GEMINI_API_KEY não configurada", self.settings.gemini_model)
        return AIStatus(self.name, True, "chave configurada", self.settings.gemini_model)

    def generate(self, prompt, system=None, facts=None, max_tokens=None, temperature=None) -> AIResponse:
        start = time.perf_counter()
        if not self.settings.gemini_api_key:
            return AIResponse("", self.name, ok=False, error="GEMINI_API_KEY ausente")
        url = GEMINI_ENDPOINT.format(model=self.settings.gemini_model)
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self.settings.ai_temperature if temperature is None else temperature,
                "maxOutputTokens": max_tokens or self.settings.ai_max_tokens,
            },
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        try:
            data = _post_json(
                url,
                body,
                {"Content-Type": "application/json", "x-goog-api-key": self.settings.gemini_api_key},
                self.settings.ai_timeout_seconds,
            )
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            return AIResponse(
                "", self.name, self.settings.gemini_model,
                latency_ms=int((time.perf_counter() - start) * 1000),
                ok=False, error=f"falha na chamada: {exc}",
            )
        try:
            candidates = data.get("candidates") or []
            parts = candidates[0]["content"]["parts"] if candidates else []
            text = "\n".join(p.get("text", "") for p in parts).strip()
        except (KeyError, IndexError, TypeError):
            text = ""
        usage = data.get("usageMetadata", {}) or {}
        if not text:
            return AIResponse(
                "", self.name, self.settings.gemini_model, ok=False,
                error=f"resposta vazia: {str(data)[:200]}",
                latency_ms=int((time.perf_counter() - start) * 1000),
            )
        return AIResponse(
            text=text,
            provider=self.name,
            model=self.settings.gemini_model,
            tokens_in=int(usage.get("promptTokenCount", 0) or 0),
            tokens_out=int(usage.get("candidatesTokenCount", 0) or 0),
            latency_ms=int((time.perf_counter() - start) * 1000),
        )


class OpenAICompatibleProvider(AIProvider):
    name = "openai_compatible"

    def status(self) -> AIStatus:
        if not self.settings.openai_compatible_base_url or not self.settings.openai_compatible_model:
            return AIStatus(
                self.name, False,
                "OPENAI_COMPATIBLE_BASE_URL/MODEL não configurados",
            )
        return AIStatus(
            self.name, True,
            f"endpoint {self.settings.openai_compatible_base_url}",
            self.settings.openai_compatible_model,
        )

    def generate(self, prompt, system=None, facts=None, max_tokens=None, temperature=None) -> AIResponse:
        start = time.perf_counter()
        if not self.settings.openai_compatible_base_url or not self.settings.openai_compatible_model:
            return AIResponse("", self.name, ok=False, error="endpoint não configurado")
        url = self.settings.openai_compatible_base_url.rstrip("/") + "/chat/completions"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body = {
            "model": self.settings.openai_compatible_model,
            "messages": messages,
            "temperature": self.settings.ai_temperature if temperature is None else temperature,
            "max_tokens": max_tokens or self.settings.ai_max_tokens,
        }
        headers = {"Content-Type": "application/json"}
        if self.settings.openai_compatible_key:
            headers["Authorization"] = f"Bearer {self.settings.openai_compatible_key}"
        try:
            data = _post_json(url, body, headers, self.settings.ai_timeout_seconds)
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            return AIResponse(
                "", self.name, self.settings.openai_compatible_model,
                latency_ms=int((time.perf_counter() - start) * 1000),
                ok=False, error=f"falha na chamada: {exc}",
            )
        choices = data.get("choices") or []
        text = (choices[0].get("message", {}).get("content", "") if choices else "").strip()
        usage = data.get("usage", {}) or {}
        if not text:
            return AIResponse("", self.name, ok=False, error="resposta vazia")
        return AIResponse(
            text=text,
            provider=self.name,
            model=self.settings.openai_compatible_model,
            tokens_in=int(usage.get("prompt_tokens", 0) or 0),
            tokens_out=int(usage.get("completion_tokens", 0) or 0),
            latency_ms=int((time.perf_counter() - start) * 1000),
        )


class OfflineProvider(AIProvider):
    """Narrativa local determinística.

    Não "inventa" conteúdo: organiza os fatos calculados em texto em português.
    É o modo de operação com orçamento R$ 0 e sem chave de API.
    """

    name = "offline"

    def status(self) -> AIStatus:
        return AIStatus(self.name, True, "modo local, sem rede e sem custo", "local-template")

    def generate(self, prompt, system=None, facts=None, max_tokens=None, temperature=None) -> AIResponse:
        start = time.perf_counter()
        lines: list[str] = []
        facts = facts or {}
        intro = facts.get("intro") or "Resumo gerado localmente a partir dos dados calculados."
        lines.append(intro)
        bullets = facts.get("bullets") or []
        for bullet in bullets:
            lines.append(f"- {bullet}")
        if facts.get("closing"):
            lines.append("")
            lines.append(str(facts["closing"]))
        if not bullets and not facts:
            lines.append(
                "- Nenhum provedor de IA generativa está configurado (modo offline). "
                "Os cálculos e a pontuação continuam válidos; a redação é local."
            )
        text = "\n".join(lines)
        return AIResponse(
            text=text,
            provider=self.name,
            model="local-template",
            tokens_in=max(1, len(prompt) // 4),
            tokens_out=max(1, len(text) // 4),
            latency_ms=int((time.perf_counter() - start) * 1000),
        )


PROVIDER_CLASSES = {
    "gemini": GeminiProvider,
    "openai_compatible": OpenAICompatibleProvider,
    "offline": OfflineProvider,
}


class AIService:
    """Orquestra provedores, limites de uso e registro de custos."""

    def __init__(self, settings: Settings | None = None, repo=None):
        self.settings = settings or get_settings()
        self.repo = repo
        self._calls_by_task: dict[str, int] = {}
        self._providers: list[AIProvider] = []
        for name in self.settings.ai_providers:
            provider_cls = PROVIDER_CLASSES.get(name)
            if provider_cls:
                self._providers.append(provider_cls(self.settings))
        if not any(isinstance(p, OfflineProvider) for p in self._providers):
            self._providers.append(OfflineProvider(self.settings))

    # ----------------------------------------------------------------- status --
    def status(self) -> list[dict[str, Any]]:
        items = []
        for provider in self._providers:
            st = provider.status()
            items.append(
                {"provider": st.name, "available": st.available, "detail": st.detail, "model": st.model}
            )
        return items

    @property
    def has_remote_provider(self) -> bool:
        return any(p.status().available for p in self._providers if p.name != "offline")

    def usage_summary(self) -> dict[str, Any]:
        if self.repo is None:
            return {"calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}
        rows = self.repo.find("ai_usage", {}, order_by="-created_at", limit=1000)
        return {
            "calls": len(rows),
            "tokens_in": sum(int(r.get("prompt_tokens") or 0) for r in rows),
            "tokens_out": sum(int(r.get("completion_tokens") or 0) for r in rows),
            "cost_usd": round(sum(float(r.get("cost_usd") or 0) for r in rows), 6),
        }

    # -------------------------------------------------------------- generate --
    def generate(
        self,
        prompt: str,
        system: str | None = None,
        facts: dict[str, Any] | None = None,
        agent: str = "",
        task_id: str = "",
        allow_remote: bool = True,
    ) -> AIResponse:
        """Tenta provedores em ordem; sempre termina com resposta (offline no pior caso)."""
        if task_id and self._calls_by_task.get(task_id, 0) >= self.settings.ai_max_calls_per_task:
            return AIResponse(
                "", "guard", ok=False,
                error="limite de chamadas de IA por tarefa atingido; usando resultados determinísticos",
            )

        candidates = [
            p for p in self._providers
            if p.name == "offline" or (allow_remote and p.status().available)
        ]
        if not allow_remote:
            candidates = [p for p in self._providers if p.name == "offline"]

        last_error = ""
        for provider in candidates:
            if provider.name != "offline":
                self._calls_by_task[task_id or "_"] = self._calls_by_task.get(task_id or "_", 0) + 1
            response = provider.generate(prompt, system=system, facts=facts)
            self._log(response, agent=agent, task_id=task_id)
            if response.ok:
                return response
            last_error = response.error
        offline = OfflineProvider(self.settings)
        response = offline.generate(prompt, system=system, facts=facts)
        response.error = last_error
        return response

    def _log(self, response: AIResponse, agent: str, task_id: str) -> None:
        if self.repo is None:
            return
        try:
            self.repo.insert(
                "ai_usage",
                {
                    "provider": response.provider,
                    "model": response.model,
                    "task_id": task_id or None,
                    "agent": agent or None,
                    "prompt_tokens": response.tokens_in,
                    "completion_tokens": response.tokens_out,
                    "cost_usd": 0.0,
                    "latency_ms": response.latency_ms,
                    "ok": response.ok,
                    "error": response.error or None,
                },
            )
        except Exception:  # pragma: no cover - telemetria nunca derruba o fluxo
            pass
