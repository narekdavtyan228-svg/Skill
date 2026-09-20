# Внешние скиллы

Сюда вендорятся скиллы, которые должны быть у всех троих одинаковые и не зависеть
от настроек конкретной машины. Максимум три штуки — каждый скилл стоит контекста.

Рекомендуемый набор:

| Каталог | Источник | Кому |
|---|---|---|
| `ui-ux-pro-max/` | github.com/nextlevelbuilder/ui-ux-pro-max-skill | роль C, витрина |
| `diagram-design/` | github.com/cathrynlavery/diagram-design | роль C, схема на слайд |
| `anydoc/` | github.com/firecrawl/anydoc | роль B, разбор PDF |

Как положить:

```bash
git clone --depth 1 <url> /tmp/s && cp -r /tmp/s .agents/skills/<имя>
find .agents/skills -name .git -type d -prune -exec rm -rf {} +
```

Ссылки на конкретные SKILL.md прописаны в корневом AGENTS.md §8 — без этого
агент может их не заметить.
