FROM node:18-alpine

WORKDIR /app

RUN corepack enable && corepack prepare pnpm@latest --activate

COPY package.json pnpm-lock.yaml* ./
COPY . .

RUN npm -g install next
RUN pnpm install

EXPOSE 3000

CMD ["next", "dev"]

# Allow mounting the project folder at runtime so local edits are
# reflected inside the container. Keep node_modules as a separate
# volume from the host to avoid overwriting container-installed
# dependencies when using a bind mount in docker-compose.
VOLUME ["/app"]
