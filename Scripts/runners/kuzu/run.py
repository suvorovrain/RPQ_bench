from ..cypher import query_text
def run(s):
    import kuzu
    s.result["version"] = kuzu.__version__
    db = kuzu.Database(str(s.folder / "database"), buffer_pool_size=512*1024**2, max_num_threads=s.threads)
    con = kuzu.Connection(db)
    con.execute("CREATE NODE TABLE Node(id INT64, name STRING, iri STRING, PRIMARY KEY(id))")
    con.execute(f"COPY Node FROM '{s.data}/csv/nodes.csv' (HEADER=true)")
    for label in s.manifest["labels"].values():
        con.execute(f"CREATE REL TABLE {label}(FROM Node TO Node)")
        con.execute(f"COPY {label} FROM '{s.data}/csv/edges_{label}.csv' (HEADER=true)")
    for q in s.queries:
        query = query_text(q)
        if query is None:
            s.skip(q, "Compound closure has no verified direct translation")
            continue
        execution = []
        compilation = []
        for iteration in range(-s.args.warmups, s.args.runs):
            result = con.execute(query)
            try:
                values = []
                while result.has_next():
                    values.append(result.get_next()[0])
                s.check(q, values)
                if iteration >= 0:
                    execution.append(result.get_execution_time())
                    compilation.append(result.get_compiling_time())
            finally:
                result.close()
        s.add(q, execution, "kuzu_execution", "endpoint_set_every_run",
              phases={"compilation": compilation})
    con.close()
    db.close()


if __name__ == "__main__":
    from ..workflow import main

    main(default_engine='kuzu')
