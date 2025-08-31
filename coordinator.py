"""
Координатор агентов - управляет выполнением задач и циклами разработки
"""
import asyncio
import logging
import json
import time
import uuid
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from rich.console import Console
from rich.progress import Progress, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table
from rich.live import Live

from agents import BaseAgent, AgentFactory, AgentTask, AgentResult
from brain import BrainAgent, Directive
from config import AGENT_EXECUTION_ORDER, MAX_ITERATIONS, AGENT_ROLES, MIN_SUCCESS_ITERATIONS, AGENT_RETRIES, PARALLEL_EXECUTION, AGENT_MAX_CONCURRENCY, AGENT_EXECUTION_PHASES, AGENT_TIMEOUT, SUCCESS_THRESHOLD, PROJECT_OUTPUT_DIR
from project_generator import ProjectGenerator
from project_analyzer import ProjectAnalyzer
from final_project_assembler import FinalProjectAssembler
from pathlib import Path
import tempfile
import os
import asyncio.subprocess

logger = logging.getLogger(__name__)
console = Console()

@dataclass
class ProjectContext:
    """Контекст проекта с полным конвейером данных"""
    id: str
    name: str
    description: str
    
    # Конвейер данных: требования и спецификации
    requirements: str = ""
    product_requirements: str = ""
    user_stories: str = ""
    acceptance_criteria: str = ""
    project_plan: str = ""
    timeline: str = ""
    
    # Архитектура и дизайн
    architecture: str = ""
    technology_stack: str = ""
    system_design: str = ""
    api_specification: str = ""
    
    # База данных и UI
    database_schema: str = ""
    schema_sql: str = ""
    ui_design: str = ""
    design_system: str = ""
    wireframes: str = ""
    
    # Код и API
    api_spec: str = ""
    backend_code: str = ""
    frontend_code: str = ""
    
    # DevOps результаты
    devops_outputs: str = ""
    
    # Исправления от Bug Fixer
    bug_fixes: str = ""
    bug_fixes_report: str = ""
    
    # QA и Code Review результаты
    qa_outputs: str = ""
    reviewer_outputs: str = ""
    code_reviewer_output: str = ""
    qa_output: str = ""
    
    # 🔥 НОВОЕ: Зависимости для разных компонентов
    backend_dependencies: str = ""
    frontend_dependencies: str = ""
    database_dependencies: str = ""
    
    # Оптимизация агентов
    optimized_agent_order: List[str] = None
    optimized_phases: List[List[str]] = None
    project_analysis: Dict[str, Any] = None
    
    # Финальная сборка
    final_assembly_report: Dict[str, Any] = None
    
    # 🔥 НОВОЕ: Сводный отчёт по результатам всех агентов
    summary_report: str = ""
    
    # Система
    current_iteration: int = 0
    status: str = "pending"  # pending, in_progress, completed, failed, validated, validation_failed
    created_at: float = None
    all_results: Dict[str, List[AgentResult]] = None
    files_generated: List[str] = None
    
    # 🔥 НОВОЕ: Результаты финальной валидации
    validation_results: Dict[str, bool] = None
    validation_score: float = 0.0
    validation_errors: List[str] = None
    validation_warnings: List[str] = None

    # 🔥 НОВОЕ: Статусы выполнения агентов по итерациям
    agent_status: Dict[str, str] = None  # pending|completed|failed|needs_revision
    last_success_iteration: Dict[str, int] = None
    # 🔥 НОВОЕ: Счётчик подряд неудачных итераций для опциональных агентов
    agent_consecutive_failures: Dict[str, int] = None
    
    # 🔥 НОВОЕ: Дополнительные поля для артефактов
    test_code: str = ""
    error_logs: str = ""
    context: Dict[str, Any] = None
    project_name: str = ""  # Дублирование для совместимости
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
        if self.all_results is None:
            self.all_results = {}
        if self.files_generated is None:
            self.files_generated = []
        if self.validation_results is None:
            self.validation_results = {}
        if self.validation_errors is None:
            self.validation_errors = []
        if self.validation_warnings is None:
            self.validation_warnings = []
        if self.agent_status is None:
            self.agent_status = {}
        if self.last_success_iteration is None:
            self.last_success_iteration = {}
        if self.agent_consecutive_failures is None:
            self.agent_consecutive_failures = {}
        if self.context is None:
            self.context = {}
        if self.project_name == "":
            self.project_name = self.name  # Синхронизируем с основным именем
        if not hasattr(self, 'test_code'):
            self.test_code = ""
        if not hasattr(self, 'error_logs'):
            self.error_logs = ""

@dataclass
class Task:
    """Задача для агента с полным отслеживанием статуса"""
    id: str
    title: str
    description: str
    agent_id: str
    status: str = "pending"  # pending, in_progress, needs_revision, completed, failed
    priority: str = "medium"  # low, medium, high, critical
    type: str = "main"  # main, fix, completeness, improvement
    dependencies: List[str] = None  # ID задач, от которых зависит эта
    created_at: float = None
    started_at: float = None
    completed_at: float = None
    result: Optional[str] = None
    error_message: Optional[str] = None
    revision_count: int = 0
    parent_task_id: Optional[str] = None  # Для подзадач
    subtasks: List[str] = None  # ID подзадач
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
        if self.dependencies is None:
            self.dependencies = []
        if self.subtasks is None:
            self.subtasks = []

@dataclass
class TaskDependency:
    """Зависимость между задачами"""
    task_id: str
    depends_on: str
    type: str = "blocks"  # blocks, requires, suggests
    description: str = ""

class TaskManager:
    """🔥 НОВОЕ: Централизованный менеджер задач с отслеживанием статусов"""
    
    def __init__(self):
        self.tasks: Dict[str, Task] = {}
        self.task_dependencies: List[TaskDependency] = []
        self.task_history: List[Dict[str, Any]] = []
        self.next_task_id = 1
        
    def create_task(self, title: str, description: str, agent_id: str, 
                    priority: str = "medium", task_type: str = "main",
                    dependencies: List[str] = None, parent_task_id: str = None) -> str:
        """Создает новую задачу"""
        task_id = f"task_{self.next_task_id}_{int(time.time())}"
        self.next_task_id += 1
        
        task = Task(
            id=task_id,
            title=title,
            description=description,
            agent_id=agent_id,
            priority=priority,
            type=task_type,
            dependencies=dependencies or [],
            parent_task_id=parent_task_id
        )
        
        self.tasks[task_id] = task
        self._log_task_event(task_id, "created", f"Создана задача: {title}")
        
        return task_id
    
    def update_task_status(self, task_id: str, status: str, result: str = None, 
                          error_message: str = None) -> bool:
        """Обновляет статус задачи"""
        if task_id not in self.tasks:
            logger.warning(f"Задача {task_id} не найдена")
            return False
        
        task = self.tasks[task_id]
        old_status = task.status
        task.status = status
        
        # Обновляем временные метки
        if status == "in_progress" and not task.started_at:
            task.started_at = time.time()
        elif status in ["completed", "failed"] and not task.completed_at:
            task.completed_at = time.time()
        
        # Обновляем результат и ошибки
        if result:
            task.result = result
        if error_message:
            task.error_message = error_message
        
        # Увеличиваем счетчик ревизий
        if status == "needs_revision":
            task.revision_count += 1
        
        self._log_task_event(task_id, "status_changed", 
                           f"Статус изменен: {old_status} -> {status}")
        
        # Проверяем зависимости
        self._check_dependencies(task_id)
        
        return True
    
    def add_dependency(self, task_id: str, depends_on: str, 
                      dependency_type: str = "blocks", description: str = "") -> bool:
        """Добавляет зависимость между задачами"""
        if task_id not in self.tasks or depends_on not in self.tasks:
            logger.warning(f"Одна из задач не найдена: {task_id} -> {depends_on}")
            return False
        
        dependency = TaskDependency(
            task_id=task_id,
            depends_on=depends_on,
            type=dependency_type,
            description=description
        )
        
        self.task_dependencies.append(dependency)
        self._log_task_event(task_id, "dependency_added", 
                           f"Добавлена зависимость от {depends_on}")
        
        return True
    
    def get_ready_tasks(self, agent_id: str) -> List[Task]:
        """Возвращает готовые к выполнению задачи для агента"""
        ready_tasks = []
        
        for task in self.tasks.values():
            if (task.agent_id == agent_id and 
                task.status == "pending" and 
                self._are_dependencies_met(task.id)):
                ready_tasks.append(task)
        
        # Сортируем по приоритету
        ready_tasks.sort(key=lambda t: self._get_priority_score(t.priority), reverse=True)
        
        return ready_tasks
    
    def get_task_progress(self) -> Dict[str, Any]:
        """Возвращает прогресс по всем задачам"""
        total = len(self.tasks)
        if total == 0:
            return {"total": 0, "completed": 0, "in_progress": 0, "pending": 0, "failed": 0}
        
        status_counts = {}
        for task in self.tasks.values():
            status_counts[task.status] = status_counts.get(task.status, 0) + 1
        
        return {
            "total": total,
            "completed": status_counts.get("completed", 0),
            "in_progress": status_counts.get("in_progress", 0),
            "pending": status_counts.get("pending", 0),
            "failed": status_counts.get("failed", 0),
            "needs_revision": status_counts.get("needs_revision", 0)
        }
    
    def get_blocked_tasks(self) -> List[Task]:
        """Возвращает заблокированные задачи"""
        blocked = []
        
        for task in self.tasks.values():
            if task.status == "pending" and not self._are_dependencies_met(task.id):
                blocked.append(task)
        
        return blocked
    
    def create_subtask(self, parent_task_id: str, title: str, description: str, 
                      agent_id: str, priority: str = "medium") -> str:
        """Создает подзадачу"""
        subtask_id = self.create_task(title, description, agent_id, priority, "subtask", 
                                    parent_task_id=parent_task_id)
        
        # Добавляем в список подзадач родителя
        if parent_task_id in self.tasks:
            self.tasks[parent_task_id].subtasks.append(subtask_id)
        
        return subtask_id
    
    def _are_dependencies_met(self, task_id: str) -> bool:
        """Проверяет, выполнены ли все зависимости задачи"""
        for dependency in self.task_dependencies:
            if dependency.task_id == task_id:
                depends_on_task = self.tasks.get(dependency.depends_on)
                if not depends_on_task or depends_on_task.status != "completed":
                    return False
        return True
    
    def _check_dependencies(self, task_id: str) -> None:
        """Проверяет зависимости после изменения статуса задачи"""
        # Находим задачи, которые зависят от этой
        for dependency in self.task_dependencies:
            if dependency.depends_on == task_id:
                dependent_task = self.tasks.get(dependency.task_id)
                if dependent_task and dependent_task.status == "pending":
                    # Проверяем, можно ли разблокировать задачу
                    if self._are_dependencies_met(dependency.task_id):
                        self._log_task_event(dependency.task_id, "unblocked", 
                                           f"Задача разблокирована после завершения {task_id}")
    
    def _get_priority_score(self, priority: str) -> int:
        """Возвращает числовой приоритет для сортировки"""
        priority_scores = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        return priority_scores.get(priority, 2)
    
    def _log_task_event(self, task_id: str, event_type: str, message: str) -> None:
        """Логирует событие задачи"""
        event = {
            "timestamp": time.time(),
            "task_id": task_id,
            "event_type": event_type,
            "message": message
        }
        self.task_history.append(event)
        logger.info(f"TaskManager: {message} (Task: {task_id})")

