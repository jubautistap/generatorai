"""
Генератор проектов - создает файлы и структуру проекта на основе результатов агентов
"""
import os
import re
import json
import logging
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import tempfile
import ast
# 🔥 УДАЛЕНО: Неиспользуемый импорт dataclass

logger = logging.getLogger(__name__)

# 🔥 УДАЛЕНО: Неиспользуемый класс FileInfo
# Логика создания файлов реализована напрямую в ProjectGenerator
# для упрощения поддержки и избежания дублирования

class CodeExtractor:
    """Извлекает код из текстовых ответов агентов"""
    
    @staticmethod
    def extract_code_blocks(text: str) -> List[Tuple[str, str, Optional[str]]]:
        """
        Извлекает блоки кода из текста
        Возвращает список (язык, код, имя файла)
        """
        code_blocks = []
        
        # Паттерн для блоков кода вида ```lang or ```lang: filename
        # захватывает язык и необязательное имя файла после двоеточия
        pattern = r'```(\w+)(?::\s*([\w/\.\-]+))?\n(.*?)\n```'
        matches = re.findall(pattern, text, re.DOTALL)

        for language, filename, code in matches:
            if code.strip():
                code_blocks.append((language or 'text', code.strip(), filename or None))
        
        # Если нет блоков с ```, ищем другие паттерны
        if not code_blocks:
            # Ищем файлы по расширениям
            file_patterns = {
                r'\.py\b': 'python',
                r'\.js\b': 'javascript', 
                r'\.html\b': 'html',
                r'\.css\b': 'css',
                r'\.json\b': 'json',
                r'\.sql\b': 'sql',
                r'\.yaml\b|\.yml\b': 'yaml'
            }
            
            for pattern, language in file_patterns.items():
                if re.search(pattern, text, re.IGNORECASE):
                    # Пытаемся извлечь код после упоминания файла
                    code_blocks.append((language, text, 'Extracted from text'))
                    break
        
        return code_blocks
    
    @staticmethod
    def extract_file_structure(text: str) -> List[str]:
        """Извлекает структуру файлов из текста"""
        file_paths = []
        
        # Ищем пути к файлам
        patterns = [
            r'[\w/]+\.[\w]+',  # path/file.ext
            r'src/[\w/]+',     # src/path  
            r'app/[\w/]+',     # app/path
            r'components/[\w/]+',  # components/path
            r'pages/[\w/]+',   # pages/path
            r'api/[\w/]+',     # api/path
            r'models/[\w/]+',  # models/path
            r'views/[\w/]+',   # views/path
            r'static/[\w/]+',  # static/path
            r'templates/[\w/]+'  # templates/path
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            file_paths.extend(matches)
        
        return list(set(file_paths))  # Убираем дубликаты

class ProjectGenerator:
    """🔥 Генератор проектов - создает файлы и структуру проекта на основе результатов агентов
    
    ОСОБЕННОСТИ:
    - Унифицированный парсинг ответов агентов
    - 🔥 УМНОЕ СЛИЯНИЕ: Автоматическое объединение содержимого файлов
    - 🔥 УМНОЕ РАЗМЕЩЕНИЕ: Файлы размещаются по роли агента и типу
    - 🔥 КОМАНДЫ РЕДАКТИРОВАНИЯ: Обработка EDIT, APPEND TO, REPLACE, UPDATE
    - 🔥 УСЛОВНАЯ ГЕНЕРАЦИЯ: Файлы создаются только при необходимости
    - Автоматическое разрешение конфликтов имен файлов
    - Добавление заголовков с информацией об агенте
    - Предотвращение дублирования файлов
    - Резервное копирование при ошибках слияния
    """
    
    def __init__(self, output_base_dir: str = "./generated_projects"):
        self.output_base_dir = Path(output_base_dir)
        # Создаем базовую директорию (со всеми родителями)
        self.output_base_dir.mkdir(parents=True, exist_ok=True)
        self.code_extractor = CodeExtractor()
        
    async def generate_project(self, 
                             project_context, 
                             agent_results: Dict[str, List]) -> List[str]:
        """
        Генерирует полный проект на основе результатов агентов
        """
        # ЕДИНЫЙ источник имени проекта: сначала project_name, затем name
        project_name = getattr(project_context, 'project_name', None) or getattr(project_context, 'name', None) or 'unnamed_project'
        project_dir = self.output_base_dir / project_name
        # Создаем директорию проекта (со всеми родителями)
        project_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Генерация проекта в директории: {project_dir}")
        
        created_files = []
        
        # Создаем базовую структуру
        await self._create_base_structure(project_dir)
        
        # Обрабатываем результаты каждого агента
        for agent_id, results in agent_results.items():
            if not results:
                continue
                
            agent_files = await self._process_agent_results(
                agent_id, results, project_dir, project_context
            )
            created_files.extend(agent_files)
        
        # Создаем дополнительные файлы
        # 🔥 Создаем дополнительные файлы проекта на основе реальных технологий
        additional_files = await self._create_additional_files(project_dir, project_context, agent_results)
        created_files.extend(additional_files)
        
        # Создаем README
        readme_file = await self._create_readme(project_dir, project_context, agent_results)
        if readme_file:
            created_files.append(readme_file)
        
        return created_files
    
    async def _create_base_structure(self, project_dir: Path):
        """Создает базовую структуру проекта"""
        # Стандартные директории
        dirs_to_create = [
            "src",
            "src/backend", 
            "src/frontend",
            "src/mobile",
            "src/database",
            "tests",
            "tests/unit",
            "tests/integration", 
            "tests/e2e",
            "docs",
            "config",
            "scripts",
            "static",
            "templates",
            "logs"
        ]
        
        for dir_name in dirs_to_create:
            dir_path = project_dir / dir_name
            dir_path.mkdir(parents=True, exist_ok=True)
            
            # Создаем .gitkeep для пустых директорий
            gitkeep_path = dir_path / ".gitkeep"
            if not any(dir_path.iterdir()):
                gitkeep_path.touch()
    
    async def _process_agent_results(self, 
                                   agent_id: str, 
                                   results: List,
                                   project_dir: Path,
                                   project_context) -> List[str]:
        """Обрабатывает результаты конкретного агента"""
        created_files = []
        
        for result in results:
            if not result.success or not result.output:
                continue
                
            # 🔥 УНИФИЦИРОВАННЫЙ ПАРСИНГ: Переиспользуем логику из BaseAgent
            # 🔥 ИСПРАВЛЕНО: Передаем agent_id для правильного размещения файлов
            operations = self._extract_file_operations_like_agent(result.output, agent_id)
            
            for op in operations:
                # 🔥 УМНАЯ ОБРАБОТКА: Разные действия для разных операций
                if op.get('is_edit_operation', False):
                    # 🔥 КОМАНДЫ РЕДАКТИРОВАНИЯ: EDIT, APPEND TO, REPLACE, UPDATE
                    self._process_edit_operation(project_dir, op, agent_id)
                    created_files.append(str(project_dir / op['resolved_path']))
                    logger.info(f"🔄 Обработана команда {op['action']}: {op['filename']}")
                else:
                    # 🔥 СОЗДАНИЕ НОВЫХ ФАЙЛОВ: Блоки кода ```
                    self._process_create_operation(project_dir, op, agent_id)
                    created_files.append(str(project_dir / op['resolved_path']))
        
        return created_files
    
    def _resolve_file_path_smart(self, project_dir: Path, original_path: str) -> Tuple[Path, bool]:
        """🔥 НОВОЕ: Умное разрешение путей файлов с возвратом флага нового файла
        
        Returns:
            Tuple[Path, bool]: (путь к файлу, является ли файл новым)
        """
        file_path = project_dir / original_path
        
        # Если файл не существует - это новый файл
        if not file_path.exists():
            return file_path, True
        
        # 🔥 УМНАЯ ЛОГИКА: Проверяем, можно ли объединить содержимое
        if self._can_merge_content(file_path, original_path):
            # Возвращаем существующий путь для слияния
            return file_path, False
        else:
            # Создаем новый файл с суффиксом
            return self._create_unique_path(project_dir, original_path), True

    def _can_merge_content(self, file_path: Path, original_path: str) -> bool:
        """🔥 НОВОЕ: Определяет, можно ли объединить содержимое файла"""
        try:
            # Читаем существующий файл
            with open(file_path, 'r', encoding='utf-8') as f:
                existing_content = f.read()
            
            # 🔥 ПРАВИЛА СЛИЯНИЯ:
            # - Python/JS файлы: можно объединять (добавлять функции/классы)
            # - HTML файлы: можно объединять (добавлять секции)
            # - CSS файлы: можно объединять (добавлять стили)
            # - SQL файлы: можно объединять (добавлять запросы)
            # - Markdown файлы: можно объединять (добавлять разделы)
            # - Конфигурационные файлы: НЕ объединяем (заменяем)
            
            file_extension = file_path.suffix.lower()
            mergeable_extensions = ['.py', '.js', '.html', '.css', '.sql', '.md', '.txt']
            
            if file_extension in mergeable_extensions:
                # Проверяем, не является ли файл конфигурационным
                config_files = ['requirements.txt', 'package.json', 'docker-compose.yml', 'Dockerfile', '.env']
                if file_path.name in config_files:
                    return False
                return True
            
            return False
            
        except Exception as e:
            logger.warning(f"⚠️ Не удалось прочитать файл {file_path}: {e}")
            return False

    def _create_unique_path(self, project_dir: Path, original_path: str) -> Path:
        """🔥 НОВОЕ: Создает уникальный путь с суффиксом"""
        file_path = project_dir / original_path
        original_path_obj = Path(original_path)
        stem = original_path_obj.stem
        suffix = original_path_obj.suffix
        counter = 1
        
        while file_path.exists():
            new_filename = f"{stem}_{counter}{suffix}"
            file_path = project_dir / original_path_obj.parent / new_filename
            counter += 1
        
        logger.debug(f"🔄 Создан уникальный путь: {original_path} → {file_path.name}")
        return file_path

    def _resolve_file_path(self, project_dir: Path, original_path: str) -> Path:
        """🔥 УСТАРЕЛО: Используйте _resolve_file_path_smart для умной обработки"""
        file_path, _ = self._resolve_file_path_smart(project_dir, original_path)
        return file_path

    def _append_to_file(self, file_path: Path, new_content: str, language: str):
        """🔥 НОВОЕ: Умно добавляет содержимое к существующему файлу"""
        try:
            # Читаем существующий файл
            with open(file_path, 'r', encoding='utf-8') as f:
                existing_content = f.read()
            
            # 🔥 УМНОЕ СЛИЯНИЕ ПО ТИПУ ФАЙЛА:
            if language in ['python', 'javascript']:
                # Для Python/JS: добавляем после последней функции/класса
                merged_content = self._merge_code_files(existing_content, new_content, language)
            elif language in ['html']:
                # Для HTML: добавляем в body или создаем новую секцию
                merged_content = self._merge_html_files(existing_content, new_content)
            elif language in ['css']:
                # Для CSS: добавляем в конец
                merged_content = self._merge_css_files(existing_content, new_content)
            elif language in ['sql']:
                # Для SQL: добавляем в конец
                merged_content = self._merge_sql_files(existing_content, new_content)
            elif language in ['markdown', 'text']:
                # Для Markdown: добавляем новый раздел
                merged_content = self._merge_markdown_files(existing_content, new_content)
            else:
                # Для остальных: просто добавляем в конец
                merged_content = existing_content + "\n\n" + new_content
            
            # Для Python дополнительно валидируем AST после слияния
            if (language or '').lower() in ['py', 'python']:
                try:
                    ast.parse(merged_content)
                except SyntaxError as e:
                    logger.warning(f"⚠️ AST валидация не прошла для {file_path}: {e}. Сохраняем новый модуль вместо порчи существующего")
                    # Создаем отдельный файл, чтобы не ломать существующий модуль
                    unique_path = self._create_unique_path(file_path.parent, file_path.name)
                    with open(unique_path, 'w', encoding='utf-8') as nf:
                        nf.write(new_content)
                    logger.info(f"✅ Новый модуль сохранен отдельно: {unique_path}")
                    return

            # Записываем объединенное содержимое (безопасно для непитоновых файлов или прошедший AST)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(merged_content)
                
            logger.debug(f"🔄 Содержимое добавлено к файлу: {file_path}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка слияния файла {file_path}: {e}")
            # При ошибке слияния создаем резервную копию
            backup_path = file_path.with_suffix(f"{file_path.suffix}.backup")
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(existing_content)
            logger.info(f"💾 Создана резервная копия: {backup_path}")

    def _merge_code_files(self, existing: str, new: str, language: str) -> str:
        """🔥 НОВОЕ: Умное слияние Python/JavaScript файлов"""
        # Убираем заголовки из нового содержимого
        lines = new.split('\n')
        content_lines = []
        header_ended = False
        
        for line in lines:
            if line.strip().startswith('#') and not header_ended:
                continue
            elif line.strip() == '' and not header_ended:
                continue
            else:
                header_ended = True
                content_lines.append(line)
        
        new_content = '\n'.join(content_lines).strip()
        
        # Добавляем разделитель и новое содержимое
        separator = "\n\n# " + "="*50 + f" Generated by {language} agent " + "="*50 + "\n\n"
        return existing.rstrip() + separator + new_content

    def _merge_html_files(self, existing: str, new: str) -> str:
        """🔥 НОВОЕ: Умное слияние HTML файлов"""
        # Убираем HTML комментарии-заголовки
        lines = new.split('\n')
        content_lines = []
        header_ended = False
        
        for line in lines:
            if line.strip().startswith('<!--') and not header_ended:
                continue
            elif line.strip() == '' and not header_ended:
                continue
            else:
                header_ended = True
                content_lines.append(line)
        
        new_content = '\n'.join(content_lines).strip()
        
        # Ищем body тег для вставки
        if '<body>' in existing and '</body>' in existing:
            body_start = existing.find('<body>') + len('<body>')
            body_end = existing.find('</body>')
            before_body = existing[:body_start]
            after_body = existing[body_end:]
            body_content = existing[body_start:body_end]
            
            separator = f"\n\n    <!-- {'='*30} Generated by HTML agent {'='*30} -->\n    "
            return before_body + body_content + separator + new_content + after_body
        else:
            # Если body нет, добавляем в конец
            separator = f"\n\n<!-- {'='*30} Generated by HTML agent {'='*30} -->\n"
            return existing.rstrip() + separator + new_content

    def _merge_css_files(self, existing: str, new: str) -> str:
        """🔥 НОВОЕ: Умное слияние CSS файлов"""
        # Убираем CSS комментарии-заголовки
        lines = new.split('\n')
        content_lines = []
        header_ended = False
        
        for line in lines:
            if line.strip().startswith('/*') and not header_ended:
                continue
            elif line.strip() == '' and not header_ended:
                continue
            else:
                header_ended = True
                content_lines.append(line)
        
        new_content = '\n'.join(content_lines).strip()
        
        # Добавляем разделитель и новое содержимое
        separator = f"\n\n/* {'='*30} Generated by CSS agent {'='*30} */\n"
        return existing.rstrip() + separator + new_content

    def _merge_sql_files(self, existing: str, new: str) -> str:
        """🔥 НОВОЕ: Умное слияние SQL файлов"""
        # Убираем SQL комментарии-заголовки
        lines = new.split('\n')
        content_lines = []
        header_ended = False
        
        for line in lines:
            if line.strip().startswith('--') and not header_ended:
                continue
            elif line.strip() == '' and not header_ended:
                continue
            else:
                header_ended = True
                content_lines.append(line)
        
        new_content = '\n'.join(content_lines).strip()
        
        # Добавляем разделитель и новое содержимое
        separator = f"\n\n-- {'='*30} Generated by SQL agent {'='*30}\n"
        return existing.rstrip() + separator + new_content

    def _merge_markdown_files(self, existing: str, new: str) -> str:
        """🔥 НОВОЕ: Умное слияние Markdown файлов"""
        # Убираем Markdown заголовки
        lines = new.split('\n')
        content_lines = []
        header_ended = False
        
        for line in lines:
            if line.strip().startswith('#') and not header_ended:
                continue
            elif line.strip() == '' and not header_ended:
                continue
            else:
                header_ended = True
                content_lines.append(line)
        
        new_content = '\n'.join(content_lines).strip()
        
        # Добавляем разделитель и новое содержимое
        separator = f"\n\n## {'='*30} Generated by Markdown agent {'='*30}\n\n"
        return existing.rstrip() + separator + new_content

    def _add_file_header(self, content: str, language: str, agent_id: str) -> str:
        """🔥 НОВОЕ: Добавляет заголовок файла с информацией об агенте"""
        header = f"Generated by {agent_id} agent\n"
        
        if language in ['python', 'javascript']:
            return f"# {header}\n{content}"
        elif language in ['html']:
            return f"<!-- {header} -->\n{content}"
        elif language in ['css']:
            return f"/* {header} */\n{content}"
        elif language in ['sql']:
            return f"-- {header}\n{content}"
        else:
            return f"# {header}\n{content}"

    def _extract_file_operations_like_agent(self, text: str, agent_id: str) -> List[Dict[str, Any]]:
        """🔥 УНИФИЦИРОВАННЫЙ ПАРСИНГ: Обрабатывает создание, редактирование и добавление файлов
        
        Args:
            text: Текст ответа агента
            agent_id: ID агента для правильного размещения файлов
        """
        ops: List[Dict[str, Any]] = []
        
        # 🔥 1. ПАРСИНГ КОМАНД РЕДАКТИРОВАНИЯ (EDIT, APPEND TO)
        edit_ops = self._extract_edit_operations(text, agent_id)
        ops.extend(edit_ops)
        
        # 🔥 2. ПАРСИНГ БЛОКОВ КОДА (создание новых файлов)
        code_ops = self._extract_code_block_operations(text, agent_id)
        ops.extend(code_ops)
        
        return ops

    def _extract_edit_operations(self, text: str, agent_id: str) -> List[Dict[str, Any]]:
        """🔥 НОВОЕ: Извлекает команды редактирования (EDIT, APPEND TO)"""
        ops: List[Dict[str, Any]] = []
        
        # 🔥 ПАТТЕРНЫ ДЛЯ КОМАНД РЕДАКТИРОВАНИЯ:
        # EDIT filename: content
        # APPEND TO filename: content
        # REPLACE filename: content
        # UPDATE filename: content
        
        edit_patterns = [
            # EDIT filename: content
            (r'EDIT\s+([\w/\-\.]+):\s*\n(.*?)(?=\n(?:EDIT|APPEND|REPLACE|UPDATE|```|$))', 'edit'),
            # APPEND TO filename: content  
            (r'APPEND\s+TO\s+([\w/\-\.]+):\s*\n(.*?)(?=\n(?:EDIT|APPEND|REPLACE|UPDATE|```|$))', 'append'),
            # REPLACE filename: content
            (r'REPLACE\s+([\w/\-\.]+):\s*\n(.*?)(?=\n(?:EDIT|APPEND|REPLACE|UPDATE|```|$))', 'replace'),
            # UPDATE filename: content
            (r'UPDATE\s+([\w/\-\.]+):\s*\n(.*?)(?=\n(?:EDIT|APPEND|REPLACE|UPDATE|```|$))', 'update'),
            # Более простые паттерны (без переноса строки)
            (r'EDIT\s+([\w/\-\.]+):\s*(.*?)(?=\n(?:EDIT|APPEND|REPLACE|UPDATE|```|$))', 'edit'),
            (r'APPEND\s+TO\s+([\w/\-\.]+):\s*(.*?)(?=\n(?:EDIT|APPEND|REPLACE|UPDATE|```|$))', 'append'),
            (r'REPLACE\s+([\w/\-\.]+):\s*(.*?)(?=\n(?:EDIT|APPEND|REPLACE|UPDATE|```|$))', 'replace'),
            (r'UPDATE\s+([\w/\-\.]+):\s*(.*?)(?=\n(?:EDIT|APPEND|REPLACE|UPDATE|```|$))', 'update')
        ]
        
        for pattern, action in edit_patterns:
            matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
            for filename, content in matches:
                if not content.strip():
                    continue
                
                # Определяем язык по расширению файла
                language = self._detect_language_by_filename(filename)
                
                # 🔥 УМНОЕ РАЗМЕЩЕНИЕ: Учитываем роль агента
                rel_path = self._map_agent_language_to_path(agent_id, language, filename, 0)
                
                ops.append({
                    'action': action,
                    'filename': filename,
                    'language': language,
                    'content': content.strip(),
                    'resolved_path': rel_path,
                    'is_edit_operation': True
                })
                
                logger.debug(f"🔄 Найдена команда {action}: {filename} → {rel_path}")
        
        return ops

    def _extract_code_block_operations(self, text: str, agent_id: str) -> List[Dict[str, Any]]:
        """🔥 НОВОЕ: Извлекает операции создания файлов из блоков кода"""
        ops: List[Dict[str, Any]] = []
        
        # Паттерн поддерживает синтаксис ```lang``` и ```lang: filename```
        pattern = r"```(\w+)(?::\s*([\w/\.\-]+))?\n(.*?)\n```"
        matches = re.findall(pattern, text, re.DOTALL)

        for i, (language, filename, code) in enumerate(matches):
            if not code.strip():
                continue

            filename = filename or self._extract_filename_from_code(code, language or 'text')
            # 🔥 ИСПРАВЛЕНО: Передаем agent_id для правильного размещения
            rel_path = self._map_agent_language_to_path(agent_id, language or 'text', filename, i)
            
            ops.append({
                'action': 'create',
                'filename': filename,
                'language': language or 'text',
                'content': code.strip(),
                'resolved_path': rel_path,
                'is_edit_operation': False
            })
        
        return ops

    def _detect_language_by_filename(self, filename: str) -> str:
        """🔥 НОВОЕ: Определяет язык программирования по имени файла"""
        if not filename:
            return 'text'
        
        # Извлекаем расширение
        if '.' in filename:
            ext = filename.split('.')[-1].lower()
        else:
            ext = filename.lower()
        
        # 🔥 МАППИНГ РАСШИРЕНИЙ НА ЯЗЫКИ:
        language_mapping = {
            # Python
            'py': 'python',
            'pyc': 'python',
            'pyo': 'python',
            'pyd': 'python',
            # JavaScript/TypeScript
            'js': 'javascript',
            'jsx': 'javascript',
            'ts': 'typescript',
            'tsx': 'typescript',
            'mjs': 'javascript',
            'cjs': 'javascript',
            # Web
            'html': 'html',
            'htm': 'html',
            'css': 'css',
            'scss': 'css',
            'sass': 'css',
            'less': 'css',
            # Backend
            'java': 'java',
            'kt': 'kotlin',
            'swift': 'swift',
            'go': 'go',
            'rs': 'rust',
            'cpp': 'cpp',
            'c': 'c',
            'cs': 'csharp',
            'php': 'php',
            'rb': 'ruby',
            # Database
            'sql': 'sql',
            'db': 'sql',
            'sqlite': 'sql',
            # Configuration
            'json': 'json',
            'yaml': 'yaml',
            'yml': 'yaml',
            'xml': 'xml',
            'toml': 'toml',
            'ini': 'ini',
            'cfg': 'ini',
            'conf': 'ini',
            # Documentation
            'md': 'markdown',
            'markdown': 'markdown',
            'rst': 'restructuredtext',
            'txt': 'text',
            # Scripts
            'sh': 'bash',
            'bash': 'bash',
            'zsh': 'bash',
            'fish': 'bash',
            'ps1': 'powershell',
            'bat': 'batch',
            'cmd': 'batch',
            # Docker
            'dockerfile': 'dockerfile',
            'docker': 'dockerfile',
            # Other
            'lock': 'text',
            'log': 'text',
            'tmp': 'text'
        }
        
        return language_mapping.get(ext, 'text')

    def _process_edit_operation(self, project_dir: Path, op: Dict[str, Any], agent_id: str):
        """🔥 НОВОЕ: Обрабатывает команды редактирования (EDIT, APPEND TO, REPLACE, UPDATE)"""
        file_path = project_dir / op['resolved_path']
        action = op['action']
        content = op['content']
        
        # Создаем директории если нужно
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            if action in ['edit', 'replace', 'update']:
                # 🔥 ЗАМЕНА/ОБНОВЛЕНИЕ: Полностью перезаписываем файл
                content_with_header = self._add_file_header(content, op['language'], agent_id)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content_with_header)
                logger.debug(f"🔄 Файл {file_path} заменен командой {action}")
                
            elif action == 'append':
                # 🔥 ДОБАВЛЕНИЕ: Добавляем содержимое к существующему файлу
                if file_path.exists():
                    # Файл существует - добавляем содержимое
                    content_with_header = self._add_file_header(content, op['language'], agent_id)
                    self._append_to_file(file_path, content_with_header, op['language'])
                    logger.debug(f"🔄 Содержимое добавлено к файлу {file_path}")
                else:
                    # Файл не существует - создаем новый
                    content_with_header = self._add_file_header(content, op['language'], agent_id)
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content_with_header)
                    logger.debug(f"✅ Создан новый файл {file_path} командой {action}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки команды {action} для файла {file_path}: {e}")

    def _process_create_operation(self, project_dir: Path, op: Dict[str, Any], agent_id: str):
        """🔥 НОВОЕ: Обрабатывает создание новых файлов из блоков кода"""
        # 🔥 УЛУЧШЕНО: Умное создание/обновление файлов
        file_path, is_new_file = self._resolve_file_path_smart(project_dir, op['resolved_path'])
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 🔥 УМНОЕ СЛИЯНИЕ: Объединяем содержимое или создаем новый
        if is_new_file:
            # Новый файл - создаем с заголовком
            content = self._add_file_header(op.get('content', ''), op.get('language', 'text'), agent_id)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"✅ Создан новый файл: {file_path}")
        else:
            # Существующий файл - добавляем содержимое
            content = self._add_file_header(op.get('content', ''), op.get('language', 'text'), agent_id)
            self._append_to_file(file_path, content, op.get('language', 'text'))
            logger.info(f"🔄 Обновлен существующий файл: {file_path}")

    def _extract_filename_from_code(self, code: str, language: str) -> Optional[str]:
        lines = code.split('\n')[:3]
        search_text = '\n'.join(lines)
        patterns = [
            r'#\s*([\w/\-\.]+\.[\w]+)',
            r'//\s*([\w/\-\.]+\.[\w]+)',
            r'/\*\s*([\w/\-\.]+\.[\w]+)\s*\*/',
            r'<!--\s*([\w/\-\.]+\.[\w]+)\s*-->',
            r'--\s*([\w/\-\.]+\.[\w]+)',
            r'^([\w/\-\.]+\.[\w]+)\s*$'
        ]
        for p in patterns:
            m = re.search(p, search_text, re.MULTILINE)
            if m:
                return m.group(1)
        return None

    def _map_agent_language_to_path(self, agent_id: str, language: str, filename: Optional[str], index: int) -> str:
        """🔥 УМНЫЙ МАППИНГ: Размещает файлы по роли агента и типу файла
        
        Args:
            agent_id: ID агента (например, 'backend_developer', 'frontend_developer')
            language: Язык/тип файла (например, 'python', 'javascript')
            filename: Имя файла (если указано)
            index: Индекс файла для fallback имен
        
        Returns:
            str: Относительный путь к файлу
        """
        # 🔥 ПРАВИЛА РАЗМЕЩЕНИЯ ПО АГЕНТАМ:
        agent_paths = {
            # Backend разработка
            'backend_developer': {
                'python': 'src/backend',
                'sql': 'src/database',
                'json': 'config',
                'yaml': 'config',
                'text': 'src/backend',
                'default': 'src/backend'
            },
            # Frontend разработка
            'frontend_developer': {
                'javascript': 'src/frontend',
                'html': 'src/frontend',
                'css': 'src/frontend',
                'typescript': 'src/frontend',
                'jsx': 'src/frontend',
                'tsx': 'src/frontend',
                'text': 'src/frontend',
                'default': 'src/frontend'
            },
            # Mobile разработка
            'mobile_developer': {
                'javascript': 'src/mobile',
                'typescript': 'src/mobile',
                'jsx': 'src/mobile',
                'tsx': 'src/mobile',
                'swift': 'src/mobile/ios',
                'kotlin': 'src/mobile/android',
                'java': 'src/mobile/android',
                'text': 'src/mobile',
                'default': 'src/mobile'
            },
            # База данных
            'database_engineer': {
                'sql': 'src/database',
                'python': 'src/database',
                'yaml': 'config',
                'text': 'src/database',
                'default': 'src/database'
            },
            # DevOps
            'devops_engineer': {
                'yaml': '',
                'dockerfile': '',
                'bash': 'scripts',
                'shell': 'scripts',
                'text': 'scripts',
                'default': 'scripts'
            },
            # QA тестирование
            'qa_tester': {
                'python': 'tests',
                'javascript': 'tests',
                'typescript': 'tests',
                'yaml': 'tests',
                'text': 'tests',
                'default': 'tests'
            },
            # UI/UX дизайн
            'ui_ux_designer': {
                'css': 'src/frontend/styles',
                'html': 'src/frontend/templates',
                'scss': 'src/frontend/styles',
                'sass': 'src/frontend/styles',
                'text': 'src/frontend/design',
                'default': 'src/frontend/design'
            },
            # Data Science
            'data_scientist': {
                'python': 'src/analytics',
                'jupyter': 'notebooks',
                'r': 'src/analytics',
                'text': 'src/analytics',
                'default': 'src/analytics'
            },
            # Интеграции
            'integration_specialist': {
                'python': 'src/integrations',
                'javascript': 'src/integrations',
                'yaml': 'config',
                'json': 'config',
                'text': 'src/integrations',
                'default': 'src/integrations'
            },
            # Безопасность
            'security_specialist': {
                'python': 'src/security',
                'javascript': 'src/security',
                'yaml': 'config',
                'text': 'src/security',
                'default': 'src/security'
            },
            # Производительность
            'performance_engineer': {
                'python': 'src/performance',
                'javascript': 'src/performance',
                'yaml': 'config',
                'text': 'src/performance',
                'default': 'src/performance'
            },
            # Техническая документация
            'technical_writer': {
                'markdown': 'docs',
                'text': 'docs',
                'default': 'docs'
            },
            # Code Reviewer
            'code_reviewer': {
                'markdown': 'docs/reviews',
                'text': 'docs/reviews',
                'default': 'docs/reviews'
            },
            # Bug Fixer
            'bug_fixer': {
                'python': 'src/fixes',
                'javascript': 'src/fixes',
                'text': 'src/fixes',
                'default': 'src/fixes'
            },
            # Product Owner и Project Manager
            'product_owner': {
                'markdown': 'docs/requirements',
                'text': 'docs/requirements',
                'default': 'docs/requirements'
            },
            'project_manager': {
                'markdown': 'docs/planning',
                'text': 'docs/planning',
                'default': 'docs/planning'
            },
            # System Architect
            'system_architect': {
                'markdown': 'docs/architecture',
                'yaml': 'config',
                'text': 'docs/architecture',
                'default': 'docs/architecture'
            }
        }
        
        # Если есть явное имя файла с путем - используем его
        if filename and '/' in filename:
            return filename
        
        # 🔥 УМНАЯ ЛОГИКА: Определяем базовый путь по агенту и языку
        agent_config = agent_paths.get(agent_id, {})
        language_key = language.lower()
        
        # Ищем подходящий путь для языка
        base_path = None
        if language_key in agent_config:
            base_path = agent_config[language_key]
        elif 'default' in agent_config:
            base_path = agent_config['default']
        else:
            # Fallback: определяем по расширению файла
            base_path = self._get_fallback_path_by_language(language_key)
        
        # Если есть явное имя файла без пути - добавляем к базовому пути
        if filename:
            return f"{base_path}/{filename}" if base_path else filename
        
        # Fallback: создаем имя файла по индексу
        ext = self._get_file_extension(language_key)
        fallback_name = f"file_{index}{ext}"
        return f"{base_path}/{fallback_name}" if base_path else fallback_name

    def _get_fallback_path_by_language(self, language: str) -> str:
        """🔥 НОВОЕ: Fallback маппинг по языку, если агент не найден"""
        fallback_paths = {
            'python': 'src/backend',
            'javascript': 'src/frontend',
            'typescript': 'src/frontend',
            'html': 'src/frontend',
            'css': 'src/frontend',
            'scss': 'src/frontend/styles',
            'sass': 'src/frontend/styles',
            'sql': 'src/database',
            'yaml': 'config',
            'yml': 'config',
            'json': 'config',
            'markdown': 'docs',
            'md': 'docs',
            'dockerfile': '',
            'bash': 'scripts',
            'shell': 'scripts',
            'swift': 'src/mobile/ios',
            'kotlin': 'src/mobile/android',
            'java': 'src/mobile/android',
            'r': 'src/analytics',
            'jupyter': 'notebooks',
            'ipynb': 'notebooks'
        }
        return fallback_paths.get(language, 'src')
    
    def _get_file_extension(self, language: str) -> str:
        """🔥 НОВОЕ: Возвращает расширение файла по языку"""
        extensions = {
            'python': '.py',
            'javascript': '.js',
            'typescript': '.ts',
            'html': '.html',
            'css': '.css',
            'scss': '.scss',
            'sass': '.sass',
            'sql': '.sql',
            'yaml': '.yml',
            'yml': '.yml',
            'json': '.json',
            'markdown': '.md',
            'md': '.md',
            'dockerfile': '',
            'bash': '.sh',
            'shell': '.sh',
            'swift': '.swift',
            'kotlin': '.kt',
            'java': '.java',
            'r': '.r',
            'jupyter': '.ipynb',
            'ipynb': '.ipynb',
            'text': '.txt'
        }
        return extensions.get(language.lower(), '.txt')

    def _analyze_project_technologies(self, project_dir: Path, agent_results: Dict) -> Dict[str, Any]:
        """🔥 НОВОЕ: Анализирует технологии, используемые в проекте
        
        Returns:
            Dict с информацией о технологиях:
            - has_python: bool - есть ли Python код
            - has_javascript: bool - есть ли JavaScript код
            - has_react: bool - есть ли React код
            - has_fastapi: bool - есть ли FastAPI код
            - has_flask: bool - есть ли Flask код
            - has_sql: bool - есть ли SQL файлы
            - has_docker: bool - есть ли Docker файлы
            - detected_dependencies: List[str] - обнаруженные зависимости
        """
        tech_info = {
            'has_python': False,
            'has_javascript': False,
            'has_react': False,
            'has_fastapi': False,
            'has_flask': False,
            'has_sql': False,
            'has_docker': False,
            'has_html': False,
            'has_css': False,
            'has_typescript': False,
            'has_mobile': False,
            'detected_dependencies': []
        }
        
        # 🔥 АНАЛИЗ ПО АГЕНТАМ: Проверяем, какие агенты успешно отработали
        successful_agents = set()
        for agent_id, results in agent_results.items():
            if results and any(r.success for r in results):
                successful_agents.add(agent_id)
        
        # 🔥 АНАЛИЗ ПО ТИПАМ ФАЙЛОВ: Сканируем созданные файлы
        for root, dirs, files in os.walk(project_dir):
            for file in files:
                file_path = Path(root) / file
                rel_path = file_path.relative_to(project_dir)
                
                # Определяем тип файла по расширению
                if file.endswith('.py'):
                    tech_info['has_python'] = True
                    # Анализируем содержимое Python файлов
                    self._analyze_python_dependencies(file_path, tech_info)
                elif file.endswith('.js') or file.endswith('.jsx'):
                    tech_info['has_javascript'] = True
                    # Анализируем содержимое JavaScript файлов
                    self._analyze_javascript_dependencies(file_path, tech_info)
                elif file.endswith('.ts') or file.endswith('.tsx'):
                    tech_info['has_typescript'] = True
                    tech_info['has_javascript'] = True
                elif file.endswith('.html'):
                    tech_info['has_html'] = True
                elif file.endswith('.css') or file.endswith('.scss') or file.endswith('.sass'):
                    tech_info['has_css'] = True
                elif file.endswith('.sql'):
                    tech_info['has_sql'] = True
                elif file in ['Dockerfile', 'docker-compose.yml', 'docker-compose.yaml']:
                    tech_info['has_docker'] = True
                elif file.endswith('.swift') or file.endswith('.kt') or file.endswith('.java'):
                    tech_info['has_mobile'] = True
        
        # 🔥 АНАЛИЗ ПО АГЕНТАМ: Дополнительная информация
        if 'backend_developer' in successful_agents:
            tech_info['has_python'] = True  # Backend обычно на Python
        if 'frontend_developer' in successful_agents:
            tech_info['has_javascript'] = True
            tech_info['has_html'] = True
            tech_info['has_css'] = True
        if 'mobile_developer' in successful_agents:
            tech_info['has_mobile'] = True
        if 'database_engineer' in successful_agents:
            tech_info['has_sql'] = True
        
        return tech_info

    def _analyze_python_dependencies(self, file_path: Path, tech_info: Dict[str, Any]):
        """🔥 НОВОЕ: Анализирует зависимости в Python файлах"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 🔥 ОБНАРУЖЕНИЕ ИМПОРТОВ И ИСПОЛЬЗОВАНИЯ:
            if 'from fastapi import' in content or 'import fastapi' in content:
                tech_info['has_fastapi'] = True
                tech_info['detected_dependencies'].extend(['fastapi', 'uvicorn'])
            if 'from flask import' in content or 'import flask' in content:
                tech_info['has_flask'] = True
                tech_info['detected_dependencies'].extend(['flask', 'gunicorn'])
            if 'from sqlalchemy import' in content or 'import sqlalchemy' in content:
                tech_info['detected_dependencies'].extend(['sqlalchemy'])
            if 'from pydantic import' in content or 'import pydantic' in content:
                tech_info['detected_dependencies'].extend(['pydantic'])
            if 'import requests' in content:
                tech_info['detected_dependencies'].extend(['requests'])
            if 'from dotenv import' in content or 'import dotenv' in content:
                tech_info['detected_dependencies'].extend(['python-dotenv'])
            if 'import pytest' in content or 'from pytest import' in content:
                tech_info['detected_dependencies'].extend(['pytest'])
            if 'import pandas' in content or 'from pandas import' in content:
                tech_info['detected_dependencies'].extend(['pandas'])
            if 'import numpy' in content or 'from numpy import' in content:
                tech_info['detected_dependencies'].extend(['numpy'])
            if 'import matplotlib' in content or 'from matplotlib import' in content:
                tech_info['detected_dependencies'].extend(['matplotlib'])
            if 'import seaborn' in content or 'from seaborn import' in content:
                tech_info['detected_dependencies'].extend(['seaborn'])
            if 'import jupyter' in content or 'from jupyter import' in content:
                tech_info['detected_dependencies'].extend(['jupyter'])
            
        except Exception as e:
            logger.warning(f"⚠️ Не удалось проанализировать Python файл {file_path}: {e}")

    def _analyze_javascript_dependencies(self, file_path: Path, tech_info: Dict[str, Any]):
        """🔥 НОВОЕ: Анализирует зависимости в JavaScript файлах"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 🔥 ОБНАРУЖЕНИЕ ИМПОРТОВ И ИСПОЛЬЗОВАНИЯ:
            if 'import React' in content or 'from "react"' in content or 'require("react")' in content:
                tech_info['has_react'] = True
                tech_info['detected_dependencies'].extend(['react', 'react-dom'])
            if 'import axios' in content or 'from "axios"' in content or 'require("axios")' in content:
                tech_info['detected_dependencies'].extend(['axios'])
            if 'import express' in content or 'from "express"' in content or 'require("express")' in content:
                tech_info['detected_dependencies'].extend(['express'])
            if 'import vue' in content or 'from "vue"' in content or 'require("vue")' in content:
                tech_info['detected_dependencies'].extend(['vue'])
            if 'import angular' in content or 'from "angular"' in content or 'require("angular")' in content:
                tech_info['detected_dependencies'].extend(['@angular/core', '@angular/common'])
            if 'import jquery' in content or 'from "jquery"' in content or 'require("jquery")' in content:
                tech_info['detected_dependencies'].extend(['jquery'])
            if 'import lodash' in content or 'from "lodash"' in content or 'require("lodash")' in content:
                tech_info['detected_dependencies'].extend(['lodash'])
            if 'import moment' in content or 'from "moment"' in content or 'require("moment")' in content:
                tech_info['detected_dependencies'].extend(['moment'])
            if 'import webpack' in content or 'from "webpack"' in content or 'require("webpack")' in content:
                tech_info['detected_dependencies'].extend(['webpack'])
            if 'import jest' in content or 'from "jest"' in content or 'require("jest")' in content:
                tech_info['detected_dependencies'].extend(['jest'])
            
        except Exception as e:
            logger.warning(f"⚠️ Не удалось проанализировать JavaScript файл {file_path}: {e}")

    # 🔥 УДАЛЕНО: Неиспользуемые методы _create_file_info и _get_file_extension
    # Логика создания файлов реализована напрямую в _process_agent_results
    # для избежания дублирования и упрощения поддержки кода
    
    # 🔥 УДАЛЕНО: Неиспользуемый метод _write_file
    # Запись файлов реализована напрямую в _process_agent_results
    # для упрощения логики и избежания дублирования
    
    async def _create_additional_files(self, project_dir: Path, project_context, agent_results: Dict = None) -> List[str]:
        """🔥 УМНОЕ СОЗДАНИЕ: Создает дополнительные файлы проекта на основе реальных технологий
        
        Args:
            project_dir: Директория проекта
            project_context: Контекст проекта
            agent_results: Результаты агентов для анализа технологий
        """
        created_files = []
        
        # 🔥 АНАЛИЗ ТЕХНОЛОГИЙ: Определяем, что реально используется
        tech_info = self._analyze_project_technologies(project_dir, agent_results or {})
        
        # .gitignore (всегда создаем)
        gitignore_content = self._create_gitignore_content(tech_info)
        gitignore_path = project_dir / ".gitignore"
        with open(gitignore_path, 'w') as f:
            f.write(gitignore_content)
        created_files.append(str(gitignore_path))
        
        # 🔥 УСЛОВНАЯ ГЕНЕРАЦИЯ requirements.txt
        if tech_info['has_python']:
            requirements_content = self._create_requirements_content(tech_info)
            req_path = project_dir / "requirements.txt"
            with open(req_path, 'w') as f:
                f.write(requirements_content)
            created_files.append(str(req_path))
            logger.info(f"✅ Создан requirements.txt с зависимостями: {tech_info['detected_dependencies']}")
        else:
            logger.info("ℹ️ Python код не обнаружен, requirements.txt не создается")
        
        # 🔥 УСЛОВНАЯ ГЕНЕРАЦИЯ package.json
        # Создаем для любых проектов, где обнаружены JS/TS/React/Vue/Angular или фронтенд-артефакты
        if tech_info['has_javascript'] or tech_info['has_typescript'] or tech_info.get('has_react'):
            package_json = self._create_package_json_content(project_context, tech_info)
            package_path = project_dir / "package.json"
            with open(package_path, 'w') as f:
                json.dump(package_json, f, indent=2)
            created_files.append(str(package_path))
            logger.info(f"✅ Создан package.json с зависимостями: {tech_info['detected_dependencies']}")
        else:
            logger.info("ℹ️ JavaScript/TypeScript код не обнаружен, package.json не создается")
        
        # 🔥 УСЛОВНАЯ ГЕНЕРАЦИЯ Docker файлов
        if tech_info['has_docker']:
            docker_files = await self._create_docker_files(project_dir, tech_info)
            created_files.extend(docker_files)
            logger.info("✅ Созданы Docker файлы")
        
        # 🔥 УСЛОВНАЯ ГЕНЕРАЦИЯ конфигурационных файлов
        if tech_info['has_sql']:
            db_config = self._create_database_config(project_dir, tech_info)
            if db_config:
                created_files.append(db_config)
                logger.info("✅ Создана конфигурация базы данных")
        
        return created_files

    def _create_gitignore_content(self, tech_info: Dict[str, Any]) -> str:
        """🔥 НОВОЕ: Создает .gitignore на основе используемых технологий"""
        gitignore_sections = []
        
        # Python секция
        if tech_info['has_python']:
            gitignore_sections.append("""
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
.env
.venv
pip-log.txt
pip-delete-this-directory.txt
.coverage
.pytest_cache/
""")

        # Node.js секция
        if tech_info['has_javascript'] or tech_info['has_typescript']:
            gitignore_sections.append("""
# Node.js
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
.npm
.yarn-integrity
""")
        
        # Mobile секция
        if tech_info['has_mobile']:
            gitignore_sections.append("""
# Mobile
*.ipa
*.apk
*.aab
build/
DerivedData/
*.xcworkspace/
*.xcodeproj/
""")
        
        # Общие секции
        gitignore_sections.append("""
# Logs
logs/
*.log

# OS
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
*.swp
*.swo

# Build
build/
dist/
""")
        
        return "\n".join(gitignore_sections)

    def _create_requirements_content(self, tech_info: Dict[str, Any]) -> str:
        """🔥 НОВОЕ: Создает requirements.txt на основе обнаруженных зависимостей"""
        # 🔥 БАЗОВЫЕ ЗАВИСИМОСТИ: Всегда добавляем основные
        base_deps = [
            "python-dotenv>=1.0.0",
            "requests>=2.31.0"
        ]
        
        # 🔥 ОБНАРУЖЕННЫЕ ЗАВИСИМОСТИ: Добавляем то, что реально используется
        detected_deps = list(set(tech_info['detected_dependencies']))  # Убираем дубликаты
        
        # 🔥 УМНЫЕ ВЕРСИИ: Определяем версии по фреймворку
        if tech_info['has_fastapi']:
            detected_deps.extend([
                "fastapi>=0.104.0",
                "uvicorn[standard]>=0.24.0"
            ])
        elif tech_info['has_flask']:
            detected_deps.extend([
                "flask>=3.0.0",
                "gunicorn>=21.0.0"
            ])
        
        if tech_info['has_sql']:
            detected_deps.extend([
                "sqlalchemy>=2.0.0",
                "alembic>=1.12.0"
            ])
        
        # 🔥 ТЕСТИРОВАНИЕ: Добавляем если есть тесты
        if any('test' in dep.lower() for dep in detected_deps) or 'pytest' in detected_deps:
            detected_deps.append("pytest>=7.4.0")
        
        # 🔥 DATA SCIENCE: Добавляем если используется
        if any(dep in detected_deps for dep in ['pandas', 'numpy', 'matplotlib', 'seaborn']):
            detected_deps.extend([
                "pandas>=2.0.0",
                "numpy>=1.24.0"
            ])
        
        # 🔥 СОБИРАЕМ ВСЕ ЗАВИСИМОСТИ
        all_deps = base_deps + detected_deps
        all_deps = list(set(all_deps))  # Убираем дубликаты
        
        # 🔥 СОРТИРУЕМ И ФОРМАТИРУЕМ
        all_deps.sort()
        
        requirements_content = f"""# 🔥 Автоматически сгенерированный requirements.txt
# Обнаруженные зависимости: {', '.join(detected_deps) if detected_deps else 'не обнаружены'}

"""
        requirements_content += "\n".join(all_deps)
        
        return requirements_content

    def _create_package_json_content(self, project_context, tech_info: Dict[str, Any]) -> Dict[str, Any]:
        """🔥 НОВОЕ: Создает package.json на основе обнаруженных технологий"""
        # 🔥 ОПРЕДЕЛЯЕМ ТИП ПРОЕКТА
        project_type = "node"
        if tech_info['has_react']:
            project_type = "react"
        elif tech_info.get('has_vue', False):
            project_type = "vue"
        elif tech_info.get('has_angular', False):
            project_type = "angular"
        
        # 🔥 БАЗОВАЯ КОНФИГУРАЦИЯ
        package_json = {
            "name": project_context.name.lower().replace(' ', '-'),
            "version": "1.0.0",
            "description": project_context.description,
            "type": "module" if tech_info['has_typescript'] else "commonjs",
            "scripts": {}
        }
        
        # 🔥 УМНЫЕ СКРИПТЫ: В зависимости от типа проекта
        if project_type == "react":
            package_json["scripts"] = {
                "start": "react-scripts start",
                "build": "react-scripts build",
                "test": "react-scripts test",
                "eject": "react-scripts eject"
            }
            package_json["main"] = "src/frontend/index.js"
        elif project_type == "vue":
            package_json["scripts"] = {
                "serve": "vue-cli-service serve",
                "build": "vue-cli-service build",
                "test:unit": "vue-cli-service test:unit"
            }
            package_json["main"] = "src/frontend/main.js"
        else:
            # Node.js проект
            package_json["scripts"] = {
                "start": "node src/frontend/app.js",
                "dev": "nodemon src/frontend/app.js",
                "test": "jest"
            }
            package_json["main"] = "src/frontend/app.js"
        
        # 🔥 ЗАВИСИМОСТИ: Добавляем только то, что реально используется
        dependencies = {}
        dev_dependencies = {}
        
        # 🔥 ОБНАРУЖЕННЫЕ ЗАВИСИМОСТИ
        for dep in tech_info['detected_dependencies']:
            if dep in ['react', 'react-dom']:
                dependencies[dep] = "^18.0.0"
            elif dep in ['vue']:
                dependencies[dep] = "^3.0.0"
            elif dep in ['express']:
                dependencies[dep] = "^4.18.0"
            elif dep in ['axios']:
                dependencies[dep] = "^1.0.0"
            elif dep in ['lodash']:
                dependencies[dep] = "^4.17.0"
            elif dep in ['moment']:
                dependencies[dep] = "^2.29.0"
            elif dep in ['jquery']:
                dependencies[dep] = "^3.7.0"
        
        # 🔥 DEV ЗАВИСИМОСТИ
        if tech_info['has_typescript']:
            dev_dependencies["typescript"] = "^5.0.0"
            dev_dependencies["@types/node"] = "^20.0.0"
        
        if any(dep in tech_info['detected_dependencies'] for dep in ['webpack', 'jest']):
            dev_dependencies["webpack"] = "^5.0.0"
            dev_dependencies["jest"] = "^29.0.0"
        
        # 🔥 ДОБАВЛЯЕМ В PACKAGE.JSON
        if dependencies:
            package_json["dependencies"] = dependencies
        if dev_dependencies:
            package_json["devDependencies"] = dev_dependencies
        
        return package_json

    async def _create_docker_files(self, project_dir: Path, tech_info: Dict[str, Any]) -> List[str]:
        """🔥 НОВОЕ: Создает Docker файлы если они нужны"""
        created_files = []
        
        # Dockerfile для Python
        if tech_info['has_python']:
            dockerfile_content = """# 🔥 Python Backend
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["uvicorn", "src.backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
"""
            dockerfile_path = project_dir / "Dockerfile"
            with open(dockerfile_path, 'w') as f:
                f.write(dockerfile_content)
            created_files.append(str(dockerfile_path))
        
        # docker-compose.yml
        if tech_info['has_python'] or tech_info['has_sql']:
            compose_content = """# 🔥 Docker Compose
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:password@db:5432/app
    depends_on:
      - db

  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=app
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
"""
            compose_path = project_dir / "docker-compose.yml"
            with open(compose_path, 'w') as f:
                f.write(compose_content)
            created_files.append(str(compose_path))
        
        return created_files

    def _create_database_config(self, project_dir: Path, tech_info: Dict[str, Any]) -> Optional[str]:
        """🔥 НОВОЕ: Создает конфигурацию базы данных если она нужна"""
        if not tech_info['has_sql']:
            return None
        
        config_content = """# 🔥 Конфигурация базы данных
DATABASE_URL=postgresql://user:password@localhost:5432/app
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20
"""
        config_path = project_dir / "config" / "database.env"
        config_path.parent.mkdir(exist_ok=True)
        
        with open(config_path, 'w') as f:
            f.write(config_content)
        
        return str(config_path)
    
    async def _create_readme(self, 
                           project_dir: Path, 
                           project_context, 
                           agent_results: Dict) -> Optional[str]:
        """Создает README файл"""
        try:
            readme_content = f"""# {project_context.name}

## Описание
{project_context.description}

## Автоматически сгенерированный проект
Этот проект был создан автоматически с помощью мульти-агентной системы.

### Участвовавшие агенты:
"""
            
            for agent_id, results in agent_results.items():
                if results and any(r.success for r in results):
                    agent_name = agent_id.replace('_', ' ').title()
                    readme_content += f"- **{agent_name}**: {len([r for r in results if r.success])} успешных задач\n"
            
            readme_content += f"""
## Структура проекта
```
{project_context.name}/
├── src/
│   ├── backend/     # Серверная часть
│   ├── frontend/    # Клиентская часть
│   ├── mobile/      # Мобильное приложение
│   └── database/    # База данных
├── tests/           # Тесты
├── docs/           # Документация
├── config/         # Конфигурация
└── scripts/        # Скрипты
```

## Установка и запуск

### Backend
```bash
pip install -r requirements.txt
python src/backend/app.py
```

### Frontend
```bash
npm install
npm start
```

## Статус разработки
- Итераций выполнено: {project_context.current_iteration}
- Статус: {project_context.status}
- Дата создания: {project_context.created_at}

---
*Проект создан автоматически с помощью AI агентов*
"""
            
            readme_path = project_dir / "README.md"
            with open(readme_path, 'w', encoding='utf-8') as f:
                f.write(readme_content)
                
            return str(readme_path)
            
        except Exception as e:
            logger.error(f"Ошибка создания README: {e}")
            return None

# 🔥 РЕФАКТОРИНГ ЗАВЕРШЕН:
# - Удалены неиспользуемые методы _create_file_info и _write_file
# - Удален неиспользуемый класс FileInfo
# - 🔥 ДОБАВЛЕНО УМНОЕ СЛИЯНИЕ: Автоматическое объединение содержимого файлов
# - 🔥 ДОБАВЛЕНО УМНОЕ РАЗМЕЩЕНИЕ: Файлы размещаются по роли агента и типу
# - 🔥 ДОБАВЛЕНЫ КОМАНДЫ РЕДАКТИРОВАНИЯ: Обработка EDIT, APPEND TO, REPLACE, UPDATE
# - 🔥 ДОБАВЛЕНА УСЛОВНАЯ ГЕНЕРАЦИЯ: Файлы создаются только при необходимости
# - Улучшена логика предотвращения конфликтов имен файлов
# - Добавлены методы слияния для разных типов файлов
# - Реализовано резервное копирование при ошибках
# - Код стал чище, умнее и проще в поддержке
