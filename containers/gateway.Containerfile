# The front door: one address for everything, and the switch to the backup UI.
FROM docker.io/library/nginx:1.28-alpine
COPY containers/gateway.nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1:8080/gateway/health || exit 1
