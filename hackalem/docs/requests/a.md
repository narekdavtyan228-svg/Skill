# Запросы от роли A

Формат строки: `[кому] что нужно и зачем`. Файл принадлежит роли A, остальные его только читают.
Сюда же пишутся блокеры, если агент остановился после трёх неудачных попыток.

[B] Реализовать `extract.extractor.extract_permit(permit_dir: str | Path) -> core.schemas.ExtractedPermit`. Все поля `ExtractedPermit` обязательны; неизвестное значение передаётся как `EvidenceValue(value=None, status="unknown" | "insufficient_evidence", prooflinks=[])`, известное — только с непустым `prooflinks`. Не создавать дублирующие модели.

[C] Реализовать `rules.engine.evaluate_rules(permit: core.schemas.ExtractedPermit, registries: core.schemas.RegistrySnapshot) -> list[core.schemas.Finding]` без I/O. Каждый `confirmed` finding обязан иметь документальный prooflink из входного комплекта.

[C] Реализовать `rules.verdict.derive_verdict(findings: Sequence[core.schemas.Finding], unknowns: Sequence[str]) -> core.schemas.Verdict`. Любой unknown, P1 или P2 должен давать `block_and_escalate`; только P3 — `approve_with_conditions`.

Минимальный B-контракт поля:

```json
{
  "value": "PERMIT-001",
  "status": "confirmed",
  "prooflinks": [
    {"source_id": "permit.csv", "location": "row:2", "quote": "PERMIT-001"}
  ]
}
```
