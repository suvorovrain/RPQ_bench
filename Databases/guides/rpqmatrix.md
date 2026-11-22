# rpqmatrix (CSR/CSC baseline)

> Актуальные команды запуска находятся в [гайде раннера](../../Scripts/runners/README.md),
> а подготовка входов — в [гайде конвертеров](../../Scripts/converters/README.md).
> Ниже сохранены команды исторической серии.

Дата проверки: 2026-10-11. Команды — из корня RPQ_bench. Перед запуском выполнить
[общую подготовку](README.md#подготовка-окружения-и-запуск) (окружение/данные).
Фактическая версия и результат находятся в [отчёте](smoke-results.md);
Docker digest / JAR checksum / source SHA — в [runtime-lock.json](runtime-lock.json).

## Сборка

```bash
cmake -S Databases/rpq-matrix -B Databases/rpq-matrix/build \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5
cmake --build Databases/rpq-matrix/build \
  --target baseline_query create_pairs baseline_build -j 2
Results/competitors_250k/venv/bin/python Scripts/competitors/smoke_250k.py rpqmatrix
```

Smoke использовал имеющиеся executables и пересоздал отдельный binary matrix
index для подготовленного уникального graph.dat. Исходные индексы пользователя
не перезаписывались. Для строгого performance reproduction пересобрать binary
и записать его hash/compiler flags.

## Формат и построение индекса

`graph.dat`: строки `s p o`, положительные 1-based IDs, без header.
`graph.dat.SO`: `id <vertex-name>`. `graph.dat.P`: `id <predicate-name>`.
Словари/индекс находятся рядом с graph.dat. В этом графе P=9, N=61017, V=24225.
Параметры N/P надо брать из manifest, а не из размера полного N3.

```bash
mkdir -p Results/competitors_250k/pairs
(cd Results/competitors_250k/pairs && \
  ../../../Databases/rpq-matrix/build/create_pairs \
  ../../../Datasets/rpqbench_250k/prepared/matrix/graph.dat 9 61017)
mkdir -p Datasets/rpqbench_250k/prepared/matrix/graph.dat.baseline-64
Databases/rpq-matrix/build/baseline_build \
  Results/competitors_250k/pairs/ \
  Datasets/rpqbench_250k/prepared/matrix/graph.dat.baseline-64 24225
```

`create_pairs` пишет binary `.pairs` в текущую директорию; trailing slash у
pairs dir нужен upstream filename concatenation. `.baseline-64/0001.mat` и
остальные `.mat` — binary native matrices, не MatrixMarket.

## Запросы

```bash
Databases/rpq-matrix/build/baseline_query \
  Datasets/rpqbench_250k/prepared/matrix/graph.dat \
  Datasets/rpqbench_250k/prepared/queries/matrix.tsv 9 61017 1 0
```

Последние параметры — measured runs, warmups в нашей ревизии. Query row:
`1 <Article1> <creator> ?t#`; знак `#` — часть формата, не SPARQL comment.
Имена должны совпадать со словарями. Файл называется TSV исторически, но здесь
строки используют пробелы. Выход `query_id;cardinality;time`; единицы времени
проверять по source, не переносить между drivers автоматически.

Конвертация из N3 выполнена общим prepare_250k.py через проверенную проекцию.
Системе нужны compiled indexes, одной смены расширения файла недостаточно.
Baseline smoke проверяет counts 6/6, не materialized relation.

Дополнительно проверены все 20 upstream шаблонов: counts 20/20. Native
parser ожидает односимвольное имя конечной переменной (`?t#`); `?obj#`
воспринимается ошибочно и может молча дать 0. Converter переименовывает
`?sub`→`?s`, `?obj`→`?t` только в native query files; RDF/Pathrex variables
сохраняются. Это ограничение формата driver, не расхождение RPQ алгоритма.

Источники: [upstream README](../rpq-matrix/README.md),
[query driver](../rpq-matrix/src/baseline_query.cpp),
[create_pairs](../rpq-matrix/src/create_pairs.cpp).

[Все гайды](README.md) · [Семантика RPQ](../reachability.md).
