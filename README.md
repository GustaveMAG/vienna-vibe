# Vienna Vibe — pipeline de données météo et écoutes musicales

Pipeline de données horaire qui croise la météo de Vienne et de Lille avec
mon historique d'écoute Spotify, pour répondre à une question simple :
**est-ce que le temps qu'il fait influence ce que j'écoute ?**

Le projet est né à Vienne, pendant un semestre d'échange, sous la forme d'une
application de génération de playlists. Il a été reconstruit en pipeline de
données : les deux sources sont désormais collectées automatiquement toutes
les heures, historisées, contrôlées, et exposées sous forme de vues d'analyse.

---

## Ce que fait le pipeline

```mermaid
flowchart LR
    OM["Open-Meteo API<br/>météo horaire"] --> ING1["ingest_weather"]
    SP["Spotify API<br/>/me/player/recently-played"] --> ING2["ingest_listening"]

    ING1 --> RAW[("raw.api_payload<br/>payloads bruts (JSONB)")]
    ING2 --> RAW

    ING1 --> FW[("core.fact_weather_hourly<br/>grain : lieu x heure")]
    ING2 --> DIM[("core.dim_track<br/>core.dim_artist")]
    DIM --> FL[("core.fact_listening_event<br/>grain : instant x titre")]
    ING2 --> FL

    FW --> QC{{"9 contrôles<br/>de qualité"}}
    FL --> QC
    QC -->|échec| STOP["DAG en erreur"]
    QC -->|succès| MARTS[("marts.*<br/>vues d'analyse")]

    AF["Airflow<br/>schedule 0 * * * *<br/>catchup activé"] -.->|pilote| ING1
    AF -.->|pilote| ING2
    AF -.->|pilote| QC
```

Trois étapes, exécutées chaque heure :

1. **`ingest_weather`** interroge Open-Meteo pour chaque lieu suivi, archive
   le payload brut, puis charge les observations horaires.
2. **`ingest_listening`** interroge l'historique d'écoute Spotify, alimente
   les dimensions titre et artiste, puis insère les nouvelles écoutes.
3. **`quality_checks`** exécute neuf contrôles sur l'état consolidé et fait
   tomber le DAG si l'un d'eux échoue.

---

## Les décisions de conception

C'est la partie qui compte. Chaque choix ci-dessous répond à une contrainte
réelle, et pas à une préférence esthétique.

### Pourquoi une collecte horaire, et pas quotidienne

L'endpoint `/me/player/recently-played` de Spotify ne renvoie que les
**50 dernières écoutes**. Au-delà, les plus anciennes sont définitivement
perdues : il n'existe aucun moyen de les récupérer plus tard.

La planification horaire n'est donc pas décorative, c'est la condition
d'existence du jeu de données. Un jour d'interruption du pipeline, et une
journée d'historique disparaît pour toujours. C'est aussi la raison pour
laquelle les collectes se **recouvrent volontairement** : chaque exécution
redemande les trois heures précédentes, pour qu'un run manqué soit rattrapé
par le suivant sans intervention manuelle.

### Pourquoi l'idempotence, et comment elle est obtenue

Un pipeline qui se rejoue doit produire le même résultat, sinon le
recouvrement décrit ci-dessus créerait des doublons à chaque heure.

Chaque table de faits porte une **clé naturelle** contrainte `UNIQUE`, et
tous les écrits passent par `INSERT ... ON CONFLICT` :

| Table | Clé naturelle | Stratégie | Pourquoi |
|---|---|---|---|
| `fact_weather_hourly` | `(location_id, observed_at)` | `DO UPDATE` | Open-Meteo affine ses valeurs récentes : la dernière version reçue est la plus juste. |
| `fact_listening_event` | `(played_at, track_id)` | `DO NOTHING` | Une écoute est un fait immuable : on ne la corrige jamais. |
| `dim_track` | `track_id` | `DO UPDATE` | Dimension à évolution lente de type 1 : la popularité change, on garde la dernière valeur connue. |

Le pipeline est paramétré par un **créneau logique** (`--window`) et non par
« maintenant ». Relancer le créneau de mardi 14 h retraite exactement les
mêmes données. C'est ce qui rend le backfill sûr : si le planificateur est
resté éteint trois jours, Airflow rejoue les créneaux manquants, et aucun
doublon n'en résulte.

