# syntax=docker/dockerfile:1.7
FROM node:20-alpine AS deps
WORKDIR /app
COPY services/frontend/package.json services/frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund 2>/dev/null || npm install --no-audit --no-fund

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY services/frontend/ ./
# Next.js needs NODE_ENV=production at build time for correct minification
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:20-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000
RUN addgroup -g 10001 documind && adduser -D -u 10001 -G documind documind

# Copy Next.js standalone output (or full .next if standalone not configured).
COPY --from=builder --chown=documind:documind /app/public ./public
COPY --from=builder --chown=documind:documind /app/.next ./.next
COPY --from=builder --chown=documind:documind /app/node_modules ./node_modules
COPY --from=builder --chown=documind:documind /app/package.json ./package.json
COPY --from=builder --chown=documind:documind /app/next.config.mjs ./next.config.mjs

USER documind
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD wget --spider -q http://localhost:3000 || exit 1
CMD ["npm", "run", "start"]
