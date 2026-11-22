# DuckDB: recursive SQL RPQ

Дата проверки: 2026-10-11. Команды — из корня RPQ_bench. Перед запуском выполнить
[общую подготовку](README.md#подготовка-окружения-и-запуск) (окружение/данные).
Фактическая версия и результат находятся в [отчёте](smoke-results.md);
Docker digest / JAR checksum / source SHA — в [runtime-lock.json](runtime-lock.json).

## Поставка и запуск

Python wheel duckdb==1.5.6, embedded DB, threads=2. Это не source build и не
DuckPGQ extension. Полный native SPARQL parser не нужен: наш converter готовит
NFA/DFA и recursive SQL для endpoint relation.

```bash
Results/competitors_250k/venv/bin/python Scripts/competitors/smoke_250k.py duckdb
```

Runner создаёт/обновляет edges в своей Results/competitors_250k/duckdb.duckdb.
Это task-specific database; пользовательские БД не затрагиваются.

## Данные / запросы

```sql
CREATE TABLE edges AS SELECT * FROM read_csv('/absolute/path/to/prepared/csv/edges.csv');
```

CSV имеет header src,pid,dst, numeric IDs; scanner определяет типы. Можно
зафиксировать schema BIGINT/INTEGER явно при другом датасете. vertices.csv
нужен для all-pairs zero-length seed. N3 превращается в этот CSV общим pipeline.

Файлы queries/q1..q6.sql и workload20/q1..q20.sql — рабочие recursive UNION
запросы по product states. Стандартный UNION дедуплицирует состояния и
завершается на finite graph; paths не перечисляются. Для обратного endpoint
binding нужны reverse transitions и reversed edge direction.

```python
import duckdb
con = duckdb.connect('Results/competitors_250k/duckdb.duckdb')
con.execute('SET threads=2')
query = open('Datasets/rpqbench_250k/prepared/queries/q4.sql').read()
print(con.execute(query).fetchall())
```

Пройдены 6/6 smoke endpoint sets и дополнительно все 20 upstream шаблонов с
фиксированными bindings. Набор20 содержит any-con, positive closure и составные
выражения; некоторые ответы пустые. Эти проверки не покрывают inverse и all-pairs.

USING KEY — другой способ организации recursive state, сейчас не используется.
Для benchmark можно сравнить его отдельно, сохранив тот же RPQ result contract.
Загрузку CSV, regex→DFA, SQL generation, planning и execution/fetching измерять
раздельно. Не полагаться на input ordering как часть endpoint semantics.

Источники: [WITH / graph examples](https://duckdb.org/docs/current/sql/query_syntax/with),
[USING KEY](https://duckdb.org/2025/05/23/using-key).

[Все гайды](README.md) · [Семантика RPQ](../reachability.md).
