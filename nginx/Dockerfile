# Stage 1: build React app
FROM node:20-alpine AS build
WORKDIR /app/ui-app
COPY ui-app/package.json ui-app/package-lock.json* ./
RUN npm ci || npm install
COPY ui-app/ ./
RUN npm run build

# Stage 2: nginx static with API proxy
FROM nginx:stable
RUN rm -f /etc/nginx/conf.d/default.conf
COPY --from=build /app/ui-app/dist /usr/share/nginx/html
COPY nginx/nginx.conf /etc/nginx/nginx.conf
EXPOSE 443