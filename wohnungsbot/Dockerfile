FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && useradd --create-home --uid 1000 bot
COPY wohnungsbot ./wohnungsbot
COPY docker-entrypoint.sh /usr/local/bin/
ENV PYTHONUNBUFFERED=1 DATEN_DIR=/daten WOHNUNGSBOT_CONFIG=/app/config.toml TZ=Europe/Berlin
VOLUME /daten
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["starten"]
