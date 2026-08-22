FROM python:3.12-slim

WORKDIR /srv

COPY shared /srv/shared
COPY bot /srv/bot

RUN pip install --no-cache-dir -e /srv/shared -e /srv/bot

WORKDIR /srv/bot

CMD ["python", "-m", "app.main"]
