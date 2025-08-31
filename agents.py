"""
Система агентов для мульти-агентной разработки проектов
"""
import asyncio
import json
import logging
import time
import re
import os
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from pathlib import Path
from deepseek_client import deepseek_client
from config import AGENT_ROLES, AGENT_TIMEOUT, PROJECT_OUTPUT_DIR, CREATE_FILES_DURING_AGENTS

logger = logging.getLogger(__name__)

@dataclass
class AgentTask:
    """Задача для агента"""
    id: str
    description: str
    context: Dict[str, Any]
    priority: int = 1
    created_at: float = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()

@dataclass
class AgentResult:
    """Результат работы агента"""
    agent_id: str
    task_id: str
    success: bool
    output: str
    files_created: List[str] = None
    errors: List[str] = None
    execution_time: float = 0
    created_at: float = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
        if self.files_created is None:
            self.files_created = []
        if self.errors is None:
            self.errors = []

class BaseAgent(ABC):
    """🔥 Базовый класс для всех агентов
    
    ОСОБЕННОСТИ:
    - Управление статусом активности (is_active)
    - История выполнения задач
    - Унифицированная обработка ошибок
    - Интеграция с DeepSeek API
    """
    
    def __init__(self, agent_id: str, role_config: Dict[str, Any]):
        self.agent_id = agent_id
        self.name = role_config.get('name', agent_id)
        self.description = role_config.get('description', '')
        self.prompt_template = role_config.get('prompt_template', '')
        # 🔥 НОВОЕ: запоминаем конфиг роли, чтобы читать флаги (например, use_reasoner)
        self.role_config = role_config
        self.is_active = True
        self.current_task = None
        self.results_history: List[AgentResult] = []
    
    async def execute_task(self, task: AgentTask) -> AgentResult:
        """Выполнить задачу - базовая реализация"""
        start_time = time.time()
        logger.info(f"{self.name} начинает выполнение задачи: {task.id}")
        
        try:
            prompt = self.format_prompt(task.description, task.context)
            
            # Некоторые агенты используют reasoner модель для сложных задач
            # 🔥 ИСПРАВЛЕНО: делаем настраиваемым через контекст/role_config с разумным дефолтом
            use_reasoner_cfg = None
            try:
                # 1) Прямой флаг в задаче
                use_reasoner_cfg = task.context.get('use_reasoner') if task and task.context else None
            except Exception:
                use_reasoner_cfg = None
            if use_reasoner_cfg is None:
                # 2) Флаг в конфиге роли агента (если добавлен там)
                use_reasoner_cfg = getattr(self, 'role_config', {}).get('use_reasoner') if hasattr(self, 'role_config') else None
            if use_reasoner_cfg is None:
                # 3) Дефолт: список ролей с повышенной потребностью в reasoner
                default_reasoner_agents = {
                    'project_manager', 'system_architect', 'product_owner',
                    'security_specialist', 'performance_engineer', 'bug_fixer'
                }
                use_reasoner_cfg = self.agent_id in default_reasoner_agents
            use_reasoner = bool(use_reasoner_cfg)
            
            response = await deepseek_client.generate_response_async(prompt, use_reasoner=use_reasoner)
            
            if response:
                logger.debug(f"Агент {self.agent_id} получил ответ размером {len(response)} символов")
                logger.debug(f"Первые 300 символов ответа: {response[:300]}...")
                
                # По конфигу: или создаем файлы сразу, или откладываем до финальной сборки
                files_created = []
                if CREATE_FILES_DURING_AGENTS:
                    logger.info(f"🔧 ВЫЗОВ _create_files_from_response для агента {self.agent_id}")
                    files_created = await self._create_files_from_response(response, task.context)
                    logger.info(f"🔧 РЕЗУЛЬТАТ _create_files_from_response: {len(files_created)} файлов")
                
                result = AgentResult(
                    agent_id=self.agent_id,
                    task_id=task.id,
                    success=True,
                    output=response,
                    files_created=files_created,
                    execution_time=time.time() - start_time
                )
                logger.info(f"{self.name} успешно завершил задачу {task.id}, создал {len(files_created)} файлов")
            else:
                result = AgentResult(
                    agent_id=self.agent_id,
                    task_id=task.id,
                    success=False,
                    output="",
                    errors=["Не удалось получить ответ от DeepSeek API"],
                    execution_time=time.time() - start_time
                )
                
        except Exception as e:
            logger.error(f"Ошибка в {self.name}: {e}")
            result = AgentResult(
                agent_id=self.agent_id,
                task_id=task.id,
                success=False,
                output="",
                errors=[str(e)],
                execution_time=time.time() - start_time
            )
            
        self.add_result(result)
        return result
    
    async def _create_files_from_response(self, response: str, context: Dict[str, Any]) -> List[str]:
        """Создает или редактирует файлы на основе ответа агента"""
        files_modified = []
        logger.debug(f"Агент {self.agent_id}: начинаем обработку ответа для создания файлов")
        
        # Если отключено создание файлов на этапе агентов — просто возвращаем пустой список
        if not CREATE_FILES_DURING_AGENTS:
            logger.info(
                f"📝 CREATE_FILES_DURING_AGENTS=False — агент {self.agent_id} не будет записывать файлы на этом этапе"
            )
            return []

        try:
            # Получаем директорию проекта
            project_name = context.get('project_name', 'UnknownProject')
            project_dir = Path(PROJECT_OUTPUT_DIR) / project_name
            project_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Директория проекта: {project_dir}")
            
            # 🔥 НОВОЕ: Проверяем качество ответа и при необходимости делаем повторный запрос
            validation = self._validate_agent_response(response)
            if not validation['is_valid']:
                logger.warning(f"⚠️ Ответ агента {self.agent_id} не прошел валидацию, пытаемся исправить...")
                
                # Получаем оригинальную задачу из контекста
                original_task = context.get('original_task')
                if original_task:
                    improved_response = await self._retry_with_improved_prompt(original_task, response, validation)
                    if improved_response != response:
                        logger.info(f"🔄 Используем улучшенный ответ для создания файлов")
                        response = improved_response
                        # Переизвлекаем операции с улучшенным ответом
                        file_operations = self._extract_file_operations(response)
                    else:
                        logger.warning(f"⚠️ Улучшение не удалось, используем оригинальный ответ")
                        file_operations = self._extract_file_operations(response)
                else:
                    logger.warning(f"⚠️ Не удалось получить оригинальную задачу для повторного запроса")
                    file_operations = self._extract_file_operations(response)
            else:
                # Извлекаем операции с файлами из ответа
                logger.debug(f"Извлекаем операции с файлами из ответа...")
                file_operations = self._extract_file_operations(response)
            
            logger.debug(f"Найдено операций с файлами: {len(file_operations)}")
            
            for i, operation in enumerate(file_operations):
                logger.debug(f"Обрабатываем операцию {i+1}: {operation}")
                file_path = self._resolve_file_path(project_dir, operation)
                logger.debug(f"Путь к файлу: {file_path}")
                
                if operation['action'] == 'create':
                    logger.debug(f"Создаем файл: {file_path}")
                    await self._create_new_file(file_path, operation, files_modified)
                elif operation['action'] == 'edit':
                    logger.debug(f"Редактируем файл: {file_path}")
                    await self._edit_existing_file(file_path, operation, files_modified)
                elif operation['action'] == 'append':
                    logger.debug(f"Добавляем к файлу: {file_path}")
                    await self._append_to_file(file_path, operation, files_modified)
                elif operation['action'] == 'delete_lines':
                    logger.debug(f"Удаляем строки из файла: {file_path}")
                    await self._delete_lines_from_file(file_path, operation, files_modified)
                else:
                    logger.warning(f"Неизвестная операция: {operation['action']}")
            
            logger.debug(f"Все операции обработаны. Всего создано/изменено файлов: {len(files_modified)}")
        
        except Exception as e:
            logger.error(f"Ошибка работы с файлами агентом {self.agent_id}: {e}")
        
        return files_modified
    
    async def _retry_with_improved_prompt(self, task: AgentTask, original_response: str, validation: Dict[str, Any]) -> str:
        """Повторный запрос с улучшенными инструкциями на основе валидации"""
        logger.info(f"🔄 Повторный запрос для агента {self.agent_id} с улучшенными инструкциями...")
        
        # Создаем улучшенный промпт
        improved_prompt = f"""
{task.description}

ВАЖНО: Ваш предыдущий ответ не прошел валидацию. Пожалуйста, исправьте следующие проблемы:

ПРОБЛЕМЫ:
{chr(10).join(f"- {issue}" for issue in validation['issues'])}

РЕКОМЕНДАЦИИ:
{chr(10).join(f"- {suggestion}" for suggestion in validation['suggestions'])}

ТРЕБОВАНИЯ К ФОРМАТУ:
1. Используйте блоки кода с указанием имен файлов: ```markdown: filename.md
2. Каждый файл должен содержать структурированный контент с заголовками
3. Минимальный размер ответа: 500 символов
4. Обязательно создайте файлы согласно вашей роли

Пожалуйста, предоставьте исправленный ответ с правильным форматированием.
"""
        
        try:
            # Повторный запрос к API
            from deepseek_client import deepseek_client
            response = await deepseek_client.generate_response_async(improved_prompt, use_reasoner=True)
            
            if response and len(response.strip()) > 100:
                logger.info(f"✅ Повторный запрос успешен: {len(response)} символов")
                return response
            else:
                logger.warning(f"⚠️ Повторный запрос не дал улучшенного результата")
                return original_response
                
        except Exception as e:
            logger.error(f"❌ Ошибка повторного запроса: {e}")
            return original_response
    
    def _validate_agent_response(self, text: str) -> Dict[str, Any]:
        """Проверяет качество ответа агента"""
        validation = {
            'is_valid': True,
            'issues': [],
            'suggestions': []
        }
        
        # Проверяем размер ответа
        if len(text.strip()) < 100:
            validation['is_valid'] = False
            validation['issues'].append('Ответ слишком короткий (менее 100 символов)')
            validation['suggestions'].append('Увеличить детализацию ответа')
        
        # Проверяем наличие блоков кода
        code_blocks = self._extract_code_blocks(text)
        if not code_blocks:
            validation['is_valid'] = False
            validation['issues'].append('Не найдено блоков кода для создания файлов')
            validation['suggestions'].append('Добавить блоки кода с указанием имен файлов')
        
        # Проверяем наличие ключевых слов
        key_phrases = ['markdown:', '```', 'File:', 'Document:', 'Create:']
        has_key_phrases = any(phrase in text for phrase in key_phrases)
        if not has_key_phrases:
            validation['issues'].append('Отсутствуют ключевые слова для создания файлов')
            validation['suggestions'].append('Использовать формат markdown: filename или ```language: filename')
        
        # Проверяем структуру ответа
        if not any(char in text for char in ['#', '-', '*', '1.', '2.']):
            validation['issues'].append('Ответ не имеет структуры (заголовки, списки)')
            validation['suggestions'].append('Добавить заголовки и структурированные списки')
        
        return validation

    def _extract_file_operations(self, text: str) -> List[Dict]:
        """Извлекает операции с файлами из ответа агента"""
        operations = []
        file_contents = {}  # Для объединения файлов и устранения дубликатов
        
        logger.debug(f"🔍 Начинаем парсинг ответа агента {self.agent_id}")
        logger.debug(f"📝 Размер ответа: {len(text)} символов")
        logger.debug(f"📝 Первые 500 символов: {text[:500]}...")
        
        # 🔥 НОВОЕ: Проверяем качество ответа
        validation = self._validate_agent_response(text)
        if not validation['is_valid']:
            logger.warning(f"⚠️ Ответ агента {self.agent_id} не прошел валидацию:")
            for issue in validation['issues']:
                logger.warning(f"  - {issue}")
            for suggestion in validation['suggestions']:
                logger.info(f"  💡 {suggestion}")
        
        # 1) Ищем директивы редактирования/добавления/удаления ПЕРВЫМИ — они имеют приоритет
        # EDIT / UPDATE / MODIFY filename:
        edit_patterns = [
            r'(?im)^EDIT\s+([\w/\.-]+):\s*\n([\s\S]*?)(?=\n\n^[A-Z]{3,}\b|\Z)',
            r'(?im)^UPDATE\s+([\w/\.-]+):\s*\n([\s\S]*?)(?=\n\n^[A-Z]{3,}\b|\Z)',
            r'(?im)^MODIFY\s+([\w/\.-]+):\s*\n([\s\S]*?)(?=\n\n^[A-Z]{3,}\b|\Z)'
        ]
        for pattern in edit_patterns:
            for filename, content in re.findall(pattern, text):
                operations.append({'action': 'edit', 'filename': filename.strip(), 'content': content.strip()})
        
        # APPEND TO / ADD TO filename:
        append_patterns = [
            r'(?im)^APPEND\s+TO\s+([\w/\.-]+):\s*\n([\s\S]*?)(?=\n\n^[A-Z]{3,}\b|\Z)',
            r'(?im)^ADD\s+TO\s+([\w/\.-]+):\s*\n([\s\S]*?)(?=\n\n^[A-Z]{3,}\b|\Z)'
        ]
        for pattern in append_patterns:
            for filename, content in re.findall(pattern, text):
                operations.append({'action': 'append', 'filename': filename.strip(), 'content': content.strip()})
        
        # DELETE LINES a-b FROM filename
        for a, b, filename in re.findall(r'(?im)^DELETE\s+LINES\s+(\d+)-(\d+)\s+FROM\s+([\w/\.-]+)', text):
            operations.append({'action': 'delete_lines', 'filename': filename.strip(), 'start_line': int(a), 'end_line': int(b)})
        
        # 2) Затем извлекаем блоки кода для CREATE, но фильтруем те, что дублируют файлы, уже попавшие как EDIT/APPEND/DELETE
        code_blocks = self._extract_code_blocks(text)
        edited_filenames = {op['filename'] for op in operations if op['action'] in ('edit', 'append', 'delete_lines') and op.get('filename')}
        for i, (language, code, filename) in enumerate(code_blocks):
            if not code.strip():
                continue
            inferred_name = filename or self._infer_filename_from_content(language or 'text', code)
            if inferred_name and inferred_name in edited_filenames:
                # Если по этому файлу уже есть директива, игнорируем CREATE во избежание коллизий
                logger.debug(f"Игнорируем создание для {inferred_name}: есть директивы редактирования")
                continue
            key = inferred_name or f"unnamed_file_{i}"
            if key in file_contents:
                file_contents[key]['content'] += '\n\n' + code.strip()
            else:
                file_contents[key] = {
                    'action': 'create',
                    'filename': inferred_name,
                    'language': language,
                    'content': code.strip(),
                    'index': i
                }
        
        operations.extend(file_contents.values())
        
        logger.debug(f"🔍 Результат парсинга для агента {self.agent_id}:")
        logger.debug(f"  - Найдено операций: {len(operations)}")
        logger.debug(f"  - Операции: {[op.get('action', 'unknown') + ':' + op.get('filename', 'unnamed') for op in operations]}")
        
        return operations

    def _infer_filename_from_content(self, language: str, content: str) -> str:
        """Пытается угадать имя файла по языку и содержимому"""
        try:
            lang = (language or 'text').lower()
            head = (content or '').strip()[:120].lower()
            full_lower = (content or '').lower()

            # Dockerfile
            if lang in ('dockerfile',) or head.startswith('from ') or '# dockerfile' in head:
                return 'Dockerfile'

            # docker-compose.yml
            if 'version:' in head and 'services:' in full_lower and lang in ('yaml', 'yml'):
                return 'docker-compose.yml'

            # GitHub Actions
            if 'github' in full_lower and 'workflow' in full_lower and lang in ('yaml', 'yml'):
                return '.github/workflows/ci.yml'

            # nginx
            if lang in ('nginx', 'conf') or ('server {' in content and 'nginx' in full_lower):
                return 'nginx.conf'

            # markdown docs: попробуем вытащить `# file.md`
            if lang in ('md', 'markdown'):
                m = re.search(r'^#\s*([A-Za-z0-9_\-./]+\.md)\b', content, re.MULTILINE)
                if m:
                    return m.group(1)
                return f'{self.agent_id}_document_{int(time.time())}.md'

            # python
            if lang in ('py', 'python'):
                if 'pytest' in full_lower:
                    return 'tests/test_generated.py'
                return f'{self.agent_id}_{int(time.time())}.py'

            # css/js/html defaults
            defaults = {
                'yaml': 'config.yml',
                'yml': 'config.yml',
                'json': 'config.json',
                'text': f'{self.agent_id}_{int(time.time())}.txt',
                'css': 'styles.css',
                'ts': 'index.ts',
                'tsx': 'App.tsx',
                'js': 'index.js',
                'html': 'index.html',
                'sql': 'schema.sql',
            }
            return defaults.get(lang, f'file_{int(time.time())}.txt')
        except Exception:
            return f'{self.agent_id}_{int(time.time())}.txt'
    
    async def _create_new_file(self, file_path: Path, operation: Dict, files_modified: List[str]):
        """Создает новый файл (если существует — перезаписывает с бэкапом)"""
        try:
            logger.debug(f"Создание файла {file_path}...")
            file_path.parent.mkdir(parents=True, exist_ok=True)
            content = operation.get('content', '')
            # Если файл уже есть — делаем бэкап и перезаписываем
            if file_path.exists():
                backup_path = file_path.with_suffix(file_path.suffix + f'.backup.{int(time.time())}')
                import shutil
                shutil.copy2(file_path, backup_path)
                logger.info(f"📦 Бэкап существующего файла: {backup_path}")
            with open(file_path, 'w', encoding='utf-8') as f:
                language = operation.get('language', 'text')
                comment = self._get_file_comment(language, self.name)
                if comment:
                    f.write(comment + '\n\n')
                f.write(content)
            files_modified.append(f"CREATED/OVERWRITTEN: {file_path}")
            logger.info(f"✅ Агент {self.agent_id} записал файл: {file_path}")
        except Exception as e:
            logger.error(f"❌ Ошибка создания файла {file_path}: {e}", exc_info=True)
    
    async def _edit_existing_file(self, file_path: Path, operation: Dict, files_modified: List[str]):
        """Редактирует существующий файл (заменяет содержимое)"""
        try:
            if not file_path.exists():
                # Если файл не существует, создаем новый
                await self._create_new_file(file_path, operation, files_modified)
                return
            
            # Сохраняем бэкап
            backup_path = file_path.with_suffix(file_path.suffix + f'.backup.{int(time.time())}')
            import shutil
            shutil.copy2(file_path, backup_path)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(operation['content'])
            
            files_modified.append(f"EDITED: {file_path}")
            logger.info(f"Агент {self.agent_id} отредактировал файл: {file_path} (бэкап: {backup_path})")
            
        except Exception as e:
            logger.error(f"Ошибка редактирования файла {file_path}: {e}")
    
    async def _append_to_file(self, file_path: Path, operation: Dict, files_modified: List[str]):
        """Добавляет содержимое к существующему файлу"""
        try:
            if not file_path.exists():
                # Если файл не существует, создаем новый
                await self._create_new_file(file_path, operation, files_modified)
                return
            
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write('\n\n' + operation['content'])
            
            files_modified.append(f"APPENDED: {file_path}")
            logger.info(f"Агент {self.agent_id} добавил содержимое к файлу: {file_path}")
            
        except Exception as e:
            logger.error(f"Ошибка добавления к файлу {file_path}: {e}")
    
    async def _delete_lines_from_file(self, file_path: Path, operation: Dict, files_modified: List[str]):
        """Удаляет строки из файла"""
        try:
            if not file_path.exists():
                logger.warning(f"Попытка удалить строки из несуществующего файла: {file_path}")
                return
            
            # Читаем файл
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Сохраняем бэкап
            backup_path = file_path.with_suffix(file_path.suffix + f'.backup.{int(time.time())}')
            import shutil
            shutil.copy2(file_path, backup_path)
            
            # Удаляем строки (нумерация с 1)
            start_line = operation['start_line'] - 1  # Преобразуем в индекс (с 0)
            end_line = operation['end_line']
            
            if 0 <= start_line < len(lines) and start_line < end_line:
                lines = lines[:start_line] + lines[end_line:]
                
                # Записываем обратно
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                
                files_modified.append(f"DELETED_LINES: {file_path} (lines {operation['start_line']}-{operation['end_line']})")
                logger.info(f"Агент {self.agent_id} удалил строки {operation['start_line']}-{operation['end_line']} из файла: {file_path}")
            
        except Exception as e:
            logger.error(f"Ошибка удаления строк из файла {file_path}: {e}")
    
    def _resolve_file_path(self, project_dir: Path, operation: Dict) -> Path:
        """Определяет путь к файлу для операции"""
        filename = operation.get('filename')
        
        if filename:
            # Если указан относительный путь, используем его
            if '/' in filename:
                return project_dir / filename
            else:
                # Если только имя файла, размещаем его в правильной директории
                if self.agent_id == 'backend_developer':
                    return project_dir / 'src' / 'backend' / filename
                elif self.agent_id == 'frontend_developer':
                    return project_dir / 'src' / 'frontend' / filename
                elif self.agent_id == 'database_engineer':
                    return project_dir / 'src' / 'database' / filename
                elif self.agent_id == 'qa_tester':
                    return project_dir / 'tests' / filename
                elif self.agent_id == 'devops_engineer':
                    return project_dir / filename  # Dockerfile, docker-compose.yml в корне
                else:
                    return project_dir / 'src' / filename
        else:
            # Генерируем имя файла
            return self._generate_filename(project_dir, operation.get('language', 'text'), operation.get('index', 0))
    
    def _extract_code_blocks(self, text: str) -> List[tuple]:
        """Извлекает блоки кода из текста"""
        code_blocks = []

        # Ищем блоки кода вида ```language``` или ```language: filename```
        pattern = r'```(\w+)(?::\s*([\w/\.\-]+))?\n(.*?)\n```'
        matches = re.findall(pattern, text, re.DOTALL)

        logger.debug(f"Найдено блоков кода: {len(matches)}")

        for language, filename, code in matches:
            if code.strip():
                # Пытаемся извлечь имя файла из комментариев или из первой строки
                filename = filename or self._extract_filename_from_code(code, language or 'text')
                code_blocks.append((language or 'text', code.strip(), filename))
                logger.debug(f"Найден блок кода: язык={language or 'text'}, размер={len(code)}, файл={filename}")

        # 2. Дополнительный поиск - ищем блоки с markdown: filename в тексте
        if not code_blocks:
            logger.debug("Блоки ``` не найдены, ищем markdown: filename в тексте...")
            markdown_inline_pattern = r'markdown:\s*([\w/\.\-]+)\n(.*?)(?=\n\n|\n#|\Z)'
            markdown_inline_matches = re.findall(markdown_inline_pattern, text, re.DOTALL | re.MULTILINE)

            for filename, code in markdown_inline_matches:
                if code.strip() and len(code.strip()) > 20:  # Минимум 20 символов
                    code_blocks.append(('markdown', code.strip(), filename))
                    logger.debug(f"✅ Найден inline markdown: файл={filename}, размер={len(code)}")
        
        # 3. Поиск по самым гибким паттернам - ищем любые упоминания файлов с контентом
        if not code_blocks:
            logger.debug("Ищем любые упоминания файлов с контентом...")
            # Паттерн для "filename:" или "filename" с последующим контентом
            flexible_pattern = r'(?:^|\n)(?:#\s*)?([\w/\.\-]+\.(?:md|txt|py|js|html|css|yml|yaml|json|sql|sh))(?:\s*[:：])?\s*\n(.*?)(?=\n(?:#|\n\n|\n[A-Z]|\Z))'
            flexible_matches = re.findall(flexible_pattern, text, re.DOTALL | re.MULTILINE)
            
            for filename, code in flexible_matches:
                if code.strip() and len(code.strip()) > 30:  # Минимум 30 символов
                    ext = Path(filename).suffix[1:] if Path(filename).suffix else 'text'
                    code_blocks.append((ext, code.strip(), filename))
                    logger.debug(f"✅ Найден гибкий паттерн: файл={filename}, размер={len(code)}")
        
        # 4. Поиск по заголовкам и ключевым словам - ищем разделы с именами файлов
        if not code_blocks:
            logger.debug("Ищем разделы с именами файлов по заголовкам...")
            # Паттерн для заголовков типа "## filename.md" или "### filename.md"
            header_pattern = r'#{2,3}\s*([\w/\.\-]+\.(?:md|txt|py|js|html|css|yml|yaml|json|sql|sh))\s*\n(.*?)(?=\n#{1,3}|\n\n|\Z)'
            header_matches = re.findall(header_pattern, text, re.DOTALL | re.MULTILINE)
            
            for filename, code in header_matches:
                if code.strip() and len(code.strip()) > 50:  # Минимум 50 символов для заголовков
                    ext = Path(filename).suffix[1:] if Path(filename).suffix else 'text'
                    code_blocks.append((ext, code.strip(), filename))
                    logger.debug(f"✅ Найден заголовок: файл={filename}, размер={len(code)}")
        
        # 5. Поиск по ключевым словам - ищем упоминания файлов в тексте
        if not code_blocks:
            logger.debug("Ищем упоминания файлов по ключевым словам...")
            # Паттерн для "File: filename" или "Document: filename"
            keyword_pattern = r'(?:File|Document|Create|Generate):\s*([\w/\.\-]+\.(?:md|txt|py|js|html|css|yml|yaml|json|sql|sh))\s*\n(.*?)(?=\n(?:File|Document|Create|Generate):|\n\n|\Z)'
            keyword_matches = re.findall(keyword_pattern, text, re.DOTALL | re.MULTILINE)
            
            for filename, code in keyword_matches:
                if code.strip() and len(code.strip()) > 40:  # Минимум 40 символов
                    ext = Path(filename).suffix[1:] if Path(filename).suffix else 'text'
                    code_blocks.append((ext, code.strip(), filename))
                    logger.debug(f"✅ Найден по ключевому слову: файл={filename}, размер={len(code)}")
        
        # 6. Дополнительный поиск - ищем блоки кода без закрывающих ```
        if not code_blocks:
            logger.debug("Блоки ``` не найдены, пытаемся найти код другими способами...")
            # Ищем код после упоминания файлов
            file_code_pattern = r'#\s*([\w/]+\.[\w]+)\n(.*?)(?=\n#|\n\n|$)'
            matches = re.findall(file_code_pattern, text, re.DOTALL | re.MULTILINE)
            
            for filename, code in matches:
                if code.strip() and len(code.strip()) > 10:  # Минимум 10 символов кода
                    ext = Path(filename).suffix[1:] if Path(filename).suffix else 'text'
                    code_blocks.append((ext, code.strip(), filename))
                    logger.debug(f"✅ Найден код через файл: {filename}, размер={len(code)}")
        
        # 9. Последняя попытка - ищем любые упоминания файлов в тексте
        if not code_blocks:
            logger.debug("Последняя попытка - ищем любые упоминания файлов...")
            # Ищем строки, начинающиеся с имени файла
            simple_file_pattern = r'^([\w/\.\-]+\.(?:md|txt|py|js|html|css|yml|yaml|json|sql|sh))\s*\n(.*?)(?=\n[\w/\.\-]+\.(?:md|txt|py|js|html|css|yml|yaml|json|sql|sh)|\n\n|\Z)'
            simple_matches = re.findall(simple_file_pattern, text, re.DOTALL | re.MULTILINE)
            
            for filename, code in simple_matches:
                if code.strip() and len(code.strip()) > 20:  # Минимум 20 символов
                    ext = Path(filename).suffix[1:] if Path(filename).suffix else 'text'
                    code_blocks.append((ext, code.strip(), filename))
                    logger.debug(f"✅ Найден простой паттерн: файл={filename}, размер={len(code)}")
                    
        logger.debug(f"🔍 ИТОГО найдено блоков кода: {len(code_blocks)}")
        for i, (lang, code, filename) in enumerate(code_blocks):
            logger.debug(f"  {i+1}. {lang}: {filename} ({len(code)} символов)")
        
        return code_blocks
    
    def _extract_filename_from_code(self, code: str, language: str) -> Optional[str]:
        """Извлекает имя файла из комментариев в коде"""
        # Ищем комментарии с именами файлов в первых 3 строках
        lines = code.split('\n')[:3]
        search_text = '\n'.join(lines)
        
        # Паттерны для разных языков
        patterns = [
            r'#\s*([\w/\-\.]+\.[\w]+)',  # Python/shell комментарии: # app.py
            r'//\s*([\w/\-\.]+\.[\w]+)',  # JS/C++ комментарии: // app.js
            r'/\*\s*([\w/\-\.]+\.[\w]+)\s*\*/',  # CSS/multi-line: /* styles.css */
            r'<!--\s*([\w/\-\.]+\.[\w]+)\s*-->', # HTML: <!-- index.html -->
            r'--\s*([\w/\-\.]+\.[\w]+)',  # SQL комментарии: -- schema.sql
            r'^([\w/\-\.]+\.[\w]+)\s*$',  # Просто имя файла на отдельной строке
        ]
        
        for pattern in patterns:
            match = re.search(pattern, search_text, re.MULTILINE)
            if match:
                filename = match.group(1)
                logger.debug(f"Извлечено имя файла из кода: {filename}")
                return filename
        
        logger.debug(f"Имя файла не найдено в коде (язык: {language})")
        return None
    
    def _generate_filename(self, project_dir: Path, language: str, index: int) -> Path:
        """Генерирует имя файла для агента"""
        extensions = {
            'python': '.py',
            'javascript': '.js',
            'html': '.html',
            'css': '.css',
            'sql': '.sql',
            'bash': '.sh',
            'json': '.json',
            'yaml': '.yml',
            'dockerfile': '',
            'markdown': '.md',
            'text': '.txt'
        }
        
        ext = extensions.get(language.lower(), '.txt')
        
        # Базовые директории для разных типов агентов
        if self.agent_id == 'backend_developer':
            base_dir = project_dir / 'src' / 'backend'
            base_name = f'app{ext}' if index == 0 else f'module_{index}{ext}'
        elif self.agent_id == 'frontend_developer':
            base_dir = project_dir / 'src' / 'frontend'
            base_name = f'index.html' if language == 'html' else f'main{ext}'
        elif self.agent_id == 'database_engineer':
            base_dir = project_dir / 'src' / 'database'
            base_name = f'schema.sql' if language == 'sql' else f'db_{index}{ext}'
        elif self.agent_id == 'qa_tester':
            base_dir = project_dir / 'tests'
            base_name = f'test_{index}{ext}'
        elif self.agent_id == 'devops_engineer':
            # Умные имена для DevOps файлов на основе языка и индекса
            if language == 'dockerfile':
                base_dir = project_dir
                base_name = 'Dockerfile'
            elif language == 'yaml':
                if index == 0:
                    base_dir = project_dir
                    base_name = 'docker-compose.yml'
                elif index == 1:
                    base_dir = project_dir / '.github' / 'workflows'
                    base_name = 'ci.yml'
                else:
                    base_dir = project_dir
                    base_name = f'config_{index}.yml'
            else:
                base_dir = project_dir
                base_name = f'deploy_{index}{ext}'
        elif self.agent_id in ['product_owner', 'project_manager', 'technical_writer', 'ui_ux_designer', 'security_specialist', 'performance_engineer', 'code_reviewer']:
            base_dir = project_dir / 'docs'
            base_name = f'{self.agent_id}_document_{index}{ext}'
        else:
            base_dir = project_dir / 'src'
            base_name = f'{self.agent_id}_{index}{ext}'
        
        return base_dir / base_name
    
    def _get_file_comment(self, language: str, agent_name: str) -> Optional[str]:
        """Возвращает комментарий для файла в зависимости от языка"""
        comments = {
            'python': f'# Generated by {agent_name}',
            'javascript': f'// Generated by {agent_name}',
            'css': f'/* Generated by {agent_name} */',
            'html': f'<!-- Generated by {agent_name} -->',
            'sql': f'-- Generated by {agent_name}',
            'bash': f'# Generated by {agent_name}',
            'markdown': f'<!-- Generated by {agent_name} -->',
            'yaml': f'# Generated by {agent_name}',
            'dockerfile': f'# Generated by {agent_name}',
            'json': f'// Generated by {agent_name}',
        }
        
        return comments.get(language.lower())
    
    def format_prompt(self, project_description: str, context: Dict[str, Any] = None) -> str:
        """Форматирует промпт для агента — безопасно, с дефолтами"""
        values = {
            'project_description': project_description,
            'requirements': '',
            'architecture': '',
            'database_schema': '',
            'ui_design': '',
            'api_spec': '',
            'product_requirements': '',
            'user_stories': '',
            'acceptance_criteria': '',
            'summary_report': '',
            'agent_artifacts': '',
            'code_reviewer_output': '',
            'qa_output': ''
        }
        if context:
            for k in values.keys():
                values[k] = context.get(k, values[k])
            # summary_report должен быть строкой
            values['summary_report'] = values['summary_report'] or ''
        # Форматируем один раз всем словарем
        prompt = self.prompt_template.format(**values)
        
        if context:
            append = []
            prev = context.get('previous_results') or []
            if prev:
                append.append(f"Последние результаты твоей роли (сжатые):\n{str(prev)[-800:]}")
            shared = context.get('shared_context') or []
            if shared:
                chunks = []
                for item in shared[-6:]:
                    chunks.append(f"[{item['agent']}] {item['output'][:400]}")
                append.append("Контекст от других агентов:\n" + "\n".join(chunks[:6]))
            if append:
                prompt += "\n\n" + "\n\n".join(append)
        
        return prompt
    
    def add_result(self, result: AgentResult):
        """Добавляет результат в историю"""
        self.results_history.append(result)
        
    def get_last_result(self) -> Optional[AgentResult]:
        """Получает последний результат"""
        return self.results_history[-1] if self.results_history else None

