#!/usr/bin/env bash
# Test de fumée à lancer APRÈS `docker compose up -d --build` (le projet doit tourner).
#
#   ./scripts/smoke-test.sh
#
# Vérifie de l'extérieur, comme un client : l'IHM répond sur 8080, un produit
# est trouvé, la 2e lecture vient du cache Redis, et aucun autre port n'est joignable.
set -u

BASE="${BASE_URL:-http://127.0.0.1:8080}"
HOST="${TARGET_HOST:-127.0.0.1}"
fail=0

ok() { printf '  OK   %s\n' "$1"; }
ko() { printf '  FAIL %s\n' "$1"; fail=$((fail + 1)); }

# check "libellé" commande [arguments...]  -> OK si la commande réussit
check() {
  local label=$1
  shift
  if "$@"; then ok "$label"; else ko "$label"; fi
}

has()    { grep -q -- "$2" <<<"$1"; }
status() { curl -s -o /dev/null -w '%{http_code}' -m 10 "$@"; }
scan()   { curl -fsS -m 10 -X POST "$BASE/api/scan" -H 'Content-Type: application/json' -d "{\"code\":\"$1\"}"; }
closed() { ! (exec 3<>"/dev/tcp/$HOST/$1") 2>/dev/null; }
is()     { [ "$1" = "$2" ]; }

echo "Point d'entrée ($BASE)"
check "l'IHM répond sur 8080" curl -fsS -m 5 -o /dev/null "$BASE/"
check "/healthz répond" has "$(curl -fsS -m 5 "$BASE/healthz" 2>/dev/null)" ok
check "la documentation interne n'est pas exposée" is "$(status "$BASE/api/docs")" 404

echo "Cache Redis (cache-aside)"
if docker compose exec -T redis sh -c 'redis-cli -a "$REDIS_PASSWORD" --no-auth-warning flushall' >/dev/null 2>&1; then
  ok "cache vidé"
else
  ko "impossible de vider Redis (docker compose exec)"
fi
first=$(scan 3760000000017 2>/dev/null)
second=$(scan 3760000000017 2>/dev/null)
check "EAN-13 connu : produit trouvé" has "$first" '"found":true'
check "1re lecture : MISS (lue en base)" has "$first" '"cache":"MISS"'
check "2e lecture : HIT (lue dans Redis)" has "$second" '"cache":"HIT"'
check "QR Code connu : produit trouvé" has "$(scan 'https://produits.example/p/1002' 2>/dev/null)" '"found":true'
check "code inconnu : found=false" has "$(scan 4006381333931 2>/dev/null)" '"found":false'
check "EAN-13 à clé incorrecte : refusé (422)" is "$(status -X POST "$BASE/api/scan" -H 'Content-Type: application/json' -d '{"code":"3760000000018"}')" 422

echo "Isolation réseau (seul 8080 doit être joignable depuis l'hôte)"
for port in 5432 6379 8000 8001 5000 80 443; do
  check "port $port fermé" closed "$port"
done
published=$(docker compose ps --format '{{.Publishers}}' 2>/dev/null | grep -o '[0-9]*->' | sort -u | tr -d '\n')
check "ports publiés par Docker : uniquement 8080 (trouvé : ${published:-aucun})" is "$published" '8080->'

echo
if [ "$fail" -eq 0 ]; then
  echo "Tous les contrôles passent."
else
  echo "$fail contrôle(s) en échec."
  exit 1
fi
