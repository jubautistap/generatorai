#!/usr/bin/env python3
"""
Демонстрация мульти-агентной системы генерации проектов

Этот файл показывает как использовать систему программно
"""
import asyncio
import os
from pathlib import Path

from coordinator import AgentCoordinator
from deepseek_client import deepseek_client
from rich.console import Console
from rich import print as rprint

console = Console()

async def demo_project_creation():
    """Демонстрация создания проекта"""
    
    # Проект для демонстрации
    demo_projects = [
        {
            "name": "TodoApp",
            "description": "Простое приложение для управления задачами с возможностью добавления, удаления и отметки задач как выполненные"
        },
        {
            "name": "WeatherApp", 
            "description": "Приложение прогноза погоды с получением данных от API, отображением текущей погоды и прогноза на несколько дней"
        },
        {
            "name": "BlogPlatform",
            "description": "Платформа для создания блогов с возможностью регистрации, создания постов, комментирования и системой тегов"
        }
    ]
    
    console.print("[bold blue]🎬 ДЕМОНСТРАЦИЯ МУЛЬТИ-АГЕНТНОЙ СИСТЕМЫ[/bold blue]")
    console.print("════════════════════════════════════════════════")
    
    # Проверяем API ключ
    if not os.getenv('DEEPSEEK_API_KEY') and deepseek_client.api_key == 'your_deepseek_api_key_here':
        console.print("[yellow]⚠️ Внимание: API ключ DeepSeek не установлен![/yellow]")
        console.print("[yellow]Для полноценной работы установите DEEPSEEK_API_KEY[/yellow]")
        console.print("[dim]Демонстрация будет работать в режиме симуляции[/dim]\n")
    
    # Выбираем проект для демонстрации
    selected_project = demo_projects[0]  # TodoApp для быстрой демонстрации
    
    console.print(f"[green]📋 Демонстрационный проект:[/green] [bold]{selected_project['name']}[/bold]")
    console.print(f"[green]📄 Описание:[/green] {selected_project['description']}")
    
    # Создаем координатор
    coordinator = AgentCoordinator()
    
    try:
        console.print(f"\n[blue]🚀 Запуск создания проекта...[/blue]")
        
        # Инициализируем проект
        project_context = await coordinator.start_project(
            selected_project['description'],
            selected_project['name']
        )
        
        console.print(f"[green]✅ Проект инициализирован: {project_context.id}[/green]")
        
        # Создаем демонстрационные результаты агентов (если нет реального API)
        if deepseek_client.api_key == 'your_deepseek_api_key_here':
            await create_demo_results(coordinator, project_context)
        else:
            # Запускаем реальный процесс (может занять время)
            console.print("[yellow]⏳ Запуск полного цикла разработки...[/yellow]")
            console.print("[dim]Это может занять 5-15 минут[/dim]")
            success = await coordinator.execute_full_cycle()
            
            if success:
                console.print("[bold green]🎉 Проект успешно создан![/bold green]")
            else:
                console.print("[red]❌ Ошибка при создании проекта[/red]")
        
        # Показываем результаты
        show_demo_results(coordinator, project_context)
        
    except Exception as e:
        console.print(f"[red]💥 Ошибка в демонстрации: {e}[/red]")

