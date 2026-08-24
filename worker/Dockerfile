FROM python:3.12-slim

WORKDIR /srv

COPY shared /srv/shared
COPY worker /srv/worker

# --root-user-action=ignore: pip's root warning is meaningless inside a container,
# and silencing it keeps real errors visible in deploy logs.
RUN pip install --no-cache-dir --root-user-action=ignore -e /srv/shared -e /srv/worker

WORKDIR /srv/worker

CMD ["arq", "app.main.WorkerSettings"]
