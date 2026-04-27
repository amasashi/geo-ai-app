FROM node:24-slim

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm install --no-audit --no-fund

COPY frontend .

EXPOSE 3000

CMD ["npm", "run", "dev:docker"]
