#!/usr/bin/env python3
"""
Главное приложение мульти-агентной системы генерации проектов

Использование:
    python main.py
    
Введите описание проекта, и система автоматически создаст полноценный проект
с помощью 16 AI агентов!
"""
import asyncio
import os
import sys
import logging
from pathlib import Path
import argparse
from typing import Optional

from rich.console import Console  
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich import print as rprint

# Импортируем наши модули
from coordinator import AgentCoordinator
from deepseek_client import deepseek_client
from config import DEEPSEEK_API_KEY, PROJECT_OUTPUT_DIR

# Настраиваем логирование
import logging.config
from config import LOGGING_CONFIG

# Применяем конфигурацию логирования
logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

console = Console()

class ProjectGeneratorApp:
    """Главное приложение"""
    
    def __init__(self):
        self.coordinator = AgentCoordinator()
        self.running = True
        
    def display_welcome(self):
        """Показывает приветствие"""
        welcome_text = Text()
        welcome_text.append("🤖 МУЛЬТИ-АГЕНТНАЯ СИСТЕМА ГЕНЕРАЦИИ ПРОЕКТОВ 🤖\n", style="bold blue")
        welcome_text.append("═══════════════════════════════════════════════════\n", style="blue")
        welcome_text.append("16 AI агентов создадут для вас полноценный проект!\n", style="green")
        welcome_text.append("\nАгенты в команде:\n", style="yellow")
        welcome_text.append("• Проект-менеджер • Системный архитектор\n", style="white")
        welcome_text.append("• Backend разработчик • Frontend разработчик\n", style="white") 
        welcome_text.append("• Mobile разработчик • Database Engineer\n", style="white")
        welcome_text.append("• DevOps Engineer • QA тестировщик\n", style="white")
        welcome_text.append("• Security специалист • UI/UX дизайнер\n", style="white")
        welcome_text.append("• Data Scientist • Technical Writer\n", style="white")
        welcome_text.append("• Performance Engineer • Integration специалист\n", style="white")
        welcome_text.append("• Code Reviewer • Product Owner\n", style="white")
        
        panel = Panel(welcome_text, title="Добро пожаловать!", border_style="blue")
        console.print(panel)
    
    def check_environment(self) -> bool:
        """Проверяет окружение"""
        console.print("\n[yellow]🔍 Проверка окружения...[/yellow]")
        
        # Проверяем API ключ; мок-режим отключен
        if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY == 'your_deepseek_api_key_here':
            console.print("[red]❌ Не установлен DEEPSEEK_API_KEY![/red]")
            console.print("[yellow]Установите переменную окружения DEEPSEEK_API_KEY или измените config.py[/yellow]")
            
            # Предлагаем ввести API ключ
            api_key = Prompt.ask("Введите ваш DeepSeek API ключ", password=True)
            if api_key:
                # Обновляем клиент
                deepseek_client.api_key = api_key
                deepseek_client.session.headers.update({
                    "Authorization": f"Bearer {api_key}"
                })
                console.print("[green]✓ API ключ установлен[/green]")
                # 🔥 НОВОЕ: Сохраняем ключ в .env в корне проекта
                try:
                    env_path = Path(".env")
                    # Обновляем/добавляем переменную в .env
                    if env_path.exists():
                        lines = env_path.read_text(encoding="utf-8").splitlines()
                        found = False
                        for i, line in enumerate(lines):
                            if line.strip().startswith("DEEPSEEK_API_KEY="):
                                lines[i] = f"DEEPSEEK_API_KEY={api_key}"
                                found = True
                                break
                        if not found:
                            lines.append(f"DEEPSEEK_API_KEY={api_key}")
                        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                    else:
                        env_path.write_text(f"DEEPSEEK_API_KEY={api_key}\n", encoding="utf-8")
                    console.print(f"[green]✓ API ключ сохранен в {env_path.resolve()}[/green]")
                except Exception as e:
                    logger.warning(f"Не удалось сохранить API ключ в .env: {e}")
                # Экспортируем в текущий процесс, чтобы downstream код видел
                os.environ["DEEPSEEK_API_KEY"] = api_key
            else:
                return False
        
        # Проверяем подключение к DeepSeek
        console.print("[yellow]📡 Проверка подключения к DeepSeek...[/yellow]")
        if deepseek_client.health_check():
            console.print("[green]✓ Подключение к DeepSeek работает[/green]")
        else:
            console.print("[red]❌ Не удалось подключиться к DeepSeek API[/red]")
            console.print("[yellow]Проверьте API ключ и интернет соединение[/yellow]")
            return False

        # Создаем выходную директорию
        Path(PROJECT_OUTPUT_DIR).mkdir(exist_ok=True)
        console.print(f"[green]✓ Выходная директория: {PROJECT_OUTPUT_DIR}[/green]")
        
        console.print("[green]🎉 Окружение готово![/green]\n")
        return True
    
    async def run_interactive(self):
        """Запускает интерактивный режим"""
        self.display_welcome()
        
        if not self.check_environment():
            console.print("[red]💥 Проблемы с окружением. Исправьте и перезапустите.[/red]")
            return
        
        while self.running:
            try:
                # Показываем главное меню
                await self.show_main_menu()
                
            except KeyboardInterrupt:
                # 🔥 НОВОЕ: on_exit hook — сохраним состояние сессии
                try:
                    state = self.coordinator.get_project_status()
                    state_path = Path("session_state.json")
                    import json
                    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
                    console.print(f"\n[yellow]💾 Состояние сохранено в {state_path.resolve()}[/yellow]")
                except Exception as e:
                    logger.warning(f"Не удалось сохранить состояние при выходе: {e}")
                console.print("[yellow]👋 До свидания![/yellow]")
                break
            except Exception as e:
                logger.error(f"Ошибка в главном цикле: {e}")
                console.print(f"[red]💥 Неожиданная ошибка: {e}[/red]")
                if not Confirm.ask("Продолжить работу?"):
                    break
    
    async def show_main_menu(self):
        """Показывает главное меню"""
        console.print("\n[bold blue]🎯 ГЛАВНОЕ МЕНЮ[/bold blue]")
        
        options = [
            "1. Создать новый проект",
            "2. Показать статус текущего проекта", 
            "3. Показать список агентов",
            "4. Настройки",
            "5. Выход"
        ]
        
        for option in options:
            console.print(f"[cyan]{option}[/cyan]")
        
        choice = Prompt.ask("\nВыберите действие", choices=["1", "2", "3", "4", "5"])
        
        if choice == "1":
            await self.create_new_project()
        elif choice == "2":
            self.show_project_status()
        elif choice == "3":
            self.show_agents_list()
        elif choice == "4":
            await self.show_settings()
        elif choice == "5":
            self.running = False
    
    async def create_new_project(self):
        """Создает новый проект"""
        console.print("\n[bold green]🚀 СОЗДАНИЕ НОВОГО ПРОЕКТА[/bold green]")
        
        # Получаем описание проекта
        project_description = Prompt.ask(
            "\n[bold yellow]Опишите ваш проект[/bold yellow]\n"
            "[dim](Например: 'Создать интернет магазин с корзиной, оплатой и админкой')[/dim]"
        )
        
        if not project_description:
            console.print("[red]❌ Описание не может быть пустым[/red]")
            return
        
        # Получаем название проекта
        default_name = f"Project_{int(asyncio.get_event_loop().time())}"
        project_name = Prompt.ask(
            "Название проекта", 
            default=default_name
        )
        
        # Подтверждение
        console.print(f"\n[yellow]📋 Параметры проекта:[/yellow]")
        console.print(f"[white]Название: {project_name}[/white]")
        console.print(f"[white]Описание: {project_description}[/white]")
        console.print(f"[white]Агентов: {len(self.coordinator.agents)}[/white]")
        
        if not Confirm.ask("\nЗапустить генерацию проекта?"):
            console.print("[yellow]Отменено[/yellow]")
            return
        
        # Запускаем генерацию
        try:
            console.print(f"\n[bold blue]🎬 Запуск проекта...[/bold blue]")
            
            # Инициализируем проект
            project_context = await self.coordinator.start_project(
                project_description, 
                project_name
            )
            
            # Запускаем полный цикл разработки с возможностью повторов
            attempts = 0
            max_retries = 2
            while True:
                logger.info("Запуск полного цикла разработки...")
                success = await self.coordinator.execute_full_cycle()
                logger.info(f"Цикл разработки завершен с результатом: {success}")

                if success:
                    console.print(f"\n[bold green]🎉 ПРОЕКТ УСПЕШНО СОЗДАН![/bold green]")
                    self.show_project_results(project_context)
                    break
                else:
                    console.print(f"[red]💥 Проект завершился с ошибками[/red]")
                    console.print("[red]Проверьте логи в logs/agents.log и настройки API ключа[/red]")
                    attempts += 1
                    if attempts > max_retries or not Confirm.ask("Повторить попытку?", default=True):
                        break
                    # Можно добавить простую адаптацию: увеличить лимиты, пересоздать контекст и т.д.
                    logger.info("Повторный запуск цикла разработки по запросу пользователя")
                
        except Exception as e:
            logger.error(f"Ошибка создания проекта: {e}")
            console.print(f"[red]💥 Критическая ошибка: {e}[/red]")
    
    def show_project_results(self, project_context):
        """Показывает результаты проекта"""
        console.print(f"\n[bold yellow]📊 РЕЗУЛЬТАТЫ ПРОЕКТА[/bold yellow]")
        
        table = Table(title="Статистика проекта")
        table.add_column("Параметр", justify="left")
        table.add_column("Значение", justify="right")
        
        table.add_row("Название", project_context.name)
        table.add_row("Статус", project_context.status)
        table.add_row("Итераций", str(project_context.current_iteration))
        table.add_row("Файлов создано", str(len(project_context.files_generated)))
        table.add_row("Агентов работало", str(len(project_context.all_results)))
        
        console.print(table)
        
        # Показываем путь к проекту
        project_path = Path(PROJECT_OUTPUT_DIR) / project_context.name
        console.print(f"\n[green]📁 Проект создан в:[/green] [bold]{project_path.absolute()}[/bold]")
        
        # Предлагаем открыть проект
        if Confirm.ask("Открыть папку проекта?"):
            import subprocess
            import platform
            
            if platform.system() == "Darwin":  # macOS
                subprocess.run(["open", str(project_path)])
            elif platform.system() == "Windows":
                subprocess.run(["explorer", str(project_path)])
            else:  # Linux / другие *nix
                # 🔥 НОВОЕ: последовательный fallback
                candidates = [
                    ["xdg-open", str(project_path)],
                    ["gio", "open", str(project_path)],
                    ["kde-open5", str(project_path)],
                    ["gnome-open", str(project_path)],
                    ["sensible-open", str(project_path)]
                ]
                opened = False
                for cmd in candidates:
                    try:
                        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        if res.returncode == 0:
                            opened = True
                            break
                    except Exception:
                        continue
                if not opened:
                    console.print(f"[yellow]Не удалось автоматически открыть папку. Откройте вручную: {project_path}[/yellow]")
    
    def show_project_status(self):
        """Показывает статус текущего проекта"""
        status = self.coordinator.get_project_status()
        
        if status.get("status") == "no_active_project":
            console.print("[yellow]📋 Нет активного проекта[/yellow]")
            return
        
        console.print(f"\n[bold blue]📊 СТАТУС ПРОЕКТА[/bold blue]")
        
        table = Table()
        table.add_column("Параметр", justify="left")
        table.add_column("Значение", justify="right")
        
        for key, value in status.items():
            table.add_row(key.replace('_', ' ').title(), str(value))
        
        console.print(table)
    
    def show_agents_list(self):
        """Показывает список агентов"""
        console.print(f"\n[bold blue]🤖 СПИСОК АГЕНТОВ[/bold blue]")
        
        table = Table()
        table.add_column("ID", justify="left")
        table.add_column("Название", justify="left") 
        table.add_column("Описание", justify="left")
        table.add_column("Статус", justify="center")
        
        for agent_id, agent in self.coordinator.agents.items():
            status = "🟢" if agent.is_active else "🔴"
            table.add_row(
                agent_id, 
                agent.name,
                agent.description[:50] + "...",
                status
            )
        
        console.print(table)
    
    async def show_settings(self):
        """Показывает настройки"""
        console.print(f"\n[bold blue]⚙️ НАСТРОЙКИ[/bold blue]")
        
        settings_info = [
            f"DeepSeek API ключ: {'✓ Установлен' if DEEPSEEK_API_KEY != 'your_deepseek_api_key_here' else '❌ Не установлен'}",
            f"Выходная директория: {PROJECT_OUTPUT_DIR}",
            f"Максимум итераций: {10}",
            f"Агентов загружено: {len(self.coordinator.agents)}"
        ]
        
        for info in settings_info:
            console.print(f"[white]{info}[/white]")

