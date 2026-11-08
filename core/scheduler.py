"""Agenda de verdade: lê as rotinas cadastradas e executa na hora certa.

Antes deste módulo as rotinas existiam só como cadastro (`automations`), sem nada
que as disparasse. Aqui elas rodam:

    python -m core.scheduler --tick        # executa o que venceu, uma vez
    python -m core.scheduler --listar      # mostra próxima execução de cada rotina
    python -m core.scheduler --loop        # fica de pé executando

Sem dependência externa: o cron de 5 campos (minuto hora dia mês dia-da-semana) é
interpretado aqui, com `*`, listas, intervalos e passos (`*/15`, `0 12,18 * * *`).

Regra do projeto que vale aqui: rotina nunca publica, compra ou paga sozinha. Ela
calcula, monta rascunho e registra o que precisa da sua aprovação.
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from database.repository import get_repository

FUSO = ZoneInfo("America/Sao_Paulo")
LIMITE_DIAS_BUSCA = 400

Executor = Callable[[dict[str, Any], Any], dict[str, Any]]


# ------------------------------------------------------------------ cron --
def _expandir(campo: str, minimo: int, maximo: int) -> set[int]:
    if not campo or campo == "*":
        return set(range(minimo, maximo + 1))
    valores: set[int] = set()
    for parte in campo.split(","):
        parte = parte.strip()
        if not parte:
            continue
        passo = 1
        if "/" in parte:
            parte, _, bruto = parte.partition("/")
            passo = max(int(bruto), 1)
        if parte in {"*", ""}:
            inicio, fim = minimo, maximo
        elif "-" in parte:
            a, _, b = parte.partition("-")
            inicio, fim = int(a), int(b)
        else:
            inicio = fim = int(parte)
        if inicio > fim:
            inicio, fim = fim, inicio
        valores.update(range(inicio, fim + 1, passo))
    return {v for v in valores if minimo <= v <= maximo}


def _dow(campo: str) -> set[int]:
    valores = _expandir(campo, 0, 7)
    return {0 if v == 7 else v for v in valores}  # 7 e 0 = domingo


def _casa(cron: str, quando: datetime) -> bool:
    campos = cron.split()
    if len(campos) != 5:
        raise ValueError(f"cron inválido: {cron!r} (use 5 campos)")
    minuto, hora, dia, mes, diasemana = campos
    if quando.minute not in _expandir(minuto, 0, 59):
        return False
    if quando.hour not in _expandir(hora, 0, 23):
        return False
    if quando.month not in _expandir(mes, 1, 12):
        return False
    dias = _expandir(dia, 1, 31)
    semanas = _dow(diasemana)
    if dia == "*" and diasemana == "*":
        return True
    if dia == "*":
        return (quando.isoweekday() % 7) in semanas
    if diasemana == "*":
        return quando.day in dias
    return quando.day in dias or (quando.isoweekday() % 7) in semanas


def proximo_disparo(cron: str, depois: datetime | None = None) -> datetime:
    """Primeira execução do cron estritamente depois de `depois`."""
    if depois is None:
        depois = datetime.now(FUSO)
    if depois.tzinfo is None:
        depois = depois.replace(tzinfo=FUSO)
    inicio = (depois + timedelta(minutes=1)).replace(second=0, microsecond=0)
    dia = inicio.replace(hour=0, minute=0)
    for _ in range(LIMITE_DIAS_BUSCA):
        for minuto in range(0, 24 * 60):
            candidato = dia + timedelta(minutes=minuto)
            if candidato < inicio:
                continue
            if _casa(cron, candidato):
                return candidato
        dia += timedelta(days=1)
        if dia.month not in _expandir(cron.split()[3], 1, 12):
            continue
    raise ValueError(f"cron sem próxima execução nos próximos {LIMITE_DIAS_BUSCA} dias: {cron}")


# -------------------------------------------------------------- agendador --
class Agendador:
    def __init__(self, repo=None, executor: Executor | None = None,
                 agora_fn: Callable[[], datetime] | None = None) -> None:
        self.repo = repo or get_repository()
        self.executor = executor or executar_rotina
        self.agora = agora_fn or (lambda: datetime.now(FUSO))

    # -------------------------------------------------------------- leitura --
    def rotinas(self, apenas_ativas: bool = False) -> list[dict[str, Any]]:
        filtro = {"enabled": 1} if apenas_ativas else {}
        return self.repo.find("automations", filtro, order_by="name") or []

    def devido(self, rotina: dict[str, Any], agora: datetime | None = None) -> bool:
        agora = agora or self.agora()
        if not rotina.get("enabled"):
            return False
        cron = str(rotina.get("schedule_cron") or "").strip()
        if not cron:
            return False
        proxima = rotina.get("next_run_at")
        if proxima:
            try:
                alvo = datetime.fromisoformat(str(proxima).replace("Z", "+00:00"))
                if alvo.tzinfo is None:
                    alvo = alvo.replace(tzinfo=FUSO)
                return agora >= alvo
            except ValueError:
                pass
        ultima = rotina.get("last_run_at")
        if ultima:
            try:
                base = datetime.fromisoformat(str(ultima).replace("Z", "+00:00"))
                if base.tzinfo is None:
                    base = base.replace(tzinfo=FUSO)
                return proximo_disparo(cron, base) <= agora
            except ValueError:
                pass
        return True  # nunca rodou: roda na próxima passagem

    # ------------------------------------------------------------- execução --
    def tick(self, agora: datetime | None = None,
             forcar: list[str] | None = None) -> list[dict[str, Any]]:
        agora = agora or self.agora()
        executadas: list[dict[str, Any]] = []
        for rotina in self.rotinas():
            forcada = bool(forcar and rotina.get("name") in forcar)
            if not forcada and not self.devido(rotina, agora):
                continue
            executadas.append(self._rodar(rotina, agora, forcada))
        return executadas

    def _rodar(self, rotina: dict[str, Any], agora: datetime, forcada: bool) -> dict[str, Any]:
        nome = rotina.get("name") or rotina.get("job")
        inicio = time.time()
        try:
            resultado = self.executor(rotina, self.repo) or {}
            status = "ok"
            resumo = str(resultado.get("summary") or "rotina executada")
        except Exception as exc:  # rotina com defeito não derruba o agendador
            status = "erro"
            resumo = f"{type(exc).__name__}: {exc}"
            resultado = {}
        duracao = round(time.time() - inicio, 2)

        campos: dict[str, Any] = {"last_run_at": agora.isoformat(timespec="seconds")}
        cron = str(rotina.get("schedule_cron") or "").strip()
        if cron:
            try:
                campos["next_run_at"] = proximo_disparo(cron, agora).isoformat(timespec="seconds")
            except ValueError:
                campos["next_run_at"] = None
        self.repo.update("automations", rotina["id"], campos)
        try:
            from analytics.reports import save_report

            save_report(self.repo, kind="rotina", title=f"{nome} · {status}",
                        body=resumo, is_demo=False)
        except Exception:
            pass
        return {"name": nome, "status": status, "summary": resumo,
                "duration_s": duracao, "forced": forcada,
                "next_run_at": campos.get("next_run_at"), **(
                    {"findings": resultado.get("findings")} if resultado.get("findings") else {})}


def executar_rotina(rotina: dict[str, Any], repo) -> dict[str, Any]:
    """Despacha a rotina para o job correspondente (ver core/jobs.py)."""
    from core import jobs

    nome = str(rotina.get("job") or rotina.get("name") or "")
    funcao = jobs.JOBS.get(nome)
    if funcao is None:
        raise ValueError(f"job desconhecido: {nome!r}. Disponíveis: {', '.join(sorted(jobs.JOBS))}")
    return funcao(repo)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agendador de rotinas")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--tick", action="store_true", help="executa o que venceu e sai")
    grupo.add_argument("--listar", action="store_true", help="mostra as rotinas")
    grupo.add_argument("--loop", action="store_true", help="fica executando")
    parser.add_argument("--forcar", nargs="*", default=None, help="nomes de rotina a rodar agora")
    parser.add_argument("--intervalo", type=int, default=60, help="segundos entre checagens")
    args = parser.parse_args(argv)

    agendador = Agendador()
    if args.listar:
        rotinas = agendador.rotinas()
        if not rotinas:
            print("Nenhuma rotina cadastrada. Rode: python -m core.automations_seed")
            return 0
        for rotina in rotinas:
            estado = "ativa" if rotina.get("enabled") else "pausada"
            print(f"{rotina.get('name'):<28} {rotina.get('schedule_cron'):<16} "
                  f"{estado:<8} próxima: {rotina.get('next_run_at') or '—'}")
        return 0

    if args.tick or args.forcar is not None:
        resultados = agendador.tick(forcar=args.forcar)
        if not resultados:
            print("Nada vencido agora.")
        for item in resultados:
            print(f"[{item['status']}] {item['name']}: {item['summary']}")
        return 0

    if args.loop:
        print("agendador no ar — Ctrl+C para parar", flush=True)
        while True:
            for item in agendador.tick():
                print(f"{datetime.now(FUSO):%H:%M} [{item['status']}] "
                      f"{item['name']}: {item['summary']}", flush=True)
            time.sleep(max(args.intervalo, 5))

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
