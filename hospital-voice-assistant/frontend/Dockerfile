FROM node:20-alpine

WORKDIR /app

COPY package.json ./
RUN yarn install

COPY . .

EXPOSE 4200

CMD ["yarn", "start", "--host", "0.0.0.0", "--port", "4200", "--poll", "1000"]
