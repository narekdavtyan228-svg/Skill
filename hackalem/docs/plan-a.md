# Роль A: первый вертикальный срез

## Цель среза (45 минут)

На одном синтетическом комплекте пройти путь `permit_dir -> extract -> mock API -> rules -> PermitResult` и напечатать JSON, валидный по Pydantic v2. Базовый ловушечный сценарий: просроченный газоанализ приводит к `block_and_escalate`, содержит реальный prooflink и явно требует решения человека. Неполные/противоречивые данные также закрываются fail-closed.

## Шаги и файлы

1. **Заморозить контракт результата и внутренние DTO.**
   - `core/schemas.py`: строгие модели `Prooflink`, `Validation`, `Finding`, `PermitResult`; enum/литералы для verdict и classification; внутренние `ExtractedPermit` и `RegistrySnapshot` для стыков B/C.
   - Инварианты: `confirmed` finding без prooflink невалиден; prooflink требует непустые `source_id`, `location`, `quote`; HITL-поля обязательны; неизвестность не превращается в догадку.
   - Готово, когда эталонный JSON из `AGENTS.md` валидируется, а негативные случаи отклоняются.

2. **Дать детерминированный слой mock-реестров и проверки доказательств.**
   - `core/mock_api.py`: `employee_clearance`, `gas_test_status`, `asset_isolation`, `site_restrictions`; фиксированные ответы с источником и записью вызова.
   - `core/prooflinks.py`: проверка существования `source_id` внутри комплекта и корректности `page:N`/`row:N`; для первого среза без сетевых вызовов.
   - Готово, когда один прогон вызывает минимум один mock API, одинаковый ввод даёт одинаковый ответ, невалидная ссылка блокирует успешный результат.

3. **Собрать сквозной оркестратор с временными адаптерами.**
   - `core/orchestrator.py`: `run(permit_dir: str | Path, run_id: str | None = None) -> PermitResult`; последовательность extraction -> четыре mock API -> rules -> verdict -> prooflink verification -> audit log.
   - До готовности B/C использовать узкие локальные заглушки за теми же сигнатурами; импорт реальных модулей не должен менять оркестратор.
   - Любая ошибка импорта, отсутствующий источник или противоречие формирует контролируемый `block_and_escalate`, а не `approve` и не необработанное исключение.
   - Готово, когда один комплект выдаёт сериализуемый `PermitResult` со статусом `completed`, находкой, prooflink и HITL-полями.

4. **Подключить минимальную оценку и команды запуска.**
   - `eval/run.py`: прочитать `data/ground_truth.json`, запустить все доступные комплекты, вывести recall, false approve и долю findings без валидного prooflink.
   - `eval/metrics.py`: чистые функции расчёта метрик с безопасным поведением на пустом наборе.
   - `Makefile`: рабочие цели `smoke`, `eval`, `test`, `ui`; `requirements.txt`: только согласованный стек; `.env.example` и `.gitignore`: без секретов и артефактов окружения.
   - Готово, когда команды имеют стабильные коды возврата и `smoke` не требует OpenAI-ключа на детерминированной фикстуре.

5. **Передать контракты ролям B/C.**
   - `docs/requests/a.md`: записать приведённые ниже сигнатуры, обязательные поля и один минимальный JSON-пример без изменения чужих каталогов.
   - Готово, когда B и C могут реализовать свои слои независимо, не импортируя детали оркестратора.

## Интерфейсы для B и C

```python
# B: extract/extractor.py
def extract_permit(permit_dir: str | Path) -> ExtractedPermit: ...

# C: rules/engine.py
def evaluate_rules(
    permit: ExtractedPermit,
    registries: RegistrySnapshot,
) -> list[Finding]: ...

# C: rules/verdict.py
def derive_verdict(
    findings: Sequence[Finding],
    unknowns: Sequence[str],
) -> Literal["approve", "approve_with_conditions", "block_and_escalate"]: ...
```

- `ExtractedPermit` и `RegistrySnapshot` определяет и замораживает `core/schemas.py`; B возвращает их без собственных дублирующих моделей.
- Каждое извлечённое значение, использованное правилом, несёт `Prooflink`; отсутствующее значение остаётся `None`/`insufficient_evidence`.
- C возвращает только `Finding` из `core/schemas.py`, сохраняет входные prooflinks и не выполняет I/O или вызовы mock API.
- Минимальный первый кейс использует единый `rule_id` для просроченного газоанализа во всех слоях и `ground_truth.json`.

## Тесты первого среза

- `core/tests/test_schemas.py`: валидный контракт; запрет пустого prooflink у `confirmed`; обязательность HITL; допустимые enum-значения.
- `core/tests/test_mock_api.py`: детерминизм четырёх адаптеров, наличие источника, фиксация вызова.
- `core/tests/test_prooflinks.py`: существующий файл/страница/строка проходят; отсутствующий источник и невозможная локация отклоняются.
- `core/tests/test_orchestrator.py`: ловушечный комплект блокируется; при пропавшем обязательном поле нет `approve`; есть mock-вызов и audit log.
- `eval/tests/test_metrics.py`: recall, false approve и доля плохих prooflinks на маленьких табличных примерах.

## Критерии готовности среза

- `make smoke` завершается без исключений и печатает валидный JSON `PermitResult`.
- Ловушечный комплект получает `block_and_escalate`; неполный комплект никогда не получает `approve`.
- Каждый `confirmed` finding имеет проверенный `source_id + location + quote`.
- Результат и каждая находка содержат обязательный HITL-контекст согласно замороженной схеме.
- За прогон зафиксирован минимум один вызов mock API, а срок газоанализа проверен детерминированным Python-кодом.
- `make eval` печатает три метрики; `make test` проходит полностью.
- После одобрения плана работа ограничивается файлами роли A; реализации B/C заменяют заглушки только через зафиксированные сигнатуры.
