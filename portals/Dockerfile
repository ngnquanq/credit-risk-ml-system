# Builds one portal: docker build --build-arg APP=staff-portal -t crs-staff-portal:<git-sha> portals/
ARG NODE_IMAGE=node:20.18.1-alpine3.20

FROM ${NODE_IMAGE} AS build
ARG APP
WORKDIR /repo
RUN corepack enable
COPY . .
RUN pnpm install --frozen-lockfile && pnpm --filter ${APP} build

FROM ${NODE_IMAGE} AS runtime
ARG APP
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /app
RUN addgroup -S app && adduser -S app -G app
COPY --from=build --chown=app:app /repo/apps/${APP}/.next/standalone ./
COPY --from=build --chown=app:app /repo/apps/${APP}/.next/static ./apps/${APP}/.next/static
USER app
EXPOSE 3000
ENV APP_DIR=apps/${APP}
CMD ["sh", "-c", "node ${APP_DIR}/server.js"]
