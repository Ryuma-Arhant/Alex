FROM node:22.12-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
# Rendered at start by the image's entrypoint: ${BACKEND_UPSTREAM} from the environment, and the container's DNS
# server into ${NGINX_LOCAL_RESOLVERS}. The default suits docker-compose; Railway sets its private backend address.
ENV BACKEND_UPSTREAM=http://backend:8000 NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1
COPY infra/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
