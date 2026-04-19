# ---------- base ----------
FROM node:22-alpine3.22 AS base

RUN npm install -g pnpm
RUN corepack enable

WORKDIR /app


# ---------- builder ----------
FROM base AS builder

COPY package.json pnpm-workspace.yaml ./
COPY apps/frontend.embed/package.json ./apps/frontend.embed/package.json
COPY packages/frontend.desktop.base/package.json ./packages/frontend.desktop.base/package.json
COPY packages/frontend.desktop.electron/package.json ./packages/frontend.desktop.electron/package.json

COPY .npmrc .npmrc

COPY apps/frontend.embed/ apps/frontend.embed/
COPY packages/frontend.desktop.base/ packages/frontend.desktop.base/
COPY packages/frontend.desktop.electron/ packages/frontend.desktop.electron/

RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm install --no-frozen-lockfile

RUN pnpm --filter @infound/desktop-base run build

RUN pnpm --filter @infound/desktop-electron run build

RUN pnpm --filter frontend.embed run build:stg


# ---------- runtime ----------
FROM nginx:1.27.3-alpine

WORKDIR /www

COPY --from=builder /app/apps/frontend.embed/dist/ .

COPY apps/frontend.embed/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

