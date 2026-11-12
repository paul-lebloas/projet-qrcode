#!/usr/bin/env python3
"""Vérification statique du docker-compose.yml (aucun conteneur lancé).

Contrôle les contraintes du cadrage §10 et §13 :
  - un seul port publié sur l'hôte : 8080 ;
  - Redis, PostgreSQL, OCR, Data Access et orchestrateur ne publient rien ;
  - Redis et PostgreSQL ne sont que sur un réseau interne ;
  - l'orchestrateur n'est branché ni sur Redis ni sur PostgreSQL (réseau `data`) ;
  - les réseaux `back` et `data` sont `internal`.

Usage : python3 scripts/check-compose.py [--env-file .env.example]
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_config(env_file: str) -> dict:
    out = subprocess.run(
        ["docker", "compose", "--env-file", env_file, "config", "--format", "json"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if out.returncode != 0:
        sys.exit(f"docker compose config a échoué :\n{out.stderr}")
    return json.loads(out.stdout)


def main() -> int:
    env_file = "--env-file"
    args = sys.argv[1:]
    env = args[args.index(env_file) + 1] if env_file in args else (
        ".env" if (ROOT / ".env").exists() else ".env.example")
    cfg = load_config(env)
    services, networks = cfg["services"], cfg["networks"]
    failures: list[str] = []

    def check(ok: bool, label: str) -> None:
        print(("  OK   " if ok else "  FAIL ") + label)
        if not ok:
            failures.append(label)

    # 1. Ports publiés
    published = {
        (name, str(p.get("published")), p.get("target"))
        for name, svc in services.items() for p in svc.get("ports", [])
    }
    check(len(published) == 1 and next(iter(published))[1] == "8080",
          f"seul le port 8080 est publié (trouvé : {sorted(published) or 'aucun'})")
    check(all(not svc.get("ports") for n, svc in services.items() if n != "ihm"),
          "aucun service interne ne publie de port")

    # 2. Réseaux internes
    check(networks["back"].get("internal") is True, "réseau `back` internal")
    check(networks["data"].get("internal") is True, "réseau `data` internal")
    check(not networks["front"].get("internal"), "réseau `front` porte le port public")

    # 3. Cloisonnement
    nets = {n: set(svc.get("networks", {}) or ["default"]) for n, svc in services.items()}
    check(nets["redis"] == {"data"}, "Redis uniquement sur `data`")
    check(nets["postgres"] == {"data"}, "PostgreSQL uniquement sur `data`")
    check(nets["ocr"] == {"back"}, "OCR uniquement sur `back`")
    check("data" not in nets["orchestrator"], "l'orchestrateur ne voit ni Redis ni PostgreSQL")
    check("data" in nets["dataaccess"], "Data Access seul pont vers Redis/PostgreSQL")
    check(nets["ihm"] == {"front"}, "l'IHM ne voit que l'orchestrateur (réseau `front`)")

    # 4. Aucun mode réseau/privilège dangereux
    for n, svc in services.items():
        check(svc.get("network_mode") not in ("host",) and not svc.get("privileged"),
              f"{n} : ni network_mode host ni privileged")

    print()
    if failures:
        print(f"{len(failures)} contrôle(s) en échec.")
        return 1
    print("Tous les contrôles de configuration réseau sont OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
