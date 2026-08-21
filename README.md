# Telegram Mini App — Магазин

Telegram Mini App с ботом (aiogram 3), Web App (FastAPI + SPA) и базой данных (SQLAlchemy 2.0 async).

## Возможности

- Каталог товаров с glassmorphism-дизайном и палитрой темы Telegram
- Корзина: добавление, изменение количества, удаление, оформление заказа
- Баланс пользователя и пополнение (уведомление приходит админу / @saintgeck)
- История покупок с деталями
- Админ-панель в боте: добавление, список и скрытие товаров
- Проверка подписи Telegram WebApp initData на сервере

## Структура

```
bot/          — aiogram-бот (хендлеры, клавиатуры)
webapp/       — FastAPI-сервер, API и SPA (static/)
database/     — модели, сессии, репозитории
services/     — бизнес-логика (корзина, оплата, товары)
config.py     — настройки из .env
seed.py       — демо-товары
```

## Запуск

1. Установите зависимости:

   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Скопируйте `.env.example` в `.env` и заполните `BOT_TOKEN`, `ADMIN_IDS`, `WEBAPP_URL`, `DATABASE_URL`.

3. Заполните каталог демо-товарами (опционально):

   ```bash
   python seed.py
   ```

4. Запустите Web App:

   ```bash
   uvicorn webapp.server:app --reload --port 8000
   ```

5. Запустите бота:

   ```bash
   python bot/main.py
   ```

6. Пробросьте localhost:8000 в HTTPS (например, `ngrok http 8000`) и укажите
   полученный адрес в `WEBAPP_URL` и в BotFather (Menu Button → Web App URL).

## Разработка без Telegram

Если `BOT_TOKEN` не задан, API использует демо-пользователя, поэтому SPA можно
открыть прямо в браузере: `http://localhost:8000`.

## База данных

По умолчанию — SQLite (`shop.db`). Для продакшена задайте
`DATABASE_URL=postgresql+asyncpg://user:password@host:5432/shop`.