class ProjectManagerAgent(BaseAgent):
    """Агент проект-менеджера"""
    
    # Используем базовое execute_task с созданием файлов

class SystemArchitectAgent(BaseAgent):
    """Агент системного архитектора"""
    
    # Используем базовое execute_task с созданием файлов

class DeveloperAgent(BaseAgent):
    """Базовый класс для разработчиков"""
    
    def __init__(self, agent_id: str, role_config: Dict[str, Any], language: str = "python"):
        super().__init__(agent_id, role_config)
        self.language = language
        
    # Убираем переопределение execute_task - используем базовое с созданием файлов!

class BackendDeveloperAgent(DeveloperAgent):
    """Агент backend разработчика"""
    def __init__(self, agent_id: str, role_config: Dict[str, Any]):
        super().__init__(agent_id, role_config, "python")

class FrontendDeveloperAgent(DeveloperAgent):
    """Агент frontend разработчика"""  
    def __init__(self, agent_id: str, role_config: Dict[str, Any]):
        super().__init__(agent_id, role_config, "javascript")

class MobileDeveloperAgent(DeveloperAgent):
    """Агент mobile разработчика"""
    def __init__(self, agent_id: str, role_config: Dict[str, Any]):
        super().__init__(agent_id, role_config, "react-native")

class QATesterAgent(BaseAgent):
    """Агент QA тестировщика"""
    
    # Используем базовое execute_task с созданием файлов

