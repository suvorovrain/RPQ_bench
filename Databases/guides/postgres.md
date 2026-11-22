# PostgreSQL: recursive SQL RPQ

> Актуальные команды запуска находятся в [гайде раннера](../../Scripts/runners/README.md),
> а подготовка входов — в [гайде конвертеров](../../Scripts/converters/README.md).
> Ниже сохранены команды исторической серии.

Дата проверки: 2026-10-11. Команды — из корня RPQ_bench. Перед запуском выполнить
[общую подготовку](README.md#подготовка-окружения-и-запуск) (окружение/данные).
Фактическая версия и результат находятся в [отчёте](smoke-results.md);
Docker digest / JAR checksum / source SHA — в [runtime-lock.json](runtime-lock.json).

## Поставка и запуск

Официальный postgres:18 Docker image, фактическая server version записана в
отчёте, image digest закреплён. Не сборка source submodule. Local port 15542,
DB rpq, user postgres, password rpq-smoke-local. Psycopg 3 driver.

```bash
Results/competitors_250k/venv/bin/python Scripts/competitors/smoke_250k.py postgres
```

## Данные / import

```sql
CREATE TABLE edges(src BIGINT, pid INTEGER, dst BIGINT);
COPY edges FROM '/input/csv/edges.csv' WITH (FORMAT CSV, HEADER TRUE);
CREATE INDEX edges_src_pid ON edges(src,pid);
CREATE INDEX edges_dst_pid ON edges(dst,pid);
ANALYZE edges;
```

COPY читает путь внутри server container, не client machine. Применены эти
команды, загружено 61 017 строк. Для all-pairs zero-length дополнительно нужна
vertices(id) из vertices.csv; endpoints нельзя восстанавливать только из
предикатов конкретного запроса. N3→CSV выполняет общий converter.

## RPQ→SQL

SQL files q1..q6.sql и workload20/qN.sql готовы. В них DFA/NFA transition
relation и рекурсивный fixpoint по `(vertex,state)` с UNION (без ALL).
Уже пройденные states удаляются; пути/depth не накапливаются. Для any-con
workload20 переворачивает граф и автомат. Это реализованный SQL RPQ algorithm,
не native SPARQL syntax и не PostgreSQL regex по строкам.

```bash
docker start rpq-bench-250k-postgres
docker exec -i rpq-bench-250k-postgres psql -U postgres -d rpq \
  < Datasets/rpqbench_250k/prepared/queries/q4.sql
```

Все шесть точных endpoint sets совпали с Python oracle. Prepared 20 SQL templates
существуют отдельно; их проверки смотреть в отчёте, не выводить из six-test pass.
Для all-pairs seed все vertices и source в recursive key; финал DISTINCT source,v.
Не добавлять path/depth в UNION key: тогда cycles могут не завернуться в fixpoint.
CYCLE по original vertex не заменяет product-state visited и может потерять
допустимые regex walks. SQL text generation, parse/plan и query execution
измерять раздельно; indexes/ANALYZE тоже вне query timing.

Расширенный запуск `smoke_250k.py postgres --workload20` также прошёл
20/20 точных endpoint sets (con-any / any-con).

Источники: [WITH RECURSIVE / UNION / CYCLE](https://www.postgresql.org/docs/current/queries-with.html),
[COPY](https://www.postgresql.org/docs/current/sql-copy.html).

[Все гайды](README.md) · [Семантика RPQ](../reachability.md).
