# Contributing

## Процесс
1. Ветка от `main`: `git checkout -b feat/short-description`.
2. Локально: `ruff check . && python -m compileall -q .`.
3. PR с описанием и ссылкой на пункт ROADMAP.
4. Зелёный CI + ревью.

## Стиль
- Python 3.11+, type hints для новых модулей.
- `ruff format`.
- Никаких секретов в коммитах.

## Целевая структура
```
app/{core,api,db,auth,services,agents,tools,schemas}
frontend/   # Next.js
tests/
```
