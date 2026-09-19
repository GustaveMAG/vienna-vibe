# Image unique, utilisée à la fois pour le pipeline et pour Airflow.
# Garder une seule image évite les écarts de version de dépendances entre
# ce qui est testé et ce qui est ordonnancé.

FROM python:3.11-slim

# Empêche Python d'écrire des .pyc et force la sortie non tamponnée :
# sans ça, les logs d'un conteneur arrivent par blocs et le débogage est pénible.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Les dépendances d'abord, le code ensuite : la couche des dépendances est
# ainsi mise en cache et n'est reconstruite que si pyproject.toml change.
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir . \
 && pip install --no-cache-dir "apache-airflow==2.10.5" \
      --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.10.5/constraints-3.11.txt"

COPY sql ./sql
COPY dags ./dags

# Utilisateur non privilégié : un conteneur ne doit jamais tourner en root.
RUN useradd --create-home --uid 1000 pipeline \
 && mkdir -p /app/.airflow \
 && chown -R pipeline:pipeline /app
USER pipeline

ENTRYPOINT []
CMD ["vienna-vibe", "run"]
