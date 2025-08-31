"""
Финальная сборка проекта - создает итоговый README и проверяет целостность
"""
import logging
from typing import Dict, List, Any, Optional
from config import SUCCESS_THRESHOLD
from pathlib import Path
from project_consistency_checker import ProjectConsistencyChecker

logger = logging.getLogger(__name__)

class FinalProjectAssembler:
    """Собирает финальный проект и генерирует итоговый README"""
    
    def __init__(self):
        self.consistency_checker = ProjectConsistencyChecker()
    
    def assemble_final_project(self, project_files: Dict[str, str], project_context: Dict[str, Any]) -> Dict[str, Any]:
        """Собирает финальный проект и проверяет целостность"""
        logger.info("🔧 Финальная сборка проекта...")
        
        assembly_report = {
            "files_created": len(project_files),
            "consistency_score": 0,
            "consistency_report": {},
            "final_readme": "",
            "project_summary": {},
            "launch_instructions": "",
            "issues_found": []
        }
        
        try:
            # 1. Проверяем консистентность
            consistency_report = self.consistency_checker.check_project_consistency(project_files, project_context)
            assembly_report["consistency_report"] = consistency_report
            assembly_report["consistency_score"] = consistency_report["overall_score"]
            
            # 2. Генерируем итоговый README
            final_readme = self._generate_final_readme(project_files, project_context, consistency_report)
            assembly_report["final_readme"] = final_readme
            
            # 3. Создаем инструкции по запуску
            launch_instructions = self._generate_launch_instructions(project_files, project_context)
            assembly_report["launch_instructions"] = launch_instructions
            
            # 4. Анализируем проект
            project_summary = self._analyze_project_structure(project_files, project_context)
            assembly_report["project_summary"] = project_summary
            
            # 5. Проверяем целостность
            integrity_issues = self._check_project_integrity(project_files, consistency_report)
            assembly_report["issues_found"] = integrity_issues
            
            logger.info(f"✅ Финальная сборка завершена. Консистентность: {consistency_report['overall_score']}/100")
            
        except Exception as e:
            logger.error(f"Ошибка при финальной сборке: {e}")
            assembly_report["issues_found"].append(f"Ошибка сборки: {e}")
        
        return assembly_report
    
    def _generate_final_readme(self, project_files: Dict[str, str], project_context: Dict[str, Any], consistency_report: Dict[str, Any]) -> str:
        """Генерирует итоговый README проекта"""
        logger.info("📝 Генерация итогового README...")
        
        # Проверяем, есть ли уже README от Technical Writer
        existing_readme = None
        for filename, content in project_files.items():
            if "readme.md" in filename.lower():
                existing_readme = content
                break
        
        # Если есть README от Technical Writer, дополняем его
        if existing_readme:
            logger.info("📖 Дополняем существующий README от Technical Writer")
            return self._enhance_existing_readme(existing_readme, project_context, consistency_report)
        else:
            logger.info("📝 Создаем новый README (Technical Writer не справился)")
            return self._create_new_readme(project_files, project_context, consistency_report)
    
    def _enhance_existing_readme(self, existing_readme: str, project_context: Dict[str, Any], consistency_report: Dict[str, Any]) -> str:
        """Дополняет существующий README"""
        enhanced_readme = existing_readme
        
        # Добавляем раздел о консистентности
        consistency_section = f"""
## 🔍 Проверка консистентности

Проект прошел автоматическую проверку консистентности.

**Общий балл: {consistency_report['overall_score']}/100**

### API покрытие
- Backend endpoints: {consistency_report['api_coverage'].get('total_backend', 0)}
- Frontend API вызовы: {consistency_report['api_coverage'].get('total_frontend', 0)}
- Совпадения: {consistency_report['api_coverage'].get('matched', 0)}

### Статус проекта
- Итераций выполнено: {project_context.get('current_iteration', 0)}
- Статус: {project_context.get('status', 'unknown')}
- Агентов задействовано: {len(project_context.get('all_results', {}))}
"""
        
        # Добавляем инструкции по запуску если их нет
        if "## Запуск" not in enhanced_readme and "## Установка" not in enhanced_readme:
            launch_section = self._generate_launch_instructions_section(project_context)
            enhanced_readme += f"\n{launch_section}"
        
        # Добавляем раздел консистентности
        if "## 🔍 Проверка консистентности" not in enhanced_readme:
            enhanced_readme += consistency_section
        
        return enhanced_readme
    
    def _create_new_readme(self, project_files: Dict[str, str], project_context: Dict[str, Any], consistency_report: Dict[str, Any]) -> str:
        """Создает новый README с нуля"""
        project_name = project_context.get('name', 'Проект')
        project_description = project_context.get('description', 'Описание отсутствует')
        
        readme = f"""# {project_name}

{project_description}

## 📋 Описание проекта

Этот проект был автоматически сгенерирован системой Multi-Agent Project Generator.

### 🏗️ Архитектура

Проект использует современную архитектуру с разделением на frontend и backend.

### 🛠️ Технологии

- **Backend**: Python Flask/FastAPI
- **Frontend**: HTML/CSS/JavaScript
- **База данных**: SQLite/PostgreSQL
- **Тестирование**: pytest

## 🚀 Быстрый старт

### Предварительные требования

- Python 3.8+
- Node.js (если используется)
- Git

### Установка

1. Клонируйте репозиторий:
```bash
git clone <repository-url>
cd {project_name}
```

2. Создайте виртуальное окружение:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\\Scripts\\activate  # Windows
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Настройте переменные окружения:
```bash
cp .env.example .env
# Отредактируйте .env файл
```

### Запуск

1. Запустите backend:
```bash
python app.py
# или
flask run
```

2. Откройте frontend в браузере:
```
http://localhost:5000
```

## 📁 Структура проекта

```
{project_name}/
├── app.py              # Основное приложение
├── requirements.txt    # Python зависимости
├── static/            # Статические файлы
├── templates/         # HTML шаблоны
├── tests/             # Тесты
└── README.md          # Этот файл
```

## 🧪 Тестирование

Запустите тесты:
```bash
pytest
```

## 🔍 Проверка консистентности

Проект прошел автоматическую проверку консистентности.

**Общий балл: {consistency_report['overall_score']}/100**

### API покрытие
- Backend endpoints: {consistency_report['api_coverage'].get('total_backend', 0)}
- Frontend API вызовы: {consistency_report['api_coverage'].get('total_frontend', 0)}
- Совпадения: {consistency_report['api_coverage'].get('matched', 0)}

### Статус проекта
- Итераций выполнено: {project_context.get('current_iteration', 0)}
- Статус: {project_context.get('status', 'unknown')}
- Агентов задействовано: {len(project_context.get('all_results', {}))}

## 📊 Анализ качества

### Критические проблемы
"""
        
        if consistency_report.get('issues'):
            for issue in consistency_report['issues']:
                readme += f"- ❌ {issue}\n"
        else:
            readme += "- ✅ Критических проблем не обнаружено\n"
        
        readme += "\n### Предупреждения\n"
        if consistency_report.get('warnings'):
            for warning in consistency_report['warnings']:
                readme += f"- ⚠️ {warning}\n"
        else:
            readme += "- ✅ Предупреждений нет\n"
        
        readme += "\n### Рекомендации\n"
        if consistency_report.get('recommendations'):
            for rec in consistency_report['recommendations']:
                readme += f"- 💡 {rec}\n"
        else:
            readme += "- ✅ Рекомендаций нет\n"
        
        readme += """
## 🤝 Вклад в проект

Этот проект был создан автоматически. Для внесения изменений:

1. Создайте feature branch
2. Внесите изменения
3. Запустите тесты
4. Создайте Pull Request

## 📄 Лицензия

MIT License

---

*Сгенерировано автоматически системой Multi-Agent Project Generator*
"""
        
        return readme
    
    def _generate_launch_instructions_section(self, project_context: Dict[str, Any]) -> str:
        """Генерирует раздел с инструкциями по запуску"""
        return f"""
## 🚀 Инструкции по запуску

### Шаг 1: Подготовка окружения
```bash
# Создайте виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\\Scripts\\activate  # Windows
```

### Шаг 2: Установка зависимостей
```bash
pip install -r requirements.txt
```

### Шаг 3: Настройка
```bash
# Скопируйте файл конфигурации
cp .env.example .env
# Отредактируйте .env файл под ваше окружение
```

### Шаг 4: Запуск
```bash
# Запустите backend
python app.py
# или
flask run

# Откройте в браузере
http://localhost:5000
```

### Шаг 5: Тестирование
```bash
# Запустите тесты
pytest
```

## 🔧 Переменные окружения

Создайте файл `.env` со следующими переменными:

```env
FLASK_ENV=development
FLASK_DEBUG=1
DATABASE_URL=sqlite:///app.db
SECRET_KEY=your-secret-key-here
```

## 📱 Доступ к приложению

- **Frontend**: http://localhost:5000
- **API**: http://localhost:5000/api
- **Документация**: http://localhost:5000/docs (если доступно)
"""
    
    def _generate_launch_instructions(self, project_files: Dict[str, str], project_context: Dict[str, Any]) -> str:
        """Генерирует инструкции по запуску на основе анализа проекта"""
        # Пытаемся определить тип проекта по файлам
        files_lower = {name.lower(): content for name, content in project_files.items()}
        has_fastapi = any("fastapi" in c.lower() for c in files_lower.values())
        has_flask = any("flask" in c.lower() for c in files_lower.values())
        has_django = any("django" in c.lower() or name.endswith("urls.py") for name, c in files_lower.items())
        has_node = any(name.endswith("package.json") for name in files_lower.keys())

        if has_django:
            return """
## 🚀 Инструкции по запуску (Django)

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt

# Миграции
python manage.py migrate

# Запуск сервера
python manage.py runserver 0.0.0.0:8000
```

- Backend: http://localhost:8000/
- API: http://localhost:8000/api/ (если настроено)
"""

        if has_fastapi:
            return """
## 🚀 Инструкции по запуску (FastAPI)

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt

# Запуск через uvicorn
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

- API Docs: http://localhost:8000/docs
"""

        if has_flask:
            return """
## 🚀 Инструкции по запуску (Flask)

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt

export FLASK_APP=app.py
flask run --host 0.0.0.0 --port 8000
```
"""

        if has_node:
            return """
## 🚀 Инструкции по запуску (Node.js frontend)

```bash
npm install
npm run dev
```
"""

        # По умолчанию — универсальная инструкция
        return self._generate_launch_instructions_section(project_context)
    
    def _analyze_project_structure(self, project_files: Dict[str, str], project_context: Dict[str, Any]) -> Dict[str, Any]:
        """Анализирует структуру проекта"""
        analysis = {
            "total_files": len(project_files),
            "file_types": {},
            "backend_files": [],
            "frontend_files": [],
            "config_files": [],
            "test_files": [],
            "documentation_files": [],
            "dependencies": set(),
            "environment_variables": set()
        }
        
        for filename, content in project_files.items():
            file_lower = filename.lower()
            
            # Определяем тип файла
            if any(ext in file_lower for ext in [".py", "requirements.txt"]):
                analysis["backend_files"].append(filename)
                analysis["file_types"]["backend"] = analysis["file_types"].get("backend", 0) + 1
            elif any(ext in file_lower for ext in [".html", ".js", ".css", ".vue", ".jsx"]):
                analysis["frontend_files"].append(filename)
                analysis["file_types"]["frontend"] = analysis["file_types"].get("frontend", 0) + 1
            elif any(ext in file_lower for ext in [".env", "config", "settings"]):
                analysis["config_files"].append(filename)
                analysis["file_types"]["config"] = analysis["file_types"].get("config", 0) + 1
            elif "test" in file_lower or "tests" in file_lower:
                analysis["test_files"].append(filename)
                analysis["file_types"]["tests"] = analysis["file_types"].get("tests", 0) + 1
            elif any(ext in file_lower for ext in [".md", "readme", "api", "docs"]):
                analysis["documentation_files"].append(filename)
                analysis["file_types"]["documentation"] = analysis["file_types"].get("documentation", 0) + 1
        
        return analysis
    
    def _check_project_integrity(self, project_files: Dict[str, str], consistency_report: Dict[str, Any]) -> List[str]:
        """Проверяет целостность проекта"""
        issues = []
        
        # Проверяем критические проблемы
        if consistency_report.get('issues'):
            issues.extend(consistency_report['issues'])
        
        # Проверяем предупреждения (без дублирующих префиксов)
        if consistency_report.get('warnings'):
            issues.extend(list(consistency_report['warnings']))
        
        # Проверяем общий балл (порог настраиваемый)
        threshold_score = int(round(SUCCESS_THRESHOLD * 100))
        if consistency_report.get('overall_score', 0) < threshold_score:
            issues.append(f"Низкий балл консистентности: {consistency_report['overall_score']}/100 (порог {threshold_score})")
        
        # Проверяем API покрытие
        api_coverage = consistency_report.get('api_coverage', {})
        if api_coverage.get('total_backend', 0) == 0:
            issues.append("Backend не содержит API endpoints")
        
        if api_coverage.get('total_frontend', 0) == 0:
            issues.append("Frontend не содержит API вызовы")
        
        if api_coverage.get('matched', 0) == 0 and api_coverage.get('total_backend', 0) > 0 and api_coverage.get('total_frontend', 0) > 0:
            issues.append("Frontend и Backend API не совпадают")
        
        return issues
    
    def generate_project_summary(self, assembly_report: Dict[str, Any]) -> str:
        """Генерирует краткое резюме проекта"""
        summary = f"""
# 📊 Итоговый отчет проекта

## 🎯 Общая информация
- Файлов создано: {assembly_report['files_created']}
- Балл консистентности: {assembly_report['consistency_score']}/100
- Проблем найдено: {len(assembly_report['issues_found'])}

## 🔍 Результаты проверки консистентности

### API покрытие
- Backend endpoints: {assembly_report['consistency_report'].get('api_coverage', {}).get('total_backend', 0)}
- Frontend API вызовы: {assembly_report['consistency_report'].get('api_coverage', {}).get('total_frontend', 0)}
- Совпадения: {assembly_report['consistency_report'].get('api_coverage', {}).get('matched', 0)}

## ⚠️ Найденные проблемы
"""
        
        if assembly_report['issues_found']:
            for issue in assembly_report['issues_found']:
                summary += f"- ❌ {issue}\n"
        else:
            summary += "- ✅ Проблем не обнаружено\n"
        
        summary += f"""
## 📋 Рекомендации

### Для улучшения качества:
1. Проверьте соответствие frontend и backend API
2. Убедитесь в наличии всех необходимых файлов
3. Запустите тесты и исправьте ошибки
4. Проверьте переменные окружения

### Для запуска:
{assembly_report['launch_instructions']}

## 🎉 Проект готов к использованию!

Балл консистентности: {assembly_report['consistency_score']}/100
"""
        
        return summary
