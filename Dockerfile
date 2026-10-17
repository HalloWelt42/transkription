# Transkription im Container. ffmpeg kommt nicht ins Abbild: es läuft das des Pi (siehe deploy/ffmpeg-vom-pi).

# --- Oberfläche bauen ---------------------------------------------------------------------------------------------
FROM node:22-slim AS oberflaeche
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/* && \
    git config --global url."https://github.com/".insteadOf "ssh://git@github.com/" && \
    git config --global --add url."https://github.com/".insteadOf "git@github.com:"
WORKDIR /bau
COPY version.json ./
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci --no-audit --no-fund
COPY frontend ./frontend
RUN cd frontend && npm run build

# --- Backend ------------------------------------------------------------------------------------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TRANSKRIPTION_DATEN=/app/daten HOME=/tmp
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends git && \
    pip install --no-cache-dir -r backend/requirements.txt && \
    apt-get purge -y git && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
COPY deploy/ffmpeg-vom-pi /usr/local/bin/ffmpeg
COPY deploy/ffmpeg-vom-pi /usr/local/bin/ffprobe
COPY version.json ./
COPY backend ./backend
COPY --from=oberflaeche /bau/frontend/dist ./frontend/dist
WORKDIR /app/backend
EXPOSE 8631
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8631", "--log-level", "warning", \
     "--ssl-certfile", "/zertifikate/transkription.pem", "--ssl-keyfile", "/zertifikate/transkription-schluessel.pem"]
