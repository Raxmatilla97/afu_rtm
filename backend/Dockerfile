FROM python:3.12-slim

WORKDIR /srv

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY shared /srv/shared
COPY backend /srv/backend

# A slow link to PyPI is the most common way this build fails, and it fails badly: pip's
# default read timeout is 15 seconds, so one stalled chunk part-way through a large wheel
# aborts the whole install and takes the deploy with it. More patience and more retries
# turn a bad minute on the network into a slow build rather than a failed one.
ENV PIP_DEFAULT_TIMEOUT=120 PIP_RETRIES=10 PIP_DISABLE_PIP_VERSION_CHECK=1

# --root-user-action=ignore silences pip's root warning, which is meaningless inside a
# container and only hides real errors in deploy logs.
#
# The cache mount matters more: the three Python images install overlapping sets of the
# same wheels, so without it one deploy downloads each of them three times over the same
# link — and a build that times out starts its downloads again from nothing. A cache
# mount is not part of any layer, so the images stay exactly as small as they were.
RUN --mount=type=cache,target=/root/.cache/pip pip install --root-user-action=ignore -e /srv/shared -e /srv/backend

WORKDIR /srv/backend

RUN chmod +x entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
