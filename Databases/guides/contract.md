# Контракт относительно Pathrex и LARPQ

Проверка 2026-10-11: исходники закреплённых checkout, CLI/API на специальном
семивершинном графе, Jena 6.2.0, Kuzu 0.11.3 и три Docker Cypher-системы.
Это дополняет [250k smoke](smoke-results.md), не заменяет проверку всего языка.
Машинные ответы: [Pathrex/LARPQ/Kuzu/Jena](contract-results.json),
[Neo4j](contract-neo4j.json), [Memgraph](contract-memgraph.json),
[FalkorDB](contract-falkordb.json).

## Какой контракт действительно есть у двух исходных систем

Обе вычисляют **WALK reachability**: допускают повторение вершин и рёбер,
проверяют регулярный язык меток, схлопывают разные пути к одному результату.
Нулевой путь входит в ответ, если автомат принимает ε. Ограничения числа hops
в этих алгоритмах нет: матричное замыкание / обход произведения до fixpoint.
Это следует из Boolean операций и подтверждено diamond, cycle и zero-length
проверками. Путь как последовательность рёбер эти API не выдают.

Но **их интерфейсы ответа различаются**:

| Интерфейс | Фактический ответ | Что означает число |
| --- | --- | --- |
| Pathrex RPQMatrix API | Boolean relation matrix `M[s,t]`, плюс `nnz` | `nnz` — число пар после ограничений endpoints; CLI его не использует |
| Pathrex RPQMatrix CLI | `reachable_target_count()` | Число непустых колонок, distinct targets |
| Pathrex NFA API/CLI | Target vector, после возможного фильтра object | Число targets; несколько источников объединяются |
| LARPQ `LAGraph_2RegularPathQuery` | Target vector от множества `S` | Distinct targets; информация о том, какой source достиг target, отсутствует |

Основание: [Pathrex result](../pathrex/pathrex/src/rpq/rpqmatrix/result.rs),
[ограничения endpoints в matrix expression](../pathrex/pathrex/src/rpq/rpqmatrix/expr.rs),
[Pathrex NFA](../pathrex/pathrex/src/rpq/nfarpq.rs),
[LARPQ implementation](../larpq/experimental/algorithm/LAGraph_RegularPathQuery.c).
Нативный алгоритм Pathrex NFA взят из его собственного LAGraph checkout;
его нельзя отождествлять с подключённой веткой LARPQ `2-rpq`.

В Pathrex variable subject в NFA означает **все вершины как sources**. Fixed
object фильтрует итоговый target vector, а не превращает его в source vector.
Поэтому `?s p D` через этот CLI отвечает на существование хотя бы одного source:
0/1. Это такое же число, как у matrix CLI, но matrix API сохраняет само отношение.
`?s p ?t` в NFA означает union targets, а не выдачу всех пар.

## Проверка режимов привязки

Fixture: `A-p-B`, `A-p-C`, `B-p-D`, `C-p-D`, `B-q-A`, `C-q-A`,
`E-z-E`, `F-p-G`, `G-q-F`. E — вершина графа, изолированная относительно p.
Для p имеется 5 пар, 4 distinct targets и 4 distinct sources.

| Запрос | Endpoint relation / SELECT DISTINCT | Оба Pathrex CLI | LARPQ adapter |
| --- | --- | --- | --- |
| `A p ?t` (con-any) | `{B,C}` / 2 | 2 | `S={A}` → `{B,C}` |
| `?s p D` (any-con) | `{B,C}` / 2 sources | 1 | От D по обратному запросу → `{B,C}` |
| `?s p ?t` (any-any) | 5 pairs | 4 targets | `S=V` → 4 targets; пары не сохраняются |
| `A p/p D` (con-con) | true | 1 | Проверить D в vector, полученном от A |
| `A p D` (con-con) | false | 0 | Та же проверка принадлежности |

Таким образом, для непосредственного сравнения текущих CLI подходит **con-any**.
Для any-con нужен source set/count: в matrix API считать строки/`nnz` при fixed
object; в vector API запускать обратный запрос от target. Для any-any нужен
полный relation API либо отдельный запуск от каждого source с сохранением
его ID. Один multi-source вызов LARPQ не заменяет эти запуски.

Пример: LARPQ от `{B,C}` по p вернул только `{D}`, а не два результата `(B,D)`
и `(C,D)`. Any-con уже выполнялся нашим 250k adapter через обращённый DFA и
inverse graph labels; это адаптация, не автоматическое поведение Pathrex CLI.

## Операторы, равенство переменных и границы графа

