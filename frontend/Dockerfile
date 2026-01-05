# syntax=docker/dockerfile:1.6

# ---- deps ----
FROM node:20-alpine AS deps
WORKDIR /app

# Needed by some npm packages (optional but often helps)
RUN apk add --no-cache libc6-compat

# Copy only lockfiles first for better caching
COPY package.json package-lock.json* ./

# Make npm more resilient on slow/blocked networks
RUN npm config set fetch-retries 5 \
 && npm config set fetch-retry-factor 2 \
 && npm config set fetch-retry-mintimeout 20000 \
 && npm config set fetch-retry-maxtimeout 120000 \
 && npm config set fetch-timeout 600000 \
 && npm config set prefer-offline true

# If you want to force a mirror (uncomment if registry.npmjs.org keeps timing out)
# RUN npm config set registry https://registry.npmmirror.com

RUN npm ci --no-audit --no-fund

# ---- build ----
FROM node:20-alpine AS builder
WORKDIR /app
RUN apk add --no-cache libc6-compat

ENV NODE_ENV=production
# Helps avoid OOM or weird stalls on small machines
ENV NODE_OPTIONS=--max-old-space-size=1024
# Make Next output standalone for a smaller runtime image
ENV NEXT_TELEMETRY_DISABLED=1

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Ensure standalone is enabled (requires next.config.js to set output: 'standalone')
# If you already have it, great. If not, we can add it.
RUN npm run build

# ---- run ----
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN apk add --no-cache libc6-compat

# If you have standalone output, this is the best/cleanest runtime.
# It avoids copying node_modules and prevents mismatch issues.
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
# Standalone output includes server.js
CMD ["node", "server.js"]
