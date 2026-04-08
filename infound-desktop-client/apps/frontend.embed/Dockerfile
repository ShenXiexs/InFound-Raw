# ---------- base ----------
FROM node:22-alpine3.22 AS base

RUN npm install -g pnpm
RUN corepack enable

WORKDIR /app
#COPY package-for-docker.json package.json
COPY package.json package.json
COPY .npmrc .npmrc


# ---------- deps ----------
FROM base AS deps

RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm install --no-frozen-lockfile


# ---------- builder ----------
FROM base AS builder

ARG BUILD_COMMAND=build
ENV BUILD_COMMAND=${BUILD_COMMAND}

COPY --from=deps /app/node_modules /app/node_modules
COPY . .

RUN pnpm run $BUILD_COMMAND


# ---------- runtime ----------
FROM nginx:1.27.3-alpine

WORKDIR /www

COPY --from=builder /app/dist/ .

COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
