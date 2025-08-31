"""
DeepSeek API клиент для отправки запросов к AI модели
"""
import requests
import asyncio
import aiohttp
import json
import time
import logging
import random
from typing import Optional, Dict, Any
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, DEEPSEEK_REASONER_MODEL, AVAILABLE_MODELS, AGENT_TIMEOUT

logger = logging.getLogger(__name__)

class DeepSeekClient:
    def __init__(self, api_key: str = DEEPSEEK_API_KEY):
        self.api_key = api_key
        self.base_url = DEEPSEEK_BASE_URL
        self.default_model = DEEPSEEK_MODEL
        self.reasoner_model = DEEPSEEK_REASONER_MODEL
        self.available_models = AVAILABLE_MODELS
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })
    
    async def chat_completion_async(self, 
                       messages: list,
                       max_tokens: int = 2000,
                       temperature: float = 0.7,
                       stream: bool = False,
                       model: str = None) -> Optional[Dict[Any, Any]]:
        """
        Отправляет запрос к DeepSeek Chat API
        """
        try:
            selected_model = model or self.reasoner_model
            requested_max_tokens = max_tokens or 2000
            model_limit = None
            try:
                caps = (self.available_models or {}).get(selected_model)
                if isinstance(caps, dict):
                    model_limit = caps.get("max_output_tokens") or caps.get("max_tokens") or caps.get("max_output")
            except Exception:
                model_limit = None
            hard_cap = model_limit or 4000
            effective_max_tokens = max(1, min(hard_cap, requested_max_tokens))
            
            payload = {
                "model": selected_model,
                "messages": messages,
                "max_tokens": effective_max_tokens,
                "temperature": temperature,
                "stream": stream
            }
            
            await asyncio.sleep(random.uniform(0.1, 0.35))
            timeout = aiohttp.ClientTimeout(total=AGENT_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                result = await self._post_with_retries(
                    session=session,
                    url=f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    retries=6,
                    base_delay=1.5,
                )
                return result
        except aiohttp.ClientError as e:
            logger.error(f"Ошибка сети при запросе к DeepSeek: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка декодирования JSON от DeepSeek: {e}")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка DeepSeek клиента: {e}")
            return None

    def _post_sync_with_retries(self, url: str, json: Dict[str, Any], headers: Dict[str, str], *, retries: int = 3, base_delay: float = 0.8) -> Optional[Dict[str, Any]]:
        """
        🔥 НОВОЕ: Синхронный POST с экспоненциальным бэкоффом и джиттером
        """
        import random
        for attempt in range(retries):
            try:
                logger.debug(f"🔄 Синхронный запрос к DeepSeek (попытка {attempt + 1}/{retries})")
                
                response = self.session.post(
                    url, 
                    json=json, 
                    headers=headers, 
                    timeout=AGENT_TIMEOUT
                )
                response.raise_for_status()
                
                logger.debug(f"✅ Синхронный запрос к DeepSeek успешен (попытка {attempt + 1})")
                return response.json()
                
            except requests.exceptions.RequestException as e:
                if attempt == retries - 1:
                    logger.error(f"❌ Финальная ошибка синхронного запроса после {retries} попыток: {e}")
                    return None
                
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.1)
                logger.warning(f"⚠️ Попытка {attempt + 1}/{retries} синхронного запроса не удалась: {e}. Повтор через {delay:.2f}s")
                time.sleep(delay)
        
        return None

    async def _post_with_retries(self, session: aiohttp.ClientSession, url: str, json: Dict[str, Any], headers: Dict[str, str], *, retries: int = 5, base_delay: float = 1.0) -> Optional[Dict[str, Any]]:
        """
        POST с экспоненциальным бэкоффом и джиттером для 429/5xx и таймаутов
        """
        import random
        for attempt in range(retries):
            try:
                async with session.post(url, json=json, headers=headers, timeout=aiohttp.ClientTimeout(total=AGENT_TIMEOUT)) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    if resp.status in (401, 403):
                        body = await resp.text()
                        logger.error(f"DeepSeek auth error {resp.status}: {body[:200]}")
                        return None
                    if resp.status in (429, 500, 502, 503, 504):
                        factor = 2.5 if resp.status == 429 else 2.0
                        delay = base_delay * (factor ** attempt) + random.uniform(0.5, 1.5)
                        logger.warning(f"DeepSeek {resp.status}, retry {attempt+1}/{retries} in {delay:.2f}s")
                        await asyncio.sleep(delay)
                    else:
                        body = await resp.text()
                        logger.error(f"DeepSeek non-OK {resp.status}: {body[:200]}")
                        delay = base_delay * (2 ** attempt) + random.uniform(0.3, 1.0)
                        await asyncio.sleep(delay)
            except asyncio.TimeoutError:
                if attempt == retries - 1:
                    logger.error(f"❌ Финальный таймаут после {retries} попыток")
                    return None
                delay = base_delay * (3 ** attempt) + random.uniform(1.0, 3.0)
                logger.warning(f"⏰ Таймаут попытка {attempt+1}/{retries}, повтор через {delay:.2f}s")
                await asyncio.sleep(delay)
            except Exception as e:
                if attempt == retries - 1:
                    logger.error(f"❌ Финальная ошибка после {retries} попыток: {e}")
                    return None
                delay = base_delay * (2 ** attempt) + random.uniform(0.5, 1.5)
                logger.warning(f"DeepSeek request error on attempt {attempt+1}/{retries}: {str(e)[:100]}. Retrying in {delay:.2f}s")
                await asyncio.sleep(delay)
        return None
    
    def generate_response(self, prompt: str, system_message: str = None, use_reasoner: bool = False) -> Optional[str]:
        """
        Генерирует ответ на основе промпта
        """
        # Требуется реальный ключ
        if not self.api_key:
            logger.error("DEEPSEEK_API_KEY не задан. Установите ключ для работы клиента.")
            return None
        messages = []
        
        if system_message:
            messages.append({
                "role": "system",
                "content": system_message
            })
        
        messages.append({
            "role": "user", 
            "content": prompt
        })
        
        # Принудительно используем reasoner-модель для стабильности
        model = self.reasoner_model
        
        # 🔥 ИСПРАВЛЕНО: Убираем run_until_complete - это вызывает зависание!
        # Вместо этого используем синхронный HTTP-клиент для sync-контекста
        try:
            logger.info(f"🔄 Синхронный запрос к DeepSeek API: модель={model}, сообщений={len(messages)}, таймаут={AGENT_TIMEOUT}с")
            
            # Используем синхронный requests для sync-контекста
            response = self._post_sync_with_retries(
                url=f"{self.base_url}/chat/completions",
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": 2000,
                    "temperature": 0.7,
                    "stream": False
                },
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
            )
            
            if response:
                logger.info("✅ Синхронный запрос к DeepSeek API успешен")
            else:
                logger.error("❌ Синхронный запрос к DeepSeek API не удался")
                
        except Exception as e:
            logger.error(f"Ошибка синхронного запроса к DeepSeek: {e}")
            return None
        
        if response and 'choices' in response and len(response['choices']) > 0:
            return response['choices'][0]['message']['content']
        else:
            logger.error("Не получен корректный ответ от DeepSeek")
            return None

    async def generate_response_async(self, prompt: str, system_message: str = None, use_reasoner: bool = False) -> Optional[str]:
        """Асинхронная версия генерации ответа (для вызова из async-кода)."""
        if not self.api_key:
            logger.error("DEEPSEEK_API_KEY не задан. Установите ключ для работы клиента.")
            return None

        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        
        # Принудительно используем reasoner-модель
        model = self.reasoner_model
        logger.info(f"🔄 Асинхронный запрос к DeepSeek API: модель={model}, сообщений={len(messages)}, таймаут={AGENT_TIMEOUT}с")
        
        response = await self.chat_completion_async(messages, model=model, max_tokens=2000)
        
        if response and 'choices' in response and len(response['choices']) > 0:
            logger.info("✅ Асинхронный запрос к DeepSeek API успешен")
            return response['choices'][0]['message']['content']
        
        logger.error("❌ Не получен корректный ответ от DeepSeek (async)")
        return None

    
    
    def generate_analysis(self, prompt: str, system_message: str = None) -> Optional[str]:
        """
        Генерирует анализ используя модель reasoner для сложных задач
        """
        return self.generate_response(prompt, system_message, use_reasoner=True)
    
    def generate_code(self, 
                     description: str, 
                     language: str = "python",
                     context: str = "") -> Optional[str]:
        """
        Генерирует код на основе описания
        """
        system_message = f"""Ты опытный {language} разработчик. 
        Создай полный, рабочий код на основе описания.
        Код должен быть готов к использованию, содержать все необходимые импорты и функции.
        Следуй best practices и добавляй комментарии на русском языке."""
        
        if context:
            prompt = f"Контекст проекта: {context}\n\nОписание задачи: {description}"
        else:
            prompt = description
            
        return self.generate_response(prompt, system_message)
    
    def analyze_requirements(self, project_description: str) -> Optional[str]:
        """
        Анализирует требования проекта
        """
        system_message = """Ты бизнес-аналитик и проект-менеджер.
        Проанализируй описание проекта и создай детальные требования.
        Включи функциональные и нефункциональные требования, технические ограничения."""
        
        prompt = f"Проанализируй проект: {project_description}"
        return self.generate_response(prompt, system_message)
    
    def create_architecture(self, requirements: str) -> Optional[str]:
        """
        Создает архитектуру системы
        """
        system_message = """Ты системный архитектор.
        На основе требований создай техническую архитектуру системы.
        Опиши компоненты, их взаимодействие, выбери технологии."""
        
        prompt = f"Требования: {requirements}\n\nСоздай архитектуру системы."
        return self.generate_response(prompt, system_message)
    
    def health_check(self) -> bool:
        """
        Проверяет доступность DeepSeek API
        """
        if not self.api_key:
            logger.error("DEEPSEEK_API_KEY не задан. health_check не может быть выполнен.")
            return False
        try:
            payload = {
                "model": self.reasoner_model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 5,
                "temperature": 0.0,
                "stream": False
            }
            resp = self.session.post(f"{self.base_url}/chat/completions", json=payload, timeout=15)
            if resp.status_code == 200:
                return True
            # 🔥 ИСПРАВЛЕНО: различаем ошибки перегрузки/лимитов/авторизации
            if resp.status_code in (429, 500, 502, 503, 504):
                logger.warning(f"DeepSeek health_check transient status: {resp.status_code}")
                return True  # сервер жив, временная проблема
            if resp.status_code in (401, 403):
                logger.error(f"DeepSeek health_check auth error: {resp.status_code}")
                return False
            logger.error(f"DeepSeek health_check non-ok status: {resp.status_code}, body: {resp.text[:200]}")
            return False
        except Exception as e:
            logger.error(f"health_check error: {e}")
            return False

# Singleton instance
deepseek_client = DeepSeekClient()
