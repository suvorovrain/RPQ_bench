# Optimizer query suite: review draft

This draft proposes additional RPQBench queries for reviewing the Pathrex
optimizer. The generator-ready source is
`optimizer_query_templates.review.txt`. It is intentionally not wired into
`benchmark_config.json` yet.

## What the existing experiments show

The new suite should distinguish four effects that the current 20 queries mix
together:

1. **Bound propagation through alternatives.** In the full server graph,
   `con-any/17` takes about 127 ms in Pathrex. The manual benchmark measured
   66.9 ms for `(D x (E|C)) x (P|Co)`, but only 0.36 ms after distributing the
   bound as `(D x E)|(D x C)`. Fully distributed matrix and vector plans were
   effectively tied at 0.42 ms. This is a plan-selection problem, not a reason
   to replace bound matrices with vectors.
2. **Recursive plan selection.** In the 250k `la-n-egg-rpq` results, all three
   tested cost functions choose an RStar plan for unbound query 10 and execute
   it in about 4.8-5.0 ms, while the sampled ideal is the ordinary
   `A/B*` plan at about 0.94 ms. The current cost function uses the same
   Seq-like estimate for LStar and RStar, a fixed multiplier of 5, and no
   estimate of frontier growth or closure iterations.
3. **Distribution is useful but not free.** For bound query 17 in the same
   results, cardinality takes 0.27-0.32 ms because it does not distribute the
   seed; MNC and hybrid select a distributed seed and take 0.05-0.06 ms.
   Conversely, MNC sometimes fully expands alternatives into more operations
   and loses to a partially factored plan.
4. **Planning and execution must be reported separately.** On short bound
   queries, execution is often tens of microseconds while planning is
   0.5-3 ms. A more detailed estimate can improve the selected plan and still
   lose end to end. Optimizing each query independently remains the fair
   default; no cross-query template cache should be used in the main result.

The current in-tree Pathrex cost function still has no explicit operation-count
or materialization penalty. `Star` is estimated as `n^2`, and LStar/RStar do
not model the closure operand. The candidates below are designed to expose
those omissions rather than merely add longer strings.

## Proposed families

Every core family has an `any-any`, `con-any`, and `any-con` form. This lets us
tell a generally good rewrite from one that only works after a singleton
diagonal has entered the plan.

| IDs | Family | Main decision under test | Nonzero strategy |
| --- | --- | --- | --- |
| 21-23 | Long path plus sparse closure | Association and whether the final star should become LStar/RStar | Select a witnessed `references/cite/creator` endpoint; the star then preserves it |
| 24-26 | Three valid paths followed by closure | Bound distribution into paths of unequal length, factoring, and recursive specialization | The `journal/editor` or `references/cite/creator` branch supplies a seed; the star preserves it |
| 27-29 | Product of three alternatives | Exponential distribution, type-disjoint products, and plan-size penalty | Requires a witnessed constant; this is a stress family |
| 30-32 | Two adjacent closures | Association between closures and choosing zero, one, or two specialized stars | `editor` supplies a seed for a journal; both stars preserve it |
| 33-35 | Starred label on the left and closure on the right | LStar and RStar in the same expression | Require a witnessed `references/cite/creator` path |
| 36-38 | Composite closure on the left and closure on the right | Recursive cardinality for a multi-operation step | `creator` after the zero closure iteration gives a seed |
| 39-41 | Three paths without recursion | Pure distribution/factoring control | `journal/editor` or `references/cite/creator` is sufficient |
| 42-44 | Closure over an alternative of paths | Recursive estimate for an expensive composite step | Star identity makes it nonzero, but constants should also have a nontrivial witness |

IDs 27-29 and 42-44 should be opt-in stress queries. Full distribution of
27-29 creates eight typed branches, most of which are structurally impossible
on RPQBench. This is deliberate: label totals alone cannot see that, while
row/column support statistics can. The outer star in 42-43 can also create a
large identity relation if the optimizer fails to specialize it.

The existing queries 17-20 should stay in every optimizer run as baseline
controls. They isolate the exact expression used by
`manual_bound_plan_bench.c`; the proposed families add complexity around that
known failure instead of replacing it.

## Local screening

The 24 templates were parsed and executed with the release build of
`la-n-egg-rpq` on `rpqbench_250k`, using `<Article1>`, `<1944>`, and
`<Paul_Erdoes>` as screening witnesses. Every result count was greater than
zero. The same instantiated file was also accepted by the current release
Pathrex; `nfarpq` and optimized `rpqmatrix` returned identical nonzero counts
for the original 23-query draft. The added any-any composite-star counterpart
was then validated together with the generated suite. These are single-run
smoke measurements, not benchmark
numbers.

| IDs | Cardinality execution, ms (AA/CA/AC) | Initial-plan execution, ms (AA/CA/AC) | Notable result |
| --- | --- | --- | --- |
| 21-23 | 7.87 / 0.18 / 1.70 | 6.07 / 3.79 / 6.25 | Bound plans improve; unbound does not |
| 24-26 | 31.89 / 1.04 / 3.52 | 28.21 / 27.37 / 30.26 | Strong bound-distribution signal |
| 27-29 | 25.21 / 1.70 / 2.98 | 14.13 / 10.49 / 12.58 | Cardinality planning was 76/228/98 ms; MNC planning was 4.2/6.2/3.8 s |
| 30-32 | 19.81 / 0.29 / 0.87 | 8.92 / 7.24 / 9.73 | Specialization helps bound forms and hurts AA |
| 33-35 | 33.59 / 0.19 / 1.13 | 8.03 / 8.16 / 7.89 | Another clear unbound-star counterexample |
| 36-38 | 130.46 / 1.13 / 119.94 | 18.24 / 16.25 / 19.20 | Cardinality badly misses AA and AC; MNC reduced AC to 3.98 ms |
| 39-41 | 16.75 / 0.53 / 4.45 | 18.88 / 14.72 / 23.95 | Pure nonrecursive optimization control |
| 42-44 | not screened as a triplet | not screened as a triplet | Stress test for a composite star; use time and memory guards |

## Generation requirements

The current `vendor/larpq/Datasets/RPQBench/gen-queries` cannot guarantee
nonzero queries. It samples constants by lexical category and never checks the
regular path. It also has a concrete bug: `add_node(s)` reads the outer `sub`
variable instead of `s`, so objects are not added to the entity pools. This
particularly biases `{person}` away from creator/editor targets.

Before generating the final suite:

1. Fix `add_node` and add a deterministic `--seed` option.
2. Generate a larger candidate pool for each bound template.
3. Execute candidates in one loaded-graph batch and retain only nonzero
   results. For starred expressions, prefer a nontrivial witness rather than a
   result caused solely by the identity path.
4. Keep the same accepted constants for all competitors and save them as the
   generated query artifact. Do not resample separately per engine.
5. Record result count, selected plan, plan operation count, e-graph
   iterations/nodes/classes, planning time, execution-only time, and total
   time. Put time and memory guards on the stress tier.
6. Use several distinct witnessed constants per bound family. A single lucky
   vertex can hide skew just as easily as random zero-result queries can hide
   optimizer mistakes.

For the paper-facing comparison, report execution-only and end-to-end results
side by side. The former evaluates plan quality and the latter evaluates the
optimizer as a usable system.
