# Vital Vortex — Flask + SQLite, served behind Caddy on the VPS.
FROM python:3.12-slim

WORKDIR /app

# Install deps first so this layer is cached until requirements change
# (the same restore-before-source trick ChoreDrawer's Dockerfile uses).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App source
COPY app.py schema.sql Index.html ./

# SQLite file and the session secret live on mounted volumes, not the image.
ENV VV_DB_PATH=/data/vitalvortex.db \
    VV_KEYS_DIR=/keys

EXPOSE 8080

# Plain HTTP inside the container; Caddy terminates TLS upstream.
# 2 workers is plenty for a 1-2 person app on a 1 vCPU droplet.
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8080", "app:app"]
