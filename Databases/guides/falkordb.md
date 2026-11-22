# FalkorDB

> Актуальные команды запуска находятся в [гайде раннера](../../Scripts/runners/README.md),
> а подготовка входов — в [гайде конвертеров](../../Scripts/converters/README.md).
> Ниже сохранены команды исторической серии.

Дата проверки: 2026-10-11. Команды — из корня RPQ_bench. Перед запуском выполнить
[общую подготовку](README.md#подготовка-окружения-и-запуск) (окружение/данные).
Фактическая версия и результат находятся в [отчёте](smoke-results.md);
Docker digest / JAR checksum / source SHA — в [runtime-lock.json](runtime-lock.json).

## Поставка / протокол

Официальный falkordb/falkordb Docker image, закреплённый digest. Redis protocol,
команда GRAPH.QUERY; не Bolt. Source checkout может отличаться от образа: версия
MODULE LIST записана в фактическом отчёте.

```bash
Results/competitors_250k/venv/bin/python Scripts/competitors/smoke_250k.py falkordb
```

Runner публикует localhost:16389 → Redis:6379, создаёт graph `rpq250k`, индекс
Node.id, все 24 225 nodes и 61 017 relationships. UI не требуется.

## Данные / запросы

Общий CSV: nodes id/name, отдельные files src/dst для каждого relationship type.
Для smoke Python Redis client преобразует rows в CREATE/UNWIND batches по 500:
графу нужен Cypher import, прямой N3 loader в этом pipeline не используется.
Наличие именованного Node.id важно: internal IDs других СУБД не совпадают.

Ручной запрос к уже созданному серверу:

```bash
docker start rpq-bench-250k-falkordb
docker exec rpq-bench-250k-falkordb redis-cli GRAPH.QUERY rpq250k \
  'MATCH (s:Node {id:1})-[:creator]->(t:Node) RETURN DISTINCT t.id'
```

Подготовленные q1/q2/q3/q5/q6 Cypher files находятся в queries/*.falkordb.cypher
после smoke. Variable-length `[:coauthor*0..]`, label alternatives и concatenation
переведены для этих примеров; endpoints 5/5 совпали. Q4 `(references/cite)*`
помечен no_translation, а не притворно заменён обычным `[:references|cite*]`:
последний допускает другой язык.

## Ограничения / timing

Не выводим full arbitrary WALK RPQ из наличия GraphBLAS внутри движка.
По отдельным запросам нужны проверки relationship uniqueness, closures и
repeated-edge semantics. Для count — DISTINCT endpoints, не count paths.
Командный `--compact` формат Redis имеет типизированные вложенные values;
runner извлекает integer IDs, а не сравнивает сериализацию node objects.
Bulk load и graph creation отдельно от измерений. Smoke server остановлен;
для persistent benchmark отдельно настроить сохранение graph state.

Источники: [официальный MATCH](https://docs.falkordb.com/cypher/match),
[README / Docker / Redis](../falkordb/README.md).

[Все гайды](README.md) · [Семантика RPQ](../reachability.md).

[Проверка контракта](contract.md): фиксированный `p/q/p` допустил повторение
ребра и совпал с WALK Pathrex/LARPQ. Поведение Neo4j/Memgraph здесь отличается;
полнота произвольных compound closures всё ещё не установлена.
