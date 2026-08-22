FROM python:3.12-slim

WORKDIR /srv

COPY shared /srv/shared
COPY worker /srv/worker

RUN pip install --no-cache-dir -e /srv/shared -e /srv/worker

WORKDIR /srv/worker

CMD ["arq", "app.main.WorkerSettings"]
