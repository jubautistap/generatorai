#!/usr/bin/env python3
"""
Тест исправленной логики создания файлов
"""
import asyncio
import logging.config
from pathlib import Path

from config import LOGGING_CONFIG, AGENT_ROLES
from agents import BaseAgent
from rich.console import Console

# Настраиваем логирование
logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

console = Console()


def test_devops_files():
    """Тестирует создание DevOps файлов с правильными именами"""
    
    console.print("[bold blue]🧪 ТЕСТ ИСПРАВЛЕННОЙ ЛОГИКИ ФАЙЛОВ[/bold blue]")
    console.print("=" * 60)
    
    try:
        # Создаем DevOps агента
        devops_agent = BaseAgent("devops_engineer", AGENT_ROLES["devops_engineer"])
        
        # Симулируем ответ DevOps агента с несколькими файлами
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
        
        console.print(f"[blue]🤖 Тестирую DevOps агента...[/blue]")
        console.print(f"[white]Размер ответа: {len(devops_response)} символов[/white]")
        
        # Тестируем функцию создания файлов
        context = {"project_name": "FileFixTest"}
        files_created = asyncio.run(
            devops_agent._create_files_from_response(devops_response, context)
        )
        
        console.print(f"\n[green]✅ РЕЗУЛЬТАТЫ:[/green]")
        console.print(f"[white]Создано файлов: {len(files_created)}[/white]")
        
        for file_info in files_created:
            console.print(f"[cyan]  📄 {file_info}[/cyan]")
        
        # Показываем созданные файлы
        project_dir = Path("generated_projects/FileFixTest")
        if project_dir.exists():
            console.print(f"\n[yellow]📁 Созданные файлы:[/yellow]")
            for file_path in project_dir.rglob("*"):
                if file_path.is_file():
                    console.print(f"[white]  {file_path.relative_to(project_dir)}[/white]")
                    
        console.print(f"\n[bold green]🎯 Проверка: все файлы должны иметь правильные имена![/bold green]")
        console.print(f"[white]• Dockerfile (не Dockerfile_1)[/white]")
        console.print(f"[white]• docker-compose.yml (не docker-compose_1.yml)[/white]") 
        console.print(f"[white]• .github/workflows/ci.yml (не docker-compose_2.yml)[/white]")
        
    except Exception as e:
        console.print(f"[red]💥 ОШИБКА: {e}[/red]")
        logger.error(f"Ошибка теста: {e}", exc_info=True)

if __name__ == "__main__":
    test_devops_files()
