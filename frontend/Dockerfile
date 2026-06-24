# Multi-stage: build the SPA, then serve the static bundle.
FROM node:20-alpine AS build
WORKDIR /app

# VITE_* vars are baked in at build time, so they must be set before `build`.
ARG VITE_API_BASE
ARG VITE_BASE_URL
ENV VITE_API_BASE=$VITE_API_BASE \
    VITE_BASE_URL=$VITE_BASE_URL

COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS serve
WORKDIR /app
RUN npm install -g serve@14
COPY --from=build /app/dist ./dist
EXPOSE 3000
# -s rewrites all routes to index.html so client-side routing works.
CMD ["sh", "-c", "serve -s dist -l ${PORT:-3000}"]
