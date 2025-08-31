"""
Конфигурация для мульти-агентной системы генерации проектов
"""
import os
from typing import Dict, List
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# DeepSeek API настройки
# ВАЖНО: ключ по умолчанию не задаем — только из окружения
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_BASE_URL = os.getenv('DEEPSEEK_BASE_URL', "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv('DEEPSEEK_MODEL', "deepseek-chat")  # Основная модель для кода
DEEPSEEK_REASONER_MODEL = os.getenv('DEEPSEEK_REASONER_MODEL', "deepseek-reasoner")  # Модель для логических рассуждений

# Доступные модели
AVAILABLE_MODELS = {
    "deepseek-chat": {
        "description": "Основная модель для генерации кода и текста",
        "max_output_tokens": 8000,
        "context_window": 32000
    },
    "deepseek-reasoner": {
        "description": "Модель для сложных логических задач и рассуждений",
        "max_output_tokens": 8000,
        "context_window": 64000
    }
}

# Настройки агентов
MAX_ITERATIONS = int(os.getenv('MAX_ITERATIONS', '10'))  # Максимальное количество циклов
AGENT_TIMEOUT = int(os.getenv('AGENT_TIMEOUT', '180'))  # Таймаут для каждого агента в секундах (увеличен с 60 до 180)
# По умолчанию разрешаем агентам создавать файлы, чтобы проект был
# сформирован даже без указания переменной окружения.
CREATE_FILES_DURING_AGENTS = os.getenv('CREATE_FILES_DURING_AGENTS', 'true').lower() == 'true'
MIN_SUCCESS_ITERATIONS = int(os.getenv('MIN_SUCCESS_ITERATIONS', '2'))  # Минимум итераций до возможности завершить
AGENT_RETRIES = int(os.getenv('AGENT_RETRIES', '3'))  # Повторы задачи агента при сбое (увеличен с 1 до 3)
SUCCESS_THRESHOLD = float(os.getenv('SUCCESS_THRESHOLD', '0.7'))  # Порог успешности агентов (70%)
PARALLEL_EXECUTION = os.getenv('PARALLEL_EXECUTION', 'true').lower() == 'true'  # Параллельный режим
AGENT_MAX_CONCURRENCY = int(os.getenv('AGENT_MAX_CONCURRENCY', '2'))  # Предел параллелизма (снижен с 4 до 2 для стабильности)
FINAL_ASSEMBLY_ENABLED_ENV = os.getenv('FINAL_ASSEMBLY_ENABLED', 'auto').lower()
# Если auto — включаем финальную сборку только когда не пишем файлы на лету
FINAL_ASSEMBLY_ENABLED = (
    (FINAL_ASSEMBLY_ENABLED_ENV == 'true') or
    (FINAL_ASSEMBLY_ENABLED_ENV == 'auto' and not CREATE_FILES_DURING_AGENTS)
)

# Директории проекта
PROJECT_OUTPUT_DIR = os.getenv('PROJECT_OUTPUT_DIR', "./generated_projects")
TEMPLATES_DIR = os.getenv('TEMPLATES_DIR', "./templates")
LOGS_DIR = os.getenv('LOGS_DIR', "./logs")

# Гарантируем наличие директории логов до конфигурации логгера
os.makedirs(LOGS_DIR, exist_ok=True)

# Роли агентов и их описания
AGENT_ROLES = {
    "project_manager": {
        "name": "Проект Менеджер", 
        "description": "Создает план проекта на основе требований от Product Owner",
        "prompt_template": "Ты опытный проект-менеджер. Создай детальный план разработки проекта: {project_description}. ИСПОЛЬЗУЙ требования от Product Owner: {product_requirements}, user_stories: {user_stories}, acceptance_criteria: {acceptance_criteria}. ДОПОЛНИТЕЛЬНО: {summary_report}. ОБЯЗАТЕЛЬНО: 1) Если требования от Product Owner еще не готовы (пустые поля) - подожди их создания и верни сообщение 'Ожидаю требования от Product Owner'. 2) Если требования готовы - создай файлы в блоках ```markdown: project_plan.md (план проекта на основе требований PO), timeline.md (временные рамки), tasks.md (задачи и этапы), risks.md (риски проекта), resource_allocation.md (распределение ресурсов), sprint_planning.md (планирование спринтов). 3) ВАЖНО: НЕ СОЗДАВАЙ новые требования - используй ТОЛЬКО требования от Product Owner. Твой план должен основываться на уже определенных требованиях, а не дублировать их. Каждый блок должен содержать полный документ с комментарием имени файла.",
        "use_reasoner": True
    },
    "system_architect": {
        "name": "Системный Архитектор",
        "description": "Проектирует архитектуру системы (без инфраструктуры)",
        "prompt_template": "Ты системный архитектор. Создай техническую архитектуру для проекта: {project_description}. ИСПОЛЬЗУЙ требования от Product Owner: {product_requirements}. ДОПОЛНИТЕЛЬНО: {summary_report}. ОБЯЗАТЕЛЬНО создай файлы в блоках ```markdown: architecture.md (техническая архитектура), technology_stack.md (выбор технологий), system_design.md (дизайн системы), api_specification.md (спецификация API), component_diagram.md (диаграмма компонентов), data_flow.md (поток данных). ВАЖНО: НЕ СОЗДАВАЙ docker-compose.yml, Dockerfile или другие инфраструктурные файлы - это задача DevOps Engineer. Фокусируйся ТОЛЬКО на архитектуре: диаграммы, модули, компоненты, API, потоки данных. Каждый блок должен содержать полный документ с комментарием имени файла."
    },
    "backend_developer": {
        "name": "Backend Разработчик",
        "description": "Создает серверную логику, API, базы данных",
        "prompt_template": "Ты senior backend разработчик. Создай серверную часть для проекта: {project_description}. ИСПОЛЬЗУЙ: требования от Product Owner: {product_requirements}, архитектуру от System Architect: {architecture}, схему БД от Database Engineer: {database_schema}. ДОПОЛНИТЕЛЬНО: {summary_report}. ОБЯЗАТЕЛЬНО напиши полный рабочий код в блоках ```python для FastAPI или Flask. Создай файлы: app.py (основное приложение), models.py (модели данных), routes.py (маршруты API). Каждый блок кода должен быть в ```python блоках с комментарием имени файла."
    },
    "frontend_developer": {
        "name": "Frontend Разработчик", 
        "description": "Создает пользовательский интерфейс",
        "prompt_template": "Ты senior frontend разработчик. Создай пользовательский интерфейс для проекта: {project_description}. ИСПОЛЬЗУЙ: требования от Product Owner: {product_requirements}, дизайн от UI/UX Designer: {ui_design}, API от Backend Developer: {api_spec}. ДОПОЛНИТЕЛЬНО: {summary_report}. ОБЯЗАТЕЛЬНО напиши полный рабочий код в блоках: ```html для index.html (основная страница), ```css для styles.css (стили), ```javascript для app.js (JavaScript логика). Каждый блок кода должен содержать полный рабочий код с комментарием имени файла."
    },
    "database_engineer": {
        "name": "Database Engineer",
        "description": "Проектирует и оптимизирует базы данных",
        "prompt_template": "Ты database engineer. Спроектируй схему базы данных для проекта: {project_description}. ИСПОЛЬЗУЙ требования от Product Owner: {product_requirements}. ДОПОЛНИТЕЛЬНО: {summary_report}. ОБЯЗАТЕЛЬНО напиши полный код в блоках ```sql для создания таблиц, индексов, триггеров. Создай файлы: schema.sql (структура БД), data.sql (начальные данные), migrations.sql (миграции). Каждый блок кода должен быть в ```sql блоках с комментарием имени файла."
    },
    "devops_engineer": {
        "name": "DevOps Engineer",
        "description": "Настраивает CI/CD, деплой, мониторинг на основе архитектуры",
        "prompt_template": "Ты DevOps engineer. Проект — Python Flask (WSGI) + Gunicorn. Никакого Django/collectstatic/manage.py. Создай конфигурацию развертывания для проекта: {project_description}. ИСПОЛЬЗУЙ архитектуру от System Architect: {architecture}. ОБЯЗАТЕЛЬНО создай файлы в блоках ```dockerfile и ```yaml и ```nginx и ```markdown: Dockerfile (контейнеризация с CMD: gunicorn app:app --bind 0.0.0.0:8000), docker-compose.yml (оркестрация на основе архитектуры SA), .github/workflows/ci.yml (CI: pytest), nginx.conf (reverse proxy к :8000), deployment.md (инструкция по деплою). ВАЖНО: docker-compose.yml должен соответствовать архитектуре от System Architect. Каждый блок должен содержать полный файл с комментарием имени файла."
    },
    "qa_tester": {
        "name": "QA Тестировщик",
        "description": "Создает тесты, проверяет качество и исправляет найденные проблемы",
        "prompt_template": "Ты QA engineer. Бэкенд — Flask. Тесты запускаются через pytest, без Django. Создай полный набор тестов для проекта: {project_description}. ИСПОЛЬЗУЙ: требования от Product Owner: {product_requirements}. 🔥 КРИТИЧНО: АНАЛИЗИРУЙ РЕАЛЬНЫЙ КОД из {agent_artifacts}: backend_code, frontend_code, api_specification, database_schema, ui_design. ИСПОЛЬЗУЙ ЭТИ АРТЕФАКТЫ для создания релевантных тестов на основе реального кода. ОБЯЗАТЕЛЬНО: 1) Напиши полный код в блоках ```python для pytest. Создай файлы: tests/test_api.py (API на основе api_specification), tests/test_models.py (модели на основе backend_code), tests/test_frontend.py (e2e-заглушки/сценарии на основе frontend_code), tests/test_database.py (тесты БД на основе database_schema). 2) КРИТИЧНО: если тесты не проходят или находят проблемы - ИСПРАВЬ ИХ СРАЗУ используя команды EDIT filename: или APPEND TO filename:. Не просто создавай тесты - исправляй код чтобы тесты проходили! 3) Создай test_results.md с результатами прогона тестов (имитируй запуск pytest). 4) АВТОМАТИЧЕСКИ исправляй найденные ошибки в коде. Каждый блок кода должен быть в ```python с комментарием имени файла."
    },
    "security_specialist": {
        "name": "Security Специалист",
        "description": "Обеспечивает безопасность приложения",
        "prompt_template": "Ты security specialist. Проанализируй безопасность проекта: {project_description}. ИСПОЛЬЗУЙ требования от Product Owner: {product_requirements}. 🔥 КРИТИЧНО: АНАЛИЗИРУЙ РЕАЛЬНЫЙ КОД других агентов из {agent_artifacts}: backend_code, frontend_code, database_schema, api_specification. ИСПОЛЬЗУЙ ЭТИ АРТЕФАКТЫ для поиска реальных уязвимостей в коде. ОБЯЗАТЕЛЬНО создай файлы в блоках ```markdown: security_audit.md (аудит безопасности с анализом реального кода), vulnerabilities.md (конкретные уязвимости найденные в коде), security_recommendations.md (рекомендации по исправлению), security_checklist.md (чек-лист безопасности). ВАЖНО: если находишь уязвимости - предложи конкретные исправления в коде с использованием команд EDIT filename: или APPEND TO filename:. Каждый блок должен содержать полный документ с комментарием имени файла."
    },
    "ui_ux_designer": {
        "name": "UI/UX Дизайнер",
        "description": "Создает дизайн интерфейса на основе требований PO",
        "prompt_template": "Ты UI/UX дизайнер. Создай дизайн интерфейса для проекта: {project_description}. ИСПОЛЬЗУЙ требования от Product Owner: {product_requirements}. ОБЯЗАТЕЛЬНО создай файлы в блоках ```markdown и ```css: design_system.md (дизайн-система на основе требований PO), wireframes.md (каркасы страниц), ux_flow.md (пользовательские сценарии), ui_components.css (основные стили компонентов). ВАЖНО: дизайн должен точно соответствовать требованиям PO, не добавляй лишних функций. Каждый блок должен содержать полный документ с комментарием имени файла."
    },
    "mobile_developer": {
        "name": "Mobile Разработчик",
        "description": "Создает мобильные приложения только для мобильных проектов",
        "prompt_template": "Ты mobile developer. АНАЛИЗИРУЙ проект: {project_description}. Если это ВЕБ-проект (сайт, веб-приложение) - НЕ СОЗДАВАЙ мобильный код, верни сообщение 'Проект не требует мобильной разработки'. Если это МОБИЛЬНЫЙ проект - создай мобильное приложение в блоках ```javascript для React Native: App.js (основное приложение), components/MainScreen.js (главный экран), package.json (зависимости). Каждый блок кода должен быть с комментарием имени файла."
    },
    "data_scientist": {
        "name": "Data Scientist",
        "description": "Добавляет аналитику и ML только при необходимости",
        "prompt_template": "Ты data scientist. АНАЛИЗИРУЙ проект: {project_description}. Если проект НЕ ТРЕБУЕТ аналитики/ML (например, простой веб-сайт) - верни сообщение 'Проект не требует Data Science компонентов'. Если проект ТРЕБУЕТ аналитику/ML (e-commerce, рекомендации, прогнозирование) - создай файлы в блоках ```python: analytics.py (аналитические модели), ml_models.py (машинное обучение), data_processing.py (обработка данных), requirements_ml.txt (ML зависимости). Каждый блок кода должен быть с комментарием имени файла."
    },
    "technical_writer": {
        "name": "Technical Writer",
        "description": "Создает документацию на основе требований и архитектуры",
        "prompt_template": "Ты technical writer. Создай полную документацию для проекта: {project_description}. ИСПОЛЬЗУЙ: требования от Product Owner: {product_requirements}, архитектуру от System Architect: {architecture}. ОБЯЗАТЕЛЬНО создай файлы в блоках ```markdown: README.md (общая документация), API.md (документация API), USER_GUIDE.md (руководство пользователя), INSTALLATION.md (инструкция по установке). ВАЖНО: документация должна точно отражать требования PO и архитектуру SA. Каждый блок должен содержать полный документ с комментарием имени файла."
    },
    "performance_engineer": {
        "name": "Performance Engineer",
        "description": "Оптимизирует производительность при необходимости",
        "prompt_template": "Ты performance engineer. АНАЛИЗИРУЙ проект: {project_description}. Если это ПРОСТОЙ проект (сайт-визитка) - верни сообщение 'Проект не требует оптимизации производительности'. Если проект СЛОЖНЫЙ (e-commerce, API, высокие нагрузки) - 🔥 КРИТИЧНО: АНАЛИЗИРУЙ РЕАЛЬНУЮ АРХИТЕКТУРУ и КОД из {agent_artifacts}: architecture, backend_code, database_schema, api_specification, frontend_code. ИСПОЛЬЗУЙ ЭТИ АРТЕФАКТЫ для анализа реальных узких мест производительности. Создай файлы в блоках ```markdown и ```python: performance_audit.md (аудит производительности с анализом реального кода), optimization_plan.md (план оптимизации на основе найденных проблем), monitoring.py (мониторинг производительности), caching.py (кэширование для найденных узких мест). Каждый блок должен содержать полный документ или код с комментарием имени файла."
    },
    "integration_specialist": {
        "name": "Integration Специалист",
        "description": "Добавляет интеграции только при необходимости",
        "prompt_template": "Ты integration specialist. АНАЛИЗИРУЙ проект: {project_description}. Если проект НЕ ТРЕБУЕТ внешних интеграций (например, простой сайт-визитка) - верни сообщение 'Проект не требует внешних интеграций'. Если проект ТРЕБУЕТ интеграции (платежи, API, webhooks) - создай файлы в блоках ```python: integrations.py (внешние API), webhooks.py (обработчики webhooks), payment_gateway.py (платежная система), third_party_services.py (сторонние сервисы). Каждый блок кода должен быть с комментарием имени файла."
    },
    "code_reviewer": {
        "name": "Code Reviewer",
        "description": "Проверяет качество кода и исправляет найденные проблемы",
        "prompt_template": "Ты senior code reviewer. Проверь код всего проекта: {project_description}. ИСПОЛЬЗУЙ: требования от Product Owner: {product_requirements}, архитектуру от System Architect: {architecture}. 🔥 КРИТИЧНО: АНАЛИЗИРУЙ РЕАЛЬНЫЙ КОД из {agent_artifacts}: backend_code, frontend_code, database_schema, architecture, test_code. ИСПОЛЬЗУЙ ЭТИ АРТЕФАКТЫ для детального анализа качества кода. ОБЯЗАТЕЛЬНО: 1) Создай файлы в блоках ```markdown: code_review.md (обзор кода с анализом реального кода), bugs_found.md (конкретные баги найденные в коде), improvements.md (предложения по улучшению на основе анализа), best_practices.md (соответствие best practices). 2) КРИТИЧНО: если находишь баги или проблемы - ИСПРАВЬ ИХ СРАЗУ используя команды EDIT filename: или APPEND TO filename:. Не просто записывай проблемы - исправляй код! 3) Проверь соответствие архитектуре и требованиям. 4) АВТОМАТИЧЕСКИ исправляй найденные ошибки в коде. Каждый блок должен содержать полный документ с комментарием имени файла."
    },
    "bug_fixer": {
        "name": "Bug Fixer",
        "description": "Автоматически исправляет найденные баги и проблемы",
        "prompt_template": "Ты bug fixer - специалист по автоматическому исправлению ошибок. АНАЛИЗИРУЙ найденные проблемы: {project_description}. ИСПОЛЬЗУЙ: отчеты от Code Reviewer: {code_reviewer_output}, результаты тестов от QA: {qa_output}. 🔥 КРИТИЧНО: АНАЛИЗИРУЙ РЕАЛЬНЫЙ КОД из {agent_artifacts}: backend_code, frontend_code, code_review_issues, qa_test_failures, error_logs. ИСПОЛЬЗУЙ ЭТИ АРТЕФАКТЫ для понимания контекста ошибок и их исправления. ОБЯЗАТЕЛЬНО: 1) Прочитай все найденные проблемы из bugs_found.md, improvements.md, test_results.md. 2) АВТОМАТИЧЕСКИ исправь ВСЕ найденные баги используя команды EDIT filename: или APPEND TO filename:. 3) Убедись что исправления не ломают существующий функционал. 4) Создай bug_fixes_report.md с отчетом об исправлениях. Каждый блок должен содержать полный код с комментарием имени файла."
    },
    "product_owner": {
        "name": "Product Owner",
        "description": "Определяет требования продукта",
        "prompt_template": "Ты product owner. Определи product requirements для проекта: {project_description}. СФОРМИРУЙ 3 ОТДЕЛЬНЫХ ДОКУМЕНТА строго в блоках ```markdown: product_requirements.md, user_stories.md, acceptance_criteria.md. Ограничения: 1) Каждый документ не более 500-700 слов; 2) Используй сжатые списки и нумерацию; 3) Не повторяй одно и то же; 4) Если информации недостаточно — чётко помечай предположения явно разделом 'Assumptions'; 5) Избегай больших прелюдий, сразу по делу. Каждый блок должен содержать полный документ с комментарием имени файла." 
    }
}

# Порядок выполнения агентов
AGENT_EXECUTION_ORDER = [
    "product_owner",
    "project_manager", 
    "system_architect",
    "ui_ux_designer",
    "database_engineer",
    "backend_developer",
    "frontend_developer", 
    "mobile_developer",
    "data_scientist",
    "integration_specialist",
    "security_specialist",
    "performance_engineer",
    "devops_engineer",
    "qa_tester",
    "technical_writer",
    "code_reviewer",
    "bug_fixer"
]

# Фазы последовательного выполнения (агенты ждут результатов предыдущих фаз)
AGENT_EXECUTION_PHASES = [
    ["product_owner"],  # Сначала только Product Owner
    ["project_manager"],  # Затем Project Manager (использует результаты PO)
    ["system_architect", "ui_ux_designer", "database_engineer"],  # Архитектура и дизайн
    ["backend_developer", "frontend_developer"],  # Разработка
    ["devops_engineer"],  # DevOps
    ["qa_tester", "technical_writer", "code_reviewer"],  # Тестирование и документация
    ["bug_fixer"],  # Исправление ошибок
]

# 🔥 Настройки логирования (ИСПРАВЛЕНО: убрано дублирование)
# Логика: 
# - root logger пишет только в консоль (уровень INFO)
# - дочерние логгеры пишут только в файл (уровень DEBUG)
# - propagate: False для всех логгеров предотвращает дублирование
# - urllib3 и asyncio логируются только в файл с уровнем WARNING
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'detailed': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        },
        'simple': {
            'format': '[%(levelname)s] %(name)s: %(message)s'
        },
    },
    'handlers': {
        'file': {
            'class': 'logging.FileHandler',
            'filename': f'{LOGS_DIR}/agents.log',
            'formatter': 'detailed',
            'level': 'DEBUG',
        },
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
            'level': 'DEBUG',
        },
    },
    'loggers': {
        '': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Дочерние логгеры пишут только в файл, НЕ дублируют в консоль
        'coordinator': {'handlers': ['file'], 'level': 'DEBUG', 'propagate': False},
        'agents': {'handlers': ['file'], 'level': 'DEBUG', 'propagate': False},
        'deepseek_client': {'handlers': ['file'], 'level': 'INFO', 'propagate': False},
        'project_generator': {'handlers': ['file'], 'level': 'DEBUG', 'propagate': False},
        'project_analyzer': {'handlers': ['file'], 'level': 'DEBUG', 'propagate': False},
        'final_project_assembler': {'handlers': ['file'], 'level': 'DEBUG', 'propagate': False},
        'project_consistency_checker': {'handlers': ['file'], 'level': 'DEBUG', 'propagate': False},
        # Отключаем технические детали urllib3
        'urllib3': {'handlers': ['file'], 'level': 'WARNING', 'propagate': False},
        'asyncio': {'handlers': ['file'], 'level': 'WARNING', 'propagate': False},
    },
}

# 🔥 РЕЗУЛЬТАТ: Каждое сообщение логируется только ОДИН раз:
# - В консоль: через root logger (уровень INFO+)
# - В файл: через соответствующий дочерний логгер (уровень DEBUG+)
# - НЕТ дублирования сообщений в логах
# - urllib3 и asyncio не засоряют консоль техническими деталями
