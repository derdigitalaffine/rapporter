FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json ./
RUN npm install
COPY frontend/ .
RUN npm run build
RUN test -s dist/superadmin/index.html \
    && test -s dist/superadmin/manifest.webmanifest \
    && test -s dist/superadmin/sw.js \
    && grep -q '<title>FamilyOS Superadmin</title>' dist/superadmin/index.html

FROM caddy:2-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=frontend /frontend/dist /srv
