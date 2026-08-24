FROM python:3.12-slim

WORKDIR /srv

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY shared /srv/shared
COPY backend /srv/backend

# --root-user-action=ignore: pip's root warning is meaningless inside a container,
# and silencing it keeps real errors visible in deploy logs.
RUN pip install --no-cache-dir --root-user-action=ignore -e /srv/shared -e /srv/backend

WORKDIR /srv/backend

RUN chmod +x entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
