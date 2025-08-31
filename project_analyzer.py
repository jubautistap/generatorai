"""
Анализатор проекта - определяет какие агенты нужны на основе описания
"""
import re
import logging
from typing import Dict, List, Set, Any
from config import AGENT_ROLES

logger = logging.getLogger(__name__)

class ProjectAnalyzer:
    """🔥 Анализирует описание проекта и определяет необходимых агентов
    
    ОСОБЕННОСТИ:
    - Автоматическое определение типа проекта
    - Умный выбор необходимых агентов
    - Динамическое отключение ненужных агентов
    - Оптимизация порядка выполнения
    """
    
    def __init__(self):
        # Ключевые слова для определения типа проекта
        self.project_types = {
            "web_only": [
                "веб-сайт", "веб-приложение", "сайт", "web site", "web app", 
                "интернет-магазин", "e-commerce", "блог", "портал", "landing page",
                "веб", "приложение"
            ],
            "mobile": [
                "мобильное приложение", "mobile app", "iOS", "Android", 
                "React Native", "Flutter", "мобильный", "смартфон", "мобильная версия",
                "мобильная", "версия", "app", "приложение"
            ],
            "desktop": [
                "десктопное приложение", "desktop app", "Windows", "macOS", 
                "Linux", "GUI", "интерфейс приложения"
            ],
            "api_only": [
                "API", "REST API", "GraphQL", "микросервис", "backend only", 
                "только бэкенд", "сервис", "endpoint"
            ]
        }
        
        # Ключевые слова для определения функциональности
        self.features = {
            "data_science": [
                "машинное обучение", "ML", "AI", "аналитика", "прогнозирование",
                "data science", "нейросеть", "классификация", "рекомендации",
                "статистика", "анализ данных", "big data"
            ],
            "integrations": [
                "интеграция", "API", "webhook", "платежи", "payment", "SMS",
                "email", "социальные сети", "third party", "сторонние сервисы",
                "платежная система", "банк", "карта", "платежными системами"
            ],
            "performance": [
                "высокие нагрузки", "масштабирование", "производительность",
                "кэширование", "оптимизация", "мониторинг", "метрики",
                "load balancing", "CDN", "балансировка"
            ],
            "security": [
                "безопасность", "аутентификация", "авторизация", "шифрование",
                "HTTPS", "SSL", "токены", "JWT", "OAuth", "защита данных",
                "GDPR", "персональные данные"
            ]
        }
        
        # Обязательные агенты для всех проектов
        self.required_agents = {
            "product_owner",
            "project_manager", 
            "system_architect",
            "backend_developer",
            "frontend_developer",
            "database_engineer",
            "qa_tester",
            "code_reviewer",
            "bug_fixer"
        }
        
        # Условные агенты
        self.conditional_agents = {
            "mobile_developer": "mobile",
            "data_scientist": "data_science", 
            "integration_specialist": "integrations",
            "performance_engineer": "performance",
            "security_specialist": "security",
            "devops_engineer": "web_only",  # DevOps нужен для веб-проектов
            "ui_ux_designer": "web_only",   # UI/UX нужен для веб-проектов
            "technical_writer": "web_only"   # Документация нужна для веб-проектов
        }
    
    def analyze_project(self, project_description: str) -> Dict[str, Any]:
        """Анализирует проект и возвращает рекомендации по агентам"""
        logger.info("🔍 Анализ проекта для определения необходимых агентов...")
        
        description_lower = project_description.lower()
        
        # Определяем тип проекта
        project_type = self._determine_project_type(description_lower)
        
        # Определяем нужные функции
        needed_features = self._determine_needed_features(description_lower)
        
        # Определяем необходимых агентов
        required_agents = self.required_agents.copy()
        conditional_agents = self._get_conditional_agents(project_type, needed_features)
        
        # Исключаем агентов, которые не нужны для данного типа проекта
        excluded_agents = self._get_excluded_agents(project_type, needed_features)
        
        # Формируем финальный список агентов
        final_agents = required_agents.union(conditional_agents)
        
        analysis = {
            "project_type": project_type,
            "needed_features": needed_features,
            "required_agents": list(required_agents),
            "conditional_agents": list(conditional_agents),
            "excluded_agents": list(excluded_agents),
            "final_agents": list(final_agents),
            "recommendations": self._generate_recommendations(project_type, needed_features)
        }
        
        logger.info(f"✅ Анализ завершен: {len(final_agents)} агентов, тип: {project_type}")
        return analysis

    def get_agent_activation_status(self, analysis: Dict[str, Any]) -> Dict[str, bool]:
        """🔥 НОВОЕ: Возвращает статус статус активации для каждого агента
        
        Args:
            analysis: Результат анализа проекта
            
        Returns:
            Dict[str, bool]: Маппинг agent_id -> is_active
        """
        final_agents = set(analysis.get('final_agents', []))
        excluded_agents = set(analysis.get('excluded_agents', []))
        
        # 🔥 ИСПРАВЛЕНО: Динамически генерируем на основе conditional_agents
        all_agents = set(self.required_agents).union(set(self.conditional_agents.keys()))
        
        # Определяем статус активации
        activation_status = {}
        for agent_id in all_agents:
            if agent_id in final_agents:
                activation_status[agent_id] = True  # Агент активен
            elif agent_id in excluded_agents:
                activation_status[agent_id] = False  # Агент отключен
            else:
                # 🔥 ИСПРАВЛЕНО: Если агент не в анализе - считаем его неактивным
                activation_status[agent_id] = False
        
        logger.info(f"🔥 Статус активации агентов: {sum(activation_status.values())} активных, {len(activation_status) - sum(activation_status.values())} отключенных")
        
        return activation_status
    
    def _determine_project_type(self, description: str) -> str:
        """Определяет тип проекта с поддержкой гибридных типов"""
        scores = {}
        
        for project_type, keywords in self.project_types.items():
            score = sum(1 for keyword in keywords if keyword in description)
            scores[project_type] = score
        
        # 🔥 ИСПРАВЛЕНО: Накопление всех совпадений для гибридных проектов
        detected_types = []
        for project_type, score in scores.items():
            if score > 0:
                detected_types.append((project_type, score))
        
        # Сортируем по количеству совпадений
        detected_types.sort(key=lambda x: x[1], reverse=True)
        
        # 🔥 ИСПРАВЛЕНО: Более гибкая логика для гибридных типов
        if len(detected_types) > 1:
            # Если есть несколько типов, создаем комбинированный
            detected_type_names = [t[0] for t in detected_types]
            
            if "mobile" in detected_type_names and "web_only" in detected_type_names:
                return "web_mobile"
            elif "api_only" in detected_type_names and "web_only" in detected_type_names:
                return "web_api"
            elif "mobile" in detected_type_names and "api_only" in detected_type_names:
                return "mobile_api"
            elif "mobile" in detected_type_names and len(detected_types) > 1:
                # Если есть мобильный + что-то еще
                return "mobile"
            elif "api_only" in detected_type_names and len(detected_types) > 1:
                # Если есть API + что-то еще
                return "api_only"
        
        # Возвращаем доминирующий тип
        return detected_types[0][0] if detected_types else "web_only"
    
    def _determine_needed_features(self, description: str) -> Set[str]:
        """Определяет нужные функции проекта"""
        needed = set()
        
        for feature, keywords in self.features.items():
            if any(keyword in description for keyword in keywords):
                needed.add(feature)
        
        return needed
    
    def _get_conditional_agents(self, project_type: str, needed_features: Set[str]) -> Set[str]:
        """Определяет условных агентов на основе типа и функций"""
        agents = set()
        
        for agent, requirement in self.conditional_agents.items():
            # 🔥 ИСПРАВЛЕНО: Более гибкая логика включения агентов
            if requirement == project_type or requirement in needed_features:
                agents.add(agent)
            elif requirement == "web_only" and project_type in ["web_mobile", "web_api"]:
                # DevOps, UI/UX, Technical Writer нужны для гибридных веб-проектов
                agents.add(agent)
            elif requirement == "web_only" and "performance" in needed_features:
                # DevOps нужен для всех проектов с требованиями к производительности
                if agent == "devops_engineer":
                    agents.add(agent)
            elif requirement == "web_only" and "integrations" in needed_features:
                # UI/UX нужен для проектов с интеграциями
                if agent == "ui_ux_designer":
                    agents.add(agent)
            # 🔥 НОВОЕ: Специальная логика для гибридных типов
            elif project_type in ["web_mobile", "mobile_api"] and agent == "mobile_developer":
                # Mobile Developer нужен для гибридных мобильных проектов
                agents.add(agent)
            elif project_type in ["web_api", "mobile_api"] and agent == "integration_specialist":
                # Integration Specialist нужен для гибридных API проектов
                agents.add(agent)
        
        return agents
    
    def _get_excluded_agents(self, project_type: str, needed_features: Set[str]) -> Set[str]:
        """Определяет агентов, которые не нужны с учетом features"""
        all_agents = self.required_agents.union(set(self.conditional_agents.keys()))
        needed_agents = self.required_agents.union(self._get_conditional_agents(project_type, needed_features))
        
        excluded = all_agents - needed_agents
        
        # 🔥 ИСПРАВЛЕНО: Условные исключения на основе features
        if "integrations" in needed_features:
            # Если есть интеграции, не исключаем UI/UX для мобильных проектов
            if project_type in ["mobile", "web_mobile", "mobile_api"]:
                excluded.discard("ui_ux_designer")
                excluded.discard("frontend_developer")
        
        if "performance" in needed_features:
            # Если нужна производительность, включаем DevOps для всех типов
            excluded.discard("devops_engineer")
        
        if "security" in needed_features:
            # Если нужна безопасность, включаем Security Specialist для всех типов
            excluded.discard("security_specialist")
        
        return excluded
    
    def _generate_recommendations(self, project_type: str, needed_features: Set[str]) -> List[str]:
        """Генерирует рекомендации по оптимизации с учетом контекста"""
        recommendations = []
        
        # 🔥 ИСПРАВЛЕНО: Более умные рекомендации на основе типа проекта
        if project_type == "web_only":
            recommendations.append("Веб-проект: включены UI/UX Designer, DevOps Engineer, Technical Writer")
        elif project_type == "web_mobile":
            recommendations.append("Гибридный веб+мобильный проект: включены все веб-специалисты + Mobile Developer")
        elif project_type == "web_api":
            recommendations.append("Гибридный веб+API проект: включены веб-специалисты, исключен Frontend Developer")
        elif project_type == "mobile_api":
            recommendations.append("Гибридный мобильный+API проект: включен Mobile Developer, исключены веб-специалисты")
        elif project_type == "mobile":
            recommendations.append("Мобильный проект: включен Mobile Developer, условно включены веб-специалисты")
        elif project_type == "api_only":
            recommendations.append("API-проект: исключены UI/UX Designer, Frontend Developer")
        
        # 🔥 ИСПРАВЛЕНО: Проверка на отсутствие ключевых слов перед исключением
        if "data_science" in needed_features:
            recommendations.append("Включен Data Scientist для ML/AI функциональности")
        elif any(keyword in project_type for keyword in ["web", "mobile", "api"]):
            # Проверяем, не может ли аналитика быть подразумеваемой
            recommendations.append("Data Scientist исключен (проект не требует аналитики)")
        else:
            recommendations.append("Data Scientist исключен (проект не требует аналитики)")
        
        if "integrations" in needed_features:
            recommendations.append("Включен Integration Specialist для внешних API")
        else:
            recommendations.append("Integration Specialist исключен (нет внешних интеграций)")
        
        if "performance" in needed_features:
            recommendations.append("Включен Performance Engineer для оптимизации")
        elif project_type in ["web_mobile", "web_api", "mobile_api"]:
            recommendations.append("Performance Engineer включен для гибридного проекта")
        else:
            recommendations.append("Performance Engineer исключен (простой проект)")
        
        # 🔥 НОВОЕ: Дополнительные рекомендации для гибридных проектов
        if project_type in ["web_mobile", "web_api", "mobile_api"]:
            recommendations.append("Гибридный проект: DevOps Engineer включен для CI/CD")
            if "integrations" in needed_features:
                recommendations.append("UI/UX Designer включен для проектов с интеграциями")
        
        return recommendations
    
    def get_optimized_agent_order(self, analysis: Dict[str, Any]) -> List[str]:
        """Возвращает оптимизированный порядок агентов"""
        final_agents = analysis["final_agents"]
        
        # Базовый порядок для обязательных агентов
        base_order = [
            "product_owner",
            "project_manager", 
            "system_architect",
            "database_engineer",
            "backend_developer",
            "frontend_developer",
            "qa_tester",
            "code_reviewer",
            "bug_fixer"
        ]
        
        # Добавляем условных агентов в нужные места
        optimized_order = base_order.copy()
        
        # UI/UX Designer после System Architect
        if "ui_ux_designer" in final_agents:
            optimized_order.insert(3, "ui_ux_designer")
        
        # Mobile Developer после Frontend Developer
        if "mobile_developer" in final_agents:
            optimized_order.insert(6, "mobile_developer")
        
        # Data Scientist после Backend Developer
        if "data_scientist" in final_agents:
            optimized_order.insert(5, "data_scientist")
        
        # Integration Specialist после Backend Developer
        if "integration_specialist" in final_agents:
            optimized_order.insert(5, "integration_specialist")
        
        # Security Specialist после Backend Developer
        if "security_specialist" in final_agents:
            optimized_order.insert(5, "security_specialist")
        
        # Performance Engineer после Backend Developer
        if "performance_engineer" in final_agents:
            optimized_order.insert(5, "performance_engineer")
        
        # DevOps Engineer после Performance Engineer
        if "devops_engineer" in final_agents:
            optimized_order.insert(5, "devops_engineer")
        
        # Technical Writer в конце
        if "technical_writer" in final_agents:
            optimized_order.append("technical_writer")
        
        return optimized_order
    
    def get_optimized_phases(self, analysis: Dict[str, Any]) -> List[List[str]]:
        """Возвращает оптимизированные фазы выполнения"""
        final_agents = analysis["final_agents"]
        
        phases = []
        
        # Фаза 1: Требования (только Product Owner)
        if "product_owner" in final_agents:
            phases.append(["product_owner"])
        
        # Фаза 2: Планирование (Project Manager после Product Owner)
        if "project_manager" in final_agents:
            phases.append(["project_manager"])
        
        # Фаза 3: Архитектура и дизайн
        phase3 = []
        if "system_architect" in final_agents:
            phase3.append("system_architect")
        if "ui_ux_designer" in final_agents:
            phase3.append("ui_ux_designer")
        if "database_engineer" in final_agents:
            phase3.append("database_engineer")
        if phase3:
            phases.append(phase3)
        
        # 🔥 НОВОЕ: Специальная фаза для гибридных проектов
        if any(project_type in analysis.get("project_type", "") for project_type in ["web_mobile", "web_api", "mobile_api"]):
            hybrid_phase = []
            if "mobile_developer" in final_agents:
                hybrid_phase.append("mobile_developer")
            if "integration_specialist" in final_agents:
                hybrid_phase.append("integration_specialist")
            if hybrid_phase:
                phases.append(hybrid_phase)
        
        # Фаза 4: Разработка
        phase4 = []
        if "backend_developer" in final_agents:
            phase4.append("backend_developer")
        if "frontend_developer" in final_agents:
            phase4.append("frontend_developer")
        if "mobile_developer" in final_agents:
            phase4.append("mobile_developer")
        if "data_scientist" in final_agents:
            phase4.append("data_scientist")
        if "integration_specialist" in final_agents:
            phase4.append("integration_specialist")
        if phase4:
            phases.append(phase4)
        
        # Фаза 5: Оптимизация и безопасность
        phase5 = []
        if "security_specialist" in final_agents:
            phase5.append("security_specialist")
        if "performance_engineer" in final_agents:
            phase5.append("performance_engineer")
        if "devops_engineer" in final_agents:
            phase5.append("devops_engineer")
        if phase5:
            phases.append(phase5)
        
        # Фаза 6: Тестирование и документация
        phase6 = []
        if "qa_tester" in final_agents:
            phase6.append("qa_tester")
        if "technical_writer" in final_agents:
            phase6.append("technical_writer")
        if "code_reviewer" in final_agents:
            phase6.append("code_reviewer")
        if phase6:
            phases.append(phase6)
        
        # Фаза 7: Исправление ошибок
        if "bug_fixer" in final_agents:
            phases.append(["bug_fixer"])
        
        return phases
