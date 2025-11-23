FROM node:18-alpine

WORKDIR /app

RUN corepack enable && corepack prepare pnpm@latest --activate

COPY package.json pnpm-lock.yaml* ./
COPY . .

RUN npm -g install next
RUN pnpm install

EXPOSE 3000

CMD ["next", "dev"]
