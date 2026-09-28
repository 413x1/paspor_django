#!/usr/bin/env bash
# Instal library native yang dibutuhkan WeasyPrint (Pango, cairo, GDK-Pixbuf, dll)
# di server Linux. Jalankan sekali saat provisioning server, sebelum `pip install -r requirements.txt`.
#
# Pemakaian: sudo bash scripts/install_weasyprint_deps.sh

set -e

if command -v apt-get >/dev/null 2>&1; then
  echo "Terdeteksi Debian/Ubuntu (apt) — menginstal dependensi WeasyPrint..."
  apt-get update
  apt-get install -y \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-liberation

elif command -v dnf >/dev/null 2>&1; then
  echo "Terdeteksi RHEL/CentOS/Fedora (dnf) — menginstal dependensi WeasyPrint..."
  dnf install -y pango cairo cairo-gobject gdk-pixbuf2 libffi-devel shared-mime-info

elif command -v apk >/dev/null 2>&1; then
  echo "Terdeteksi Alpine (apk) — menginstal dependensi WeasyPrint..."
  apk add --no-cache pango cairo gdk-pixbuf ttf-liberation

else
  echo "Package manager tidak dikenali. Instal manual: pango, cairo, gdk-pixbuf, libffi." >&2
  exit 1
fi

echo "Selesai. Dependensi native WeasyPrint sudah terpasang."
