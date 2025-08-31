"""
Центральный мозг: извлекает инсайты из результатов агентов и формирует адресные директивы
"""
from dataclasses import dataclass
from typing import List, Dict, Any
import re


@dataclass
class Insight:
    source_agent: str
    severity: str
    message: str


@dataclass
class Directive:
    target_agent: str
    title: str
    description: str
    context: Dict[str, Any]


class BrainAgent:
    def __init__(self, logger):
        self.logger = logger

    def extract_insights(self, all_results: Dict[str, List[Any]]) -> List[Insight]:
        insights: List[Insight] = []
        
        # 🔥 ИСПРАВЛЕНО: Проверка на пустые результаты
        if not all_results:
            self.logger.warning("⚠️ Brain: all_results пуст, возвращаем пустой список insights")
            return []
        
        # Code Reviewer эвристики
        for r in all_results.get('code_reviewer', []):
            if not (getattr(r, 'success', False) and getattr(r, 'output', None)):
                continue
            txt = r.output.lower()
            
            # 🔥 ИСПРАВЛЕНО: Используем re.IGNORECASE и контекст для UX
            if re.search(r'контраст|типограф|ux|ui|accessibility|wcag', txt, re.IGNORECASE):
                # Проверяем контекст - это замечание или просто упоминание?
                if any(word in txt for word in ['проблема', 'ошибка', 'issue', 'error', 'замечание', 'нужно исправить']):
                    insights.append(Insight('code_reviewer', 'medium', 'Замечания по UX/контрасту'))
            
            # 🔥 ИСПРАВЛЕНО: Используем re.IGNORECASE и контекст для безопасности
            if re.search(r'critical|sql injection|xss|уязвимость|vulnerability|security issue', txt, re.IGNORECASE):
                # Проверяем контекст - это реальная проблема или просто упоминание?
                if any(word in txt for word in ['найдена', 'обнаружена', 'проблема', 'issue', 'error', 'нужно исправить', 'критично']):
                    insights.append(Insight('code_reviewer', 'high', 'Критические проблемы безопасности'))

        # QA эвристики
        for r in all_results.get('qa_tester', []):
            if not getattr(r, 'output', None):
                continue
            low = r.output.lower()
            
            # 🔥 ИСПРАВЛЕНО: Расширенный regex для различных паттернов ошибок
            test_failure_patterns = [
                r'failed|=== fail|assert.*false|assert.*raises',  # pytest/unittest
                r'error:|exception:|traceback:',  # Общие ошибки
                r'test.*failed|test.*error',  # Тестовые ошибки
                r'assertion.*failed|assertion.*error',  # Assertion ошибки
                r'failed.*tests|errors.*tests',  # Множественные ошибки
                r'✗|❌|FAIL|ERROR',  # Символы ошибок
                r'expected.*but.*got',  # Ошибки сравнения
                r'raised.*exception',  # Исключения
                r'broken|not working|doesn\'t work'  # Общие проблемы
            ]
            
            for pattern in test_failure_patterns:
                if re.search(pattern, low, re.IGNORECASE):
                    # Проверяем контекст - это реальная ошибка теста?
                    if any(word in low for word in ['test', 'pytest', 'unittest', 'assert', 'failed', 'error']):
                        insights.append(Insight('qa_tester', 'high', 'Падают тесты'))
                        break  # Не добавляем дубликаты

        return insights

    def derive_directives(self, project_ctx, insights: List[Insight]) -> List[Directive]:
        directives: List[Directive] = []
        
        # 🔥 ИСПРАВЛЕНО: Проверка на пустые insights
        if not insights:
            self.logger.info("ℹ️ Brain: insights пуст, возвращаем пустой список директив")
            return []
        
        # 🔥 ИСПРАВЛЕНО: Динамическая генерация директив на основе message
        for ins in insights:
            # UX/UI директивы
            if ins.source_agent == 'code_reviewer' and any(word in ins.message.lower() for word in ['ux', 'контраст', 'типограф', 'accessibility']):
                # 🔥 НОВОЕ: Динамический заголовок на основе message
                title = self._generate_ux_title(ins.message)
                description = self._generate_ux_description(ins.message)
                
                directives.append(Directive(
                    target_agent='ui_ux_designer',
                    title=title,
                    description=description,
                    context={
                        'project_name': project_ctx.name,
                        'source_insight': ins.message,
                        'severity': ins.severity
                    }
                ))
            
            # Безопасность директивы
            elif any(word in ins.message.lower() for word in ['безопас', 'security', 'уязвимость', 'vulnerability']) or (ins.severity == 'high' and ins.source_agent == 'code_reviewer'):
                title = self._generate_security_title(ins.message)
                description = self._generate_security_description(ins.message)
                
                directives.append(Directive(
                    target_agent='security_specialist',
                    title=title,
                    description=description,
                    context={
                        'project_name': project_ctx.name,
                        'source_insight': ins.message,
                        'severity': ins.severity
                    }
                ))
            
            # QA директивы
            elif ins.source_agent == 'qa_tester' and any(word in ins.message.lower() for word in ['падают тесты', 'failed', 'error', 'test']):
                title = self._generate_qa_title(ins.message)
                description = self._generate_qa_description(ins.message)
                
                directives.append(Directive(
                    target_agent='backend_developer',
                    title=title,
                    description=description,
                    context={
                        'project_name': project_ctx.name,
                        'source_insight': ins.message,
                        'severity': ins.severity
                    }
                ))
        
        # 🔥 НОВОЕ: Убираем дубликаты директив
        unique_directives = self._deduplicate_directives(directives)
        
        self.logger.info(f"✅ Brain: сгенерировано {len(unique_directives)} уникальных директив")
        return unique_directives
    
    def _generate_ux_title(self, message: str) -> str:
        """🔥 НОВОЕ: Динамически генерирует заголовок для UX директивы"""
        message_lower = message.lower()
        if 'контраст' in message_lower:
            return 'Улучшить контраст и читаемость'
        elif 'типограф' in message_lower:
            return 'Исправить типографические проблемы'
        elif 'accessibility' in message_lower or 'wcag' in message_lower:
            return 'Улучшить доступность (WCAG)'
        else:
            return 'Улучшить UX/UI дизайн'
    
    def _generate_ux_description(self, message: str) -> str:
        """🔥 НОВОЕ: Динамически генерирует описание для UX директивы"""
        message_lower = message.lower()
        if 'контраст' in message_lower:
            return 'Улучшить контраст цветов, состояния фокуса/hover, соответствие WCAG AA стандартам.'
        elif 'типограф' in message_lower:
            return 'Исправить размеры шрифтов, межстрочные интервалы, иерархию текста.'
        elif 'accessibility' in message_lower or 'wcag' in message_lower:
            return 'Добавить ARIA-атрибуты, улучшить навигацию с клавиатуры, соответствие WCAG 2.1.'
        else:
            return 'Общие улучшения UX: контраст, типографика, доступность, состояния интерактивных элементов.'
    
    def _generate_security_title(self, message: str) -> str:
        """🔥 НОВОЕ: Динамически генерирует заголовок для security директивы"""
        message_lower = message.lower()
        if 'sql injection' in message_lower:
            return 'Исправить SQL injection уязвимости'
        elif 'xss' in message_lower:
            return 'Исправить XSS уязвимости'
        elif 'уязвимость' in message_lower or 'vulnerability' in message_lower:
            return 'Исправить критические уязвимости безопасности'
        else:
            return 'Улучшить безопасность приложения'
    
    def _generate_security_description(self, message: str) -> str:
        """🔥 НОВОЕ: Динамически генерирует описание для security директивы"""
        message_lower = message.lower()
        if 'sql injection' in message_lower:
            return 'Использовать параметризованные запросы, валидацию ввода, ORM с экранированием.'
        elif 'xss' in message_lower:
            return 'Экранировать пользовательский ввод, использовать CSP заголовки, валидировать HTML.'
        elif 'уязвимость' in message_lower or 'vulnerability' in message_lower:
            return 'Включить валидации ввода, секреты из env, rate limiting, заголовки безопасности.'
        else:
            return 'Общие меры безопасности: валидация, аутентификация, авторизация, шифрование.'
    
    def _generate_qa_title(self, message: str) -> str:
        """🔥 НОВОЕ: Динамически генерирует заголовок для QA директивы"""
        message_lower = message.lower()
        if 'pytest' in message_lower:
            return 'Исправить падающие pytest тесты'
        elif 'unittest' in message_lower:
            return 'Исправить падающие unittest тесты'
        else:
            return 'Починить падающие тесты'
    
    def _generate_qa_description(self, message: str) -> str:
        """🔥 НОВОЕ: Динамически генерирует описание для QA директивы"""
        message_lower = message.lower()
        if 'pytest' in message_lower:
            return 'Разобраться с падениями pytest, исправить тесты, обновить фикстуры.'
        elif 'unittest' in message_lower:
            return 'Разобраться с падениями unittest, исправить тесты, обновить mock объекты.'
        else:
            return 'Разобраться с падениями тестов и исправить эндпоинты/валидацию.'
    
    def _deduplicate_directives(self, directives: List[Directive]) -> List[Directive]:
        """🔥 НОВОЕ: Убирает дубликаты директив на основе target_agent и title"""
        seen = set()
        unique_directives = []
        
        for directive in directives:
            # Создаем ключ для проверки дубликатов
            key = (directive.target_agent, directive.title)
            if key not in seen:
                seen.add(key)
                unique_directives.append(directive)
            else:
                self.logger.debug(f"🔄 Brain: пропускаем дубликат директивы {directive.target_agent} - {directive.title}")
        
        return unique_directives


