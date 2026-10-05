# syntax=docker/dockerfile:1
# Omnix web image (WP-11.1): the built SPA behind Nginx, which also routes API
# traffic to the gateway processes (deploy/docker/nginx/omnix.conf, generated
# from deploy/gateway-route-policy.json). Runs as Nginx's unprivileged user.
#
#   docker build -f deploy/docker/web.Dockerfile -t omnix-web .

ARG NODE_IMAGE=node:22.23.2-bookworm-slim
ARG NGINX_IMAGE=nginxinc/nginx-unprivileged:1.29-alpine

FROM ${NODE_IMAGE} AS build
ARG VITE_GIT_SHA=unknown
ENV VITE_GIT_SHA=${VITE_GIT_SHA} \
    VITE_GIT_DIRTY=false \
    VITE_LIVE_VOICE_CRITICAL_DIRTY_FILES=[] \
    OMNIX_GATEWAY_API_REPLICAS=0 \
    npm_config_update_notifier=false \
    npm_config_fund=false \
    npm_config_audit=false
WORKDIR /repo
COPY package.json package-lock.json .node-version ./
COPY src/apps/web/package.json src/apps/web/package.json
RUN npm ci --workspace src/apps/web --include-workspace-root=false
COPY deploy/gateway-route-policy.json deploy/gateway-route-policy.json
COPY src/apps/web src/apps/web
RUN npm --prefix src/apps/web run build

FROM ${NGINX_IMAGE} AS runtime
# Base tags lag distribution security fixes; take them at build time.
USER root
RUN apk upgrade --no-cache
USER 101
COPY deploy/docker/nginx/omnix.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/src/apps/web/dist /srv/omnix/web
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/index.html"]
