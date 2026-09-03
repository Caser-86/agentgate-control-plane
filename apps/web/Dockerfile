FROM node:24-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:1.29-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf
COPY config.js.template /usr/share/nginx/html/config.js.template
COPY docker-entrypoint.sh /docker-entrypoint.d/40-agentgate-config.sh
RUN sed -i 's/\r$//' /docker-entrypoint.d/40-agentgate-config.sh

EXPOSE 80

CMD ["/bin/sh", "/docker-entrypoint.d/40-agentgate-config.sh"]