- **Повторение ребра:** `F p/q/p ?t` должно вернуть G, использовав `F-p-G`
  дважды. Pathrex Matrix/NFA и LARPQ вернули G. Diamond `A p/p ?t` дал только D,
  хотя к нему ведут два пути.
- **Нулевой путь:** `E p* ?t` вернул E; `E p+ ?t` пуст. `p?` работает в Pathrex
  NFA; RPQMatrix явно отклоняет ZeroOrOne. LARPQ принимает готовый ε-free
  автомат: nullable выражение передаётся через пересечение start/final states.
- **Inverse:** LARPQ имеет `inverse_labels` и `inverse` для всего запроса.
  При `inverse=true` caller должен поменять QS/QF местами и начинать от target:
  правильный вызов от D вернул B,C, вызов без перестановки states — пусто.
  Pathrex `PathExpr` не имеет Reverse. Однако SPARQL parser может обратить
  endpoints для `^p` или `^(p*)`, и они исполняются; CLI тогда опять считает
  fixed-target column и выдаёт 1. Вложенное `(p|^q)*` было явно отклонено обоими
  evaluators. Нельзя обозначать всю поддержку inverse одним «да» или «нет».
- **Одна и та же переменная:** `?x p ?x` в SPARQL означает диагональ, здесь
  ответ пуст. Оба Pathrex CLI выдали 4: имена variables не используются для
  ограничения равенства endpoints. Это отдельное несоответствие SPARQL,
  в отличие от intentionally target-only count. Пока workload должен иметь
  разные endpoint variables. LARPQ вообще не читает имена variables: такое
  равенство нужно реализовать адаптером.
- **Отсутствующая метка:** `E missing* ?t` в Pathrex завершился LabelNotFound,
  а Jena вернула E. Для согласованного RPQ алгоритма missing label — пустая
  adjacency matrix, и ε сохраняется. Upstream `sparql-to-fa` такие запросы
  пропускает, поэтому этот случай надо учитывать в генерации workload.
- **Вершина вне V:** `Outside p* ?t` в Pathrex — VertexNotFound; Jena возвращает
  Outside по SPARQL zero-length semantics. Graph-relative RPQ relation имеет
  domain `V×V`; выбираем constants из V либо явно тестируем отдельный SPARQL
  контракт. Не смешивать эти два универсума.

Нативный ε-free LARPQ алгоритм не выполняет ε-переходы: их надо удалить при
подготовке автомата. Нулевой путь при этом сохраняется в accepting start state.

## Как относительно них работают остальные кандидаты

В таблице «сравнимо» относится к семантике endpoints после адаптации. Новый
семивершинный runtime test выполнен только для явно названных систем;
для остальных основание — [250k проверки](smoke-results.md), код и источники.

| Система | Относительно Pathrex/LARPQ | Что требуется для сравнения |
| --- | --- | --- |
| rpqmatrix / rpqmatrixGB | Boolean relation, WALK; CLI cardinality пар | В con-any/any-con это cardinality endpoint set, в any-any — pairs; сравнивать с `nnz`, а не Pathrex target count. Семивершинный тест отдельно не выполнялся |
| Ring-RPQ | RPQ relation / endpoint pairs, WALK | Нормализовать режим привязки и убрать/контролировать CLI result bound 1M; не сравнивать пары с union targets |
| Jena | SPARQL endpoint relation; новый fixture подтвердил WALK, dedup, any-con, pairs и equality | `SELECT DISTINCT ?t`, `?s` или `?s ?t` по binding mode; учесть absent-label/Outside zero-length отличие от Pathrex |
| Blazegraph / Virtuoso | SPARQL endpoints; 20/20 подготовленных запросов | DISTINCT, одинаковый RDF graph, inference off. Новый fixture для этих двух не запускался; SPARQL corner cases не объявляются проверенными |
| MillenniumDB | RDF endpoint evaluator; 20/20 | DISTINCT; отдельно проверить zero-length any-any по известному отклонению upstream и остальные corner cases |
| PostgreSQL / DuckDB | Наш обход `(vertex,state)` до fixpoint воспроизводит vector RPQ | UNION по product states; для pairs сохранять source dimension; any-con — reversed graph/automaton либо полное отношение. Новый fixture не запускался |
| Kuzu | Новый fixture допускает повторение ребра, сохраняет source/pairs, проверяет equality | Default depth 30 неполон: цепочка 31 hops теряет последний target. После `CALL var_length_extend_max_depth=31` ответ полный для этой цепочки; compound regex ещё не переведён |
| FalkorDB | Новый fixture допускает повторение ребра в фиксированном p/q/p; any-con/pairs/equality/zero-length совпали | Не приравнивать к Neo4j TRAIL автоматически. Всё ещё нужен проверенный перевод compound closures; fixture не доказывает полный язык WALK RPQ |
| Neo4j 5.26 / Memgraph 3.13.2 | Один MATCH p/q/p исключил повторное ребро и дал пусто, тогда как WALK ответ — G | Несколько отдельных MATCH вернули G для фиксированной последовательности. Это рабочая адаптация этого случая, не общий regex evaluator; plain label-star может быть сравним по endpoints даже при TRAIL |

