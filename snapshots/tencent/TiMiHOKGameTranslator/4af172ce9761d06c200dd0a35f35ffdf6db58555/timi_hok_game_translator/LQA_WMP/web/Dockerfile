FROM node:22-alpine AS build
WORKDIR /app
ARG NPM_REGISTRY=https://registry.npmjs.org
RUN npm install -g pnpm@11.7.0 --registry=${NPM_REGISTRY}
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
RUN pnpm install --frozen-lockfile --registry=${NPM_REGISTRY}
COPY . .
RUN pnpm build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
