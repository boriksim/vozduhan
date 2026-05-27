# Vozduhan

Локальный Telegram-бот для группового чата. Он читает все текстовые сообщения, хранит память в SQLite, иногда вмешивается по decision engine, генерирует ответы через локальный Ollama и имеет минимальную FastAPI-панель.

## Возможности MVP

- aiogram v3 polling для Telegram.
- SQLite-память: `messages`, `users`, `state`, `bot_control`.
- Decision engine со score, cooldown и anti-spam.
- Состояние персонажа: `mood`, `irritation`, `engagement`.
- Ollama через `http://localhost:11434/api/generate`.
- FastAPI UI: `/`, `/status`, `/toggle`, `/intervention`, `/logs`, `/state`.

## Запуск

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Заполните `TELEGRAM_BOT_TOKEN` в `.env`.

Установите и запустите Ollama, затем скачайте модель:

```powershell
ollama pull mistral
ollama serve
```

В BotFather отключите privacy mode, иначе бот не увидит все сообщения группы:

```text
/setprivacy -> выбрать бота -> Disable
```

Запуск:

```powershell
python main.py
```

Панель управления будет доступна по адресу:

```text
http://127.0.0.1:8080
```

## Рестарт без возни с PID

Если бот завис, используйте скрипты из корня проекта:

```powershell
powershell -ExecutionPolicy Bypass -File .\restart.ps1
```

Отдельно:

```powershell
powershell -ExecutionPolicy Bypass -File .\stop.ps1
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

Логи:

```powershell
Get-Content .\logs\bot.err.log -Tail 80
Get-Content .\logs\bot.out.log -Tail 80
```

## Как бот решает отвечать

Бот молчит по умолчанию. Ответ появляется, если его упомянули, ответили на его сообщение, явно обратились к нему или decision engine набрал порог `score >= 45`.

Anti-spam:

- максимум один ответ чаще чем раз в 5 сообщений без прямого обращения;
- cooldown 20-90 секунд;
- если бот уже говорил в последних 10 сообщениях, приоритет снижается.

## Структура

```text
Vozduhan/
  main.py
  bot/
    telegram.py
    handlers.py
    decision_engine.py
  ai/
    ollama_client.py
    prompt_builder.py
  memory/
    sqlite.py
  state/
    state_manager.py
  web/
    app.py
    templates/
      index.html
  config.py
  .env.example
```
