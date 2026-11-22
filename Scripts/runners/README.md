# Запуск конкурентов

Из корня репозитория:

```bash
Scripts/runners/run_rpq250k --name basic4 --runs 4 --warmups 1
Scripts/runners/run_rpq250k --engines pathrex larpq rpqmatrixGB --queries 1 3 --name matrix
python3 -m Scripts.runners.postgres.run --queries 2 --name postgres-debug
python3 -m Scripts.runners --dataset wiki --config /path/to/config.json --dry-run
```

`RPQ_PYTHON` задаёт интерпретатор для shell-обёртки. При работе из venv
можно просто активировать его. `--dry-run` показывает выбранные наборы
и ID. Подготовка входов описана в [converters](../converters/README.md).

| Каталог / имя для `--engines` | Поставка и подготовка |
| --- | --- |
| `pathrex` | [Rust CLI](../../Databases/guides/pathrex.md), `cargo build --release --manifest-path Databases/pathrex/Cargo.toml --features bench`. |
| `larpq` | [LAGraph experimental](../../Databases/guides/build-native.md#larpq), драйвер собирается из `larpq/driver.c`. |
| `rpqmatrix` | [C++ baseline](../../Databases/guides/rpqmatrix.md), нужны `baseline_query`, `create_pairs` и `baseline_build`. |
| `rpqmatrixGB` | [GraphBLAS baseline](../../Databases/guides/rpqmatrixGB.md), нужен `baselineGB_query`. |
| `ring` | [Ring-RPQ и SDSL](../../Databases/guides/build-native.md#ring-rpq), драйвер собирается из закреплённой версии исходника. |
| `millenniumdb` | [Нативный mdb](../../Databases/guides/build-native.md#millenniumdb), отдельный локальный HTTP-процесс. |
| `duckdb`, `kuzu` | Python wheels из `requirements.txt`, локальные базы. [DuckDB](../../Databases/guides/duckdb.md) · [Kuzu](../../Databases/guides/kuzu.md). |
| `jena`, `blazegraph` | Закреплённые архив/JAR и Temurin. [Jena](../../Databases/guides/jena.md) · [Blazegraph](../../Databases/guides/blazegraph.md). |
| `postgres`, `virtuoso`, `neo4j`, `memgraph`, `falkordb` | Закреплённые Docker-образы из `Databases/guides/runtime-lock.json`. |

Для всех движков индивидуальная команда имеет вид
`python3 -m Scripts.runners.<имя>.run` с теми же флагами. Для полного стенда
нужны Python 3.12, Docker и библиотеки для нативных движков.

```bash
python3 -m venv .rpq-runtime/venv
source .rpq-runtime/venv/bin/activate
python -m pip install -r Scripts/runners/requirements.txt
python Scripts/runners/download_tools.py --images
```

## Конфигурация

Скопируйте [config.json](config.json) для своего эксперимента. Все относительные
пути разрешаются от корня репозитория. `defaults` задаёт число замеров и
прогревов, бюджет потоков, таймаут команд, опциональную Docker memory quota
и каталог сборок/инструментов. По умолчанию движки запускаются последовательно
со всеми CPU, видимыми процессу, а Docker CPU quota не задаётся. В метаданных
это запрошенный бюджет. Фактический лимит GraphBLAS после загрузки зависит от
версии Pathrex и её `ThreadScope`.

Каждый элемент `datasets` задаёт `prepared`, `graph`, `engines` и
`query_set`. Например, внутри записи датасета можно добавить:

```json
{
  "competitors": {
    "pathrex": {"query_ids": ["1", "3"], "optimizer": "pang-hybrid"},
    "postgres": {"query_ids": ["2"], "query_set": "basic4"}
  }
}
```

`query_dir` позволяет указать конкретный подготовленный каталог для движка.
`--engines`, `--queries`, `--query-set`, `--runs`, `--warmups`
и `--threads` переопределяют конфиг на один запуск. При другом наборе ID
для каждого движка удобнее запись `datasets.<name>.competitors`.

## Результаты

`Results/<датасет>/<UTC timestamp>-<name>/info.txt` содержит время,
выбранные наборы, границы таймеров и команды. В `metadata.json` есть
состояние Git и настройки. В каталоге каждого движка лежат отобранные входы,
`run.log`, `result.json` и дополнительные файлы соответствующего адаптера.
Сбои видны в JSON и дают ненулевой код завершения. Для сравнения укажите
[анализатор](../analyse/README.md) на каталог прогона.

Готовый ответ — отношение достижимости. Серверные адаптеры для запросов
с фиксированным источником дочитывают все ID. Нативные адаптеры используют
свои границы таймеров. Pathrex, обе матрицы и Ring принимают и другие
комбинации концов пути, когда manifest содержит нужный эталон.
[Форматы эталона](../converters/README.md).

## Что измеряет каждый раннер

Основная серия записывается в `samples_ms` с границей `scope`. Дополнительные
фазы того же повтора лежат в `phase_samples_ms`. Все значения в миллисекундах.
Загрузка базы, индекса, прогревы и проверка ответа находятся вне основной серии.
Для HTTP, Bolt, Redis и PostgreSQL результаты дочитываются целиком, а время
берётся из метрик движка. Границы этих метрик различаются.

| Движок | Как читается результат | Основной таймер и дополнительные фазы |
| --- | --- | --- |
| Pathrex | `result_count` по ID запроса из JSON нативного CLI | `total_ns` включает подготовку, оптимизацию и вычисление. `ffi_only_ns` — отдельная серия с готовым планом |
| LA-RPQ | `TIMING` содержит число ответов каждого замера. После серии драйвер возвращает множество ID из вектора | Таймер C-драйвера вокруг вызова NFA и `GrB_Vector_wait(GrB_MATERIALIZE)` |
| rpqmatrix | Строка CLI `query_id;count;ns`, проверяется число пар | Время построения дерева RPQ и вычисления результата |
| rpqmatrixGB | Строка CLI `query_id;count;ns`, проверяется число пар | Время построения дерева RPQ и вычисления с `GrB_Matrix_wait(GrB_MATERIALIZE)` |
| Ring | Строка CLI `ordinal;count;ms`, проверяются порядок и число пар | Время вызова query API до заполнения результата из копии upstream-драйвера с исправленной единицей |
| DuckDB | Все строки `fetchall()`, число возвращённых строк сверяется с профилем | `latency` из JSON-профиля. Отдельно планировщик, оптимизаторы и физический планировщик. Профили в `profiles/` |
| Kùzu | Итерация по строкам `QueryResult` | `get_execution_time()` и отдельно `get_compiling_time()` из того же объекта |
| Jena | Обход `ResultSet` внутри транзакции TDB2, преобразование URI в ID и сверка множества после таймера | Таймер Java-драйвера на транзакцию чтения. Отдельно парсинг SPARQL в `QueryFactory.create` |
| PostgreSQL | Все строки SQL-курсора | Приращение `total_exec_time` из `pg_stat_statements` для того же запроса. Отдельно `total_plan_time`. Проверяется один вызов и одно планирование |
| MillenniumDB | CSV по HTTP, сверка запроса и числа строк с журналом | `Execution` из `server.log`, включая серверную запись строк ответа. Отдельно `Parser` и `Optimizer` из того же блока |
| Blazegraph | SPARQL JSON по HTTP, UUID связывает вызов с записью в журнале | `elapsed` верхнего уровня `QueryLog`, от старта до завершения вычисления движком |
| Virtuoso | SPARQL JSON по HTTP, сверка числа, порядка и текста вызовов с журналом | `ql_rt_msec` из `SYS_QUERY_LOG`. Отдельно `ql_c_msec` для компиляции |
| Neo4j | Все Bolt-записи, затем `ResultSummary` | `t_first + t_last`, запуск запроса и стриминг результата. Оба значения сохранены отдельно |
| Memgraph | Все Bolt-записи, затем поля Memgraph из метаданных Bolt | `plan_execution_time`, отдельно `parsing_time` и `planning_time`. Перевод из секунд в миллисекунды |
| FalkorDB | ID из строк компактного Redis-ответа | `Query internal execution time` из статистики того же `GRAPH.QUERY --compact` |

Neo4j, Blazegraph и Virtuoso возвращают целое число миллисекунд. Нули
сохраняются в JSON и CSV. На логарифмическом графике они отмечаются числом
нулевых замеров под значением медианы.

Семантика серверных полей описана в документации
[`pg_stat_statements`](https://www.postgresql.org/docs/18/pgstatstatements.html),
[Bolt](https://neo4j.com/docs/bolt/current/bolt/message/) и
[`SYS_QUERY_LOG`](https://docs.openlinksw.com/virtuoso/ch-server/).
