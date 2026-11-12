# Configuration-only hotfix; build with the frontend directory as context.
ARG BASE_WEB_IMAGE=istay-web:phase5-local-20261111
FROM ${BASE_WEB_IMAGE}
COPY nginx.conf /etc/nginx/conf.d/default.conf
