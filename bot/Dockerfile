FROM python:3.12-slim

WORKDIR /srv

COPY shared /srv/shared
COPY bot /srv/bot

# --root-user-action=ignore: pip's root warning is meaningless inside a container,
# and silencing it keeps real errors visible in deploy logs.
RUN pip install --no-cache-dir --root-user-action=ignore -e /srv/shared -e /srv/bot

WORKDIR /srv/bot

CMD ["python", "-m", "app.main"]