async def create_demo_results(coordinator, project_context):
    """Создает демонстрационные результаты для показа работы системы"""
    from agents import AgentResult, AgentTask
    
    console.print("[yellow]📝 Создание демонстрационных результатов...[/yellow]")
    
    # Имитируем результаты от разных агентов
    demo_results = {
        "project_manager": [
            AgentResult(
                agent_id="project_manager",
                task_id="demo_task_1",
                success=True,
                output="""# Техническое Задание - TodoApp

## Функциональные требования:
1. Добавление новых задач
2. Отметка задач как выполненные  
3. Удаление задач
4. Фильтрация задач (все/активные/выполненные)
5. Подсчет активных задач

## Технические требования:
- Frontend: React.js
- Backend: FastAPI (Python) 
- База данных: SQLite
- Стилизация: CSS/Tailwind

## Архитектура:
- SPA приложение
- REST API
- Локальное хранение данных""",
                execution_time=2.5
            )
        ],
        "backend_developer": [
            AgentResult(
                agent_id="backend_developer", 
                task_id="demo_task_2",
                success=True,
                output="""```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
from datetime import datetime

app = FastAPI(title="TodoApp API")

class TodoItem(BaseModel):
    id: Optional[int] = None
    title: str
    completed: bool = False
    created_at: Optional[datetime] = None

class TodoCreate(BaseModel):
    title: str

# База данных
def init_db():
    conn = sqlite3.connect('todos.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            completed BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

@app.on_event("startup")
async def startup():
    init_db()

@app.get("/todos", response_model=List[TodoItem])
async def get_todos():
    conn = sqlite3.connect('todos.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM todos ORDER BY created_at DESC")
    todos = cursor.fetchall()
    conn.close()
    
    return [
        TodoItem(id=todo[0], title=todo[1], completed=bool(todo[2]), created_at=todo[3])
        for todo in todos
    ]

@app.post("/todos", response_model=TodoItem)
async def create_todo(todo: TodoCreate):
    conn = sqlite3.connect('todos.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO todos (title) VALUES (?)",
        (todo.title,)
    )
    todo_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return TodoItem(id=todo_id, title=todo.title, completed=False)

@app.put("/todos/{todo_id}")
async def update_todo(todo_id: int, todo: TodoItem):
    conn = sqlite3.connect('todos.db')
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE todos SET title=?, completed=? WHERE id=?",
        (todo.title, todo.completed, todo_id)
    )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Todo not found")
    conn.commit()
    conn.close()
    return {"message": "Todo updated"}

@app.delete("/todos/{todo_id}")
async def delete_todo(todo_id: int):
    conn = sqlite3.connect('todos.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM todos WHERE id=?", (todo_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Todo not found")
    conn.commit()
    conn.close()
    return {"message": "Todo deleted"}
```""",
                execution_time=4.2
            )
        ],
        "frontend_developer": [
            AgentResult(
                agent_id="frontend_developer",
                task_id="demo_task_3", 
                success=True,
                output="""```javascript
import React, { useState, useEffect } from 'react';
import axios from 'axios';

const TodoApp = () => {
  const [todos, setTodos] = useState([]);
  const [newTodo, setNewTodo] = useState('');
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    fetchTodos();
  }, []);

  const fetchTodos = async () => {
    try {
      const response = await axios.get('/api/todos');
      setTodos(response.data);
    } catch (error) {
      console.error('Error fetching todos:', error);
    }
  };

  const addTodo = async (e) => {
    e.preventDefault();
    if (!newTodo.trim()) return;

    try {
      const response = await axios.post('/api/todos', { title: newTodo });
      setTodos([response.data, ...todos]);
      setNewTodo('');
    } catch (error) {
      console.error('Error adding todo:', error);
    }
  };

  const toggleTodo = async (id) => {
    const todo = todos.find(t => t.id === id);
    try {
      await axios.put(`/api/todos/${id}`, { 
        ...todo, 
        completed: !todo.completed 
      });
      setTodos(todos.map(t => 
        t.id === id ? { ...t, completed: !t.completed } : t
      ));
    } catch (error) {
      console.error('Error updating todo:', error);
    }
  };

  const deleteTodo = async (id) => {
    try {
      await axios.delete(`/api/todos/${id}`);
      setTodos(todos.filter(t => t.id !== id));
    } catch (error) {
      console.error('Error deleting todo:', error);
    }
  };

  const filteredTodos = todos.filter(todo => {
    if (filter === 'active') return !todo.completed;
    if (filter === 'completed') return todo.completed;
    return true;
  });

  return (
    <div className="todo-app">
      <h1>Todo App</h1>
      
      <form onSubmit={addTodo}>
        <input
          type="text"
          value={newTodo}
          onChange={(e) => setNewTodo(e.target.value)}
          placeholder="Добавить новую задачу..."
          className="todo-input"
        />
        <button type="submit">Добавить</button>
      </form>

      <div className="filters">
        <button 
          className={filter === 'all' ? 'active' : ''}
          onClick={() => setFilter('all')}
        >
          Все
        </button>
        <button 
          className={filter === 'active' ? 'active' : ''}
          onClick={() => setFilter('active')}
        >
          Активные
        </button>
        <button 
          className={filter === 'completed' ? 'active' : ''}
          onClick={() => setFilter('completed')}
        >
          Выполненные
        </button>
      </div>

      <ul className="todo-list">
        {filteredTodos.map(todo => (
          <li key={todo.id} className={todo.completed ? 'completed' : ''}>
            <input
              type="checkbox"
              checked={todo.completed}
              onChange={() => toggleTodo(todo.id)}
            />
            <span>{todo.title}</span>
            <button onClick={() => deleteTodo(todo.id)}>Удалить</button>
          </li>
        ))}
      </ul>
      
      <p>{todos.filter(t => !t.completed).length} активных задач</p>
    </div>
  );
};

export default TodoApp;
```

```css
.todo-app {
  max-width: 600px;
  margin: 0 auto;
  padding: 20px;
  font-family: Arial, sans-serif;
}

.todo-input {
  width: 70%;
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
}

.filters {
  margin: 20px 0;
}

.filters button {
  margin-right: 10px;
  padding: 5px 10px;
  border: 1px solid #ddd;
  background: white;
  border-radius: 4px;
  cursor: pointer;
}

.filters button.active {
  background: #007bff;
  color: white;
}

.todo-list {
  list-style: none;
  padding: 0;
}

.todo-list li {
  padding: 10px;
  border-bottom: 1px solid #eee;
  display: flex;
  align-items: center;
}

.todo-list li.completed {
  text-decoration: line-through;
  opacity: 0.6;
}
```""",
                execution_time=6.1
            )
        ]
    }
    
    # Добавляем результаты в проект
    project_context.all_results = demo_results
    project_context.status = "completed"
    project_context.current_iteration = 1
    
    console.print("[green]✅ Демонстрационные результаты созданы[/green]")

