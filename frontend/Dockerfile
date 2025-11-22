FROM node:18-alpine

# set working directory
WORKDIR /app

# enable corepack and activate pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

# copy package metadata first for caching
COPY package.json pnpm-lock.yaml* ./

# copy rest of the source
COPY . .

RUN pnpm install

# expose typical frontend port (adjust if your start script uses a different port)
EXPOSE 3000

# run install on container start and then start the app
CMD ["pnpm", "start"]