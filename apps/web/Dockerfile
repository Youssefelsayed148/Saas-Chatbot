FROM node:24-bookworm-slim AS builder
WORKDIR /workspace
# The /api proxy destination is baked at build time (Next.js rewrites manifest).
ARG API_PROXY_TARGET=http://127.0.0.1:8000
ENV NEXT_TELEMETRY_DISABLED=1 NEXT_STANDALONE=1 API_PROXY_TARGET=${API_PROXY_TARGET}
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
RUN npm ci
COPY apps/web ./apps/web
RUN npm run build

FROM node:24-bookworm-slim AS runtime
WORKDIR /workspace
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
COPY --from=builder --chown=node:node /workspace/apps/web/.next/standalone ./
COPY --from=builder --chown=node:node /workspace/apps/web/.next/static ./apps/web/.next/static
USER node
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
