# =====================================================================
# ATUDIC DevOps - Dockerfile
# =====================================================================
# Build:   docker build -t atudic .
# Run:     docker compose up -d
# =====================================================================

# --- Stage 1: build (instala deps, minifica assets) ---
FROM python:3.12-slim AS builder

WORKDIR /build

# Deps do sistema para compilar psycopg2-binary e git
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev git \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependências Python (sem dev/test)
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install \
    Flask==3.0.0 Werkzeug==3.0.1 \
    cryptography==46.0.5 bcrypt==5.0.0 flask-cors==4.0.0 \
    psycopg2-binary==2.9.11 gunicorn==25.1.0 gevent==25.9.1 \
    requests==2.32.5 python-dateutil==2.9.0.post0 \
    beautifulsoup4==4.13.4 \
    rjsmin==1.2.5 rcssmin==1.2.2

# Copiar código-fonte e minificar assets
COPY . .
RUN PYTHONPATH=/install/lib/python3.12/site-packages python scripts/minify_assets.py


# --- Stage 2: runtime (imagem final enxuta) ---
FROM python:3.12-slim

WORKDIR /app

# Deps de runtime: libpq (PostgreSQL client) e git (operações de repositório)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 git openssh-client \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -r -s /bin/false atudic

# Copiar dependências Python do builder
COPY --from=builder /install /usr/local

# Copiar código-fonte
COPY app/ ./app/
COPY static/ ./static/
COPY scripts/ ./scripts/
COPY run.py license_system.py activate_license.py ./
COPY index.html theme.css ./

# Copiar assets minificados do builder (sobrescreve os não-minificados)
COPY --from=builder /build/static/js/app.min.js ./static/js/app.min.js
COPY --from=builder /build/static/js/*.min.js ./static/js/
COPY --from=builder /build/static/css/app.min.css ./static/css/app.min.css

# Diretórios de runtime
RUN mkdir -p logs cloned_repos patches \
    && chown -R atudic:atudic /app

# Variáveis de ambiente padrão (sem secrets — definir via .env ou compose)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_ENV=production \
    DB_HOST=db \
    DB_PORT=5432 \
    DB_NAME=atudic \
    DB_USER=atudic

EXPOSE 5000

USER atudic

# Health check — liveness probe leve (sem acesso ao banco)
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import requests; r=requests.get('http://localhost:5000/api/health', timeout=3); exit(0 if r.status_code==200 else 1)"]

# Gunicorn com gevent para suportar SSE (long-polling)
# Workers = 2 * CPU + 1 (recomendação gunicorn para I/O bound)
CMD ["sh", "-c", "gunicorn run:app \
     --bind 0.0.0.0:5000 \
     --workers ${GUNICORN_WORKERS:-$(python -c 'import os; print(2 * os.cpu_count() + 1)')} \
     --worker-class gevent \
     --timeout 120 \
     --access-logfile - \
     --error-logfile -"]
