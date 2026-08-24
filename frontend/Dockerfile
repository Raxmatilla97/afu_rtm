# Multi-stage: build the SPA with node, then serve the static output with nginx.
FROM node:20-alpine AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

COPY frontend/ ./

# Vite inlines import.meta.env.* at BUILD time, so this must arrive as a build arg —
# setting it as a runtime environment variable has no effect on the built bundle.
# Empty means same-origin relative API calls (/api/...), which is what we want behind Caddy.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:alpine

COPY deploy/frontend-nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