def show_demo_results(coordinator, project_context):
    """Показывает результаты демонстрации"""
    console.print(f"\n[bold yellow]📊 РЕЗУЛЬТАТЫ ДЕМОНСТРАЦИИ[/bold yellow]")
    
    from rich.table import Table
    
    table = Table(title="Статистика проекта")
    table.add_column("Параметр", justify="left")
    table.add_column("Значение", justify="right")
    
    table.add_row("Название проекта", project_context.name)
    table.add_row("Статус", project_context.status)
    table.add_row("Итераций выполнено", str(project_context.current_iteration))
    table.add_row("Агентов отработало", str(len(project_context.all_results)))
    table.add_row("Время выполнения", "~3 минуты (демо)")
    
    console.print(table)
    
    # Показываем какие агенты сработали
    console.print(f"\n[green]🤖 Агенты, принявшие участие:[/green]")
    for agent_id, results in project_context.all_results.items():
        agent_name = coordinator.agents[agent_id].name
        successful_tasks = len([r for r in results if r.success])
        console.print(f"[white]• {agent_name}: {successful_tasks} успешных задач[/white]")
    
    # Информация о том, что бы создалось в реальном режиме
    console.print(f"\n[blue]📁 В полном режиме создались бы файлы:[/blue]")
    example_files = [
        "src/backend/app.py",
        "src/frontend/TodoApp.js", 
        "src/frontend/App.css",
        "requirements.txt",
        "package.json",
        "README.md",
        "tests/test_api.py",
        "docker-compose.yml"
    ]
    
    for file_path in example_files:
        console.print(f"[dim]  {file_path}[/dim]")
    
    console.print(f"\n[bold green]🎉 Демонстрация завершена успешно![/bold green]")

if __name__ == "__main__":
    asyncio.run(demo_project_creation())