Cette propriété est vérifiée par un test d'intégration qui charge deux fois
le même jeu de données et compare les volumes.

### Pourquoi ces endpoints Spotify, et pas les descripteurs musicaux

En novembre 2024, Spotify a restreint aux applications historiques les
endpoints `audio-features`, `audio-analysis` et `recommendations`. Énergie,
tempo et valence ne sont donc plus accessibles à une application créée
aujourd'hui — ce qui a condamné la première version du projet.

Le pipeline s'appuie sur l'historique d'écoute réel, toujours disponible.
C'est une meilleure base : au lieu de descripteurs calculés par un tiers, on
accumule un historique de comportement, qu'on croise ensuite avec la météo.
La donnée est propriétaire, elle grandit chaque heure, et personne ne peut
la retirer.

### Pourquoi trois couches

- **`raw`** archive chaque payload en JSONB, avant toute transformation. Si
  la logique de transformation se révèle buguée, on rejoue depuis l'archive
  sans réinterroger des API dont les fenêtres d'historique sont limitées.
- **`core`** porte le modèle dimensionnel, avec un grain explicite par table
  de faits et des contraintes qui rendent une donnée incohérente
  impossible à insérer.
- **`marts`** expose des vues d'analyse. Recalculées à la lecture, donc
  toujours cohérentes avec `core`, sans tâche de rafraîchissement à gérer.

### Pourquoi `timeformat=unixtime` sur Open-Meteo

L'API peut renvoyer des horodatages sans décalage explicite. Avec deux
sources dans deux fuseaux, et un changement d'heure deux fois par an, c'est
la porte ouverte à un décalage d'une heure qui fausserait toute la jointure
météo-écoute — silencieusement. Un entier en secondes UTC ne laisse aucune
place à l'interprétation.

Un test vérifie que toutes les dates produites portent un fuseau, et un
autre que la jointure horaire rattache effectivement des lignes.

### Pourquoi les contrôles de qualité font échouer le DAG

Un pipeline qui tourne sans erreur ne garantit rien : il peut charger
fidèlement des données fausses. Un tableau de bord silencieusement faux est
plus dangereux qu'un tableau de bord absent, parce qu'on prend des décisions
avec.

Les neuf contrôles couvrent six familles :

| Famille | Contrôle | Ce qu'il détecte |
|---|---|---|
| Fraîcheur | `weather_freshness` | Le pipeline a cessé de tourner. |
| Unicité | `weather_uniqueness`, `listening_uniqueness` | La clé naturelle ne tient plus. |
| Complétude | `weather_completeness` | Une variable critique arrive vide. |
| Plages | `weather_plausible_ranges`, `listening_not_in_future` | Valeurs physiquement impossibles. |
| Intégrité | `listening_referential_integrity`, `weather_code_referential_integrity` | Un fait pointe vers une dimension absente. |
| Volumétrie | `weather_volume_anomaly` | Effondrement du volume par rapport à l'historique. |

Le contrôle de volumétrie tolère volontairement un historique court : sans
cette précaution, il échouerait les premiers jours du projet et on prendrait
l'habitude d'ignorer ses alertes.

---

## Modèle de données

**Dimensions** — `dim_location` (lieux suivis), `dim_weather_condition`
(les 28 codes WMO utilisés par Open-Meteo, avec famille et sévérité),
`dim_artist`, `dim_track`.

**Faits** — `fact_weather_hourly` (grain : un lieu, une heure),
`fact_listening_event` (grain : un instant, un titre).

**Journal** — `pipeline_run` enregistre pour chaque étape le nombre de lignes
lues, écrites, ignorées, et la durée. Le décompte des lignes **ignorées** est
la mesure du recouvrement entre exécutions : s'il tombe à zéro, la collecte
est trop espacée et des écoutes ont probablement été perdues. Le pipeline
émet un avertissement dans ce cas.

**Vues d'analyse** — `v_listening_with_weather` (la jointure centrale),
`v_listening_by_weather_family`, `v_listening_by_hour`,
`v_top_artists_by_weather`, `v_weather_coverage` (complétude par jour),
`v_pipeline_health`, `v_project_stats`.

---

## Démarrage

### En production, sur Azure

Le pipeline tourne sur Azure, sans serveur à administrer : un
**Container Apps Job** déclenché par cron horaire, une base
**PostgreSQL Flexible Server**, les secrets dans **Key Vault**, l'image dans
**Container Registry**.

