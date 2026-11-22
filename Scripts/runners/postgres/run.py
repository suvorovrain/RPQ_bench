import time
def run(s):
    import psycopg
    image = "postgres:18"
    port = 15542
    extra = ["-p", f"127.0.0.1:{port}:5432"]
    extra += ["-e", "POSTGRES_PASSWORD=rpq-smoke-local", "-e", "POSTGRES_DB=rpq"]
    s.docker(image, extra, ["-c", "shared_preload_libraries=pg_stat_statements",
                            "-c", "pg_stat_statements.track_planning=on"])
    con = None
    for _ in range(50):
        try:
            con = psycopg.connect(host="127.0.0.1", port=port, user="postgres",
                                 password="rpq-smoke-local",
                                 dbname="rpq", connect_timeout=2, autocommit=True,
                                 prepare_threshold=None)
            break
        except Exception:
            time.sleep(1)
    if con is None:
        raise RuntimeError("PostgreSQL wire endpoint did not become ready")
    with con:
        s.result["version"] = con.execute("SELECT version()").fetchone()[0]
        con.execute("CREATE EXTENSION pg_stat_statements")
        con.execute("CREATE TABLE edges(src BIGINT, pid INTEGER, dst BIGINT)")
        # Server-side COPY reads the mounted CSV file.
        con.execute("COPY edges FROM '/input/csv/edges.csv' WITH (FORMAT CSV, HEADER TRUE)")
        con.execute("CREATE INDEX edges_src_pid ON edges(src,pid)")
        con.execute("CREATE INDEX edges_dst_pid ON edges(dst,pid)")
        con.execute("ANALYZE edges")
        if con.execute("SELECT count(*) FROM edges").fetchone()[0] != s.manifest["edges"]:
            raise ValueError("PostgreSQL imported edge count differs from manifest")
        def statement_stats():
            rows = con.execute("""
                SELECT queryid, plans, calls, total_plan_time, total_exec_time
                FROM pg_stat_statements
                WHERE toplevel AND dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
                  AND query NOT LIKE '%FROM pg_stat_statements%'
            """).fetchall()
            return {queryid: (plans, calls, planning, execution)
                    for queryid, plans, calls, planning, execution in rows}

        stats = statement_stats()
        for q in s.queries:
            text = (s.query_dir / f'q{q["id"]}.sql').read_text()
            planning = []
            execution = []
            for iteration in range(-s.args.warmups, s.args.runs):
                s.check(q, [r[0] for r in con.execute(text).fetchall()])
                updated = statement_stats()
                changed = [key for key, values in updated.items()
                           if values[1] != stats.get(key, (0, 0, 0, 0))[1]]
                if len(changed) != 1:
                    raise ValueError(f"Expected one PostgreSQL statement for query {q['id']}, got {changed}")
                key = changed[0]
                plans, calls, plan_ms, exec_ms = [
                    after - before for after, before in zip(updated[key], stats.get(key, (0, 0, 0, 0))
                )]
                if (plans, calls) != (1, 1):
                    raise ValueError(f"Expected one PostgreSQL plan and call, got {plans}/{calls}")
                stats = updated
                if iteration >= 0:
                    planning.append(plan_ms)
                    execution.append(exec_ms)
            s.add(q, execution, "postgres_executor", "endpoint_set_every_run",
                  phases={"planning": planning})


if __name__ == "__main__":
    from ..workflow import main

    main(default_engine='postgres')
