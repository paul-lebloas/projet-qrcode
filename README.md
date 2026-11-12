# Scan produit

Application conteneurisée avec Docker Compose : on fournit un **EAN-13**, le contenu d'un **QR Code** ou une **photo** du code, et l'application retrouve le produit. Les lectures sont mises en cache dans Redis.

## Démarrer

```bash
cp .env.example .env        # puis changer les deux mots de passe
docker compose up -d --build
```

Ouvrir <http://localhost:8080>. Pour arrêter : `docker compose down` (ajouter `-v` pour supprimer aussi la base).

Vérifier que tout est en place :

```bash
python3 scripts/check-compose.py   # contrôle statique : un seul port publié, réseaux cloisonnés
./scripts/smoke-test.sh            # contrôle du projet en marche : produit trouvé, MISS puis HIT, ports fermés
```

## Architecture

```
navigateur ──8080──▶ IHM (Vue 3 + nginx)
                       │  réseau « front »
                       ▼
                 Orchestrateur (Python / FastAPI)
                       │  réseau « back » (internal)
            ┌──────────┴───────────┐
            ▼                      ▼
     OCR (Python)          Data Access (C# / ASP.NET)
                                   │  réseau « data » (internal)
                          ┌────────┴────────┐
                          ▼                 ▼
                    Redis (cache)      PostgreSQL
```

| Service | Rôle | Technologie |
|---|---|---|
| `ihm` | Interface, seul service qui publie un port (8080) ; relaie `/api` vers l'orchestrateur | Vue 3, Vite, nginx |
| `orchestrator` | Détecte EAN-13 ou QR Code, appelle l'OCR si une image est fournie, interroge Data Access, assemble la réponse | Python, FastAPI |
| `ocr` | Extrait un code d'une image : lecture directe des codes (ZBar), sinon OCR du numéro imprimé (Tesseract) | Python |
| `dataaccess` | Seul accès à PostgreSQL ; cache-aside dans Redis | C#, ASP.NET, Npgsql, StackExchange.Redis |
| `redis` | Cache (mémoire bornée, éviction LRU, sans persistance, mot de passe) | Redis 7 |
| `postgres` | Stockage persistant | PostgreSQL 16 |

Tout le front utilise des logiciels libres (Vue, Vite, nginx, police Archivo sous licence OFL).

## Réseau et sécurité

- **Seul le port 8080 est publié.** Aucun autre service n'a de `ports:` dans `docker-compose.yml`.
- Trois réseaux : `front` (IHM ↔ orchestrateur), `back` (orchestrateur ↔ OCR / Data Access) et `data` (Data Access ↔ Redis / PostgreSQL). `back` et `data` sont `internal` : pas de route vers l'extérieur.
- L'orchestrateur ne voit ni Redis ni PostgreSQL ; l'OCR ne voit que l'orchestrateur ; **Data Access est le seul pont vers la base et le cache**.
- Conteneurs applicatifs : utilisateur non root, système de fichiers en lecture seule, `cap_drop: ALL`, `no-new-privileges`.
- nginx : en-têtes de sécurité et CSP stricte (aucun script ni style inline), limite de débit sur `/api`, images limitées à 5 Mo, documentation Swagger/OpenAPI non exposée.
- Les mots de passe sont lus dans `.env` (non versionné). Le compose refuse de démarrer s'ils manquent.

## Cache Redis

Cache-aside, géré par Data Access :

- lecture : Redis d'abord ; en cas d'absence, PostgreSQL puis écriture dans Redis (10 min par défaut) ;
- un code **inconnu** est aussi mémorisé, 60 s, pour ne pas solliciter la base à chaque scan ;
- écriture (`POST`/`PUT`/`DELETE`) : invalidation des clés du produit et de toutes les recherches en cache ;
- si Redis tombe, le service répond directement depuis PostgreSQL (`cache: "BYPASS"`).

Chaque réponse indique son origine (`HIT`, `MISS` ou `BYPASS`), affichée dans l'IHM, et `GET /api/cache/stats` donne le taux de réussite.

## API publique (via le port 8080)

| Méthode et chemin | Corps / paramètres | Réponse |
|---|---|---|
| `POST /api/scan` | `{"code": "3760000000017"}` (champ `type` facultatif : `auto`, `ean13`, `qr`) | produit, type détecté, origine du cache |
| `POST /api/scan/image` | formulaire `file` (image, 5 Mo max) | idem, avec `source: "image"` |
| `GET /api/products/search?q=…&limit=…` | nom, marque ou catégorie | liste de produits |
| `GET /api/cache/stats` | | hits, misses, taux, état de Redis |

Règle de détection : 13 chiffres (espaces et tirets tolérés) = EAN-13, dont la clé de contrôle doit être valide ; tout autre texte non vide = contenu de QR Code.

Les endpoints d'écriture (`POST/PUT/DELETE /products`) existent dans Data Access mais ne sont volontairement **pas relayés** par l'orchestrateur : ils restent internes.

## Données de démonstration

`db/init.sql` crée la table `products` et 10 produits fictifs (EAN-13 à clé valide, 7 avec QR Code). Il ne s'exécute qu'à la création du volume `pgdata`. Exemples : `3760000000017` (biscuits), `https://produits.example/p/1002` (café), `4006381333931` (inconnu).

## Remplacer un composant

Chaque service n'est lié aux autres que par son contrat HTTP :

- **OCR** : tout service qui répond à `POST /decode` (champ `file`) par `{"candidates": [{"type": "ean13"|"qr", "value": "…", "source": "barcode"|"text"}]}` et à `GET /health`.
- **Data Access** : voir les routes `/products/lookup`, `/products/search`, `/cache/stats` ; l'en-tête `X-Cache` porte l'origine.
- **IHM** : n'importe quel front servi sur 8080 qui appelle `/api`.

## Tests

```bash
cd orchestrator && pip install -r requirements-dev.txt && python -m pytest   # 47 tests
cd ocr          && pip install -r requirements-dev.txt && python -m pytest   # 27 tests (images générées, Tesseract et ZBar requis)
cd ihm          && npm ci && npm test                                         # 7 tests (EAN-13, détection du type)
```

## Structure

```
docker-compose.yml   .env.example   db/init.sql
ihm/  orchestrator/  ocr/  dataaccess/  scripts/
```
