from ..cypher import run_bolt


def measure(s, session, q, query):
    phases = {"parsing_time": [], "planning_time": [], "plan_execution_time": []}
    for iteration in range(-s.args.warmups, s.args.runs):
        result = session.run(query)
        s.check(q, [record["id"] for record in result])
        result.consume()
        # The pinned Neo4j driver retains Memgraph's additional Bolt summary fields here.
        metadata = result._metadata
        if iteration >= 0:
            for field, samples in phases.items():
                samples.append(float(metadata[field]) * 1000)
    s.add(q, phases.pop("plan_execution_time"), "memgraph_plan_execution", "endpoint_set_every_run",
          phases=phases)


def run(s):
    run_bolt(s, measure)


if __name__ == "__main__":
    from ..workflow import main

    main(default_engine='memgraph')