```powershell
cd infra/azure
./deploy.ps1 -SpotifyClientId "..." -SpotifyClientSecret "..." -SpotifyRefreshToken "..."
```

Le pipeline s'exécute une minute par heure : payer une machine allumée en
permanence n'aurait aucun sens. Un job serverless facturé à la seconde aligne
le coût sur l'usage réel, et l'image déployée est exactement celle testée en
local. Détails, arbitrages et commandes d'exploitation dans
[`infra/azure/README.md`](infra/azure/README.md).

### Avec Docker, en local

```bash
cp .env.example .env        # puis renseigner les identifiants Spotify
docker compose up -d
# Airflow : http://localhost:8080
```

Le service `migrate` applique le schéma avant qu'Airflow ne démarre. Le DAG
`vienna_vibe_hourly` s'active ensuite tout seul.

### En local, sans Docker

```bash
pip install -e ".[dev]"
export DATABASE_URL=postgresql://vienna:vienna@localhost:5432/vienna_vibe

vienna-vibe migrate        # applique le schéma
vienna-vibe run            # une exécution complète
vienna-vibe stats          # les chiffres du jeu de données
```

Rejouer un créneau passé :

```bash
vienna-vibe run --window 2026-09-19T14:00:00Z
```

### Obtenir un refresh token Spotify

1. Créer une application sur le [dashboard développeur](https://developer.spotify.com/dashboard)
   et y ajouter `http://127.0.0.1:8888/callback` comme Redirect URI.
2. Ouvrir dans un navigateur, en remplaçant `CLIENT_ID` :
   ```
   https://accounts.spotify.com/authorize?client_id=CLIENT_ID&response_type=code&redirect_uri=http://127.0.0.1:8888/callback&scope=user-read-recently-played
   ```
3. Après autorisation, récupérer le paramètre `code` dans l'URL de retour, puis :
   ```bash
   curl -X POST https://accounts.spotify.com/api/token \
     -u "CLIENT_ID:CLIENT_SECRET" \
     -d grant_type=authorization_code \
     -d code=LE_CODE \
     -d redirect_uri=http://127.0.0.1:8888/callback
   ```
4. Le `refresh_token` renvoyé va dans `.env`. Il n'expire pas.

Les secrets ne sont lus que depuis l'environnement, jamais écrits dans le
code, et `.env` est dans le `.gitignore`.

---

## Tests et intégration continue

```bash
make test     # suite complète
make lint     # ruff : analyse statique et formatage
```

**Tests unitaires** — sans réseau ni base de données : repivotage des
colonnes Open-Meteo, protection contre les colonnes de longueurs inégales,
dédoublonnage Spotify, tolérance aux payloads malformés, validation des
modèles, structure des contrôles qualité.

**Tests d'intégration** — contre un vrai PostgreSQL, ignorés
automatiquement si `DATABASE_URL` est absent : idempotence du double
chargement, absence de doublons sur les clés naturelles, exécution des
contrôles, et compilation de chacune des sept vues d'analyse. Une vue SQL
cassée est invisible aux tests unitaires, d'où ce filet.

La CI GitHub Actions exécute les deux, et vérifie en plus que les migrations
sont rejouables et que les contrôles échouent bien sur une base vide.

---

## Ce que le projet démontre

| Compétence | Où elle se voit |
|---|---|
| Modélisation dimensionnelle | `sql/001_schema.sql` : grain explicite, dimensions conformes, SCD de type 1 |
| Idempotence et backfill | `load.py`, clés naturelles, `test_integration_idempotence.py` |
| Qualité de données | `quality.py` : neuf contrôles, six familles, échec bloquant |
| Orchestration | `dags/vienna_vibe_hourly.py` : DAG horaire, catchup, retries exponentiels |
| Robustesse réseau | `http_client.py` : reprise sur erreurs passagères, respect de `Retry-After` |
| SQL analytique | `sql/002_marts.sql` : fenêtrage, agrégations, CTE |
| Cloud | `infra/azure/` : Container Apps Job, PostgreSQL Flexible Server, Key Vault, Container Registry |
| Industrialisation | Docker, docker-compose, CI, linter, tests |

---

## Chiffres

À renseigner depuis `vienna-vibe stats` après quelques semaines de
fonctionnement :

- observations météo collectées
- écoutes enregistrées
- jours d'historique continu
- jours de fonctionnement sans intervention manuelle