class AgentFactory:
    """Фабрика для создания агентов"""
    
    @staticmethod
    def create_agent(agent_type: str, role_config: Dict[str, Any]) -> BaseAgent:
        """Создает агента по типу"""
        agent_classes = {
            "project_manager": ProjectManagerAgent,
            "system_architect": SystemArchitectAgent,
            "backend_developer": BackendDeveloperAgent,
            "frontend_developer": FrontendDeveloperAgent,
            "mobile_developer": MobileDeveloperAgent,
            "qa_tester": QATesterAgent,
            # Для остальных агентов используем базовый класс
            "database_engineer": BaseAgent,
            "devops_engineer": BaseAgent,
            "security_specialist": BaseAgent,
            "ui_ux_designer": BaseAgent,
            "data_scientist": BaseAgent,
            "technical_writer": BaseAgent,
            "performance_engineer": BaseAgent,
            "integration_specialist": BaseAgent,
            "code_reviewer": BaseAgent,
            "product_owner": BaseAgent
        }
        
        agent_class = agent_classes.get(agent_type, BaseAgent)
        return agent_class(agent_type, role_config)
    
    @staticmethod
    def create_all_agents() -> Dict[str, BaseAgent]:
        """Создает всех агентов из конфигурации"""
        agents = {}
        for agent_type, config in AGENT_ROLES.items():
            agents[agent_type] = AgentFactory.create_agent(agent_type, config)
        return agents
