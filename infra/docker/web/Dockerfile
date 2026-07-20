FROM node:24.18.0-bookworm-slim@sha256:6f7b03f7c2c8e2e784dcf9295400527b9b1270fd37b7e9a7285cf83b6951452d AS base

ENV PNPM_HOME="/pnpm" \
    PATH="/pnpm:${PATH}"

RUN corepack enable && corepack prepare pnpm@11.14.0 --activate

WORKDIR /workspace

FROM base AS dependencies

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .node-version /workspace/
COPY apps/web/package.json /workspace/apps/web/package.json
COPY packages/contracts/package.json /workspace/packages/contracts/package.json

RUN pnpm install --frozen-lockfile --filter @reactorfront/web...

FROM dependencies AS builder

COPY apps/web /workspace/apps/web
COPY packages/contracts/generated /workspace/packages/contracts/generated

RUN pnpm --filter @reactorfront/web build

FROM node:24.18.0-bookworm-slim@sha256:6f7b03f7c2c8e2e784dcf9295400527b9b1270fd37b7e9a7285cf83b6951452d AS runtime

LABEL org.opencontainers.image.title="ReactorFront Portfolio Web" \
      org.opencontainers.image.description="Document upload, progress, and terminal-result Next.js application" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/Kentaro-Ono-jp/Portfolio"

ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000

RUN groupadd --gid 10003 portfolio-web && \
    useradd --uid 10003 --gid portfolio-web --no-create-home --home-dir /nonexistent portfolio-web

WORKDIR /app
COPY --from=builder --chown=10003:10003 /workspace/apps/web/.next/standalone /app
COPY --from=builder --chown=10003:10003 /workspace/apps/web/.next/static /app/apps/web/.next/static

USER 10003:10003
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
