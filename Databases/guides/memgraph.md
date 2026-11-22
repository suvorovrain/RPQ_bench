# Memgraph

Дата проверки: 2026-10-11. Команды — из корня RPQ_bench. Перед запуском выполнить
[общую подготовку](README.md#подготовка-окружения-и-запуск) (окружение/данные).
Фактическая версия и результат находятся в [отчёте](smoke-results.md);
Docker digest / JAR checksum / source SHA — в [runtime-lock.json](runtime-lock.json).

## Поставка и запуск

Официальный memgraph/memgraph image, фактическая версия 3.13.2, digest закреплён.
Bolt protocol, Python Neo4j driver. Runner использует localhost:17688,
создаёт Node.id index, nodes и relationships через parameterized UNWIND batches.

```bash
Results/competitors_250k/venv/bin/python Scripts/competitors/smoke_250k.py memgraph
```

## Данные / import alternatives

Подготовленные nodes.csv и per-label edges CSV пригодны для LOAD CSV, если
файлы видны контейнеру и allow-load-csv включён. Реально проверенный import в
нашем runner — UNWIND по Bolt, поэтому не требуется mgconsole или внешний CSV
HTTP server. Полный RDF не загружается напрямую: применяется общая N3→graph→CSV
проекция с теми же vertex IDs и relationship labels.

## Запросы и поправка для star

Query format — Cypher; Python `driver.session().run(query)` возвращает endpoint
ID rows. Файлы queries/qN.memgraph.cypher записываются после smoke.

Для обычного label-star BFS экономичнее полного перечисления paths, но на
проверенной версии `*BFS 0..` не вернул источник по нулевому пути. Наш правильный
перевод для coauthor* явно добавляет zero-length ответ:

```cypher
MATCH (s:Node {id:103})-[:coauthor*BFS]->(t:Node)
RETURN DISTINCT t.id AS id
UNION
MATCH (s:Node {id:103}) RETURN s.id AS id
```

ID 103 соответствует Tashiya_Marrable в нашем manifest; для других графов брать
ID из их словаря, не переносить это число. После
поправки совпали sets q1/q2/q3/q5/q6; q4 не имеет проверенного прямого перевода.
BFS на graph vertices с arbitrary path-dependent filter не заменяет посещение
`(vertex, automaton_state)` и не доказывает general RPQ support.

Для большого workload учитывать HOPS LIMIT, query memory и timeouts; обрезанный
обход не считать правильным полным ответом. WSP/ASP/KSP — другие задачи,
не нужны для endpoint RPQ. Import/driver round trip отдельно от server execution.

Источники: [traversal algorithms](https://memgraph.com/docs/advanced-algorithms/deep-path-traversal),
[LOAD CSV](https://memgraph.com/docs/querying/clauses/load-csv).

[Все гайды](README.md) · [Семантика RPQ](../reachability.md).

[Проверка контракта](contract.md): один MATCH для `F-p-G-q-F-p-G` дал пустой
ответ из-за повторения ребра; три отдельных MATCH вернули G. Это различие
с WALK Pathrex/LARPQ и рабочий перевод фиксированной последовательности.
