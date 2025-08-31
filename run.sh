#!/bin/bash
# Скрипт запуска мульти-агентной системы генерации проектов

echo "🤖 Запуск мульти-агентной системы генерации проектов"
echo "════════════════════════════════════════════════════"

# Проверяем наличие Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не найден. Установите Python 3.8+ и повторите попытку."
    exit 1
fi

# Проверяем наличие pip
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 не найден. Установите pip и повторите попытку."
    exit 1
fi

# Создаем виртуальное окружение если нет
if [ ! -d "venv" ]; then
    echo "📦 Создание виртуального окружения..."
    python3 -m venv venv
fi

# Активируем виртуальное окружение
echo "🔧 Активация виртуального окружения..."
source venv/bin/activate

# Устанавливаем зависимости
echo "📥 Установка зависимостей..."
pip install -r requirements.txt

# Создаем необходимые директории
mkdir -p logs
mkdir -p generated_projects

# Проверяем файл окружения
if [ ! -f ".env" ]; then
    echo "⚠️  Файл .env не найден. Скопируйте env_example.txt в .env и настройте API ключи."
    echo "📝 Создаю файл .env из примера..."
    cp env_example.txt .env
    echo "✅ Файл .env создан. Отредактируйте его перед запуском!"
fi

# Запускаем приложение
echo "🚀 Запуск системы..."
python3 main.py "$@"

# Деактивируем окружение
deactivate

echo "👋 Завершение работы"
