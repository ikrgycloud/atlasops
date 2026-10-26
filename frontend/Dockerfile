FROM node:24.14.0-alpine AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN --mount=type=secret,id=proxy_ca if [ -f /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; npm ci --no-audit --no-fund
COPY frontend ./
RUN npm run build
FROM nginxinc/nginx-unprivileged:1.27.4-alpine
COPY --chmod=644 frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