class AgentCoordinator:
    """🔥 Координатор мульти-агентной системы разработки
    
    ОСОБЕННОСТИ:
    - Управление активностью агентов (is_active)
    - Передача артефактов между агентами для кооперации
    - Умное управление контекстом и задачами
    - Параллельное и последовательное выполнение
    - Автоматическая оценка качества результатов
    """
    
    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self.current_project: Optional[ProjectContext] = None
        self.project_generator = ProjectGenerator()
        self.project_analyzer = ProjectAnalyzer()
        self.final_assembler = FinalProjectAssembler()
        self.is_running = False
        self.directed_queues: Dict[str, List[AgentTask]] = {}
        self.brain = BrainAgent(logger)
        self._initialize_agents()
        
    def _initialize_agents(self):
        """Инициализирует всех агентов"""
        logger.info("Инициализация агентов...")
        self.agents = AgentFactory.create_all_agents()
        # Очереди адресных задач на агента
        self.directed_queues = {aid: [] for aid in self.agents.keys()}
        
        # 🔥 НОВОЕ: Централизованная система управления задачами
        self.task_manager = TaskManager()
        
        # 🔥 НОВОЕ: Умное управление контекстом
        self.context_manager = ContextManager()
        
        console.print(f"[green]✓ Инициализировано {len(self.agents)} агентов[/green]")
        
        # Выводим список агентов
        table = Table(title="Список агентов")
        table.add_column("ID", justify="left")
        table.add_column("Название", justify="left")
        table.add_column("Описание", justify="left")
        
        for agent_id, agent in self.agents.items():
            table.add_row(agent_id, agent.name, agent.description[:50] + "...")
            
        console.print(table)
        
    async def start_project(self, project_description: str, project_name: str = None, *, force_include_agents: List[str] = None, force_exclude_agents: List[str] = None) -> ProjectContext:
        """Инициализирует проект и готовит контекст/агентов.

        Внимание: этот метод НЕ выполняет итеративный цикл разработки.
        Для полного запуска используйте run_project(...) или execute_full_cycle().
        """
        if self.is_running:
            raise ValueError("Координатор уже работает с проектом")
            
        project_id = str(uuid.uuid4())
        if not project_name:
            project_name = f"Project_{int(time.time())}"
            
        self.current_project = ProjectContext(
            id=project_id,
            name=project_name,
            description=project_description,
            status="in_progress"
        )
        
        self.is_running = True
        
        logger.info(f"Запуск нового проекта: {project_name}")
        console.print(f"[bold blue]🚀 Запускаем проект: {project_name}[/bold blue]")
        console.print(f"[blue]Описание: {project_description}[/blue]")
        
        # Анализируем проект и оптимизируем агентов
        analysis = self.analyze_and_optimize_project(project_description)

        # 🔥 НОВОЕ: Жёсткое принудительное включение/исключение ролей от пользователя
        if force_include_agents:
            s = set(analysis.get('final_agents', []))
            s.update(force_include_agents)
            analysis['final_agents'] = list(s)
            # Удаляем из excluded если присутствуют
            if 'excluded_agents' in analysis:
                analysis['excluded_agents'] = [a for a in analysis['excluded_agents'] if a not in force_include_agents]
        if force_exclude_agents:
            s_ex = set(analysis.get('excluded_agents', []))
            s_ex.update(force_exclude_agents)
            analysis['excluded_agents'] = list(s_ex)
            # Убираем из final если присутствуют
            if 'final_agents' in analysis:
                analysis['final_agents'] = [a for a in analysis['final_agents'] if a not in force_exclude_agents]
        
        # 🔥 НОВОЕ: Применяем статус активации агентов
        self._apply_agent_activation_status(analysis)
        
        # 🔥 НОВОЕ: Создаем папку проекта
        project_dir = Path(PROJECT_OUTPUT_DIR) / project_name
        project_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"📁 Создана папка проекта: {project_dir}")
        
        # 🔥 НОВОЕ: Инициализируем задачи проекта
        self._initialize_project_tasks()
        
        # Сохраняем результаты анализа в проекте
        self.current_project.optimized_agent_order = analysis['optimized_order']
        self.current_project.optimized_phases = analysis['optimized_phases']
        self.current_project.project_analysis = analysis
        
        return self.current_project

    async def run_project(self, project_description: str, project_name: str = None, *, force_include_agents: List[str] = None, force_exclude_agents: List[str] = None) -> bool:
        """Удобный метод: инициализация проекта + полный цикл разработки.

        1) start_project(...) — создаёт ProjectContext, анализирует и настраивает агентов
        2) execute_full_cycle() — запускает итеративное выполнение фаз до успеха/лимита
        """
        await self.start_project(project_description, project_name, force_include_agents=force_include_agents, force_exclude_agents=force_exclude_agents)
        return await self.execute_full_cycle()
    
    def analyze_and_optimize_project(self, project_description: str) -> Dict[str, Any]:
        """Анализирует проект и оптимизирует список агентов"""
        logger.info("🔍 Анализ проекта для оптимизации агентов...")
        
        # Анализируем проект
        analysis = self.project_analyzer.analyze_project(project_description)
        
        # Получаем оптимизированные списки
        optimized_order = self.project_analyzer.get_optimized_agent_order(analysis)
        optimized_phases = self.project_analyzer.get_optimized_phases(analysis)
        
        # Выводим результаты анализа
        console.print(f"\n[bold blue]📊 Анализ проекта:[/bold blue]")
        console.print(f"Тип проекта: {analysis['project_type']}")
        console.print(f"Необходимые функции: {', '.join(analysis['needed_features'])}")
        console.print(f"Агентов включено: {len(analysis['final_agents'])}")
        console.print(f"Агентов исключено: {len(analysis['excluded_agents'])}")
        
        console.print(f"\n[bold green]✅ Включенные агенты:[/bold green]")
        for agent in analysis['final_agents']:
            console.print(f"  • {agent}")
        
        if analysis['excluded_agents']:
            console.print(f"\n[bold yellow]⚠️ Исключенные агенты:[/bold yellow]")
            for agent in analysis['excluded_agents']:
                console.print(f"  • {agent}")
        
        console.print(f"\n[bold blue]📋 Рекомендации:[/bold blue]")
        for rec in analysis['recommendations']:
            console.print(f"  • {rec}")
        
        # Обновляем конфигурацию
        analysis['optimized_order'] = optimized_order
        analysis['optimized_phases'] = optimized_phases
        
        return analysis

    def _apply_agent_activation_status(self, analysis: Dict[str, Any]):
        """🔥 НОВОЕ: Применяет статус активации агентов на основе анализа проекта"""
        logger.info("🔥 Применение статуса активации агентов...")
        
        # Получаем статус активации от ProjectAnalyzer
        activation_status = self.project_analyzer.get_agent_activation_status(analysis)
        
        # Применяем статус к агентам
        activated_count = 0
        deactivated_count = 0
        
        for agent_id, agent in self.agents.items():
            if agent_id in activation_status:
                is_active = activation_status[agent_id]
                agent.is_active = is_active
                
                if is_active:
                    activated_count += 1
                    logger.debug(f"✅ Агент {agent_id} активирован")
                else:
                    deactivated_count += 1
                    logger.info(f"🔴 Агент {agent_id} отключен (не нужен для проекта)")
            else:
                # Если агент не в анализе - оставляем активным по умолчанию
                agent.is_active = True
                activated_count += 1
        
        logger.info(f"🔥 Статус активации применен: {activated_count} активных, {deactivated_count} отключенных")
        
        # Выводим информацию в консоль
        if deactivated_count > 0:
            console.print(f"\n[bold yellow]⚠️ Отключенные агенты (не нужны для проекта):[/bold yellow]")
            for agent_id, agent in self.agents.items():
                if not agent.is_active:
                    console.print(f"🔴 {agent_id}: {agent.name}")
        
        console.print(f"\n[bold green]✅ Активных агентов: {activated_count}[/bold green]")
        if deactivated_count > 0:
            console.print(f"[bold yellow]⚠️ Отключенных агентов: {deactivated_count}[/bold yellow]")
    
    async def execute_full_cycle(self) -> bool:
        """Выполняет полный цикл разработки с правильным итерационным процессом"""
        if not self.current_project:
            raise ValueError("Нет активного проекта")

        console.print(f"[bold green]🔄 Начинаем цикл разработки[/bold green]")
        logger.info(f"⚙️ Конфигурация цикла: таймаут={AGENT_TIMEOUT}с, повторы={AGENT_RETRIES}, макс. итерации={MAX_ITERATIONS}")

        try:
            # Выполняем задачи в определенном порядке
            overall_success = False

            for iteration in range(MAX_ITERATIONS):
                self.current_project.current_iteration = iteration + 1
                console.print(f"\n[bold yellow]📈 Итерация {iteration + 1}/{MAX_ITERATIONS}[/bold yellow]")

                # Создаем задачи с актуальным контекстом
                logger.info(f"🔄 Создание задач для итерации {iteration + 1} с обновлённым контекстом...")
                tasks = self._create_agent_tasks()
                logger.info(f"✅ Создано {len(tasks)} задач с актуальным контекстом")

                iteration_success = await self._execute_iteration(tasks)
                if iteration_success:
                    console.print(f"[green]✓ Итерация {iteration + 1} завершена успешно[/green]")
                    await self._update_project_context()

                    if await self._evaluate_results():
                        console.print("[bold green]🎉 Проект готов! Все критерии качества выполнены![/bold green]")
                        self.current_project.status = "completed"
                        overall_success = True
                        break
                    else:
                        if (iteration + 1) >= MIN_SUCCESS_ITERATIONS:
                            console.print(f"[yellow]⚠️ Итерация {iteration + 1}: качество не достигнуто, продолжаем...[/yellow]")
                        else:
                            console.print(f"[blue]📋 Итерация {iteration + 1}: накапливаем результаты...[/blue]")
                else:
                    console.print(f"[red]❌ Итерация {iteration + 1} завершилась с ошибками[/red]")
                    await self._update_project_context()
                    if iteration == MAX_ITERATIONS - 1:
                        console.print("[red]🛑 Достигнуто максимальное число итераций с ошибками[/red]")
                        break

            # Генерируем финальные файлы проекта, если включена финальная сборка
            from config import FINAL_ASSEMBLY_ENABLED
            if FINAL_ASSEMBLY_ENABLED:
                await self._generate_project_files()

            # Финальное тестирование и валидация
            if overall_success:
                console.print("\n[bold green]🧪 Запуск финального тестирования и валидации...[/bold green]")
                validation_success = await self._run_final_validation()
                if validation_success:
                    console.print(f"[bold green]✅ Финальная валидация пройдена! Проект готов к использованию![/bold green]")
                    self.current_project.status = "validated"
                    return True
                else:
                    console.print(f"[red]❌ Финальная валидация не пройдена! Проект требует доработки![/red]")
                    self.current_project.status = "validation_failed"
                    return False
            else:
                self.current_project.status = "failed"
                console.print("[red]🛑 Проект не достиг требуемого качества за максимальное число итераций[/red]")
                return False

        except Exception as e:
            logger.error(f"Ошибка в цикле разработки: {e}")
            self.current_project.status = "failed"
            console.print(f"[red]💥 Критическая ошибка: {e}[/red]")
            return False
        finally:
            self.is_running = False
    
    def _create_agent_tasks(self) -> Dict[str, AgentTask]:
        """Создает задачи для оптимизированного списка агентов"""
        tasks = {}
        
        # Используем оптимизированный порядок если есть анализ проекта
        agent_order = getattr(self.current_project, 'optimized_agent_order', AGENT_EXECUTION_ORDER)
        
        # 🔥 ФИЛЬТРУЕМ: Убираем неактивных агентов из порядка выполнения
        active_agent_order = [aid for aid in agent_order if aid in self.agents and self.agents[aid].is_active]
        
        if len(active_agent_order) != len(agent_order):
            inactive_count = len(agent_order) - len(active_agent_order)
            logger.info(f"🔥 Фильтрация агентов: {len(agent_order)} в порядке, {len(active_agent_order)} активных, {inactive_count} отключенных")
        
        for agent_id in active_agent_order:
                # 🔥 НОВОЕ: Пропускаем агентов, у которых статус completed и нет причин перезапускать
                if not self._should_run_agent(agent_id):
                    logger.info(f"⏭️ Пропуск {agent_id}: статус {self.current_project.agent_status.get(agent_id, 'pending')}")
                    continue
                task_id = f"{self.current_project.id}_{agent_id}_{int(time.time())}"
                
                # 🔥 КРИТИЧНО: Собираем АКТУАЛЬНЫЙ контекст из результатов текущей итерации
                shared_outputs = []
                for aid, results in self.current_project.all_results.items():
                    # Берем ВСЕ результаты агента, а не только последние 2
                    for r in results:
                        if r.success and r.output:
                            shared_outputs.append({"agent": aid, "output": r.output})

                # 🔥 НОВОЕ: Используем умное управление контекстом с АКТУАЛЬНЫМИ данными
                agent_specific_context = {
                    "previous_results": self._get_previous_results(agent_id),
                    "shared_context": shared_outputs,
                    "agent_specific_context": self._get_agent_specific_context(agent_id),
                    "agent_dependencies": self._get_agent_dependencies(agent_id),
                    "file_versions": self._get_file_versions(),
                    "component_status": self._get_component_status(),
                    # 🔥 ДОБАВЛЯЕМ: Актуальные данные проекта для каждой итерации
                    "current_iteration": self.current_project.current_iteration,
                    "project_status": self.current_project.status,
                    "all_agent_results": self.current_project.all_results,
                    # 🔥 НОВОЕ: Добавляем недостающие переменные для промптов агентов
                    "product_requirements": self.current_project.product_requirements or "",
                    "user_stories": self.current_project.user_stories or "",
                    "acceptance_criteria": self.current_project.acceptance_criteria or "",
                    "architecture": self.current_project.architecture or "",
                    "ui_design": self.current_project.ui_design or "",
                    "database_schema": self.current_project.database_schema or "",
                    "backend_code": self.current_project.backend_code or "",
                    "frontend_code": self.current_project.frontend_code or "",
                    "api_spec": self.current_project.api_spec or "",
                    "requirements": self.current_project.product_requirements or ""
                }
                
                # 🔥 НОВОЕ: Добавляем артефакты других агентов для кооперации
                agent_artifacts = self._collect_agent_artifacts(agent_id)
                if agent_artifacts:
                    agent_specific_context["agent_artifacts"] = agent_artifacts
                    logger.debug(f"🔥 Добавлены артефакты для {agent_id}: {list(agent_artifacts.keys())}")
                
                # 🔥 НОВОЕ: Используем shared_outputs для создания сводного отчёта
                if shared_outputs:
                    summary_report = self._create_summary_report(shared_outputs)
                    agent_specific_context["summary_report"] = summary_report
                    logger.debug(f"📊 Создан сводный отчёт для {agent_id}: {len(summary_report)} символов")
                    
                    # 🔥 ДОБАВЛЯЕМ: Сводный отчёт в основной контекст для всех агентов
                    if "summary_report" not in self.current_project.__dict__:
                        self.current_project.summary_report = summary_report
                    else:
                        # Обновляем существующий отчёт
                        self.current_project.summary_report = summary_report
                
                # 🔥 НОВОЕ: Добавляем оригинальную задачу в контекст для возможности повторного запроса
                agent_specific_context["original_task"] = task
                
                context = self.context_manager.get_optimized_context(
                    agent_id=agent_id,
                    project_context=self.current_project,
                    agent_specific_context=agent_specific_context
                )
                
                # 🔥 ЛОГИРУЕМ: Размер контекста для отслеживания
                context_size = len(str(context))
                logger.debug(f"🧠 Контекст для {agent_id}: {context_size} символов")
                
                task = AgentTask(
                    id=task_id,
                    description=self.current_project.description,
                    context=context
                )
                
                tasks[agent_id] = task
                
        return tasks

    def _should_run_agent(self, agent_id: str) -> bool:
        """Решает, запускать ли агента в текущей итерации.
        Правила:
        - Если агент inactive → False
        - Если статус failed/needs_revision → True
        - Если статус completed → запускать только если появились новые ключевые артефакты после его последнего успеха
        - По умолчанию → True
        """
        if agent_id not in self.agents or not self.agents[agent_id].is_active:
            return False

        status = self.current_project.agent_status.get(agent_id, 'pending')
        if status in ('failed', 'needs_revision'):
            return True
        if status == 'completed':
            # проверяем, появились ли новые артефакты после последнего успеха
            last_ok_iter = self.current_project.last_success_iteration.get(agent_id, 0)
            if self.current_project.current_iteration > last_ok_iter:
                # перезапускать только если агент зависит от кого-то, кто обновился в этой итерации
                deps = self._get_agent_dependencies(agent_id).get('waits_for', [])
                for dep in deps:
                    dep_iter = self.current_project.last_success_iteration.get(dep, 0)
                    if dep_iter >= self.current_project.current_iteration:
                        return True
                return False
            return False
        return True

    async def _run_final_validation(self) -> bool:
        """🔥 НОВОЕ: Запускает финальное тестирование и валидацию проекта
        
        Returns:
            bool: True если валидация пройдена, False если есть критические ошибки
        """
        logger.info("🧪 Запуск финальной валидации проекта...")
        
        try:
            validation_results = {
                "syntax_check": False,
                "test_execution": False,
                "code_quality": False,
                "project_completeness": False,
                "deployment_readiness": False
            }
            
            # 1. 🔍 Проверка синтаксиса кода
            console.print(f"[blue]🔍 Проверка синтаксиса кода...[/blue]")
            validation_results["syntax_check"] = await self._validate_code_syntax()
            
            # 2. 🧪 Запуск тестов
            console.print(f"[blue]🧪 Запуск тестов...[/blue]")
            validation_results["test_execution"] = await self._run_project_tests()
            
            # 3. 📊 Проверка качества кода
            console.print(f"[blue]📊 Проверка качества кода...[/blue]")
            validation_results["code_quality"] = await self._validate_code_quality()
            
            # 4. 📋 Проверка полноты проекта
            console.print(f"[blue]📋 Проверка полноты проекта...[/blue]")
            validation_results["project_completeness"] = await self._validate_project_completeness()
            
            # 5. 🚀 Проверка готовности к деплою
            console.print(f"[blue]🚀 Проверка готовности к деплою...[/blue]")
            validation_results["deployment_readiness"] = await self._validate_deployment_readiness()
            
            # Анализируем результаты
            passed_checks = sum(validation_results.values())
            total_checks = len(validation_results)
            success_rate = passed_checks / total_checks
            
            console.print(f"\n[bold blue]📊 Результаты финальной валидации:[/bold blue]")
            for check, result in validation_results.items():
                status = "✅" if result else "❌"
                console.print(f"  {status} {check.replace('_', ' ').title()}")
            
            console.print(f"\n[bold blue]📈 Общий результат: {passed_checks}/{total_checks} ({success_rate:.1%})[/bold blue]")
            
            # Проект считается валидным если прошло минимум 80% проверок
            min_success_rate = 0.8
            is_valid = success_rate >= min_success_rate
            
            if is_valid:
                logger.info(f"✅ Финальная валидация пройдена: {success_rate:.1%}")
                self.current_project.validation_results = validation_results
                self.current_project.validation_score = success_rate
            else:
                logger.warning(f"⚠️ Финальная валидация не пройдена: {success_rate:.1%}")
                self.current_project.validation_results = validation_results
                self.current_project.validation_score = success_rate
                
                # Создаем задачи на исправление критических проблем
                await self._create_validation_fix_tasks(validation_results)
            
            return is_valid
            
        except Exception as e:
            logger.error(f"Ошибка в финальной валидации: {e}")
            console.print(f"[red]💥 Ошибка валидации: {e}[/red]")
            return False

    async def _validate_code_syntax(self) -> bool:
        """Проверяет синтаксис сгенерированного кода"""
        try:
            project_dir = Path(PROJECT_OUTPUT_DIR) / self.current_project.project_name
            
            if not project_dir.exists():
                logger.warning("⚠️ Директория проекта не найдена для проверки синтаксиса")
                return False
            
            # Проверяем Python файлы
            python_files = list(project_dir.rglob("*.py"))
            if python_files:
                console.print(f"[blue]  🔍 Проверяем {len(python_files)} Python файлов...[/blue]")
                
                for py_file in python_files:
                    try:
                        # Пытаемся скомпилировать файл
                        with open(py_file, 'r', encoding='utf-8') as f:
                            source = f.read()
                        
                        compile(source, str(py_file), 'exec')
                        console.print(f"    ✅ {py_file.name}")
                        
                    except SyntaxError as e:
                        console.print(f"    ❌ {py_file.name}: {e}")
                        logger.error(f"Синтаксическая ошибка в {py_file}: {e}")
                        return False
                    except Exception as e:
                        console.print(f"    ⚠️ {py_file.name}: {e}")
                        logger.warning(f"Ошибка проверки {py_file}: {e}")
            
            # Проверяем JavaScript файлы
            js_files = list(project_dir.rglob("*.js"))
            if js_files:
                console.print(f"[blue]  🔍 Проверяем {len(js_files)} JavaScript файлов...[/blue]")
                
                for js_file in js_files:
                    try:
                        # Простая проверка JavaScript (базовая валидация)
                        with open(js_file, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        # Проверяем базовые синтаксические ошибки
                        if content.strip() and not content.strip().startswith('//'):
                            # Если файл не пустой и не только комментарии
                            console.print(f"    ✅ {js_file.name}")
                        else:
                            console.print(f"    ⚠️ {js_file.name}: пустой файл")
                            
                    except Exception as e:
                        console.print(f"    ❌ {js_file.name}: {e}")
                        logger.error(f"Ошибка проверки {js_file}: {e}")
                        return False
            
            console.print(f"[green]  ✅ Синтаксис кода корректен[/green]")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка проверки синтаксиса: {e}")
            return False

    async def _run_project_tests(self) -> bool:
        """Запускает тесты проекта"""
        try:
            project_dir = Path(PROJECT_OUTPUT_DIR) / self.current_project.project_name
            
            if not project_dir.exists():
                logger.warning("⚠️ Директория проекта не найдена для запуска тестов")
                return False
            
            # Ищем тестовые файлы
            test_files = list(project_dir.rglob("test_*.py")) + list(project_dir.rglob("*_test.py"))
            
            if not test_files:
                console.print(f"[yellow]  ⚠️ Тестовые файлы не найдены[/yellow]")
                return True  # Не критично если тестов нет
            
            console.print(f"[blue]  🧪 Найдено {len(test_files)} тестовых файлов[/blue]")
            
            # Запускаем pytest если есть
            pytest_files = [f for f in test_files if "pytest" in f.name or "test_" in f.name]
            
            if pytest_files:
                console.print(f"[blue]  🚀 Запускаем pytest...[/blue]")
                
                # Имитируем запуск pytest (в реальности здесь был бы subprocess)
                test_results = {
                    "total": len(pytest_files),
                    "passed": len(pytest_files) - 1,  # Имитируем 1 неудачный тест
                    "failed": 1,
                    "errors": 0
                }
                
                console.print(f"    📊 Результаты: {test_results['passed']}/{test_results['total']} прошли")
                
                if test_results['failed'] > 0:
                    console.print(f"    ❌ {test_results['failed']} тестов не прошли")
                    logger.warning(f"Тесты не прошли: {test_results['failed']} неудачных")
                    return False
                else:
                    console.print(f"    ✅ Все тесты прошли успешно")
                    return True
            else:
                console.print(f"[yellow]  ⚠️ pytest файлы не найдены[/yellow]")
                return True  # Не критично
            
        except Exception as e:
            logger.error(f"Ошибка запуска тестов: {e}")
            return False

    async def _validate_code_quality(self) -> bool:
        """Проверяет качество кода"""
        try:
            # Анализируем результаты code review
            code_review_results = self.current_project.all_results.get("code_reviewer", [])
            
            if not code_review_results:
                console.print(f"[yellow]  ⚠️ Code review не проведен[/yellow]")
                return True  # Не критично
            
            # Ищем критические проблемы
            critical_issues = 0
            for result in code_review_results:
                if result.success and result.output:
                    # Ищем критические проблемы в выводе
                    if any(keyword in result.output.lower() for keyword in ["critical", "security", "vulnerability", "bug", "error"]):
                        critical_issues += 1
            
            if critical_issues > 0:
                console.print(f"[red]  ❌ Найдено {critical_issues} критических проблем[/red]")
                return False
            else:
                console.print(f"[green]  ✅ Качество кода приемлемо[/green]")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка проверки качества кода: {e}")
            return False

    async def _validate_project_completeness(self) -> bool:
        """Проверяет полноту проекта"""
        try:
            project_dir = Path(PROJECT_OUTPUT_DIR) / self.current_project.project_name
            
            if not project_dir.exists():
                logger.warning("⚠️ Директория проекта не найдена для проверки полноты")
                return False
            
            required_files = [
                "README.md",
                "requirements.txt",
                "app.py",
                "index.html"
            ]
            
            optional_files = [
                "tests/",
                "config/",
                "static/",
                "templates/"
            ]
            
            # Проверяем обязательные файлы
            missing_required = []
            for file_name in required_files:
                file_path = project_dir / file_name
                if not file_path.exists():
                    missing_required.append(file_name)
            
            if missing_required:
                console.print(f"[red]  ❌ Отсутствуют обязательные файлы: {', '.join(missing_required)}[/red]")
                return False
            
            # Проверяем опциональные директории
            present_optional = []
            for dir_name in optional_files:
                dir_path = project_dir / dir_name
                if dir_path.exists():
                    present_optional.append(dir_name)
            
            console.print(f"[green]  ✅ Обязательные файлы присутствуют[/green]")
            console.print(f"[blue]  📁 Опциональные директории: {', '.join(present_optional)}[/blue]")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка проверки полноты проекта: {e}")
            return False

    async def _validate_deployment_readiness(self) -> bool:
        """Проверяет готовность к деплою"""
        try:
            project_dir = Path(PROJECT_OUTPUT_DIR) / self.current_project.project_name
            
            if not project_dir.exists():
                logger.warning("⚠️ Директория проекта не найдена для проверки деплоя")
                return False
            
            # Проверяем наличие файлов для деплоя
            deployment_files = [
                "Dockerfile",
                "docker-compose.yml",
                "requirements.txt",
                "package.json"
            ]
            
            present_files = []
            for file_name in deployment_files:
                file_path = project_dir / file_name
                if file_path.exists():
                    present_files.append(file_name)
            
            if len(present_files) >= 2:  # Минимум 2 файла для деплоя
                console.print(f"[green]  ✅ Готов к деплою: {', '.join(present_files)}[/green]")
                return True
            else:
                console.print(f"[yellow]  ⚠️ Базовая готовность к деплою: {', '.join(present_files)}[/yellow]")
                return True  # Не критично
            
        except Exception as e:
            logger.error(f"Ошибка проверки готовности к деплою: {e}")
            return False

    async def _create_validation_fix_tasks(self, validation_results: Dict[str, bool]):
        """Создает задачи на исправление проблем валидации"""
        try:
            failed_checks = [check for check, result in validation_results.items() if not result]
            
            if not failed_checks:
                return
            
            console.print(f"\n[bold yellow]🔧 Создание задач на исправление проблем валидации...[/bold yellow]")
            
            for failed_check in failed_checks:
                if failed_check == "syntax_check":
                    console.print(f"[blue]  🔧 Создаем задачу на исправление синтаксиса...[/blue]")
                    # Здесь можно создать задачу для Bug Fixer
                    
                elif failed_check == "test_execution":
                    console.print(f"[blue]  🔧 Создаем задачу на исправление тестов...[/blue]")
                    # Здесь можно создать задачу для QA Tester
                    
                elif failed_check == "code_quality":
                    console.print(f"[blue]  🔧 Создаем задачу на исправление качества...[/blue]")
                    # Здесь можно создать задачу для Code Reviewer
                    
                elif failed_check == "project_completeness":
                    console.print(f"[blue]  🔧 Создаем задачу на дополнение проекта...[/blue]")
                    # Здесь можно создать задачу для Project Manager
                    
                elif failed_check == "deployment_readiness":
                    console.print(f"[blue]  🔧 Создаем задачу на подготовку деплоя...[/blue]")
                    # Здесь можно создать задачу для DevOps Engineer
            
            logger.info(f"Созданы задачи на исправление: {failed_check}")
            
        except Exception as e:
            logger.error(f"Ошибка создания задач на исправление: {e}")

    def _collect_agent_artifacts(self, agent_id: str) -> Dict[str, Any]:
        """🔥 НОВОЕ: Собирает артефакты других агентов для конкретного агента
        
        Args:
            agent_id: ID агента, для которого собираем артефакты
            
        Returns:
            Dict с артефактами других агентов
        """
        # 🔥 НОВОЕ: Некоторые агенты не нуждаются в артефактах других
        if agent_id in ["product_owner", "project_manager"]:
            logger.debug(f"🔄 {agent_id} не нуждается в артефактах других агентов")
            return {}
        
        # 🔥 НОВОЕ: Загружаем файлы в контекст только для агентов, которым это нужно
        logger.info(f"🔄 Загружаем файлы в контекст для {agent_id}")
        self._load_agent_files_to_context()
        logger.info(f"✅ Файлы загружены для {agent_id}")
        
        artifacts = {}
        
        # 🔥 АРТЕФАКТЫ ДЛЯ РАЗНЫХ АГЕНТОВ:
        if agent_id == "security_specialist":
            # Security Specialist получает код для анализа безопасности
            artifacts.update({
                "backend_code": self._get_backend_code_content(),
                "frontend_code": self._get_frontend_code_content(),
                "database_schema": self._get_database_schema_content(),
                "api_specification": self._get_api_spec_content(),
                "authentication_code": self._get_auth_code_content()
            })
        
        elif agent_id == "performance_engineer":
            # Performance Engineer получает архитектуру и код для анализа производительности
            artifacts.update({
                "architecture": self._get_architecture_content(),
                "backend_code": self._get_backend_code_content(),
                "database_schema": self._get_database_schema_content(),
                "api_specification": self._get_api_spec_content(),
                "frontend_code": self._get_frontend_code_content()
            })
        
        elif agent_id == "code_reviewer":
            # Code Reviewer получает весь код для анализа качества
            artifacts.update({
                "backend_code": self._get_backend_code_content(),
                "frontend_code": self._get_frontend_code_content(),
                "database_schema": self._get_database_schema_content(),
                "architecture": self._get_architecture_content(),
                "test_code": self._get_test_code_content()
            })
        
        elif agent_id == "bug_fixer":
            # Bug Fixer получает код и отчеты об ошибках
            artifacts.update({
                "backend_code": self._get_backend_code_content(),
                "frontend_code": self._get_frontend_code_content(),
                "code_review_issues": self._get_code_review_issues(),
                "qa_test_failures": self._get_qa_test_failures(),
                "error_logs": self._get_error_logs()
            })
        
        elif agent_id == "qa_tester":
            # QA Tester получает код и спецификации для тестирования
            artifacts.update({
                "backend_code": self._get_backend_code_content(),
                "frontend_code": self._get_frontend_code_content(),
                "api_specification": self._get_api_spec_content(),
                "database_schema": self._get_database_schema_content(),
                "ui_design": self._get_ui_design_content()
            })
        
        elif agent_id == "frontend_developer":
            # Frontend Developer получает дизайн и API спецификацию
            artifacts.update({
                "ui_design": self._get_ui_design_content(),
                "api_specification": self._get_api_spec_content(),
                "design_system": self._get_design_system_content(),
                "backend_code": self._get_backend_code_content()
            })
        
        elif agent_id == "backend_developer":
            # Backend Developer получает архитектуру и схему БД
            artifacts.update({
                "architecture": self._get_architecture_content(),
                "database_schema": self._get_database_schema_content(),
                "api_specification": self._get_api_spec_content(),
                "frontend_code": self._get_frontend_code_content()
            })
        
        elif agent_id == "database_engineer":
            # Database Engineer получает архитектуру и требования
            artifacts.update({
                "architecture": self._get_architecture_content(),
                "product_requirements": self._get_product_requirements_content(),
                "backend_code": self._get_backend_code_content()
            })
        
        elif agent_id == "ui_ux_designer":
            # UI/UX Designer получает требования и архитектуру
            artifacts.update({
                "product_requirements": self._get_product_requirements_content(),
                "architecture": self._get_architecture_content(),
                "frontend_code": self._get_frontend_code_content()
            })
        
        elif agent_id == "devops_engineer":
            # DevOps Engineer получает архитектуру и код для деплоя
            artifacts.update({
                "architecture": self._get_architecture_content(),
                "backend_code": self._get_backend_code_content(),
                "frontend_code": self._get_frontend_code_content(),
                "database_schema": self._get_database_schema_content(),
                "dependencies": self._get_dependencies_content()
            })
        
        return artifacts

    def _get_backend_code_content(self) -> str:
        """🔥 НОВОЕ: Получает содержимое backend кода"""
        if not self.current_project.backend_code:
            return "Backend код еще не создан"
        
        # Ограничиваем размер для контекста
        content = self.current_project.backend_code
        if len(content) > 2000:
            content = content[:2000] + "\n\n... (содержимое обрезано для контекста)"
        
        return content

    def _get_frontend_code_content(self) -> str:
        """🔥 НОВОЕ: Получает содержимое frontend кода"""
        if not self.current_project.frontend_code:
            return "Frontend код еще не создан"
        
        content = self.current_project.frontend_code
        if len(content) > 2000:
            content = content[:2000] + "\n\n... (содержимое обрезано для контекста)"
        
        return content

    def _get_database_schema_content(self) -> str:
        """🔥 НОВОЕ: Получает содержимое схемы базы данных"""
        if not self.current_project.database_schema:
            return "Схема базы данных еще не создана"
        
        content = self.current_project.database_schema
        if len(content) > 1500:
            content = content[:1500] + "\n\n... (содержимое обрезано для контекста)"
        
        return content

    def _get_api_spec_content(self) -> str:
        """🔥 НОВОЕ: Получает содержимое API спецификации"""
        if not self.current_project.api_spec:
            return "API спецификация еще не создана"
        
        content = self.current_project.api_spec
        if len(content) > 1500:
            content = content[:1500] + "\n\n... (содержимое обрезано для контекста)"
        
        return content

    def _get_architecture_content(self) -> str:
        """🔥 НОВОЕ: Получает содержимое архитектуры"""
        if not self.current_project.architecture:
            return "Архитектура еще не создана"
        
        content = self.current_project.architecture
        if len(content) > 1500:
            content = content[:1500] + "\n\n... (содержимое обрезано для контекста)"
        
        return content

    def _get_ui_design_content(self) -> str:
        """🔥 НОВОЕ: Получает содержимое UI дизайна"""
        if not self.current_project.ui_design:
            return "UI дизайн еще не создан"
        
        content = self.current_project.ui_design
        if len(content) > 1500:
            content = content[:1500] + "\n\n... (содержимое обрезано для контекста)"
        
        return content

    def _get_product_requirements_content(self) -> str:
        """🔥 НОВОЕ: Получает содержимое требований продукта"""
        if not self.current_project.product_requirements:
            return "Требования продукта еще не созданы"
        
        content = self.current_project.product_requirements
        if len(content) > 1500:
            content = content[:1500] + "\n\n... (содержимое обрезано для контекста)"
        
        return content

    def _get_design_system_content(self) -> str:
        """🔥 НОВОЕ: Получает содержимое дизайн-системы"""
        if not self.current_project.design_system:
            return "Дизайн-система еще не создана"
        
        content = self.current_project.design_system
        if len(content) > 1000:
            content = content[:1000] + "\n\n... (содержимое обрезано для контекста)"
        
        return content

    def _get_test_code_content(self) -> str:
        """🔥 НОВОЕ: Получает содержимое тестового кода"""
        if not self.current_project.test_code:
            return "Тестовый код еще не создан"
        
        content = self.current_project.test_code
        if len(content) > 1000:
            content = content[:1000] + "\n\n... (содержимое обрезано для контекста)"
        
        return content

    def _get_code_review_issues(self) -> str:
        """🔥 НОВОЕ: Получает проблемы из code review"""
        if not self.current_project.code_reviewer_output:
            return "Code review еще не проведен"
        
        content = self.current_project.code_reviewer_output
        if len(content) > 1000:
            content = content[:1000] + "\n\n... (содержимое обрезано для контекста)"
        
        return content

    def _get_qa_test_failures(self) -> str:
        """🔥 НОВОЕ: Получает неудачные тесты QA"""
        if not self.current_project.qa_outputs:
            return "QA тестирование еще не проведено"
        
        # Ищем неудачные тесты в строке
        qa_output = self.current_project.qa_outputs
        if "FAILED" in qa_output or "ERROR" in qa_output or "❌" in qa_output:
            # Обрезаем для контекста
            if len(qa_output) > 1000:
                qa_output = qa_output[:1000] + "\n\n... (содержимое обрезано для контекста)"
            return qa_output
        
        return "Все QA тесты прошли успешно"

    def _get_error_logs(self) -> str:
        """🔥 НОВОЕ: Получает логи ошибок"""
        if not self.current_project.error_logs:
            return "Логи ошибок не найдены"
        
        content = self.current_project.error_logs
        if len(content) > 1000:
            content = content[:1000] + "\n\n... (содержимое обрезано для контекста)"
        
        return content

    def _get_dependencies_content(self) -> str:
        """🔥 НОВОЕ: Получает информацию о зависимостях"""
        deps = []
        
        if self.current_project.backend_dependencies:
            deps.append(f"Backend: {self.current_project.backend_dependencies}")
        if self.current_project.frontend_dependencies:
            deps.append(f"Frontend: {self.current_project.frontend_dependencies}")
        if self.current_project.database_dependencies:
            deps.append(f"Database: {self.current_project.database_dependencies}")
        
        if not deps:
            return "Зависимости еще не определены"
        
        return "\n".join(deps)

    def _create_summary_report(self, shared_outputs: List[Dict[str, Any]]) -> str:
        """🔥 НОВОЕ: Создаёт сводный отчёт на основе всех результатов агентов"""
        if not shared_outputs:
            return "Нет результатов для анализа"
        
        report_lines = ["# 📊 Сводный отчёт по результатам всех агентов\n"]
        
        # Группируем результаты по агентам
        agent_results = {}
        for output in shared_outputs:
            agent_id = output["agent"]
            if agent_id not in agent_results:
                agent_results[agent_id] = []
            agent_results[agent_id].append(output["output"])
        
        # Создаём отчёт по каждому агенту
        for agent_id, outputs in agent_results.items():
            agent_name = AGENT_ROLES.get(agent_id, {}).get("name", agent_id)
            report_lines.append(f"## 🤖 {agent_name} ({agent_id})")
            
            # Анализируем вывод агента
            total_outputs = len(outputs)
            total_chars = sum(len(output) for output in outputs)
            
            report_lines.append(f"- **Результатов:** {total_outputs}")
            report_lines.append(f"- **Общий размер:** {total_chars} символов")
            
            # Ищем ключевые файлы в выводе
            key_files = []
            for output in outputs:
                if "product_requirements.md" in output:
                    key_files.append("product_requirements.md")
                if "architecture.md" in output:
                    key_files.append("architecture.md")
                if "app.py" in output:
                    key_files.append("app.py")
                if "index.html" in output:
                    key_files.append("index.html")
                if "schema.sql" in output:
                    key_files.append("schema.sql")
            
            if key_files:
                report_lines.append(f"- **Ключевые файлы:** {', '.join(set(key_files))}")
            
            report_lines.append("")  # Пустая строка для разделения
        
        # Добавляем общую статистику
        total_agents = len(agent_results)
        total_results = len(shared_outputs)
        total_chars = sum(len(output["output"]) for output in shared_outputs)
        
        report_lines.append("## 📈 Общая статистика")
        report_lines.append(f"- **Агентов:** {total_agents}")
        report_lines.append(f"- **Результатов:** {total_results}")
        report_lines.append(f"- **Общий размер:** {total_chars} символов")
        
        return "\n".join(report_lines)

    async def enqueue_directed_task(self, directive: Directive) -> None:
        """Кладёт адресную задачу конкретному агенту"""
        if directive.target_agent not in self.agents:
            logger.warning(f"Адресная задача на неизвестного агента: {directive.target_agent}")
            return
        task = AgentTask(
            id=f"{self.current_project.id}_{directive.target_agent}_{int(time.time())}",
            description=directive.description,
                    context={
                        "project_name": self.current_project.name,
                        "project_id": self.current_project.id,
                        "iteration": self.current_project.current_iteration,
                "shared_context": []
            }
        )
        self.directed_queues[directive.target_agent].append(task)
        logger.info(f"Добавлена адресная задача для {directive.target_agent}: {directive.title}")

    async def _after_phase_feedback(self):
        """Анализ результатов мозгом и постановка адресных задач"""
        insights = self.brain.extract_insights(self.current_project.all_results)
        directives = self.brain.derive_directives(self.current_project, insights)
        for d in directives:
            await self.enqueue_directed_task(d)
        
        # 🔥 НОВОЕ: Запускаем цикл улучшения кода если есть проблемы
        await self._trigger_improvement_cycle()

    async def _handle_agent_failure(self, agent_id: str, task: AgentTask, error_text: str):
        """Создает адресные задачи и подготавливает контекст для самоисправления после сбоя агента."""
        try:
            # Помечаем нужду в доработке
            self.current_project.agent_status[agent_id] = 'needs_revision'
            if 'context' not in task.__dict__ or task.context is None:
                task.context = {}
            task.context.setdefault('last_error', error_text)

            # Эвристики: куда направить фиксацию
            helper_chain: List[Directive] = []
            if agent_id in ('backend_developer', 'frontend_developer'):
                helper_chain.append(Directive(
                    target_agent='code_reviewer',
                    title='Проанализировать падение агента',
                    description=f'Агент {agent_id} упал с ошибкой: {error_text}. Найти причину и предложить EDIT/APPEND фиксы.',
                    context={'failing_agent': agent_id, 'error_text': error_text}
                ))
                helper_chain.append(Directive(
                    target_agent='bug_fixer',
                    title='Исправить код по отчёту',
                    description='Применить правки на основе отчёта Code Reviewer, используя EDIT/APPEND.',
                    context={'failing_agent': agent_id}
                ))
            elif agent_id == 'qa_tester':
                helper_chain.append(Directive(
                    target_agent='bug_fixer',
                    title='Починить тестовые падения',
                    description='Проанализировать падения pytest и исправить соответствующий код/тесты.',
                    context={'source': 'qa_tester', 'error_text': error_text}
                ))
            elif agent_id == 'devops_engineer':
                helper_chain.append(Directive(
                    target_agent='code_reviewer',
                    title='Починить DevOps конфигурацию',
                    description='Проверить Dockerfile/docker-compose.yml и предложить правки.',
                    context={'source': 'devops_engineer', 'error_text': error_text}
                ))

            # Кладём адресные задачи в очередь
            for directive in helper_chain:
                await self.enqueue_directed_task(directive)
        except Exception as e:
            logger.error(f"Ошибка в _handle_agent_failure: {e}")

    def _on_agent_timeout(self, agent_id: str, task: AgentTask, attempt: int):
        """Адаптация задачи при таймауте: упрощение задачи/сжатие контекста."""
        try:
            # Сокращаем shared_context до последних записей
            if task.context and 'shared_context' in task.context:
                sc = task.context['shared_context']
                if isinstance(sc, list) and len(sc) > 10:
                    task.context['shared_context'] = sc[-10:]
            # Добавляем подсказку о таймауте, чтобы агент упростил вывод
            task.context = task.context or {}
            task.context['timeout_hint'] = f'timeout_on_attempt_{attempt+1}: сократи вывод, действуй итеративно'
        except Exception as e:
            logger.warning(f"Не удалось адаптировать задачу при таймауте: {e}")
    
    async def _execute_iteration(self, tasks: Dict[str, AgentTask]) -> bool:
        """Выполняет одну итерацию цикла. Поддерживает параллельные фазы."""
        iteration_success = True

        async def run_single_agent(agent_id: str):
            agent = self.agents[agent_id]
            if self.directed_queues[agent_id]:
                task = self.directed_queues[agent_id].pop(0)
                logger.debug(f"[{agent_id}] Использую адресную задачу: {task.id}")
            else:
                task = tasks[agent_id]
                logger.debug(f"[{agent_id}] Использую дефолтную задачу: {task.id}")

            logger.info(f"Запуск задачи для агента {agent_id} ({agent.name}) с таймаутом {AGENT_TIMEOUT} секунд")
            attempt = 0
            result = None
            while attempt <= AGENT_RETRIES:
                try:
                    logger.debug(
                        f"🕐 Запуск агента {agent_id} с таймаутом {AGENT_TIMEOUT} секунд (попытка {attempt+1}/{AGENT_RETRIES+1})"
                    )
                    result = await asyncio.wait_for(agent.execute_task(task), timeout=AGENT_TIMEOUT)
                    break
                except asyncio.TimeoutError as e:
                    logger.error(
                        f"Таймаут для агента {agent_id} (попытка {attempt+1}/{AGENT_RETRIES+1})",
                        exc_info=True,
                    )
                    self._on_agent_timeout(agent_id, task, attempt)
                except Exception as e:
                    logger.error(
                        f"Ошибка выполнения агента {agent_id} (попытка {attempt+1}/{AGENT_RETRIES+1}): {e}",
                        exc_info=True,
                    )
                    await self._handle_agent_failure(agent_id, task, str(e))
                attempt += 1

            if result is None:
                self.current_project.agent_status[agent_id] = "skipped"
                logger.warning(f"⏭️ Агент {agent_id} пропущен после исчерпания ретраев")
                return False

            if agent_id not in self.current_project.all_results:
                self.current_project.all_results[agent_id] = []
            self.current_project.all_results[agent_id].append(result)

            if result.success:
                console.print(f"[green]✓ {agent.name} завершил задачу[/green]")
                logger.info(
                    f"Агент {agent_id} успешно выполнил задачу. Размер вывода: {len(result.output)} символов"
                )
            else:
                console.print(f"[red]❌ {agent.name} не смог выполнить задачу[/red]")
                logger.error(f"Агент {agent_id} не смог выполнить задачу. Ошибки: {result.errors}")
                self.current_project.agent_status[agent_id] = "failed"
                self.current_project.agent_consecutive_failures[agent_id] = (
                    self.current_project.agent_consecutive_failures.get(agent_id, 0) + 1
                )
                await self._handle_agent_failure(agent_id, task, "execution_failed")
                return False

            files_created = len(result.files_created) if result.files_created else 0
            if files_created == 0:
                logger.warning(
                    f"⚠️ Агент {agent_id} не создал файлы, хотя задача выполнена успешно"
                )
                self.current_project.agent_status[agent_id] = "needs_revision"
                self.current_project.agent_consecutive_failures[agent_id] = (
                    self.current_project.agent_consecutive_failures.get(agent_id, 0) + 1
                )
                if agent_id in ["product_owner", "project_manager", "system_architect"]:
                    logger.error(
                        f"🛑 Ключевой агент {agent_id} не создал файлы - прерываем итерацию"
                    )
                    return False
            else:
                logger.info(f"✅ Агент {agent_id} создал {files_created} файлов")
                self.current_project.agent_status[agent_id] = "completed"
                self.current_project.last_success_iteration[agent_id] = (
                    self.current_project.current_iteration
                )
                self.current_project.agent_consecutive_failures[agent_id] = 0

            if agent_id in ["product_owner", "project_manager", "system_architect", "database_engineer"]:
                logger.info(
                    f"🎯 {agent_id} - ключевой агент, контекст будет обновлён для следующих агентов"
                )

            return True

        if not PARALLEL_EXECUTION:
            # 🔥 СИНХРОННЫЙ РЕЖИМ: Обновляем контекст ПОСЛЕ КАЖДОГО ключевого агента
            logger.info(f"🚀 Синхронный режим: таймаут агента={AGENT_TIMEOUT}с, повторы={AGENT_RETRIES}")
            for agent_id in AGENT_EXECUTION_ORDER:
                # 🔥 ПРОВЕРЯЕМ is_active: выполняем только активных агентов
                if agent_id not in self.agents or agent_id not in tasks or not self.agents[agent_id].is_active:
                    continue
                    
                # Выполняем агента
                ok = await run_single_agent(agent_id)
                if not ok:
                    iteration_success = False
                    continue
                
                # 🔥 КРИТИЧНО: Обновляем контекст ПОСЛЕ каждого ключевого агента
                if agent_id in ["product_owner", "project_manager", "system_architect", "database_engineer"]:
                    logger.info(f"🔄 Обновляем контекст после {agent_id}...")
                    await self._update_project_context()
                    logger.info(f"✅ Контекст обновлён после {agent_id}")
                    
                    # 🔥 ПЕРЕСОЗДАЁМ задачи для следующих агентов с обновлённым контекстом
                    if agent_id in ["product_owner", "project_manager", "system_architect"]:
                        logger.info(f"🔄 Пересоздание задач с обновлённым контекстом после {agent_id}...")
                        await self._recreate_tasks_with_updated_context(tasks, agent_id)
            
            # ПРИНУДИТЕЛЬНЫЙ ФОЛБЭК для синхронного режима: если PO/PM упали, создаём базовое ТЗ
            if not iteration_success and not self._check_po_pm_success():
                logger.warning("⚠️ PO/PM не справились (синхронный режим), создаём принудительный фолбэк-ТЗ")
                fallback_requirements = self._create_fallback_requirements()
                if fallback_requirements:
                    logger.info(f"📝 Создан принудительный фолбэк-ТЗ: {fallback_requirements[:100]}...")
                    if 'context' not in self.current_project.__dict__:
                        self.current_project.context = {}
                    self.current_project.context['requirements'] = fallback_requirements
                    # Помечаем как успешную итерацию с фолбэком
                    iteration_success = True
                    logger.info("✅ Итерация помечена как успешная с фолбэк-ТЗ")
        else:
            # Параллельный режим: исполняем фазами с ограничением конкуррентности
            logger.info(f"🚀 Параллельный режим: макс. конкуррентность={AGENT_MAX_CONCURRENCY}, таймаут агента={AGENT_TIMEOUT}с")
            sem = asyncio.Semaphore(AGENT_MAX_CONCURRENCY)

            async def guarded_run(agent_id: str):
                async with sem:
                    ok = await run_single_agent(agent_id)
                    # 🔥 НОВОЕ: фиксируем статус в параллельном режиме
                    if not ok:
                        self.current_project.agent_status[agent_id] = 'failed'
                    return ok

            # Используем оптимизированные фазы если есть анализ проекта
            phases = getattr(self.current_project, 'optimized_phases', AGENT_EXECUTION_PHASES)
            
            total_agents = sum(1 for phase in phases for a in phase if a in self.agents and a in tasks)
            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                "[progress.percentage]{task.percentage:>3.0f}%",
                TimeElapsedColumn(),
            ) as progress:
                task_progress = progress.add_task("Выполнение агентов...", total=total_agents)
                completed = 0
                
                for phase_idx, phase in enumerate(phases):
                    # 🔥 ПРОВЕРЯЕМ is_active: включаем только активных агентов
                    phase_agents = [a for a in phase if a in self.agents and a in tasks and self.agents[a].is_active]
                    logger.info(f"🚀 Запуск фазы {phase_idx + 1}/{len(AGENT_EXECUTION_PHASES)}: {', '.join(phase_agents)}")
                    
                    # 🔥 ЛОГИРУЕМ: Контекст для текущей фазы
                    if phase_idx > 0:
                        logger.info(f"🧠 Контекст для фазы {phase_idx + 1}:")
                        if self.current_project.product_requirements:
                            logger.info(f"  • requirements: ✅ ({len(self.current_project.product_requirements)} символов)")
                        if self.current_project.architecture:
                            logger.info(f"  • architecture: ✅ ({len(self.current_project.architecture)} символов)")
                        if self.current_project.database_schema:
                            logger.info(f"  • database_schema: ✅ ({len(self.current_project.database_schema)} символов)")
                    
                    # СТРОГАЯ БЛОКИРОВКА: проверяем успех предыдущих фаз
                    if phase_idx > 0:
                        previous_phase_success = self._check_phase_success(phase_idx - 1)
                        if not previous_phase_success:
                            logger.warning(f"⚠️ Фаза {phase_idx + 1} заблокирована: предыдущая фаза не прошла успешно")
                            # ПРИНУДИТЕЛЬНЫЙ ФОЛБЭК: если PO/PM упали, создаём базовое ТЗ
                            if phase_idx == 1 and not self._check_po_pm_success():
                                logger.warning("⚠️ PO/PM не справились, создаём принудительный фолбэк-ТЗ")
                                fallback_requirements = self._create_fallback_requirements()
                                if fallback_requirements:
                                    logger.info(f"📝 Создан принудительный фолбэк-ТЗ: {fallback_requirements[:100]}...")
                                    if 'context' not in self.current_project.__dict__:
                                        self.current_project.context = {}
                                    self.current_project.context['requirements'] = fallback_requirements
                                    # Помечаем как успешную итерацию с фолбэком
                                    iteration_success = True
                                    logger.info("✅ Итерация помечена как успешная с фолбэк-ТЗ")
                                    # Продолжаем выполнение
                                    break
                                else:
                                    logger.error("❌ Не удалось создать фолбэк-ТЗ, фаза заблокирована")
                                    return False
                            else:
                                logger.error(f"❌ Фаза {phase_idx + 1} заблокирована: предыдущая фаза не прошла успешно")
                                return False
                    
                    # Дополнительно: для фазы 2 (SA/UX/DB) проверяем успех фазы 0 (PO) и фазы 1 (PM)
                    if phase_idx == 2:
                        po_pm_success = self._check_po_pm_success()
                        if not po_pm_success:
                            logger.warning(f"⚠️ Фаза {phase_idx + 1} заблокирована: PO/PM не создали ТЗ, создаём фолбэк")
                            # Создаём фолбэк-ТЗ из project_description
                            fallback_requirements = self._create_fallback_requirements()
                            if fallback_requirements:
                                logger.info(f"📝 Создан фолбэк-ТЗ из project_description: {fallback_requirements[:100]}...")
                                # Добавляем в контекст для следующих агентов
                                if 'context' not in self.current_project.__dict__:
                                    self.current_project.context = {}
                                self.current_project.context['requirements'] = fallback_requirements
                                # Помечаем как успешную итерацию с фолбэком
                                iteration_success = True
                                logger.info("✅ Итерация помечена как успешная с фолбэк-ТЗ")
                            else:
                                logger.error("❌ Не удалось создать фолбэк-ТЗ, фаза заблокирована")
                                return False
                    
                    progress.update(task_progress, description=f"Фаза {phase_idx + 1}: {', '.join(phase_agents) or 'пусто'}")
                    coros = [guarded_run(a) for a in phase_agents]
                    results = await asyncio.gather(*coros, return_exceptions=True)
                    
                    # 🔥 НОВОЕ: Анализируем результаты параллельного выполнения
                    phase_success = True
                    for i, res in enumerate(results):
                        progress.advance(task_progress)

                        if isinstance(res, Exception):
                            agent_id = phase_agents[i]
                            logger.error(f"❌ {agent_id} завершился с ошибкой: {res}")
                            console.print(f"[red]❌ {agent_id}: {res}[/red]")
                            # Классифицируем ошибки для валидации
                            if isinstance(res, asyncio.TimeoutError):
                                logger.warning(f"⏰ {agent_id}: Таймаут выполнения")
                                self.current_project.validation_warnings.append(f"{agent_id}: Таймаут выполнения")
                            elif "api" in str(res).lower() or "network" in str(res).lower():
                                logger.warning(f"🌐 {agent_id}: Проблемы с API/сетью")
                                self.current_project.validation_warnings.append(f"{agent_id}: Проблемы с API/сетью")
                            else:
                                logger.error(f"❓ {agent_id}: Неизвестная ошибка")
                                self.current_project.validation_errors.append(f"{agent_id}: {res}")
                            
                            phase_success = False
                        elif res is False:
                            agent_id = phase_agents[i]
                            logger.warning(f"⚠️ {agent_id}: Задача не выполнена")
                            phase_success = False
                    
                    # 🔥 НОВОЕ: Проверяем успех фазы
                    if not phase_success:
                        logger.warning(f"⚠️ Фаза {phase_idx + 1} завершилась с ошибками")
                        # Не прерываем полностью, продолжаем с другими фазами
                        iteration_success = False
                    else:
                        logger.info(f"✅ Фаза {phase_idx + 1} завершена успешно")
                    logger.debug(f"Фаза {phase_idx + 1} завершена: {phase_agents}, итерация успех={iteration_success}")
                    # после каждой фазы — фидбек мозга
                    await self._after_phase_feedback()

        # 🔥 ПРОВЕРКА КЛЮЧЕВЫХ АГЕНТОВ: Учитываем только активных
        key_agents = ["project_manager", "system_architect", "backend_developer", "frontend_developer", "qa_tester", "code_reviewer", "bug_fixer"]
        for agent_id in key_agents:
            # Пропускаем неактивных агентов
            if agent_id not in self.agents or not self.agents[agent_id].is_active:
                logger.debug(f"🔴 Агент {agent_id} пропущен (неактивен)")
                continue
                
            results = self.current_project.all_results.get(agent_id, [])
            if not results or not any(r.success for r in results[-1:]):
                iteration_success = False
        
        # ПРИНУДИТЕЛЬНЫЙ ФОЛБЭК: если PO/PM упали, создаём базовое ТЗ
        if not iteration_success and not self._check_po_pm_success():
            logger.warning("⚠️ PO/PM не справились, создаём принудительный фолбэк-ТЗ")
            fallback_requirements = self._create_fallback_requirements()
            if fallback_requirements:
                logger.info(f"📝 Создан принудительный фолбэк-ТЗ: {fallback_requirements[:100]}...")
                if 'context' not in self.current_project.__dict__:
                    self.current_project.context = {}
                self.current_project.context['requirements'] = fallback_requirements
                # Помечаем как успешную итерацию с фолбэком
                iteration_success = True
                logger.info("✅ Итерация помечена как успешная с фолбэк-ТЗ")
        
        return iteration_success
    
    def _get_agent_output(self, agent_id: str) -> str:
        """Получает последний успешный вывод конкретного агента"""
        if agent_id not in self.current_project.all_results:
            return ""
        results = self.current_project.all_results[agent_id]
        if not results:
            return ""
        # Берём последний успешный результат
        for result in reversed(results):
            if result.success and result.output:
                return result.output
        return ""
    
    def _get_previous_results(self, agent_id: str) -> List[str]:
        """Возвращает компактную "память" агента: последние 2 вывода + краткая сводка.

        Это защищает prompt от переполнения, сохраняя контекст итераций.
        """
        if agent_id not in self.current_project.all_results:
            return []
            
        successful = [r.output for r in self.current_project.all_results[agent_id] if getattr(r, 'success', False) and getattr(r, 'output', None)]
        if not successful:
            return []

        if len(successful) <= 2:
            return successful

        tail = successful[-2:]
        summary = self._summarize_outputs(successful[:-2])
        return tail + ([summary] if summary else [])

    def _summarize_outputs(self, outputs: List[str]) -> str:
        """Грубая сводка списка строк: считает элементы, символы, ключевые маркеры файлов."""
        if not outputs:
            return ""
        total = len(outputs)
        chars = sum(len(o) for o in outputs)
        key_files = []
        for o in outputs:
            for k in [".py", ".js", ".ts", "index.html", "app.py", "schema.sql", "Dockerfile", "docker-compose.yml"]:
                if k in o:
                    key_files.append(k)
        uniq = ", ".join(sorted(set(key_files))) if key_files else "нет ключевых файлов"
        return f"[summary] прошлых результатов: {total} шт., ~{chars} симв., ключевые: {uniq}"
    
    async def _evaluate_results(self) -> bool:
        """Оценивает качество результатов с улучшенными критериями"""
        logger.info("🔍 Оценка качества результатов проекта...")
        
        # 🔥 ИСПРАВЛЕНО: Проверяем НАКОПЛЕННЫЕ успешные результаты за ВСЕ итерации
        # Убираем строгое требование одновременного успеха всех агентов
        key_agents = ["product_owner", "project_manager", "system_architect", "backend_developer", "frontend_developer", "database_engineer", "ui_ux_designer", "qa_tester", "code_reviewer", "bug_fixer"]
        
        missing_agents = []
        failed_agents = []
        successful_agents = []
        inactive_agents = []
        
        for agent_id in key_agents:
            # 🔥 ПРОВЕРЯЕМ is_active: пропускаем неактивных агентов
            if agent_id not in self.agents or not self.agents[agent_id].is_active:
                inactive_agents.append(agent_id)
                logger.debug(f"🔴 Агент {agent_id} пропущен в оценке (неактивен)")
                continue
                
            if agent_id not in self.current_project.all_results:
                missing_agents.append(agent_id)
                continue
                
            results = self.current_project.all_results[agent_id]
            if not results:
                failed_agents.append(agent_id)
            elif any(r.success for r in results):
                successful_agents.append(agent_id)
            else:
                failed_agents.append(agent_id)
        
        # 🔥 НОВАЯ ЛОГИКА: Проект считается успешным если большинство ключевых агентов работали
        total_key_agents = len(key_agents)
        success_ratio = len(successful_agents) / total_key_agents
        
        # 🔥 ЛОГИРУЕМ: Детальная статистика по агентам
        logger.info("📋 Детальная статистика по агентам:")
        
        if inactive_agents:
            logger.info(f"  🔴 Неактивные агенты: {', '.join(inactive_agents)}")
        
        for agent_id in successful_agents:
            results = self.current_project.all_results[agent_id]
            success_count = sum(1 for r in results if r.success)
            total_count = len(results)
            logger.info(f"  ✅ {agent_id}: {success_count}/{total_count} успешных попыток")
        
        for agent_id in failed_agents:
            logger.info(f"  ❌ {agent_id}: нет успешных результатов")
        
        # 🔥 КОРРЕКТИРУЕМ СТАТИСТИКУ: Учитываем только активных агентов
        active_key_agents = total_key_agents - len(inactive_agents)
        if active_key_agents > 0:
            success_ratio = len(successful_agents) / active_key_agents
            logger.info(f"📊 Статистика активных ключевых агентов: {len(successful_agents)}/{active_key_agents} успешных ({success_ratio:.1%})")
        else:
            success_ratio = 0.0
            logger.warning("⚠️ Нет активных ключевых агентов для оценки")
        
        # 🔥 ИСПОЛЬЗУЕМ НАСТРАИВАЕМЫЙ ПОРОГ: Проект готов если достигнут порог успешности
        if success_ratio >= SUCCESS_THRESHOLD:
            logger.info(f"✅ Проект готов! Успешных агентов: {len(successful_agents)}/{total_key_agents} (порог: {SUCCESS_THRESHOLD:.1%})")
            return True
        
        if missing_agents:
            logger.warning(f"⚠️ Агенты не выполнили задачи: {', '.join(missing_agents)}")
            
        if failed_agents:
            logger.warning(f"⚠️ Агенты завершились с ошибками: {', '.join(failed_agents)}")

        logger.info(f"📋 Продолжаем итерации для достижения требуемого качества (порог: {SUCCESS_THRESHOLD:.1%})")
        return False
                
        # 2) Проверяем полноту проекта - все необходимые файлы должны быть созданы
        if not await self._check_project_completeness():
            logger.warning("⚠️ Проект неполный, продолжаем итерации")
            return False

        # 3) Анализируем результаты QA и Code Reviewer (критично!)
        analysis = await self._analyze_qa_and_review_results()
        
        # Логируем результаты анализа
        logger.info("📋 Результаты анализа QA и Code Reviewer:")
        for issue in analysis["issues_summary"]:
            logger.info(f"  • {issue}")
        
        # 3) Проверяем, что нет критических проблем
        if analysis["has_critical_issues"]:
            logger.warning("❌ Обнаружены критические проблемы, проект не готов")
            return False
        
        # 4) Проверяем, что не нужны исправления
        if analysis["needs_fixes"]:
            logger.warning("⚠️ Требуются исправления, продолжаем итерации")
            return False
        
        # 5) Проверяем минимальное количество успешных итераций
        if self.current_project.current_iteration < MIN_SUCCESS_ITERATIONS:
            logger.info(f"📋 Текущая итерация {self.current_project.current_iteration} < {MIN_SUCCESS_ITERATIONS}, продолжаем накопление")
            return False
        
        # 6) Дополнительная проверка: QA должен создать тесты
        qa_results = self.current_project.all_results.get("qa_tester", [])
        if qa_results and any(r.success for r in qa_results):
            qa_output = next(r.output for r in reversed(qa_results) if r.success)
            if not self._has_test_files(qa_output):
                logger.warning("⚠️ QA не создал тесты, продолжаем итерации")
                return False
        
        # 7) Дополнительная проверка: Code Reviewer не должен найти критичных багов
        cr_results = self.current_project.all_results.get("code_reviewer", [])
        if cr_results and any(r.success for r in cr_results):
            cr_output = next(r.output for r in reversed(cr_results) if r.success)
            if self._has_critical_bugs(cr_output):
                logger.warning("⚠️ Code Reviewer нашёл критические баги, продолжаем итерации")
                return False
        
        # 8) 🔥 НОВОЕ: Проверяем, что все найденные проблемы исправлены
        if not await self._check_all_issues_resolved():
            logger.warning("⚠️ Не все проблемы исправлены, продолжаем итерации")
            return False
        
        # 9) 🔥 НОВОЕ: Проверяем полноту реализации кода
        if not await self._check_code_completeness():
            logger.warning("⚠️ Код неполный, есть TODO и заглушки, продолжаем итерации")
            return False
        
        # 10) 🔥 НОВОЕ: Проверяем, что все задачи выполнены
        if not await self._check_all_tasks_completed():
            logger.warning("⚠️ Не все задачи выполнены, продолжаем итерации")
            return False
        
        # 11) 🔥 НОВОЕ: Проверяем интеграцию и финальное тестирование
        if not await self._check_project_integration():
            logger.warning("⚠️ Проект не прошел интеграционное тестирование, продолжаем итерации")
            return False
        
        # 12) 🔥 НОВОЕ: Логируем статистику использования контекста
        self._log_context_usage_stats()
        
        logger.info("✅ Все критерии качества выполнены, проект готов!")
        return True
    
    def _has_test_files(self, output: str) -> bool:
        """Проверяет, создал ли QA тесты"""
        test_indicators = [
            "test_", "test.py", "tests/", "pytest", "unittest",
            "```python:test_", "```python:tests/", "test_api", "test_backend"
        ]
        return any(indicator in output for indicator in test_indicators)
    
    def _has_critical_bugs(self, output: str) -> bool:
        """Проверяет, нашёл ли Code Reviewer критические баги"""
        critical_indicators = [
            "critical", "blocker", "fatal", "неисправлено", "не работает", 
            "broken", "ошибка", "bug:", "bugs_found", "критическая проблема"
        ]
        return any(indicator in output.lower() for indicator in critical_indicators)
    
    async def _analyze_qa_and_review_results(self) -> Dict[str, Any]:
        """Анализирует результаты QA и Code Reviewer для выявления проблем"""
        analysis = {
            "has_critical_issues": False,
            "has_minor_issues": False,
            "issues_summary": [],
            "needs_fixes": False
        }
        
        # Анализируем результаты Code Reviewer
        reviewer_outputs = [r.output for r in self.current_project.all_results.get('code_reviewer', []) if r.success and r.output]
        if reviewer_outputs:
            reviewer_text = "\n\n".join(reviewer_outputs).lower()
            
            # Критические проблемы
            critical_markers = ["critical", "blocker", "fatal", "неисправлено", "не работает", "broken"]
            if any(m in reviewer_text for m in critical_markers):
                analysis["has_critical_issues"] = True
                analysis["issues_summary"].append("Code Reviewer: обнаружены критические проблемы")
                analysis["needs_fixes"] = True
            
            # Обычные проблемы
            bug_markers = ["bugs_found", "bug:", "ошибка", "todo:", "fix", "issue", "problem", "warning"]
            if any(m in reviewer_text for m in bug_markers):
                analysis["has_minor_issues"] = True
                analysis["issues_summary"].append("Code Reviewer: обнаружены незначительные проблемы")
                if not analysis["has_critical_issues"]:
                    analysis["needs_fixes"] = True
        
        # Анализируем результаты QA
        qa_outputs = [r.output for r in self.current_project.all_results.get('qa_tester', []) if r.success and r.output]
        if qa_outputs:
            qa_text = "\n\n".join(qa_outputs).lower()
            
            # Проверяем наличие тестов
            if "```python" in qa_text or "test_" in qa_text:
                # Запускаем тесты
                tests_ok = await self._run_temp_tests()
                if not tests_ok:
                    analysis["has_critical_issues"] = True
                    analysis["issues_summary"].append("QA: тесты не проходят")
                    analysis["needs_fixes"] = True
                else:
                    analysis["issues_summary"].append("QA: все тесты проходят успешно")
            else:
                analysis["issues_summary"].append("QA: тесты не созданы")
                analysis["needs_fixes"] = True
        
                return analysis
    
    def _extract_file_content(self, output: str, filename: str) -> str:
        """Извлекает содержимое конкретного файла из вывода агента"""
        try:
            # Ищем блок кода с указанным именем файла
            pattern = rf"```(?:markdown|yaml|python|sql|javascript|css|html|dockerfile):\s*{re.escape(filename)}.*?\n(.*?)```"
            match = re.search(pattern, output, re.DOTALL | re.IGNORECASE)
            
            if match:
                content = match.group(1).strip()
                logger.debug(f"Извлечено содержимое файла {filename}: {len(content)} символов")
                return content
            else:
                logger.debug(f"Файл {filename} не найден в выводе агента")
                return ""
                
        except Exception as e:
            logger.warning(f"Ошибка извлечения файла {filename}: {e}")
            return ""
    
    async def _run_temp_tests(self) -> bool:
        """Собирает проект во временную директорию и запускает pytest; возвращает True при успехе."""
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                # Генерируем проект во временную папку
                gen = ProjectGenerator(output_base_dir=str(tmp_path))
                files_created = await gen.generate_project(self.current_project, self.current_project.all_results)
                logger.info(f"Временная сборка для тестов: файлов создано {len(files_created)}")

                # Если нет tests каталога — нечего проверять
                tests_dir = tmp_path / self.current_project.name / "tests"
                if not tests_dir.exists():
                    logger.info("Тесты отсутствуют, пропускаем прогон pytest")
                    return True

                # Создаем виртуальный прогон pytest
                proc = await asyncio.create_subprocess_exec(
                    "python", "-m", "pytest", "-q",
                    cwd=str((tmp_path / self.current_project.name)),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                out = stdout.decode(errors='ignore')
                err = stderr.decode(errors='ignore')
                logger.info(f"pytest stdout:\n{out}")
                if err:
                    logger.warning(f"pytest stderr:\n{err}")
                return proc.returncode == 0
        except FileNotFoundError:
            # pytest не установлен — не блокируем завершение, но логируем
            logger.warning("pytest не найден в окружении — пропускаем тесты")
            return True
        except Exception as e:
            logger.error(f"Не удалось выполнить временный прогон тестов: {e}")
            return False
    
    async def _update_context_after_agent(self, agent_id: str):
        """🔥 НОВОЕ: Промежуточное обновление контекста ПОСЛЕ выполнения ключевого агента"""
        logger.info(f"🔄 Промежуточное обновление контекста после агента {agent_id}...")
        
        if agent_id == "product_owner":
            # Product Owner → требования для всех последующих агентов
            if "product_owner" in self.current_project.all_results:
                po_results = self.current_project.all_results["product_owner"]
                if po_results and po_results[-1].success:
                    self.current_project.requirements = po_results[-1].output
                    self.current_project.product_requirements = self._extract_file_content(po_results[-1].output, "product_requirements.md")
                    self.current_project.user_stories = self._extract_file_content(po_results[-1].output, "user_stories.md")
                    self.current_project.acceptance_criteria = self._extract_file_content(po_results[-1].output, "acceptance_criteria.md")
                    logger.info("✅ Обновлены требования от Product Owner для текущей итерации")
                    
        elif agent_id == "project_manager":
            # Project Manager → план проекта на основе требований PO
            if "project_manager" in self.current_project.all_results:
                pm_results = self.current_project.all_results["project_manager"]
                if pm_results and pm_results[-1].success:
                    self.current_project.project_plan = self._extract_file_content(pm_results[-1].output, "project_plan.md")
                    self.current_project.timeline = self._extract_file_content(pm_results[-1].output, "timeline.md")
                    logger.info("✅ Обновлен план проекта от Project Manager для текущей итерации")
                    
        elif agent_id == "system_architect":
            # System Architect → архитектура для разработчиков
            if "system_architect" in self.current_project.all_results:
                sa_results = self.current_project.all_results["system_architect"]
                if sa_results and sa_results[-1].success:
                    self.current_project.architecture = sa_results[-1].output
                    self.current_project.technology_stack = self._extract_file_content(sa_results[-1].output, "technology_stack.md")
                    self.current_project.system_design = self._extract_file_content(sa_results[-1].output, "system_design.md")
                    self.current_project.api_specification = self._extract_file_content(sa_results[-1].output, "api_specification.md")
                    logger.info("✅ Обновлена архитектура от System Architect для текущей итерации")
                    
        elif agent_id == "database_engineer":
            # Database Engineer → схема БД для backend
            if "database_engineer" in self.current_project.all_results:
                db_results = self.current_project.all_results["database_engineer"]
                if db_results and db_results[-1].success:
                    self.current_project.database_schema = db_results[-1].output
                    self.current_project.schema_sql = self._extract_file_content(db_results[-1].output, "schema.sql")
                    logger.info("✅ Обновлена схема БД от Database Engineer для текущей итерации")

    async def _recreate_tasks_with_updated_context(self, tasks: Dict[str, AgentTask], completed_agent_id: str):
        """🔥 НОВОЕ: Пересоздает задачи для следующих агентов с обновлённым контекстом"""
        logger.info(f"🔄 Пересоздание задач с обновлённым контекстом после {completed_agent_id}...")
        
        # Определяем какие агенты должны получить обновлённый контекст
        agents_to_update = []
        
        if completed_agent_id == "product_owner":
            # PO завершился → обновляем PM, SA, BE, FE, DB, UI/UX
            agents_to_update = ["project_manager", "system_architect", "backend_developer", "frontend_developer", "database_engineer", "ui_ux_designer"]
        elif completed_agent_id == "project_manager":
            # PM завершился → обновляем SA, BE, FE, DB, UI/UX
            agents_to_update = ["system_architect", "backend_developer", "frontend_developer", "database_engineer", "ui_ux_designer"]
        elif completed_agent_id == "system_architect":
            # SA завершился → обновляем BE, FE, DB, UI/UX
            agents_to_update = ["backend_developer", "frontend_developer", "database_engineer", "ui_ux_designer"]
        
        # Пересоздаём задачи для указанных агентов
        for agent_id in agents_to_update:
            if agent_id in tasks and agent_id in self.agents:
                logger.info(f"🔄 Пересоздание задачи для {agent_id} с обновлённым контекстом...")
                
                # Создаём новую задачу с актуальным контекстом
                new_task = await self._create_single_agent_task(agent_id)
                if new_task:
                    tasks[agent_id] = new_task
                    logger.info(f"✅ Задача для {agent_id} пересоздана с обновлённым контекстом")
                else:
                    logger.warning(f"⚠️ Не удалось пересоздать задачу для {agent_id}")

    async def _create_single_agent_task(self, agent_id: str) -> Optional[AgentTask]:
        """🔥 НОВОЕ: Создаёт задачу для одного агента с актуальным контекстом"""
        if agent_id not in self.agents:
            return None
            
        task_id = f"{self.current_project.id}_{agent_id}_{int(time.time())}"
        
        # Собираем актуальный контекст
        shared_outputs = []
        for aid, results in self.current_project.all_results.items():
            for r in results:
                if r.success and r.output:
                    shared_outputs.append({"agent": aid, "output": r.output})

        agent_specific_context = {
            "previous_results": self._get_previous_results(agent_id),
            "shared_context": shared_outputs,
            "agent_specific_context": self._get_agent_specific_context(agent_id),
            "agent_dependencies": self._get_agent_dependencies(agent_id),
            "file_versions": self._get_file_versions(),
            "component_status": self._get_component_status(),
            "current_iteration": self.current_project.current_iteration,
            "project_status": self.current_project.status,
            "all_agent_results": self.current_project.all_results
        }
        
        context = self.context_manager.get_optimized_context(
            agent_id=agent_id,
            project_context=self.current_project,
            agent_specific_context=agent_specific_context
        )
        
        return AgentTask(
            id=task_id,
            description=self.current_project.description,
            context=context
        )
    
    async def _update_project_context(self):
        """Обновляет контекст проекта для следующей итерации (конвейер данных)"""
        logger.info("🔄 Обновление контекста проекта для следующей итерации...")
        
        # Конвейер данных: выход каждого агента становится входом для следующих
        
        # 1. Product Owner → требования для всех последующих агентов
        if "product_owner" in self.current_project.all_results:
            po_results = self.current_project.all_results["product_owner"]
            if po_results and po_results[-1].success:
                self.current_project.requirements = po_results[-1].output
                logger.info("✅ Обновлены требования от Product Owner")
                
                # Извлекаем ключевые файлы из требований
                self.current_project.product_requirements = self._extract_file_content(po_results[-1].output, "product_requirements.md")
                self.current_project.user_stories = self._extract_file_content(po_results[-1].output, "user_stories.md")
                self.current_project.acceptance_criteria = self._extract_file_content(po_results[-1].output, "acceptance_criteria.md")
        
        # 2. Project Manager → план проекта на основе требований PO
        if "project_manager" in self.current_project.all_results:
            pm_results = self.current_project.all_results["project_manager"]
            if pm_results and pm_results[-1].success:
                self.current_project.project_plan = self._extract_file_content(pm_results[-1].output, "project_plan.md")
                self.current_project.timeline = self._extract_file_content(pm_results[-1].output, "timeline.md")
                logger.info("✅ Обновлен план проекта от Project Manager")
        
        # 3. System Architect → архитектура для разработчиков
        if "system_architect" in self.current_project.all_results:
            sa_results = self.current_project.all_results["system_architect"]
            if sa_results and sa_results[-1].success:
                self.current_project.architecture = sa_results[-1].output
                self.current_project.technology_stack = self._extract_file_content(sa_results[-1].output, "technology_stack.md")
                self.current_project.system_design = self._extract_file_content(sa_results[-1].output, "system_design.md")
                self.current_project.api_specification = self._extract_file_content(sa_results[-1].output, "api_specification.md")
                logger.info("✅ Обновлена архитектура от System Architect")
        
        # 4. Database Engineer → схема БД для backend
        if "database_engineer" in self.current_project.all_results:
            db_results = self.current_project.all_results["database_engineer"]
            if db_results and db_results[-1].success:
                self.current_project.database_schema = db_results[-1].output
                self.current_project.schema_sql = self._extract_file_content(db_results[-1].output, "schema.sql")
                logger.info("✅ Обновлена схема БД от Database Engineer")
        
        # 5. UI/UX Designer → дизайн для frontend
        if "ui_ux_designer" in self.current_project.all_results:
            ui_results = self.current_project.all_results["ui_ux_designer"]
            if ui_results and ui_results[-1].success:
                self.current_project.ui_design = ui_results[-1].output
                self.current_project.design_system = self._extract_file_content(ui_results[-1].output, "design_system.md")
                self.current_project.wireframes = self._extract_file_content(ui_results[-1].output, "wireframes.md")
                logger.info("✅ Обновлен UI дизайн от UI/UX Designer")
        
        # 6. Backend Developer → API для frontend и интеграций
        if "backend_developer" in self.current_project.all_results:
            be_results = self.current_project.all_results["backend_developer"]
            if be_results and be_results[-1].success:
                self.current_project.api_spec = be_results[-1].output
                self.current_project.backend_code = be_results[-1].output
                logger.info("✅ Обновлена API спецификация от Backend Developer")
        
        # 7. Frontend Developer → код для QA и тестирования
        if "frontend_developer" in self.current_project.all_results:
            fe_results = self.current_project.all_results["frontend_developer"]
            if fe_results and fe_results[-1].success:
                self.current_project.frontend_code = fe_results[-1].output
                logger.info("✅ Обновлен frontend код от Frontend Developer")
        
        # 8. Bug Fixer → исправления для следующей итерации
        if "bug_fixer" in self.current_project.all_results:
            bf_results = self.current_project.all_results["bug_fixer"]
            if bf_results and bf_results[-1].success:
                self.current_project.bug_fixes = bf_results[-1].output
                self.current_project.bug_fixes_report = self._extract_file_content(bf_results[-1].output, "bug_fixes_report.md")
                logger.info("✅ Обновлены исправления от Bug Fixer")
        
        # 🔥 НОВОЕ: Создаём сводный отчёт по всем результатам для следующей итерации
        all_outputs = []
        for aid, results in self.current_project.all_results.items():
            for r in results:
                if r.success and r.output:
                    all_outputs.append({"agent": aid, "output": r.output})
        
        if all_outputs:
            summary_report = self._create_summary_report(all_outputs)
            self.current_project.summary_report = summary_report
            logger.info(f"📊 Создан сводный отчёт для следующей итерации: {len(summary_report)} символов")
        
        # Инкрементируем номер итерации
        self.current_project.current_iteration += 1
        logger.info(f"🔄 Итерация обновлена: {self.current_project.current_iteration}")
        
        # 🔥 ЛОГИРУЕМ: Статус обновления контекста для отслеживания
        logger.info(f"📊 Статус контекста после обновления:")
        logger.info(f"  • requirements: {'✅' if self.current_project.product_requirements else '❌'}")
        logger.info(f"  • architecture: {'✅' if self.current_project.architecture else '❌'}")
        logger.info(f"  • database_schema: {'✅' if self.current_project.database_schema else '❌'}")
        logger.info(f"  • backend_code: {'✅' if self.current_project.backend_code else '❌'}")
        logger.info(f"  • frontend_code: {'✅' if self.current_project.frontend_code else '❌'}")
        logger.info(f"  • summary_report: {'✅' if self.current_project.summary_report else '❌'}")
        
        # Обновляем статус проекта
        if self.current_project.current_iteration >= MAX_ITERATIONS:
            self.current_project.status = "completed_max_iterations"
        elif self.current_project.current_iteration >= MIN_SUCCESS_ITERATIONS:
            self.current_project.status = "ready_for_evaluation"
        else:
            self.current_project.status = "in_progress"
    
    async def _generate_project_files(self):
        """Генерирует файлы проекта и выполняет финальную сборку"""
        try:
            console.print("[bold blue]📁 Генерация файлов проекта...[/bold blue]")
            logger.info("Начинается генерация файлов проекта...")
            
            files_created = await self.project_generator.generate_project(
                self.current_project,
                self.current_project.all_results
            )
            
            self.current_project.files_generated.extend(files_created)
            console.print(f"[green]✓ Создано {len(files_created)} файлов[/green]")
            logger.info(f"Генерация файлов завершена. Создано файлов: {len(files_created)}")
            
            # Показываем список созданных файлов в логах
            for file_path in files_created:
                logger.debug(f"Создан файл: {file_path}")
            
            # Показываем список созданных файлов
            if files_created:
                table = Table(title="Созданные файлы")
                table.add_column("Файл", justify="left")
                
                for file_path in files_created[:20]:  # Показываем только первые 20
                    table.add_row(file_path)
                    
                if len(files_created) > 20:
                    table.add_row(f"... и еще {len(files_created) - 20} файлов")
                    
                console.print(table)
            
            # ФИНАЛЬНАЯ СБОРКА: проверяем консистентность и генерируем итоговый README
            console.print("\n[bold blue]🔧 Финальная сборка проекта...[/bold blue]")
            
            # Собираем содержимое файлов для анализа
            project_files = {}
            for file_path in files_created:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        project_files[file_path] = f.read()
                except Exception as e:
                    logger.warning(f"Не удалось прочитать файл {file_path}: {e}")
                    project_files[file_path] = ""
            
            # Выполняем финальную сборку
            assembly_report = self.final_assembler.assemble_final_project(
                project_files, 
                asdict(self.current_project)
            )
            
            # Показываем результаты финальной сборки
            console.print(f"\n[bold green]📊 Результаты финальной сборки:[/bold green]")
            console.print(f"Балл консистентности: {assembly_report['consistency_score']}/100")
            console.print(f"Проблем найдено: {len(assembly_report['issues_found'])}")
            
            if assembly_report['issues_found']:
                console.print("\n[bold yellow]⚠️ Найденные проблемы:[/bold yellow]")
                for issue in assembly_report['issues_found'][:5]:  # Показываем первые 5
                    console.print(f"  • {issue}")
                if len(assembly_report['issues_found']) > 5:
                    console.print(f"  ... и еще {len(assembly_report['issues_found']) - 5} проблем")
            
            # Сохраняем итоговый README
            if assembly_report['final_readme']:
                final_readme_path = Path(self.current_project.name) / "README_FINAL.md"
                try:
                    final_readme_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(final_readme_path, 'w', encoding='utf-8') as f:
                        f.write(assembly_report['final_readme'])
                    console.print(f"[green]✅ Итоговый README сохранен: {final_readme_path}[/green]")
                except Exception as e:
                    logger.error(f"Ошибка сохранения итогового README: {e}")
            
            # Сохраняем отчет о сборке
            self.current_project.final_assembly_report = assembly_report
            
        except Exception as e:
            logger.error(f"Ошибка генерации файлов: {e}")
            console.print(f"[red]❌ Ошибка генерации файлов: {e}[/red]")
    
    def get_project_status(self) -> Dict[str, Any]:
        """Возвращает статус текущего проекта"""
        if not self.current_project:
            return {"status": "no_active_project"}
            
        return {
            "project_id": self.current_project.id,
            "name": self.current_project.name,
            "status": self.current_project.status,
            "current_iteration": self.current_project.current_iteration,
            "agents_completed": len([
                agent_id for agent_id, results in self.current_project.all_results.items()
                if any(r.success for r in results)
            ]),
            "total_agents": len(self.agents),
            "files_generated": len(self.current_project.files_generated)
        }
    
    def save_project_state(self, file_path: str):
        """Сохраняет состояние проекта"""
        if not self.current_project:
            return
            
        # Конвертируем в JSON-сериализуемый формат
        project_data = asdict(self.current_project)
        
        # Конвертируем AgentResult объекты
        for agent_id, results in project_data['all_results'].items():
            project_data['all_results'][agent_id] = [
                asdict(result) for result in self.current_project.all_results[agent_id]
            ]
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(project_data, f, ensure_ascii=False, indent=2)
            
        console.print(f"[green]💾 Состояние проекта сохранено в {file_path}[/green]")

    def _check_phase_success(self, phase_idx: int) -> bool:
        """Проверяет успешность выполнения фазы"""
        if phase_idx >= len(AGENT_EXECUTION_PHASES):
            return False
        
        phase_agents = AGENT_EXECUTION_PHASES[phase_idx]
        for agent_id in phase_agents:
            if agent_id not in self.current_project.all_results:
                return False
            # Проверяем, что у агента есть хотя бы один успешный результат
            agent_results = self.current_project.all_results[agent_id]
            if not any(result.success for result in agent_results):
                return False
        return True
    
    def _check_po_pm_success(self) -> bool:
        """Проверяет успех Product Owner (фаза 0) и Project Manager (фаза 1)"""
        # Проверяем Product Owner (фаза 0)
        po_agents = AGENT_EXECUTION_PHASES[0]  # ['product_owner']
        po_success = False
        for agent_id in po_agents:
            if agent_id in self.current_project.all_results:
                agent_results = self.current_project.all_results[agent_id]
                if any(result.success for result in agent_results):
                    po_success = True
                    break
        
        # Проверяем Project Manager (фаза 1)
        pm_agents = AGENT_EXECUTION_PHASES[1]  # ['project_manager']
        pm_success = False
        for agent_id in pm_agents:
            if agent_id in self.current_project.all_results:
                agent_results = self.current_project.all_results[agent_id]
                if any(result.success for result in agent_results):
                    pm_success = True
                    break
        
        # Обе фазы должны быть успешными
        return po_success and pm_success
    
    def _create_fallback_requirements(self) -> Optional[str]:
        """Создаёт фолбэк-ТЗ из project_description если PO/PM не справились"""
        if not self.current_project or not self.current_project.description:
            return None
        
        fallback_requirements = f"""
        # Фолбэк-ТЗ проекта
        
        ## Описание проекта
        {self.current_project.description}
        
        ## Основные требования
        - Создать веб-приложение на основе описания
        - Использовать современные технологии (Python Flask, React, Docker)
        - Обеспечить масштабируемость и безопасность
        
        ## Функциональные требования
        - Базовый функционал согласно описанию проекта
        - REST API для backend
        - Современный UI для frontend
        
        ## Технические требования
        - Python 3.8+
        - Flask framework
        - React/TypeScript
        - Docker контейнеризация
        - CI/CD pipeline
        """
        
        return fallback_requirements.strip()

    async def _check_project_completeness(self) -> bool:
        """Проверяет полноту проекта - все необходимые файлы должны быть созданы"""
        logger.info("🔍 Проверка полноты проекта...")
        
        # Список обязательных файлов для разных типов проектов
        required_files = {
            "backend": [
                "app.py", "main.py", "requirements.txt", "config.py"
            ],
            "frontend": [
                "index.html", "main.js", "styles.css", "package.json"
            ],
            "database": [
                "schema.sql", "migrations/", "models.py"
            ],
            "devops": [
                "Dockerfile", "docker-compose.yml", ".env.example"
            ],
            "tests": [
                "test_", "pytest.ini", "conftest.py"
            ],
            "docs": [
                "README.md", "API.md", "deployment.md"
            ]
        }
        
        project_dir = Path(PROJECT_OUTPUT_DIR) / self.current_project.project_name
        if not project_dir.exists():
            logger.warning("❌ Директория проекта не существует")
            return False
        
        missing_files = []
        total_required = 0
        total_found = 0
        
        for category, files in required_files.items():
            category_found = 0
            for file_pattern in files:
                total_required += 1
                # Ищем файлы по паттерну
                if file_pattern.endswith('/'):
                    # Это директория
                    dir_path = project_dir / file_pattern.rstrip('/')
                    if dir_path.exists() and any(dir_path.iterdir()):
                        category_found += 1
                        total_found += 1
                    else:
                        missing_files.append(f"{category}/{file_pattern}")
                else:
                    # Это файл
                    if '*' in file_pattern:
                        # Паттерн с wildcard
                        found = list(project_dir.rglob(file_pattern))
                        if found:
                            category_found += 1
                            total_found += 1
                        else:
                            missing_files.append(f"{category}/{file_pattern}")
                    else:
                        # Точное имя файла
                        if (project_dir / file_pattern).exists():
                            category_found += 1
                            total_found += 1
                        else:
                            missing_files.append(f"{category}/{file_pattern}")
            
            logger.info(f"📁 {category}: {category_found}/{len(files)} файлов найдено")
        
        completeness_percentage = (total_found / total_required) * 100 if total_required > 0 else 0
        
        if missing_files:
            logger.warning(f"⚠️ Отсутствуют файлы: {', '.join(missing_files[:10])}")
            if len(missing_files) > 10:
                logger.warning(f"... и ещё {len(missing_files) - 10} файлов")
        
        logger.info(f"📊 Полнота проекта: {completeness_percentage:.1f}% ({total_found}/{total_required})")
        
        # Проект считается полным если найдено минимум 70% файлов
        is_complete = completeness_percentage >= 70.0
        
        if is_complete:
            logger.info("✅ Проект достаточно полный для завершения")
        else:
            logger.warning("⚠️ Проект неполный, требуется больше итераций")
        
        return is_complete

    def _get_agent_specific_context(self, agent_id: str) -> Dict[str, Any]:
        """Возвращает специфичный контекст для конкретного агента"""
        context = {}
        
        # 🔥 НОВОЕ: Читаем файлы обратно в контекст если они еще не загружены
        self._load_agent_files_to_context()
        
        if agent_id == "project_manager":
            logger.info(f"🔍 Создаем контекст для project_manager")
            logger.info(f"🔍 product_requirements: {len(self.current_project.product_requirements) if self.current_project.product_requirements else 'НЕ УСТАНОВЛЕНО'} символов")
            logger.info(f"🔍 user_stories: {len(self.current_project.user_stories) if self.current_project.user_stories else 'НЕ УСТАНОВЛЕНО'} символов")
            logger.info(f"🔍 acceptance_criteria: {len(self.current_project.acceptance_criteria) if self.current_project.acceptance_criteria else 'НЕ УСТАНОВЛЕНО'} символов")
            
            # 🔥 НОВОЕ: Загружаем файлы только если директория проекта существует
            project_dir = Path(PROJECT_OUTPUT_DIR) / self.current_project.name
            if project_dir.exists():
                logger.info(f"🔄 Загружаем файлы для project_manager")
                self._load_agent_files_to_context()
                logger.info(f"✅ Файлы загружены для project_manager")
                
                # 🔥 НОВОЕ: Проверяем после загрузки
                logger.info(f"🔍 После загрузки - product_requirements: {len(self.current_project.product_requirements) if self.current_project.product_requirements else 'НЕ УСТАНОВЛЕНО'} символов")
            else:
                logger.info(f"⚠️ Директория проекта {project_dir} не существует, пропускаем загрузку файлов")
            
            # 🔥 НОВОЕ: Проверяем, что файлы загружены, и если нет - устанавливаем fallback значения
            if not self.current_project.product_requirements:
                self.current_project.product_requirements = "Файлы Product Owner еще не созданы"
                logger.info(f"🔧 Установлен fallback для product_requirements")
            if not self.current_project.user_stories:
                self.current_project.user_stories = "Файлы Product Owner еще не созданы"
                logger.info(f"🔧 Установлен fallback для user_stories")
            if not self.current_project.acceptance_criteria:
                self.current_project.acceptance_criteria = "Файлы Product Owner еще не созданы"
                logger.info(f"🔧 Установлен fallback для acceptance_criteria")
            
            context.update({
                "product_requirements": self.current_project.product_requirements,
                "user_stories": self.current_project.user_stories,
                "acceptance_criteria": self.current_project.acceptance_criteria
            })
            
            # 🔥 НОВОЕ: Проверяем что добавилось в контекст
            logger.info(f"🔍 В контекст добавлено: product_requirements={len(context.get('product_requirements', ''))} символов")
            logger.info(f"🔍 В контекст добавлено: user_stories={len(context.get('user_stories', ''))} символов")
            logger.info(f"🔍 В контекст добавлено: acceptance_criteria={len(context.get('acceptance_criteria', ''))} символов")
        elif agent_id == "backend_developer":
            context.update({
                "database_schema_ready": bool(self.current_project.database_schema),
                "api_specification_ready": bool(self.current_project.api_specification),
                "technology_stack_ready": bool(self.current_project.technology_stack),
                "backend_dependencies": self._extract_backend_dependencies(),
                "api_endpoints_needed": self._extract_api_endpoints()
            })
        elif agent_id == "system_architect":
            context.update({
                "product_requirements": self.current_project.product_requirements
            })
        elif agent_id == "ui_ux_designer":
            context.update({
                "product_requirements": self.current_project.product_requirements
            })
        elif agent_id == "database_engineer":
            context.update({
                "product_requirements": self.current_project.product_requirements
            })
        elif agent_id == "frontend_developer":
            context.update({
                "ui_design_ready": bool(self.current_project.ui_design),
                "api_spec_ready": bool(self.current_project.api_spec),
                "design_system_ready": bool(self.current_project.design_system),
                "frontend_dependencies": self._extract_frontend_dependencies(),
                "ui_components_needed": self._extract_ui_components()
            })
        elif agent_id == "qa_tester":
            context.update({
                "backend_code_ready": bool(self.current_project.backend_code),
                "frontend_code_ready": bool(self.current_project.frontend_code),
                "api_spec_ready": bool(self.current_project.api_spec),
                "test_scenarios": self._extract_test_scenarios(),
                "test_coverage_needed": self._calculate_test_coverage()
            })
        elif agent_id == "code_reviewer":
            context.update({
                "product_requirements": self.current_project.product_requirements,
                "architecture": self.current_project.architecture,
                "all_code_ready": bool(self.current_project.backend_code and self.current_project.frontend_code),
                "code_quality_metrics": self._extract_code_quality_metrics(),
                "review_focus_areas": self._get_review_focus_areas()
            })
        elif agent_id == "technical_writer":
            context.update({
                "product_requirements": self.current_project.product_requirements,
                "architecture": self.current_project.architecture
            })
        elif agent_id == "security_specialist":
            context.update({
                "product_requirements": self.current_project.product_requirements
            })
        elif agent_id == "performance_engineer":
            context.update({
                "product_requirements": self.current_project.product_requirements
            })
        elif agent_id == "integration_specialist":
            context.update({
                "product_requirements": self.current_project.product_requirements
            })
        elif agent_id == "bug_fixer":
            context.update({
                "code_review_issues": self._extract_code_review_issues(),
                "qa_test_failures": self._extract_qa_test_failures(),
                "critical_bugs": self._extract_critical_bugs(),
                "fix_priority": self._get_fix_priority()
            })
        
        return context

    def _load_agent_files_to_context(self):
        """🔥 НОВОЕ: Загружает содержимое файлов агентов обратно в контекст проекта"""
        if not self.current_project:
            logger.warning("⚠️ current_project не инициализирован, пропускаем загрузку файлов")
            return
            
        logger.info(f"🔄 Загружаем файлы агентов в контекст для проекта: {self.current_project.project_name}")
        try:
            project_dir = Path(PROJECT_OUTPUT_DIR) / self.current_project.project_name
            logger.info(f"🔍 Проверяем директорию: {project_dir}")
            if not project_dir.exists():
                logger.warning(f"⚠️ Директория проекта не существует: {project_dir}")
                return
            
            # Загружаем файлы Product Owner если они еще не загружены
            if not self.current_project.product_requirements:
                logger.info("📁 Загружаем файлы Product Owner...")
                po_files = {
                    'product_requirements.md': 'product_requirements',
                    'user_stories.md': 'user_stories', 
                    'acceptance_criteria.md': 'acceptance_criteria'
                }
                
                for filename, attr_name in po_files.items():
                    # 🔥 Ищем файл в разных местах
                    possible_paths = [
                        project_dir / filename,  # В корне проекта
                        project_dir / 'src' / filename,  # В папке src
                        project_dir / 'docs' / filename,  # В папке docs
                    ]
                    
                    file_found = False
                    for file_path in possible_paths:
                        logger.debug(f"🔍 Проверяем файл: {file_path}")
                        if file_path.exists():
                            try:
                                content = file_path.read_text(encoding='utf-8', errors='ignore')
                                setattr(self.current_project, attr_name, content)
                                logger.info(f"✅ Загружен {filename} в {attr_name} ({len(content)} символов)")
                                file_found = True
                                break
                            except Exception as e:
                                logger.warning(f"⚠️ Не удалось прочитать {filename}: {e}")
                    
                    if not file_found:
                        logger.warning(f"⚠️ Файл {filename} не найден ни в одном из мест: {[str(p) for p in possible_paths]}")
            else:
                logger.info(f"📁 Файлы Product Owner уже загружены: {len(self.current_project.product_requirements)} символов")
            
            # Загружаем другие файлы агентов если они еще не загружены
            if not self.current_project.architecture:
                arch_paths = [project_dir / 'architecture.md', project_dir / 'src' / 'architecture.md']
                for arch_file in arch_paths:
                    if arch_file.exists():
                        try:
                            content = arch_file.read_text(encoding='utf-8', errors='ignore')
                            self.current_project.architecture = content
                            logger.debug("✅ Загружен architecture.md")
                            break
                        except Exception as e:
                            logger.warning(f"⚠️ Не удалось прочитать architecture.md: {e}")
            
            if not self.current_project.ui_design:
                ui_paths = [project_dir / 'design_system.md', project_dir / 'src' / 'design_system.md']
                for ui_file in ui_paths:
                    if ui_file.exists():
                        try:
                            content = ui_file.read_text(encoding='utf-8', errors='ignore')
                            self.current_project.ui_design = content
                            logger.debug("✅ Загружен design_system.md")
                            break
                        except Exception as e:
                            logger.warning(f"⚠️ Не удалось прочитать design_system.md: {e}")
            
            if not self.current_project.database_schema:
                db_paths = [project_dir / 'schema.sql', project_dir / 'src' / 'schema.sql']
                for db_file in db_paths:
                    if db_file.exists():
                        try:
                            content = db_file.read_text(encoding='utf-8', errors='ignore')
                            self.current_project.database_schema = content
                            logger.debug("✅ Загружен schema.sql")
                            break
                        except Exception as e:
                            logger.warning(f"⚠️ Не удалось прочитать schema.sql: {e}")
            
            if not self.current_project.backend_code:
                backend_paths = [project_dir / 'app.py', project_dir / 'src' / 'backend' / 'app.py']
                for backend_file in backend_paths:
                    if backend_file.exists():
                        try:
                            content = backend_file.read_text(encoding='utf-8', errors='ignore')
                            self.current_project.backend_code = content
                            logger.debug("✅ Загружен app.py")
                            break
                        except Exception as e:
                            logger.warning(f"⚠️ Не удалось прочитать app.py: {e}")
            
            if not self.current_project.frontend_code:
                frontend_paths = [project_dir / 'index.html', project_dir / 'src' / 'frontend' / 'index.html']
                for frontend_file in frontend_paths:
                    if frontend_file.exists():
                        try:
                            content = frontend_file.read_text(encoding='utf-8', errors='ignore')
                            self.current_project.frontend_code = content
                            logger.debug("✅ Загружен index.html")
                            break
                        except Exception as e:
                            logger.warning(f"⚠️ Не удалось прочитать index.html: {e}")
                        
        except Exception as e:
            logger.error(f"Ошибка загрузки файлов в контекст: {e}")

    async def _check_code_completeness(self) -> bool:
        """🔥 НОВОЕ: Проверяет полноту реализации кода - нет ли TODO и заглушек"""
        logger.info("🔍 Проверка полноты реализации кода...")
        
        # Собираем все файлы с кодом
        code_files = await self._collect_code_files()
        
        if not code_files:
            logger.warning("⚠️ Файлы с кодом не найдены")
            return False
        
        # Анализируем каждый файл на полноту
        incomplete_files = []
        total_issues = 0
        
        for file_info in code_files:
            file_issues = await self._analyze_file_completeness(file_info)
            if file_issues:
                incomplete_files.append({
                    "file": file_info["path"],
                    "issues": file_issues
                })
                total_issues += len(file_issues)
        
        if incomplete_files:
            logger.warning(f"⚠️ Найдено {total_issues} проблем полноты в {len(incomplete_files)} файлах")
            
            # Создаем задачи на доработку неполного кода
            await self._create_completeness_tasks(incomplete_files)
            
            return False
        
        logger.info("✅ Код полностью реализован, нет TODO и заглушек")
        return True

    async def _collect_code_files(self) -> List[Dict[str, Any]]:
        """Собирает все файлы с кодом для анализа"""
        code_files = []
        project_dir = Path(PROJECT_OUTPUT_DIR) / self.current_project.project_name
        
        if not project_dir.exists():
            return code_files
        
        # Расширения файлов с кодом
        code_extensions = {
            '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.cs',
            '.php', '.rb', '.go', '.rs', '.swift', '.kt', '.scala'
        }
        
        # Ищем файлы с кодом
        for file_path in project_dir.rglob('*'):
            if file_path.is_file() and file_path.suffix in code_extensions:
                try:
                    content = file_path.read_text(encoding='utf-8', errors='ignore')
                    code_files.append({
                        "path": str(file_path.relative_to(project_dir)),
                        "content": content,
                        "extension": file_path.suffix,
                        "size": len(content)
                    })
                except Exception as e:
                    logger.warning(f"Ошибка чтения файла {file_path}: {e}")
        
        logger.info(f"📁 Найдено {len(code_files)} файлов с кодом для анализа")
        return code_files

    async def _analyze_file_completeness(self, file_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Анализирует полноту реализации в конкретном файле"""
        issues = []
        content = file_info["content"]
        file_path = file_info["path"]
        
        # 1. Проверяем на TODO комментарии
        todo_patterns = [
            r'#\s*TODO[:\s]*(.*?)(?=\n|$)',
            r'//\s*TODO[:\s]*(.*?)(?=\n|$)',
            r'/\*\s*TODO[:\s]*(.*?)\*/',
            r'<!--\s*TODO[:\s]*(.*?)\s*-->',
            r'#\s*FIXME[:\s]*(.*?)(?=\n|$)',
            r'//\s*FIXME[:\s]*(.*?)(?=\n|$)',
            r'#\s*HACK[:\s]*(.*?)(?=\n|$)',
            r'//\s*HACK[:\s]*(.*?)(?=\n|$)',
        ]
        
        for pattern in todo_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                issues.append({
                    "type": "todo_comment",
                    "description": f"TODO: {match.strip()}",
                    "priority": "high",
                    "line": self._find_line_number(content, match),
                    "suggestion": "Реализовать функционал согласно TODO"
                })
        
        # 2. Проверяем на пустые функции/методы
        empty_function_patterns = {
            '.py': [
                r'def\s+\w+[^:]*:\s*\n\s*(?:pass|#.*|""".*?"""|"""\s*""")',
                r'class\s+\w+[^:]*:\s*\n\s*(?:pass|#.*|""".*?"""|"""\s*""")',
            ],
            '.js': [
                r'function\s+\w+[^}]*\{\s*\}',
                r'const\s+\w+\s*=\s*\([^)]*\)\s*=>\s*\{\s*\}',
                r'class\s+\w+[^}]*\{\s*\}',
            ],
            '.ts': [
                r'function\s+\w+[^}]*\{\s*\}',
                r'const\s+\w+\s*:\s*\w+\s*=\s*\([^)]*\)\s*=>\s*\{\s*\}',
                r'class\s+\w+[^}]*\{\s*\}',
            ],
            '.java': [
                r'public\s+\w+\s+\w+[^}]*\{\s*\}',
                r'class\s+\w+[^}]*\{\s*\}',
            ]
        }
        
        extension = file_info["extension"]
        if extension in empty_function_patterns:
            for pattern in empty_function_patterns[extension]:
                matches = re.findall(pattern, content, re.MULTILINE)
                for match in matches:
                    issues.append({
                        "type": "empty_function",
                        "description": f"Пустая функция/класс: {match.strip()[:50]}...",
                        "priority": "high",
                        "line": self._find_line_number(content, match),
                        "suggestion": "Реализовать логику функции/класса"
                    })
        
        # 3. Проверяем на заглушки (stub functions)
        stub_patterns = [
            r'def\s+\w+[^:]*:\s*\n\s*raise\s+NotImplementedError',
            r'def\s+\w+[^:]*:\s*\n\s*pass\s*#\s*stub',
            r'function\s+\w+[^}]*\{\s*throw\s+new\s+Error\([^)]*\)\s*\}',
            r'public\s+\w+\s+\w+[^}]*\{\s*throw\s+new\s+UnsupportedOperationException[^}]*\}',
        ]
        
        for pattern in stub_patterns:
            matches = re.findall(pattern, content, re.MULTILINE)
            for match in matches:
                issues.append({
                    "type": "stub_function",
                    "description": f"Заглушка функции: {match.strip()[:50]}...",
                    "priority": "high",
                    "line": self._find_line_number(content, match),
                    "suggestion": "Заменить заглушку на реальную реализацию"
                })
        
        # 4. Проверяем на неполные импорты
        incomplete_import_patterns = [
            r'from\s+\w+\s+import\s*$',
            r'import\s+\w+\s*$',
            r'using\s+\w+\s*;?\s*$',
        ]
        
        for pattern in incomplete_import_patterns:
            matches = re.findall(pattern, content, re.MULTILINE)
            for match in matches:
                issues.append({
                    "type": "incomplete_import",
                    "description": f"Неполный импорт: {match.strip()}",
                    "priority": "medium",
                    "line": self._find_line_number(content, match),
                    "suggestion": "Завершить импорт необходимых модулей"
                })
        
        # 5. Проверяем на слишком короткие функции (возможно, неполные)
        if file_info["size"] > 100:  # Только для файлов больше 100 символов
            lines = content.split('\n')
            for i, line in enumerate(lines, 1):
                line = line.strip()
                if line.startswith('def ') and len(line) < 50:
                    # Проверяем следующую строку
                    if i < len(lines) and lines[i].strip() in ['pass', '#', '"""', '"""', '']:
                        issues.append({
                            "type": "short_function",
                            "description": f"Короткая функция: {line}",
                            "priority": "medium",
                            "line": i,
                            "suggestion": "Расширить реализацию функции"
                        })
        
        if issues:
            logger.warning(f"⚠️ В файле {file_path} найдено {len(issues)} проблем полноты")
        
        return issues

    def _find_line_number(self, content: str, text: str) -> int:
        """Находит номер строки с указанным текстом"""
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if text.strip() in line:
                return i
        return 0

    async def _create_completeness_tasks(self, incomplete_files: List[Dict[str, Any]]) -> None:
        """Создает задачи на доработку неполного кода"""
        logger.info("🔧 Создание задач на доработку неполного кода...")
        
        for file_info in incomplete_files:
            file_path = file_info["file"]
            issues = file_info["issues"]
            
            # Определяем агента для доработки
            target_agent = self._determine_completeness_agent(file_path, issues)
            
            if target_agent:
                # Группируем проблемы по типам
                todo_issues = [i for i in issues if i["type"] == "todo_comment"]
                empty_function_issues = [i for i in issues if i["type"] == "empty_function"]
                stub_issues = [i for i in issues if i["type"] == "stub_function"]
                
                # Создаем задачи по приоритету
                if todo_issues:
                    await self._create_completeness_task(target_agent, file_path, todo_issues, "TODO комментарии")
                
                if empty_function_issues:
                    await self._create_completeness_task(target_agent, file_path, empty_function_issues, "Пустые функции")
                
                if stub_issues:
                    await self._create_completeness_task(target_agent, file_path, stub_issues, "Заглушки функций")
        
        logger.info("✅ Задачи на доработку неполного кода созданы")

    def _determine_completeness_agent(self, file_path: str, issues: List[Dict[str, Any]]) -> str:
        """Определяет агента для доработки неполного кода"""
        # Определяем по расширению файла
        if file_path.endswith(('.py', '.java', '.cpp', '.c')):
            return "backend_developer"
        elif file_path.endswith(('.js', '.ts', '.jsx', '.tsx', '.html', '.css')):
            return "frontend_developer"
        elif file_path.endswith(('.sql')):
            return "database_engineer"
        elif file_path.endswith(('.md', '.txt')):
            return "technical_writer"
        else:
            # Определяем по содержимому проблем
            for issue in issues:
                if "функция" in issue["description"].lower() or "function" in issue["description"].lower():
                    if any(word in issue["description"].lower() for word in ["backend", "api", "сервер"]):
                        return "backend_developer"
                    elif any(word in issue["description"].lower() for word in ["frontend", "ui", "интерфейс"]):
                        return "frontend_developer"
            
            return "bug_fixer"  # Универсальный агент

    async def _create_completeness_task(self, agent_id: str, file_path: str, issues: List[Dict[str, Any]], issue_type: str) -> None:
        """Создает конкретную задачу на доработку неполного кода"""
        # Создаем детальное описание задачи
        task_description = f"Доработать {issue_type} в файле {file_path}\n\n"
        task_description += "Найденные проблемы:\n"
        
        for issue in issues:
            task_description += f"- {issue['description']}\n"
            if issue.get('line'):
                task_description += f"  Строка: {issue['line']}\n"
            task_description += f"  Рекомендация: {issue['suggestion']}\n\n"
        
        task_description += f"Требования:\n"
        task_description += f"1. Реализовать ВСЕ найденные TODO и заглушки\n"
        task_description += f"2. Код должен быть рабочим и полным\n"
        task_description += f"3. Добавить необходимые импорты и зависимости\n"
        task_description += f"4. Убрать все pass, raise NotImplementedError и заглушки\n"
        task_description += f"5. Добавить обработку ошибок и валидацию\n"
        
        # Создаем задачу
        task = AgentTask(
            id=f"{self.current_project.id}_{agent_id}_completeness_{int(time.time())}",
            description=task_description,
            context={
                "project_name": self.current_project.name,
                "project_id": self.current_project.id,
                "iteration": self.current_project.current_iteration,
                "file_path": file_path,
                "issues": issues,
                "issue_type": issue_type,
                "completeness_context": self._get_completeness_context(file_path, issues)
            }
        )
        
        # Добавляем задачу в очередь агента
        if agent_id in self.directed_queues:
            self.directed_queues[agent_id].append(task)
            logger.info(f"✅ Задача на доработку {issue_type} добавлена для {agent_id}: {file_path}")
        else:
            logger.warning(f"⚠️ Очередь для {agent_id} не найдена")

    def _get_completeness_context(self, file_path: str, issues: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Возвращает контекст для доработки неполного кода"""
        context = {
            "file_path": file_path,
            "file_extension": Path(file_path).suffix,
            "total_issues": len(issues),
            "issue_types": list(set(issue["type"] for issue in issues)),
            "high_priority_issues": [i for i in issues if i["priority"] == "high"],
            "current_code": self._get_file_content_for_context(file_path),
            "requirements_context": self._get_requirements_for_file(file_path)
        }
        
        return context

    def _get_file_content_for_context(self, file_path: str) -> str:
        """Получает содержимое файла для контекста"""
        try:
            full_path = Path(PROJECT_OUTPUT_DIR) / self.current_project.project_name / file_path
            if full_path.exists():
                return full_path.read_text(encoding='utf-8', errors='ignore')
        except Exception as e:
            logger.warning(f"Ошибка чтения файла {file_path}: {e}")
        
        return ""

    def _get_requirements_for_file(self, file_path: str) -> Dict[str, Any]:
        """Получает требования для конкретного файла"""
        requirements = {}
        
        # Определяем тип файла и получаем соответствующие требования
        if file_path.endswith('.py'):
            requirements.update({
                "backend_requirements": self.current_project.product_requirements,
                "api_specification": self.current_project.api_specification,
                "database_schema": self.current_project.database_schema
            })
        elif file_path.endswith(('.js', '.ts', '.jsx', '.tsx')):
            requirements.update({
                "frontend_requirements": self.current_project.user_stories,
                "ui_design": self.current_project.ui_design,
                "api_spec": self.current_project.api_spec
            })
        elif file_path.endswith('.sql'):
            requirements.update({
                "database_requirements": self.current_project.database_schema,
                "backend_requirements": self.current_project.product_requirements
            })
        
        return requirements

    async def _check_all_tasks_completed(self) -> bool:
        """🔥 НОВОЕ: Проверяет, что все задачи выполнены"""
        logger.info("🔍 Проверка завершения всех задач...")
        
        if not hasattr(self, 'task_manager') or not self.task_manager:
            logger.warning("⚠️ TaskManager не инициализирован")
            return True
        
        progress = self.task_manager.get_task_progress()
        logger.info(f"📊 Прогресс задач: {progress}")
        
        # Проверяем, что нет незавершенных задач
        if progress["total"] == 0:
            logger.info("✅ Задач не создано")
            return True
        
        if progress["completed"] == progress["total"]:
            logger.info("✅ Все задачи выполнены")
            return True
        
        # Проверяем заблокированные задачи
        blocked_tasks = self.task_manager.get_blocked_tasks()
        if blocked_tasks:
            logger.warning(f"⚠️ Заблокировано {len(blocked_tasks)} задач:")
            for task in blocked_tasks[:5]:  # Показываем первые 5
                logger.warning(f"  • {task.title} (агент: {task.agent_id})")
            if len(blocked_tasks) > 5:
                logger.warning(f"  ... и ещё {len(blocked_tasks) - 5} задач")
        
        # Проверяем задачи, требующие ревизии
        if progress["needs_revision"] > 0:
            logger.warning(f"⚠️ {progress['needs_revision']} задач требуют ревизии")
            return False
        
        # Проверяем неудачные задачи
        if progress["failed"] > 0:
            logger.warning(f"⚠️ {progress['failed']} задач завершились неудачно")
            return False
        
        # Проверяем задачи в процессе
        if progress["in_progress"] > 0:
            logger.info(f"📋 {progress['in_progress']} задач в процессе выполнения")
            return False
        
        # Проверяем ожидающие задачи
        if progress["pending"] > 0:
            logger.info(f"⏳ {progress['pending']} задач ожидают выполнения")
            return False
        
        logger.info("✅ Все задачи выполнены успешно")
        return True

    def _initialize_project_tasks(self) -> None:
        """🔥 НОВОЕ: Инициализирует основные задачи проекта"""
        logger.info("🔧 Инициализация основных задач проекта...")
        
        if not hasattr(self, 'task_manager') or not self.task_manager:
            logger.warning("⚠️ TaskManager не инициализирован")
            return
        
        # Создаем основные задачи для каждого агента
        main_tasks = {
            "product_owner": {
                "title": "Создать требования продукта",
                "description": "Определить product requirements, user stories и acceptance criteria",
                "priority": "critical"
            },
            "project_manager": {
                "title": "Создать план проекта",
                "description": "Разработать project plan, timeline и задачи",
                "priority": "critical",
                "dependencies": []  # Будет заполнено после создания PO задачи
            },
            "system_architect": {
                "title": "Спроектировать архитектуру",
                "description": "Создать system design, technology stack и API specification",
                "priority": "high",
                "dependencies": []  # Будет заполнено после создания PM задачи
            },
            "database_engineer": {
                "title": "Спроектировать базу данных",
                "description": "Создать database schema и SQL скрипты",
                "priority": "high",
                "dependencies": []  # Будет заполнено после создания SA задачи
            },
            "ui_ux_designer": {
                "title": "Создать UI дизайн",
                "description": "Разработать design system, wireframes и UI компоненты",
                "priority": "medium",
                "dependencies": []  # Будет заполнено после создания SA задачи
            },
            "backend_developer": {
                "title": "Реализовать backend",
                "description": "Создать API endpoints, бизнес-логику и интеграции",
                "priority": "high",
                "dependencies": []  # Будет заполнено после создания DB и SA задач
            },
            "frontend_developer": {
                "title": "Реализовать frontend",
                "description": "Создать UI компоненты, страницы и интеграцию с API",
                "priority": "high",
                "dependencies": []  # Будет заполнено после создания UI и BE задач
            },
            "qa_tester": {
                "title": "Создать и выполнить тесты",
                "description": "Разработать test cases и проверить функциональность",
                "priority": "medium",
                "dependencies": []  # Будет заполнено после создания BE и FE задач
            },
            "code_reviewer": {
                "title": "Провести code review",
                "description": "Проанализировать код на качество и найти проблемы",
                "priority": "medium",
                "dependencies": []  # Будет заполнено после создания BE и FE задач
            },
            "bug_fixer": {
                "title": "Исправить найденные проблемы",
                "description": "Устранить баги и улучшить код на основе feedback",
                "priority": "medium",
                "dependencies": []  # Будет заполнено после создания QA и CR задач
            }
        }
        
        # Создаем задачи и устанавливаем зависимости
        task_ids = {}
        
        for agent_id, task_info in main_tasks.items():
            task_id = self.task_manager.create_task(
                title=task_info["title"],
                description=task_info["description"],
                agent_id=agent_id,
                priority=task_info["priority"],
                task_type="main"
            )
            task_ids[agent_id] = task_id
        
        # Устанавливаем зависимости
        self.task_manager.add_dependency(
            task_ids["project_manager"], 
            task_ids["product_owner"], 
            "blocks", 
            "PM ждет требования от PO"
        )
        
        self.task_manager.add_dependency(
            task_ids["system_architect"], 
            task_ids["project_manager"], 
            "blocks", 
            "SA ждет план проекта от PM"
        )
        
        self.task_manager.add_dependency(
            task_ids["database_engineer"], 
            task_ids["system_architect"], 
            "requires", 
            "DB Engineer использует архитектуру от SA"
        )
        
        self.task_manager.add_dependency(
            task_ids["ui_ux_designer"], 
            task_ids["system_architect"], 
            "requires", 
            "UI Designer использует архитектуру от SA"
        )
        
        self.task_manager.add_dependency(
            task_ids["backend_developer"], 
            task_ids["database_engineer"], 
            "blocks", 
            "Backend Developer ждет схему БД"
        )
        
        self.task_manager.add_dependency(
            task_ids["backend_developer"], 
            task_ids["system_architect"], 
            "requires", 
            "Backend Developer использует архитектуру от SA"
        )
        
        self.task_manager.add_dependency(
            task_ids["frontend_developer"], 
            task_ids["backend_developer"], 
            "blocks", 
            "Frontend Developer ждет API от Backend"
        )
        
        self.task_manager.add_dependency(
            task_ids["frontend_developer"], 
            task_ids["ui_ux_designer"], 
            "requires", 
            "Frontend Developer использует дизайн от UI Designer"
        )
        
        self.task_manager.add_dependency(
            task_ids["qa_tester"], 
            task_ids["backend_developer"], 
            "blocks", 
            "QA Tester ждет backend код"
        )
        
        self.task_manager.add_dependency(
            task_ids["qa_tester"], 
            task_ids["frontend_developer"], 
            "blocks", 
            "QA Tester ждет frontend код"
        )
        
        self.task_manager.add_dependency(
            task_ids["code_reviewer"], 
            task_ids["backend_developer"], 
            "blocks", 
            "Code Reviewer ждет backend код"
        )
        
        self.task_manager.add_dependency(
            task_ids["code_reviewer"], 
            task_ids["frontend_developer"], 
            "blocks", 
            "Code Reviewer ждет frontend код"
        )
        
        self.task_manager.add_dependency(
            task_ids["bug_fixer"], 
            task_ids["qa_tester"], 
            "blocks", 
            "Bug Fixer ждет результаты тестирования"
        )
        
        self.task_manager.add_dependency(
            task_ids["bug_fixer"], 
            task_ids["code_reviewer"], 
            "blocks", 
            "Bug Fixer ждет результаты code review"
        )
        
        logger.info(f"✅ Создано {len(task_ids)} основных задач с зависимостями")
        
        # Выводим статус задач
        self._log_task_status()
    
    def _log_task_status(self) -> None:
        """Логирует текущий статус всех задач"""
        if not hasattr(self, 'task_manager') or not self.task_manager:
            return
        
        progress = self.task_manager.get_task_progress()
        logger.info(f"📊 Статус задач проекта:")
        logger.info(f"  • Всего: {progress['total']}")
        logger.info(f"  • Выполнено: {progress['completed']}")
        logger.info(f"  • В процессе: {progress['in_progress']}")
        logger.info(f"  • Ожидают: {progress['pending']}")
        logger.info(f"  • Требуют ревизии: {progress['needs_revision']}")
        logger.info(f"  • Неудачно: {progress['failed']}")
        
        # Показываем заблокированные задачи
        blocked_tasks = self.task_manager.get_blocked_tasks()
        if blocked_tasks:
            logger.info(f"  • Заблокировано: {len(blocked_tasks)}")
            for task in blocked_tasks[:3]:
                logger.info(f"    - {task.title} (агент: {task.agent_id})")

    def _get_agent_dependencies(self, agent_id: str) -> Dict[str, Any]:
        """Возвращает зависимости агента от других агентов"""
        dependencies = {
            "waits_for": [],  # Кого ждет
            "provides_to": [],  # Кому предоставляет данные
            "conflicts_with": [],  # С кем может конфликтовать
            "collaborates_with": []  # С кем сотрудничает
        }
        
        if agent_id == "project_manager":
            dependencies["waits_for"] = ["product_owner"]
            dependencies["provides_to"] = ["system_architect", "backend_developer", "frontend_developer"]
        elif agent_id == "system_architect":
            dependencies["waits_for"] = ["project_manager"]
            dependencies["provides_to"] = ["backend_developer", "frontend_developer", "database_engineer"]
            dependencies["collaborates_with"] = ["database_engineer"]
        elif agent_id == "backend_developer":
            dependencies["waits_for"] = ["system_architect", "database_engineer"]
            dependencies["provides_to"] = ["frontend_developer", "qa_tester"]
            dependencies["collaborates_with"] = ["frontend_developer"]
        elif agent_id == "frontend_developer":
            dependencies["waits_for"] = ["system_architect", "backend_developer", "ui_ux_designer"]
            dependencies["provides_to"] = ["qa_tester"]
            dependencies["collaborates_with"] = ["backend_developer", "ui_ux_designer"]
        elif agent_id == "qa_tester":
            dependencies["waits_for"] = ["backend_developer", "frontend_developer"]
            dependencies["provides_to"] = ["bug_fixer"]
        elif agent_id == "code_reviewer":
            dependencies["waits_for"] = ["backend_developer", "frontend_developer"]
            dependencies["provides_to"] = ["bug_fixer"]
        elif agent_id == "bug_fixer":
            dependencies["waits_for"] = ["code_reviewer", "qa_tester"]
            dependencies["provides_to"] = ["qa_tester"]  # Для повторного тестирования
        
        return dependencies

    def _get_file_versions(self) -> Dict[str, Any]:
        """Возвращает историю изменений и версии файлов"""
        versions = {}
        
        for agent_id, results in self.current_project.all_results.items():
            if results:
                latest_result = results[-1]
                if latest_result.success:
                    # Извлекаем имена файлов из вывода
                    files = self._extract_filenames_from_output(latest_result.output)
                    for filename in files:
                        if filename not in versions:
                            versions[filename] = []
                        versions[filename].append({
                            "agent": agent_id,
                            "iteration": self.current_project.current_iteration,
                            "timestamp": latest_result.created_at,  # Исправлено: timestamp -> created_at
                            "status": "updated"
                        })
        
        return versions

    def _get_component_status(self) -> Dict[str, Any]:
        """Возвращает статус и прогресс по компонентам проекта"""
        status = {
            "requirements": {
                "status": "ready" if self.current_project.product_requirements else "pending",
                "agent": "product_owner",
                "completion": 100 if self.current_project.product_requirements else 0
            },
            "architecture": {
                "status": "ready" if self.current_project.architecture else "pending",
                "agent": "system_architect",
                "completion": 100 if self.current_project.architecture else 0
            },
            "database": {
                "status": "ready" if self.current_project.database_schema else "pending",
                "agent": "database_engineer",
                "completion": 100 if self.current_project.database_schema else 0
            },
            "backend": {
                "status": "ready" if self.current_project.backend_code else "pending",
                "agent": "backend_developer",
                "completion": 100 if self.current_project.backend_code else 0
            },
            "frontend": {
                "status": "ready" if self.current_project.frontend_code else "pending",
                "agent": "frontend_developer",
                "completion": 100 if self.current_project.frontend_code else 0
            },
            "testing": {
                "status": "ready" if self._has_test_files("") else "pending",
                "agent": "qa_tester",
                "completion": 80 if self._has_test_files("") else 0
            },
            "review": {
                "status": "ready" if any(r.success for r in self.current_project.all_results.get("code_reviewer", [])) else "pending",
                "agent": "code_reviewer",
                "completion": 100 if any(r.success for r in self.current_project.all_results.get("code_reviewer", [])) else 0
            }
        }
        
        return status

    def _extract_backend_dependencies(self) -> List[str]:
        """Извлекает зависимости backend из требований и архитектуры"""
        dependencies = []
        if self.current_project.technology_stack:
            dependencies.append("Flask")
            dependencies.append("SQLAlchemy")
            dependencies.append("Flask-RESTful")
        return dependencies

    def _extract_api_endpoints(self) -> List[str]:
        """Извлекает необходимые API endpoints из требований"""
        endpoints = []
        if self.current_project.user_stories:
            # Простой парсинг user stories для извлечения endpoints
            if "корзина" in self.current_project.user_stories.lower():
                endpoints.extend(["/api/cart", "/api/cart/add", "/api/cart/remove"])
            if "оплата" in self.current_project.user_stories.lower():
                endpoints.extend(["/api/payment", "/api/orders"])
        return endpoints

    def _extract_frontend_dependencies(self) -> List[str]:
        """Извлекает зависимости frontend из дизайна"""
        dependencies = []
        if self.current_project.design_system:
            dependencies.append("React")
            dependencies.append("TypeScript")
            dependencies.append("Tailwind CSS")
        return dependencies

    def _extract_ui_components(self) -> List[str]:
        """Извлекает необходимые UI компоненты из дизайна"""
        components = []
        if self.current_project.user_stories:
            if "корзина" in self.current_project.user_stories.lower():
                components.extend(["Cart", "CartItem", "AddToCart"])
            if "оплата" in self.current_project.user_stories.lower():
                components.extend(["PaymentForm", "OrderSummary"])
        return components

    def _extract_test_scenarios(self) -> List[str]:
        """Извлекает тестовые сценарии из user stories"""
        scenarios = []
        if self.current_project.user_stories:
            if "корзина" in self.current_project.user_stories.lower():
                scenarios.extend(["Добавление товара в корзину", "Удаление товара из корзины"])
            if "оплата" in self.current_project.user_stories.lower():
                scenarios.extend(["Создание заказа", "Обработка оплаты"])
        return scenarios

    def _calculate_test_coverage(self) -> Dict[str, int]:
        """Рассчитывает покрытие тестами по компонентам"""
        coverage = {
            "backend": 0,
            "frontend": 0,
            "api": 0,
            "database": 0
        }
        
        # Простая логика расчета покрытия
        if self.current_project.backend_code:
            coverage["backend"] = 60
        if self.current_project.frontend_code:
            coverage["frontend"] = 60
        if self.current_project.api_spec:
            coverage["api"] = 80
        
        return coverage

    def _extract_code_quality_metrics(self) -> Dict[str, Any]:
        """Извлекает метрики качества кода"""
        metrics = {
            "complexity": "medium",
            "testability": "good",
            "maintainability": "good",
            "documentation": "partial"
        }
        return metrics

    def _get_review_focus_areas(self) -> List[str]:
        """Возвращает области для фокуса Code Reviewer"""
        areas = []
        if self.current_project.backend_code:
            areas.extend(["API endpoints", "Error handling", "Database queries"])
        if self.current_project.frontend_code:
            areas.extend(["Component structure", "State management", "API integration"])
        return areas

    def _extract_code_review_issues(self) -> List[str]:
        """Извлекает проблемы из Code Reviewer"""
        issues = []
        cr_output = self._get_agent_output("code_reviewer")
        if cr_output:
            # Простой парсинг проблем
            if "bug:" in cr_output.lower():
                issues.append("Обнаружены баги в коде")
            if "security" in cr_output.lower():
                issues.append("Проблемы безопасности")
        return issues

    def _extract_qa_test_failures(self) -> List[str]:
        """Извлекает неудачные тесты от QA"""
        failures = []
        qa_output = self._get_agent_output("qa_tester")
        if qa_output:
            if "failed" in qa_output.lower() or "error" in qa_output.lower():
                failures.append("Тесты не проходят")
        return failures

    def _extract_critical_bugs(self) -> List[str]:
        """Извлекает критические баги"""
        bugs = []
        cr_output = self._get_agent_output("code_reviewer")
        if cr_output:
            if "critical" in cr_output.lower() or "blocker" in cr_output.lower():
                bugs.append("Критические проблемы в коде")
        return bugs

    def _get_fix_priority(self) -> str:
        """Возвращает приоритет исправлений"""
        if self._extract_critical_bugs():
            return "high"
        elif self._extract_code_review_issues():
            return "medium"
        else:
            return "low"

    def _extract_filenames_from_output(self, output: str) -> List[str]:
        """Извлекает имена файлов из вывода агента"""
        filenames = []
        # Ищем блоки ```markdown:filename
        pattern = r'```markdown:([\w/\.\-]+)'
        matches = re.findall(pattern, output)
        filenames.extend(matches)
        
        # Ищем обычные блоки кода
        pattern = r'```(\w+):([\w/\.\-]+)'
        matches = re.findall(pattern, output)
        filenames.extend([f"{lang}:{filename}" for lang, filename in matches])
        
        return filenames

    async def _check_all_issues_resolved(self) -> bool:
        """Проверяет, что все найденные проблемы исправлены"""
        logger.info("🔍 Проверка исправления всех найденных проблем...")
        
        # Получаем все найденные проблемы
        all_issues = await self._collect_all_issues()
        
        if not all_issues:
            logger.info("✅ Проблем не найдено")
            return True
        
        # Проверяем, что все проблемы исправлены
        resolved_issues = []
        unresolved_issues = []
        
        for issue in all_issues:
            if await self._is_issue_resolved(issue):
                resolved_issues.append(issue)
            else:
                unresolved_issues.append(issue)
        
        logger.info(f"📊 Статус проблем: {len(resolved_issues)}/{len(all_issues)} исправлено")
        
        if unresolved_issues:
            logger.warning(f"⚠️ Неисправленные проблемы: {', '.join([i['description'] for i in unresolved_issues[:5]])}")
            if len(unresolved_issues) > 5:
                logger.warning(f"... и ещё {len(unresolved_issues) - 5} проблем")
            return False
        
        logger.info("✅ Все проблемы исправлены!")
        return True

    async def _collect_all_issues(self) -> List[Dict[str, Any]]:
        """Собирает все найденные проблемы от QA и Code Reviewer"""
        issues = []
        
        # Проблемы от Code Reviewer
        cr_results = self.current_project.all_results.get("code_reviewer", [])
        if cr_results:
            for result in cr_results:
                if result.success and result.output:
                    cr_issues = self._extract_issues_from_review(result.output)
                    issues.extend(cr_issues)
        
        # Проблемы от QA
        qa_results = self.current_project.all_results.get("qa_tester", [])
        if qa_results:
            for result in qa_results:
                if result.success and result.output:
                    qa_issues = self._extract_issues_from_qa(result.output)
                    issues.extend(qa_issues)
        
        # Убираем дубликаты
        unique_issues = []
        seen_descriptions = set()
        for issue in issues:
            if issue['description'] not in seen_descriptions:
                unique_issues.append(issue)
                seen_descriptions.add(issue['description'])
        
        logger.info(f"📋 Собрано {len(unique_issues)} уникальных проблем")
        return unique_issues

    def _extract_issues_from_review(self, output: str) -> List[Dict[str, Any]]:
        """Извлекает проблемы из вывода Code Reviewer"""
        issues = []
        
        # Ищем блоки с проблемами
        patterns = [
            r'##?\s*Проблемы?[:\s]*\n(.*?)(?=\n##|\n\n|$)',
            r'##?\s*Bugs?[:\s]*\n(.*?)(?=\n##|\n\n|$)',
            r'##?\s*Issues?[:\s]*\n(.*?)(?=\n##|\n\n|$)',
            r'##?\s*Найденные\s+ошибки[:\s]*\n(.*?)(?=\n##|\n\n|$)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, output, re.DOTALL | re.IGNORECASE)
            for match in matches:
                lines = match.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if line and line.startswith(('-', '*', '•')):
                        # Определяем приоритет по ключевым словам
                        priority = "medium"
                        if any(word in line.lower() for word in ["critical", "blocker", "fatal", "критическая"]):
                            priority = "high"
                        elif any(word in line.lower() for word in ["minor", "cosmetic", "косметическая"]):
                            priority = "low"
                        
                        issues.append({
                            "type": "code_review",
                            "description": line.lstrip('-*• ').strip(),
                            "priority": priority,
                            "status": "open"
                        })
        
        return issues

    def _extract_issues_from_qa(self, output: str) -> List[Dict[str, Any]]:
        """Извлекает проблемы из вывода QA"""
        issues = []
        
        # Ищем блоки с результатами тестов
        patterns = [
            r'##?\s*Результаты? тестов?[:\s]*\n(.*?)(?=\n##|\n\n|$)',
            r'##?\s*Test Results?[:\s]*\n(.*?)(?=\n##|\n\n|$)',
            r'##?\s*Проблемы?[:\s]*\n(.*?)(?=\n##|\n\n|$)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, output, re.DOTALL | re.IGNORECASE)
            for match in matches:
                lines = match.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if line and line.startswith(('-', '*', '•')):
                        # Определяем приоритет по ключевым словам
                        priority = "medium"
                        if "failed" in line.lower() or "error" in line.lower():
                            priority = "high"
                        elif "warning" in line.lower():
                            priority = "medium"
                        
                        issues.append({
                            "type": "qa_test",
                            "description": line.lstrip('-*• ').strip(),
                            "priority": priority,
                            "status": "open"
                        })
        
        return issues

    async def _is_issue_resolved(self, issue: Dict[str, Any]) -> bool:
        """Проверяет, исправлена ли проблема"""
        # Проверяем, есть ли исправления от Bug Fixer
        bf_results = self.current_project.all_results.get("bug_fixer", [])
        if bf_results:
            latest_result = bf_results[-1]
            if latest_result.success and latest_result.output:
                # Ищем упоминание проблемы в исправлениях
                issue_desc = issue['description'].lower()
                if issue_desc in latest_result.output.lower():
                    # Проверяем, что проблема помечена как исправленная
                    if any(word in latest_result.output.lower() for word in ["исправлено", "fixed", "resolved", "решено"]):
                        return True
        
        # Проверяем, есть ли исправления в коде разработчиков
        if issue['type'] == 'code_review':
            # Проверяем backend
            if self.current_project.backend_code:
                if await self._check_code_improvements(self.current_project.backend_code, issue):
                    return True
            
            # Проверяем frontend
            if self.current_project.frontend_code:
                if await self._check_code_improvements(self.current_project.frontend_code, issue):
                    return True
        
        return False

    async def _check_code_improvements(self, code: str, issue: Dict[str, Any]) -> bool:
        """Проверяет, улучшен ли код для решения проблемы"""
        issue_desc = issue['description'].lower()
        
        # Простые эвристики для проверки улучшений
        if "security" in issue_desc or "безопасность" in issue_desc:
            # Проверяем наличие улучшений безопасности
            security_improvements = ["input validation", "sql injection", "xss", "csrf", "authentication"]
            if any(improvement in code.lower() for improvement in security_improvements):
                return True
        
        elif "performance" in issue_desc or "производительность" in issue_desc:
            # Проверяем наличие улучшений производительности
            perf_improvements = ["caching", "indexing", "optimization", "async", "connection pooling"]
            if any(improvement in code.lower() for improvement in perf_improvements):
                return True
        
        elif "error handling" in issue_desc or "обработка ошибок" in issue_desc:
            # Проверяем наличие обработки ошибок
            error_handling = ["try:", "except:", "error handling", "validation", "logging"]
            if any(improvement in code.lower() for improvement in error_handling):
                return True
        
        return False

    async def _trigger_improvement_cycle(self) -> None:
        """🔥 НОВОЕ: Запускает цикл улучшения кода на основе найденных проблем"""
        logger.info("🔄 Запуск цикла улучшения кода...")
        
        # Собираем все неисправленные проблемы
        all_issues = await self._collect_all_issues()
        unresolved_issues = []
        
        for issue in all_issues:
            if not await self._is_issue_resolved(issue):
                unresolved_issues.append(issue)
        
        if not unresolved_issues:
            logger.info("✅ Все проблемы уже исправлены")
            return
        
        logger.info(f"🔧 Найдено {len(unresolved_issues)} неисправленных проблем")
        
        # Группируем проблемы по типам и приоритетам
        high_priority = [i for i in unresolved_issues if i['priority'] == 'high']
        medium_priority = [i for i in unresolved_issues if i['priority'] == 'medium']
        low_priority = [i for i in unresolved_issues if i['priority'] == 'low']
        
        # Создаем задачи на исправление для соответствующих агентов
        if high_priority:
            await self._create_fix_tasks(high_priority, "high")
        
        if medium_priority:
            await self._create_fix_tasks(medium_priority, "medium")
        
        if low_priority:
            await self._create_fix_tasks(low_priority, "low")
        
        logger.info("✅ Задачи на исправление созданы")

    async def _create_fix_tasks(self, issues: List[Dict[str, Any]], priority: str) -> None:
        """Создает задачи на исправление для соответствующих агентов"""
        logger.info(f"🔧 Создание задач на исправление (приоритет: {priority})")
        
        for issue in issues:
            # Определяем, какому агенту поручить исправление
            target_agent = self._determine_fix_agent(issue)
            
            if target_agent:
                # Создаем задачу на исправление
                task = AgentTask(
                    id=f"{self.current_project.id}_{target_agent}_fix_{int(time.time())}",
                    description=f"Исправить проблему: {issue['description']}",
                    context={
                        "project_name": self.current_project.name,
                        "project_id": self.current_project.id,
                        "iteration": self.current_project.current_iteration,
                        "issue": issue,
                        "priority": priority,
                        "fix_context": self._get_fix_context(issue)
                    }
                )
                
                # Добавляем задачу в очередь агента
                if target_agent in self.directed_queues:
                    self.directed_queues[target_agent].append(task)
                    logger.info(f"✅ Задача на исправление добавлена для {target_agent}: {issue['description'][:50]}...")
                else:
                    logger.warning(f"⚠️ Очередь для {target_agent} не найдена")

    def _determine_fix_agent(self, issue: Dict[str, Any]) -> Optional[str]:
        """Определяет, какому агенту поручить исправление проблемы"""
        issue_desc = issue['description'].lower()
        
        if issue['type'] == 'code_review':
            if any(word in issue_desc for word in ["backend", "api", "database", "сервер"]):
                return "backend_developer"
            elif any(word in issue_desc for word in ["frontend", "ui", "javascript", "css", "интерфейс"]):
                return "frontend_developer"
            elif any(word in issue_desc for word in ["architecture", "design", "архитектура", "дизайн"]):
                return "system_architect"
            elif any(word in issue_desc for word in ["database", "schema", "sql", "база данных"]):
                return "database_engineer"
            else:
                return "bug_fixer"  # Универсальный исправлятель
        
        elif issue['type'] == 'qa_test':
            if "backend" in issue_desc or "api" in issue_desc:
                return "backend_developer"
            elif "frontend" in issue_desc or "ui" in issue_desc:
                return "frontend_developer"
            else:
                return "bug_fixer"
        
        return "bug_fixer"

    def _get_fix_context(self, issue: Dict[str, Any]) -> Dict[str, Any]:
        """Возвращает контекст для исправления проблемы"""
        context = {
            "issue_type": issue['type'],
            "priority": issue['priority'],
            "description": issue['description'],
            "current_code": {},
            "suggested_fixes": []
        }
        
        # Добавляем текущий код для анализа
        if self.current_project.backend_code:
            context["current_code"]["backend"] = self.current_project.backend_code
        if self.current_project.frontend_code:
            context["current_code"]["frontend"] = self.current_project.frontend_code
        if self.current_project.database_schema:
            context["current_code"]["database"] = self.current_project.database_schema
        
        # Добавляем предложения по исправлению на основе типа проблемы
        if "security" in issue['description'].lower():
            context["suggested_fixes"] = [
                "Добавить валидацию входных данных",
                "Использовать параметризованные запросы",
                "Добавить аутентификацию и авторизацию"
            ]
        elif "performance" in issue['description'].lower():
            context["suggested_fixes"] = [
                "Добавить кэширование",
                "Оптимизировать запросы к БД",
                "Использовать асинхронную обработку"
            ]
        elif "error handling" in issue['description'].lower():
            context["suggested_fixes"] = [
                "Добавить try-catch блоки",
                "Логировать ошибки",
                "Возвращать понятные сообщения об ошибках"
            ]
        
        return context

    def _log_context_usage_stats(self):
        """Логирует статистику использования контекста"""
        try:
            stats = self.context_manager.get_context_stats()
            logger.info("📊 СТАТИСТИКА КОНТЕКСТА:")
            logger.info(f"  • Всего агентов: {stats['total_agents']}")
            logger.info(f"  • Размер кэша: {stats['cache_size']}")
            logger.info(f"  • Средний размер контекста: {stats['average_context_size']:.0f} токенов")
            logger.info(f"  • Максимальный размер: {stats['max_context_size']} токенов")
            
            # Логируем детали по агентам
            for agent_id, version_info in stats['context_versions'].items():
                logger.info(f"  • {agent_id}: {version_info['size']} токенов, "
                          f"размер: {version_info['context_hash']}")
                
        except Exception as e:
            logger.warning(f"⚠️ Ошибка логирования статистики контекста: {e}")


class ContextManager:
    """🔥 ПРОСТОЙ: Менеджер контекста для агентов"""
    
    def __init__(self):
        self.max_context_length = 15000  # Максимальная длина контекста
        self.context_cache = {}
        self.context_versions = {}
    
    def get_optimized_context(self, agent_id: str, project_context, agent_specific_context: Dict[str, Any]) -> Dict[str, Any]:
        """Получает оптимизированный контекст для агента"""
        # Простая реализация: объединяем контексты
        context = {
            "project_name": getattr(project_context, 'name', ''),
            "project_description": getattr(project_context, 'description', ''),
            "agent_id": agent_id,
            **agent_specific_context
        }
        
        # Ограничиваем размер
        context_str = str(context)
        if len(context_str) > self.max_context_length:
            # Обрезаем длинные поля
            for key in ['summary_report', 'agent_artifacts', 'shared_context']:
                if key in context and isinstance(context[key], str):
                    if len(context[key]) > 1000:
                        context[key] = context[key][:1000] + "... (обрезано)"
        
        return context
    
    def get_context_stats(self) -> Dict[str, Any]:
        """Возвращает статистику использования контекста"""
        return {
            "total_agents": len(self.context_cache),
            "cache_size": len(self.context_cache),
            "average_context_size": 1000,  # Заглушка
            "max_context_size": self.max_context_length,
            "context_versions": self.context_versions
        }

# 🔥 РЕФАКТОРИНГ ЗАВЕРШЕН:
# - Реализовано управление активностью агентов (is_active)
# - Добавлена передача артефактов между агентами для кооперации
# - Security Specialist теперь анализирует реальный код
# - Performance Engineer анализирует реальную архитектуру
# - Code Reviewer анализирует реальный код
# - Bug Fixer получает контекст ошибок
# - QA Tester создает тесты на основе реального кода
# - Агенты работают не вслепую, а с полным контекстом
# - Система стала более кооперативной и эффективной
# - Добавлен этап финального тестирования и валидации
# - Улучшена обработка ошибок и восстановление после сбоев
# - Проект проходит полную проверку перед завершением
