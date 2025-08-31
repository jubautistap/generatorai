"""
Проверка консистентности проекта - анализирует согласованность frontend/backend
"""
import re
import logging
from typing import Dict, List, Any, Set
from pathlib import Path

logger = logging.getLogger(__name__)

class ProjectConsistencyChecker:
    """Проверяет согласованность проекта между frontend и backend"""
    
    def __init__(self):
        # Паттерны для поиска API endpoints
        self.api_patterns = {
            "flask": [
                r"@app\.route\(['\"]([^'\"]+)['\"]",
                r"@bp\.route\(['\"]([^'\"]+)['\"]",
                r"@api\.route\(['\"]([^'\"]+)['\"]"
            ],
            "fastapi": [
                r"@app\.(get|post|put|delete|patch)\(['\"]([^'\"]+)['\"]",
                r"@router\.(get|post|put|delete|patch)\(['\"]([^'\"]+)['\"]"
            ],
            "django": [
                r"path\(['\"]([^'\"]+)['\"]",
                r"re_path\(['\"]([^'\"]+)['\"]",
                r"url\(['\"]([^'\"]+)['\"]",
                r"router\.register\(['\"]([^'\"]+)['\"]"
            ]
        }
        
        # Паттерны для поиска frontend API вызовов
        self.frontend_api_patterns = [
            r"fetch\(['\"]([^'\"]+)['\"]",
            r"axios\.(get|post|put|delete|patch)\(['\"]([^'\"]+)['\"]",
            r"\.get\(['\"]([^'\"]+)['\"]",
            r"\.post\(['\"]([^'\"]+)['\"]",
            r"api_url\s*\+\s*['\"]([^'\"]+)['\"]"
        ]
        
        # Паттерны для поиска переменных окружения
        self.env_patterns = [
            r"process\.env\.([A-Z_]+)",
            r"os\.environ\[['\"]([^'\"]+)['\"]\]",
            r"config\[['\"]([^'\"]+)['\"]\]"
        ]
    
    def check_project_consistency(self, project_files: Dict[str, str], project_context: Dict[str, Any]) -> Dict[str, Any]:
        """Проверяет консистентность проекта"""
        logger.info("🔍 Проверка консистентности проекта...")
        
        consistency_report = {
            "overall_score": 0,
            "issues": [],
            "warnings": [],
            "recommendations": [],
            "api_coverage": {},
            "missing_endpoints": [],
            "environment_variables": set(),
            "file_structure": {},
            "dependencies": set()
        }
        
        try:
            # 1. Проверяем структуру файлов
            consistency_report["file_structure"] = self._analyze_file_structure(project_files)
            
            # 2. Проверяем API endpoints
            api_analysis = self._analyze_api_endpoints(project_files)
            consistency_report["api_coverage"] = api_analysis["coverage"]
            consistency_report["missing_endpoints"] = api_analysis["missing"]
            
            # 3. Проверяем переменные окружения
            consistency_report["environment_variables"] = self._extract_environment_variables(project_files)
            
            # 4. Проверяем зависимости
            consistency_report["dependencies"] = self._extract_dependencies(project_files)
            
            # 5. Анализируем проблемы
            issues = self._identify_consistency_issues(project_files, api_analysis, project_context)
            consistency_report["issues"] = issues["critical"]
            consistency_report["warnings"] = issues["warnings"]
            consistency_report["recommendations"] = issues["recommendations"]
            
            # 6. Вычисляем общий балл
            consistency_report["overall_score"] = self._calculate_consistency_score(consistency_report)
            
            logger.info(f"✅ Проверка консистентности завершена. Балл: {consistency_report['overall_score']}/100")
            
        except Exception as e:
            logger.error(f"Ошибка при проверке консистентности: {e}")
            consistency_report["issues"].append(f"Ошибка проверки: {e}")
            consistency_report["overall_score"] = 0
        
        return consistency_report
    
    def _analyze_file_structure(self, project_files: Dict[str, str]) -> Dict[str, Any]:
        """Анализирует структуру файлов проекта"""
        structure = {
            "backend_files": [],
            "frontend_files": [],
            "config_files": [],
            "test_files": [],
            "documentation_files": [],
            "missing_critical": []
        }
        
        # Критические файлы для проверки
        critical_files = {
            "backend": ["app.py", "main.py", "requirements.txt"],
            "frontend": ["index.html", "app.js", "styles.css"],
            "config": [".env", "config.py", "settings.py"],
            "tests": ["test_", "pytest.ini", "tests/"],
            "docs": ["README.md", "API.md", "INSTALLATION.md"]
        }
        
        for filename, content in project_files.items():
            file_lower = filename.lower()
            
            # Определяем тип файла
            if any(ext in file_lower for ext in [".py", "requirements.txt"]):
                structure["backend_files"].append(filename)
            elif any(ext in file_lower for ext in [".html", ".js", ".css", ".vue", ".jsx"]):
                structure["frontend_files"].append(filename)
            elif any(ext in file_lower for ext in [".env", "config", "settings"]):
                structure["config_files"].append(filename)
            elif "test" in file_lower or "tests" in file_lower:
                structure["test_files"].append(filename)
            elif any(ext in file_lower for ext in [".md", "readme", "api", "docs"]):
                structure["documentation_files"].append(filename)
        
        # Проверяем наличие критических файлов
        for category, files in critical_files.items():
            for file in files:
                if not any(file.lower() in f.lower() for f in project_files.keys()):
                    structure["missing_critical"].append(f"{category}: {file}")
        
        return structure
    
    def _analyze_api_endpoints(self, project_files: Dict[str, str]) -> Dict[str, Any]:
        """Анализирует API endpoints в backend и frontend"""
        backend_endpoints = set()
        frontend_calls = set()
        
        # Ищем backend endpoints
        for filename, content in project_files.items():
            if any(ext in filename.lower() for ext in [".py", "app.py", "main.py", "routes.py", "urls.py"]):
                for pattern_list in self.api_patterns.values():
                    for pattern in pattern_list:
                        matches = re.findall(pattern, content)
                        for match in matches:
                            if isinstance(match, tuple):
                                endpoint = match[1] if len(match) > 1 else match[0]
                            else:
                                endpoint = match
                            backend_endpoints.add(endpoint)
        
        # Ищем frontend API вызовы
        for filename, content in project_files.items():
            if any(ext in filename.lower() for ext in [".js", ".jsx", ".vue", ".html"]):
                for pattern in self.frontend_api_patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        if isinstance(match, tuple):
                            call = match[-1]
                        else:
                            call = match
                        frontend_calls.add(call)
        
        # Анализируем покрытие
        coverage = {
            "backend_endpoints": list(backend_endpoints),
            "frontend_calls": list(frontend_calls),
            "total_backend": len(backend_endpoints),
            "total_frontend": len(frontend_calls),
            "matched": 0,
            "unmatched_frontend": [],
            "unmatched_backend": []
        }
        
        # Находим совпадения
        for frontend_call in frontend_calls:
            matched = False
            for backend_endpoint in backend_endpoints:
                if self._endpoints_match(frontend_call, backend_endpoint):
                    coverage["matched"] += 1
                    matched = True
                    break
            if not matched:
                coverage["unmatched_frontend"].append(frontend_call)
        
        # Находим неиспользуемые backend endpoints
        for backend_endpoint in backend_endpoints:
            matched = False
            for frontend_call in frontend_calls:
                if self._endpoints_match(frontend_call, backend_endpoint):
                    matched = True
                    break
            if not matched:
                coverage["unmatched_backend"].append(backend_endpoint)
        
        return {
            "coverage": coverage,
            "missing": coverage["unmatched_frontend"]
        }

    def _has_backend_code(self, project_files: Dict[str, str]) -> bool:
        """Пытается определить наличие backend-кода в проекте"""
        for filename in project_files.keys():
            lower = filename.lower()
            if any(token in lower for token in ["app.py", "main.py", "routes.py", "urls.py", "views.py", "manage.py", "requirements.txt", "fastapi", "flask"]):
                return True
        for filename in project_files.keys():
            lower = filename.lower()
            if lower.endswith(".py") and not any(seg in lower for seg in ["test", "docs", "readme"]):
                return True
        return False
    
    def _endpoints_match(self, frontend_call: str, backend_endpoint: str) -> bool:
        """Проверяет соответствие frontend вызова и backend endpoint"""
        # Нормализуем endpoints
        frontend = frontend_call.strip("/")
        backend = backend_endpoint.strip("/")
        
        # Простое сравнение
        if frontend == backend:
            return True
        
        # Проверяем частичные совпадения
        if frontend in backend or backend in frontend:
            return True
        
        # Проверяем API версионирование
        if "/api/" in frontend and "/api/" in backend:
            frontend_api = frontend.split("/api/")[-1]
            backend_api = backend.split("/api/")[-1]
            if frontend_api == backend_api:
                return True
        
        return False
    
    def _extract_environment_variables(self, project_files: Dict[str, str]) -> Set[str]:
        """Извлекает переменные окружения из файлов"""
        env_vars = set()
        
        for filename, content in project_files.items():
            for pattern in self.env_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    env_vars.add(match)
        
        return env_vars
    
    def _extract_dependencies(self, project_files: Dict[str, str]) -> Set[str]:
        """Извлекает зависимости из файлов"""
        dependencies = set()
        
        # Ищем в requirements.txt, package.json, etc.
        for filename, content in project_files.items():
            if "requirements.txt" in filename.lower():
                lines = content.split("\n")
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        dependencies.add(line.split("==")[0].split(">=")[0].split("<=")[0])
            elif "package.json" in filename.lower():
                # Точный парсинг package.json через json
                try:
                    import json
                    pkg = json.loads(content)
                    dep_objs = []
                    for key in ["dependencies", "devDependencies", "peerDependencies", "optionalDependencies"]:
                        if isinstance(pkg.get(key), dict):
                            dep_objs.append(pkg[key])
                    for dep_map in dep_objs:
                        for dep_name in dep_map.keys():
                            dependencies.add(dep_name)
                except Exception:
                    # fallback на грубый regex, если package.json битый
                    import_pattern = r'"([a-zA-Z0-9_@./\-]+)":\s*"[^"]*"'
                    matches = re.findall(import_pattern, content)
                    for match in matches:
                        if match not in ["name", "version", "description", "main", "scripts"]:
                            dependencies.add(match)
        
        return dependencies
    
    def _identify_consistency_issues(self, project_files: Dict[str, str], api_analysis: Dict[str, Any], project_context: Dict[str, Any]) -> Dict[str, List[str]]:
        """Идентифицирует проблемы консистентности"""
        issues = {
            "critical": [],
            "warnings": [],
            "recommendations": []
        }
        
        coverage = api_analysis["coverage"]
        
        # Критические проблемы с учетом наличия соответствующего слоя
        project_type = (project_context or {}).get("project_type") or (project_context or {}).get("type")
        has_backend = self._has_backend_code(project_files)
        has_frontend = any(f.lower().endswith(ext) for f in project_files.keys() for ext in [".js", ".jsx", ".vue", ".html", ".css"])

        if coverage["total_backend"] == 0 and has_backend:
            issues["critical"].append("Backend не содержит API endpoints")
        
        if coverage["total_frontend"] == 0 and has_frontend:
            issues["critical"].append("Frontend не содержит API вызовы")
        
        if coverage["matched"] == 0 and coverage["total_frontend"] > 0 and coverage["total_backend"] > 0:
            issues["critical"].append("Frontend и Backend API не совпадают")
        
        # Предупреждения
        if coverage["unmatched_frontend"]:
            issues["warnings"].append(f"Frontend вызывает несуществующие API: {', '.join(coverage['unmatched_frontend'][:3])}")
        
        if coverage["unmatched_backend"]:
            issues["warnings"].append(f"Backend содержит неиспользуемые endpoints: {', '.join(coverage['unmatched_backend'][:3])}")
        
        # Рекомендации
        if coverage["total_backend"] > 0 and coverage["total_frontend"] > 0:
            match_percentage = (coverage["matched"] / max(coverage["total_frontend"], coverage["total_backend"])) * 100
            if match_percentage < 80:
                issues["recommendations"].append(f"API покрытие: {match_percentage:.1f}%. Улучшите соответствие frontend/backend")
        
        # Проверяем структуру проекта
        structure = self._analyze_file_structure(project_files)
        if structure["missing_critical"]:
            issues["warnings"].append(f"Отсутствуют критические файлы: {', '.join(structure['missing_critical'][:3])}")
        
        return issues
    
    def _calculate_consistency_score(self, report: Dict[str, Any]) -> int:
        """Вычисляет общий балл консистентности"""
        # Базовый балл
        score = 100
        
        # Бонусы за покрытие применяем раньше
        try:
            coverage = report.get("api_coverage") or {}
            tb = coverage.get("total_backend", 0)
            tf = coverage.get("total_frontend", 0)
            if tb > 0 and tf > 0:
                match_percentage = (coverage.get("matched", 0) / max(tf, tb)) * 100
                if match_percentage >= 90:
                    score += 12
                elif match_percentage >= 75:
                    score += 8
                elif match_percentage >= 60:
                    score += 4
        except Exception:
            pass
        
        # Взвешенные штрафы
        critical_weight = 25
        warning_weight = 8
        missing_weight = 3
        
        score -= max(0, len(report.get("issues", []))) * critical_weight
        score -= max(0, len(report.get("warnings", []))) * warning_weight
        score -= max(0, len(report.get("missing_endpoints", []))) * missing_weight
        
        return max(0, min(100, int(round(score))))
    
    def generate_consistency_summary(self, report: Dict[str, Any]) -> str:
        """Генерирует краткое резюме проверки консистентности"""
        summary = f"""
# Отчет о консистентности проекта

## Общий балл: {report['overall_score']}/100

## API покрытие
- Backend endpoints: {report['api_coverage'].get('total_backend', 0)}
- Frontend API вызовы: {report['api_coverage'].get('total_frontend', 0)}
- Совпадения: {report['api_coverage'].get('matched', 0)}

## Критические проблемы
"""
        
        if report["issues"]:
            for issue in report["issues"]:
                summary += f"- ❌ {issue}\n"
        else:
            if report.get("overall_score", 0) < 70:
                summary += "- ⚠️ Критических проблем не выявлено, но общий балл низкий — проверьте покрытие и структуру\n"
            else:
                summary += "- ✅ Критических проблем не обнаружено\n"
        
        summary += "\n## Предупреждения\n"
        if report["warnings"]:
            for warning in report["warnings"]:
                summary += f"- ⚠️ {warning}\n"
        else:
            summary += "- ✅ Предупреждений нет\n"
        
        summary += "\n## Рекомендации\n"
        if report["recommendations"]:
            for rec in report["recommendations"]:
                summary += f"- 💡 {rec}\n"
        else:
            summary += "- ✅ Рекомендаций нет\n"
        
        return summary
