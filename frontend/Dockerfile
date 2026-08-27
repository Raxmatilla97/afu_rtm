# Multi-stage: build the SPA with node, then serve the static output with nginx.
FROM node:20-alpine AS build

WORKDIR /app

# Same reasoning as the pip timeouts in the Python images: the registry is reached over
# the same link, and a default of two retries is not enough when it is having a bad day.
ENV NPM_CONFIG_FETCH_RETRIES=5 NPM_CONFIG_FETCH_RETRY_MAXTIMEOUT=120000

COPY frontend/package.json frontend/package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm npm install

COPY frontend/ ./

# Vite inlines import.meta.env.* at BUILD time, so this must arrive as a build arg —
# setting it as a runtime environment variable has no effect on the built bundle.
# Empty means same-origin relative API calls (/api/...) — this container proxies them
# to the backend itself, see deploy/frontend-nginx.conf.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:alpine

COPY deploy/frontend-nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
