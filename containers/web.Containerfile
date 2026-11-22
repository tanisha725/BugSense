# BugSense user interface (React), built once and served by nginx.
# The same image runs twice: web-main and web-backup (UI_NAME tells them apart).
# Build from the repository root:  podman build -f containers/web.Containerfile .

# Step 1: build the React app
FROM docker.io/library/node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
# The gateway sends /api/... to the backend, so the UI and API share one address
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Step 2: serve the built files (no Node.js in the final image)
FROM docker.io/library/nginx:1.28-alpine
COPY --from=build /app/dist /usr/share/nginx/html
# nginx's own start script fills ${UI_NAME} into this file
COPY containers/web.nginx.conf.template /etc/nginx/templates/default.conf.template
ENV UI_NAME=web-main
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1/served-by || exit 1
