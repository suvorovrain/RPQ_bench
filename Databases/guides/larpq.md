# LARPQ / LAGraph 2-rpq

> Актуальные команды запуска находятся в [гайде раннера](../../Scripts/runners/README.md),
> а подготовка входов — в [гайде конвертеров](../../Scripts/converters/README.md).
> Ниже сохранены команды исторической серии.

Дата проверки: 2026-10-11. Команды — из корня RPQ_bench. Перед запуском выполнить
[общую подготовку](README.md#подготовка-окружения-и-запуск) (окружение/данные).
Фактическая версия и результат находятся в [отчёте](smoke-results.md);
Docker digest / JAR checksum / source SHA — в [runtime-lock.json](runtime-lock.json).

## Сборка и запуск

Это C library API, штатного SPARQL command-line executable в подключённой ветке
нет. Сборка библиотеки и нашего минимального
[larpq_smoke.c](../../Scripts/archive/competitors/larpq_smoke.c) описаны в
[build-native.md](build-native.md#larpq).

```bash
Results/competitors_250k/build/larpq-smoke \
  Datasets/rpqbench_250k/prepared/matrix/graph.dat \
  Datasets/rpqbench_250k/prepared/queries/larpq.tsv 24225 9
Results/competitors_250k/venv/bin/python Scripts/competitors/smoke_250k.py larpq
```

## Данные и query API

Алгоритм получает arrays of LAGraph_Graph: по одной Boolean adjacency matrix
на метку для исходного графа и NFA. Переходы epsilon нужно устранить заранее;
source IDs и состояния в API 0-based. Дополнительные параметры: starting/final
states, sources, inverse labels и inverse whole query.

Наш harness читает 1-based `graph.dat`, строит GraphBLAS matrices, кеширует
transpose и вызывает именно `LAGraph_2RegularPathQuery`. Его query file —
собственный компактный TSV, не upstream SPARQL: `qid source0 states final_bitmask
n_transitions`, затем тройки `from_state label0 to_state` в той же строке.
Полная спецификация и generator находятся в prepare_250k.py. Для шести NFA
также подготовлены JSON и MatrixMarket `automata/q<id>-<pid>.mtx`.

## Нюансы

Adjacency и cached transpose должны быть BY_ROW; иначе pinned CheckGraph
возвращает `only by-row format supported`, особенно на automata 1×1.
Harness задаёт оба явно. Библиотека собрана с GraphBLAS 10.3.1, алгоритмическая
ветка идентифицирована SHA в lock. Это рабочая комбинация, не обещание ABI
совместимости со всеми системными GraphBLAS.

На выходе GrB_Vector targets; multi-source объединяет ответы и не сохраняет
source provenance. Any-any — повторение по sources либо отдельный алгоритм;
any-con — reverse graph/automaton, а не сравнение union targets с pairs.
Наш smoke проверяет точные sets 6/6; расширенный workload — 20/20, включая
any-con. `larpq.tsv` для workload20 имеет extended header: qid source0 states
start_bitmask final_bitmask inverse_graph ntrans, затем transition triples;
запускать harness с дополнительным аргументом `extended`. Для any-con автомат
уже перевёрнут converter-ом, inverse_labels переворачивает только graph edges. Harness не является полноценным
production adapter или performance driver: импорт и подготовка не замеряются.

N3 конвертируется общим pipeline; сам library API RDF не читает.
Источники: [API source](../larpq/experimental/algorithm/LAGraph_RegularPathQuery.c),
[header](../larpq/include/LAGraphX.h),
[статья авторов](https://arxiv.org/html/2412.10287).

[Все гайды](README.md) · [Семантика RPQ](../reachability.md).

[Проверка контракта](contract.md) отдельно подтвердила nullable/zero-length,
повторение ребра, union multi-source и inverse. Для native whole-query inverse
caller меняет QS/QF местами; multi-source vector не сохраняет пары.
