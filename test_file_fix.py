#!/usr/bin/env python3
"""
Тест исправленной логики создания файлов
"""
import os
import asyncio
import logging.config

# Включаем создание файлов на этапе агентов
os.environ['CREATE_FILES_DURING_AGENTS'] = 'true'

from config import LOGGING_CONFIG, AGENT_ROLES  # noqa: E402
from agents import BaseAgent  # noqa: E402

# Настраиваем логирование
logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

def test_devops_files():
    """Тестирует создание DevOps файлов с правильными именами"""

    async def _run():
        try:
            devops_agent = BaseAgent("devops_engineer", AGENT_ROLES["devops_engineer"])

            devops_response = """Создаю конфигурацию для развертывания проекта:

```dockerfile
# Dockerfile
FROM node:18-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production

COPY . .
RUN npm run build

EXPOSE 3000
CMD ["node", "dist/index.js"]
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=production
    restart: unless-stopped

  db:
    image: postgres:15-alpine
    environment:
      - POSTGRES_DB=testdb
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

```yaml
# .github/workflows/ci.yml
name: CI/CD Pipeline

on:
  push:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    - name: Setup Node.js
      uses: actions/setup-node@v3
      with:
        node-version: '18'
    - run: npm ci
    - run: npm test
```"""

            context = {"project_name": "FileFixTest"}
            files_created = await devops_agent._create_files_from_response(devops_response, context)

            assert len(files_created) == 3
            assert any("Dockerfile" in f for f in files_created)
            assert any("docker-compose.yml" in f for f in files_created)
            assert any(".github/workflows/ci.yml" in f for f in files_created)

        except Exception as e:
            logger.error(f"Ошибка теста: {e}", exc_info=True)

    asyncio.run(_run())


if __name__ == "__main__":
    test_devops_files()
