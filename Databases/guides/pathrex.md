# Pathrex и оптимизаторы

> Актуальные команды запуска находятся в [гайде раннера](../../Scripts/runners/README.md),
> а подготовка входов — в [гайде конвертеров](../../Scripts/converters/README.md).
> Ниже сохранены команды исторической серии.

Дата проверки: 2026-10-11. Команды — из корня RPQ_bench. Перед запуском выполнить
[общую подготовку](README.md#подготовка-окружения-и-запуск) (окружение/данные).
Фактическая версия и результат находятся в [отчёте](smoke-results.md);
Docker digest / JAR checksum / source SHA — в [runtime-lock.json](runtime-lock.json).

## Сборка и запуск

Используется текущий локальный source; пользовательские изменения сохраняются.
Rust 1.90+, CMake, C/C++ compiler, OpenMP. `bench` включает CLI; GraphBLAS/LAGraph
строятся автоматически. Первая сборка требует сеть и существенно дольше smoke.

```bash
cargo build --release --manifest-path Databases/pathrex/Cargo.toml --features bench -j 2
Databases/pathrex/target/release/pathrex query --help
Results/competitors_250k/venv/bin/python Scripts/competitors/smoke_250k.py pathrex
```

Ручной запрос:

```bash
Databases/pathrex/target/release/pathrex query \
  -g Datasets/rpqbench_250k/pathrex \
  -q Datasets/rpqbench_250k/prepared/queries/pathrex.txt \
  --base-iri http://example.org/ -a rpqmatrix -p pang-hybrid \
  -o Results/competitors_250k/pathrex-manual.json
```

`-p` меняет optimizer: none, pang-hybrid
(доступность проверить в help именно собранного binary). Текущий smoke запускает
`none` и `pang-hybrid` и проверяет result_count; исторический отчёт охватывал
шесть оптимизаторов. В текущем RPQMatrix `?` явно unsupported: 5/6
smoke queries проходят для каждого optimizer; NFA evaluator отдельно прошёл 6/6. Старый binary первоначально поддерживал лишь
первые четыре; source SHA не гарантирует актуальность executable.

## Данные и запросы

MatrixMarket directory: `vertices.txt` — `<name> 1-based-id`, `edges.txt` —
`<label> 1-based-id`, `N.txt` — square Boolean adjacency по метке N.
Это уже существующий вход, сверенный с исходным N3. Внутренние индексы 0-based.
Для нового датасета сначала создать согласованные словари/матрицы.

Queries — одна строка `query_id,SPARQL triple/property-path pattern`, например:

```text
1,<Article1> <creator> ?t
4,<Article1> (<references>/<cite>)* ?t
```

Base IRI разрешает короткие IRI в SPARQL; MM loader добавляет этот base к
словарям. Если словари уже содержат полные IRI, `--base-iri` не указывать:
loader иначе добавит prefix повторно. Для полного RDF сохранять полные IRI. CLI `-f` проверять по help; основной
проверенный graph input здесь MM, а не прямой N3.

## Контракт ответа и benchmark

Smoke проверяет con-any cardinalities, не сами endpoints. RPQMatrix не поддерживает
ZeroOrOne (`?`), хотя parser его принимает. Это явный unsupported, не неверный ответ.
В any-con и any-any `reachable_target_count` считает непустые **колонки**, поэтому
его нельзя сравнивать с числом distinct sources / pairs. На шаблоне20 q12 все
шесть optimizers вернули CLI count=1, а эталон и другие endpoint engines — 136
sources. Это расхождение контракта счётчика; relation API имеет отдельный `nnz`,
но CLI в этой проверке само отношение не выгружает. Корректность underlying
relation не опровергается сравнением этих разных счётчиков.
Подготовленные 20 шаблонов есть в `prepared/workload20/pathrex.txt`; это
другой набор, включающий any-con и positive closure. На нём 19/20 counts
совпали у каждого optimizer; q12 выявляет описанную проблему. Для корректного
benchmark сначала согласовать binding-dependent count contract.

Отдельный рабочий NFA режим, включая optional:

```bash
Databases/pathrex/target/release/pathrex query \
  -g Datasets/rpqbench_250k/pathrex \
  -q Datasets/rpqbench_250k/prepared/queries/pathrex.txt \
  --base-iri http://example.org/ -a nfarpq \
  -o Results/competitors_250k/pathrex-nfarpq.json
```

Для timings использовать `bench --runs ... --warm-up-runs ...` и один процесс
на весь файл; число повторов/потоки фиксировать. Новый smoke не меняет общий
runner. Inverse/negation не объявляются поддержанными только по SPARQL syntax.

Источники: [локальный AGENTS](../pathrex/AGENTS.md),
[build guide](../pathrex/README.md#local-build-linux),
[CLI args](../pathrex/pathrex/src/cli/args.rs).

[Все гайды](README.md) · [Семантика RPQ](../reachability.md).

[Контракт на отдельном графе](contract.md): оба CLI считают union targets;
`?x p ?x` не ограничивает равенство endpoints. Simple inverse может быть
переписан SPARQL parser в обращённые endpoints, nested inverse отклоняется.
