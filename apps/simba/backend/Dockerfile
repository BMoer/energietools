# Simba-Image — FastAPI auf energietools (Rechenkern) + vendored pvtool (Connectoren).
#
# WICHTIG: Build-Context = REPO-ROOT (damit energietools/ verfügbar ist):
#   docker build -f apps/simba/backend/Dockerfile -t simba .
#   (Fly/Render: siehe apps/simba/fly.toml bzw. render.yaml — Context = ".")

FROM python:3.12-slim

WORKDIR /app

# Build-Tools nur für evtl. native Wheels; danach aufräumen.
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ \
    && rm -rf /var/lib/apt/lists/*

# 1) energietools (Rechenkern) aus dem Monorepo — zieht pydantic/pandas/numpy/… mit.
COPY pyproject.toml /src/pyproject.toml
COPY energietools /src/energietools
RUN pip install --no-cache-dir /src

# 2) App-Abhängigkeiten (fastapi/uvicorn/… + pvtool-Runtime: requests/python-dotenv)
COPY apps/simba/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3) vendored pvtool auf den Pfad legen — NICHT pip-installiert (zöge sonst matplotlib);
#    wird von der App nur LAZY importiert (Live-Connectoren + volle WP-Summary).
COPY apps/simba/vendor/pvtool /app/pvtool

# 4) Anwendung + Beispieldaten
COPY apps/simba/backend/app /app/app
COPY apps/simba/backend/data /app/data
RUN mkdir -p /app/data/uploads

ENV PYTHONPATH=/app
ENV PVTOOL_DATA_DIR=/app/data
ENV PVTOOL_UPLOAD_DIR=/app/data/uploads

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