def main():
    """Главная функция"""
    parser = argparse.ArgumentParser(description="Мульти-агентная система генерации проектов")
    parser.add_argument("--project", type=str, help="Описание проекта для быстрого запуска")
    parser.add_argument("--name", type=str, help="Название проекта")
    parser.add_argument("--non-interactive", action="store_true", help="Неинтерактивный режим")
    
    args = parser.parse_args()
    
    app = ProjectGeneratorApp()
    
    if args.project:
        # Быстрый режим
        async def quick_mode():
            if not app.check_environment():
                return
            
            project_name = args.name or f"QuickProject_{int(asyncio.get_event_loop().time())}"
            
            console.print(f"[blue]🚀 Быстрый режим: создание проекта '{project_name}'[/blue]")
            console.print(f"[blue]Описание: {args.project}[/blue]")
            
            try:
                project_context = await app.coordinator.start_project(args.project, project_name)
                success = await app.coordinator.execute_full_cycle()
                
                if success:
                    app.show_project_results(project_context)
                    console.print("[green]✓ Проект создан в быстром режиме![/green]")
                else:
                    console.print("[red]❌ Ошибка в быстром режиме[/red]")
                    
            except Exception as e:
                console.print(f"[red]💥 Ошибка: {e}[/red]")
        
        asyncio.run(quick_mode())
    else:
        # Интерактивный режим  
        asyncio.run(app.run_interactive())

if __name__ == "__main__":
    main()
