from ..cypher import run_bolt


def measure(s, session, q, query):
    first = []
    last = []
    for iteration in range(-s.args.warmups, s.args.runs):
        result = session.run(query)
        s.check(q, [record["id"] for record in result])
        summary = result.consume()
        if iteration >= 0:
            first.append(summary.result_available_after)
            last.append(summary.result_consumed_after)
    s.add(q, [a + b for a, b in zip(first, last)], "neo4j_bolt_run_and_stream",
          "endpoint_set_every_run", extra={"resolution_ms": 1},
          phases={"t_first": first, "t_last": last})


def run(s):
    run_bolt(s, measure)


if __name__ == "__main__":
    from ..workflow import main

    main(default_engine='neo4j')