Конечный depth bound сам по себе не запрещает корректное сравнение: bound
должен быть доказан достаточным для данного выражения и графа. В общем RPQ
достаточность связывается с размером произведения графа и автомата, а не с
числом вершин графа без учёта automaton states. Default 30 такой гарантии не даёт.
Снятие bound не превращает перечислитель WALK paths в terminating reachability.

Источники: [W3C SPARQL paths](https://www.w3.org/TR/sparql11-query/#propertypaths),
[Neo4j 5 variable-length paths](https://neo4j.com/docs/cypher-manual/5/patterns/variable-length-paths/),
[Memgraph traversal](https://memgraph.com/docs/advanced-algorithms/deep-path-traversal),
[FalkorDB MATCH](https://docs.falkordb.com/cypher/match),
[Kuzu WALK](https://kuzudb.github.io/docs/cypher/query-clauses/match/),
[Ring paper](https://www.aidanhogan.com/docs/ring-graph-rpq.pdf).
Другие первичные источники и отклонения — в [reachability.md](../reachability.md).

## Конвертеры автора и проверка прежнего преобразования

В этом checkout репозиторий `la-rpq` называется **`vendor/larpq`**.
[Scripts/README](../../vendor/larpq/Scripts/README.md) описывает `truncate`,
`deprefix-nt`, `remove-dups`, `nt-to-mm`, `nt-to-csv`, `sparql-to-fa`.
Использован авторский `nt-to-mm` для нового fixture с **полными IRI**, без
`deprefix-nt`. Pathrex CLI при этом запускается без `--base-iri`: его MM loader
добавляет base ко всем dictionary keys, даже уже полным IRI.

Отдельно повторён авторский RPQBench pipeline на исходном 250k с flags из
[RPQBench/truncate](../../vendor/larpq/Datasets/RPQBench/truncate):
truncate → deprefix-nt → remove-dups → nt-to-mm.
[Аудит](conversion-audit.json) подтвердил 63 052 строки, 61 017 уникальных рёбер,
равенство всего edge set и **точное совпадение vertex IDs** с прежними матрицами.
Собственная подготовка ранее сохраняла эту существующую проекцию; сокращение
IRI не было новой операцией. Семантические коллизии исходных IRI всё равно есть.

Авторский `sparql-to-fa` также реально запущен на шести fixture queries;
его automata переданы в LARPQ, 6/6 cardinalities совпали, включая optional
и zero-length. Этот probe входит в `check_contract.py`.

Нюансы upstream scripts: общий truncate по умолчанию отбрасывает blank nodes,
но RPQBench wrapper сохраняет `_:`; nt-to-mm не схлопывает duplicates сам;
deprefix меняет identity; nt-to-csv имеет свой schema и назначает IDs заново;
sparql-to-fa — текстовый переводчик под ожидаемый формат, не полноценный SPARQL
parser, с ограниченной поддержкой inverse и пропуском missing vertices/labels.
Их нельзя применять к любому N3 без проверки входного синтаксиса и словарей.

## Повторение проверки

После [общей подготовки](README.md#подготовка-окружения-и-запуск) и native builds:

```bash
Results/competitors_250k/venv/bin/python Scripts/competitors/check_contract.py --jena
Results/competitors_250k/venv/bin/python Scripts/competitors/check_cypher_contract.py neo4j
Results/competitors_250k/venv/bin/python Scripts/competitors/check_cypher_contract.py memgraph
Results/competitors_250k/venv/bin/python Scripts/competitors/check_cypher_contract.py falkordb
Results/competitors_250k/venv/bin/python Scripts/competitors/audit_upstream_conversion.py
```

Fixtures, full native outputs и логи находятся в `Results/contract/`; исходные
датасеты/checkout не изменяются. Новые Docker containers имеют имена
`rpq-contract-*`, localhost ports 18687/18688/17389 и после проверки остановлены.
Скрипты фиксируют наблюдаемый контракт, включая расхождения, а не исправляют
evaluator или автоматически объявляют все query counts корректными.
