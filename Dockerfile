# syntax=docker/dockerfile:1
# Image produksi PASPOR (Django + Gunicorn + WeasyPrint).
# Dibangun di Synology Container Manager, lihat wiki/instructions/DEPLOY_SYNOLOGY.MD

# ---------------------------------------------------------------------------
# Tahap 1: build wheel (mysqlclient perlu dikompilasi)
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        pkg-config \
        default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt


# ---------------------------------------------------------------------------
# Tahap 2: image runtime (tanpa compiler, lebih kecil)
# ---------------------------------------------------------------------------
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Jakarta \
    DJANGO_SETTINGS_MODULE=paspor_project.settings

# libmariadb3       : library client MySQL untuk mysqlclient
# pango/harfbuzz    : dibutuhkan WeasyPrint untuk membuat PDF
# fonts-liberation  : "Liberation Sans", pengganti metrik-identik Arial di template PDF
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libmariadb3 \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz-subset0 \
        shared-mime-info \
        fonts-liberation \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY . .

# Kumpulkan file static saat build. Nilai env di bawah hanya dummy agar
# settings.py bisa di-import; nilai asli diberikan lewat .env saat container jalan.
RUN DJANGO_SECRET_KEY=build-only S3_ACCESS_KEY=build-only S3_SECRET_KEY=build-only \
    python manage.py collectstatic --noinput

# Pastikan entrypoint ber-line-ending LF (aman walau di-commit dari Windows).
RUN sed -i 's/\r$//' docker/entrypoint.sh && chmod +x docker/entrypoint.sh

# Jalankan sebagai user non-root. Folder log dibuat ulang milik user app
# (collectstatic di atas berjalan sebagai root dan sudah membuat paspor.log).
RUN useradd --create-home --uid 1000 app \
    && rm -rf /app/var \
    && mkdir -p /app/var/log \
    && chown -R app:app /app/var
USER app

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "paspor_project.wsgi:application", "--config", "docker/gunicorn.conf.py"]
