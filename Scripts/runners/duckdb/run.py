import json

def run(s):
    import duckdb
    s.result["version"] = duckdb.__version__
    con = duckdb.connect(str(s.folder / "duckdb.duckdb"))
    con.execute(f"SET threads={s.threads}")
    con.execute(f"CREATE OR REPLACE TABLE edges AS SELECT * FROM read_csv('{s.data}/csv/edges.csv')")
    if con.execute("SELECT count(*) FROM edges").fetchone()[0] != s.manifest["edges"]:
        raise ValueError("DuckDB imported edge count differs from manifest")
    profiles = s.folder / "profiles"
    profiles.mkdir()
    con.execute("SET enable_profiling='json'")
    con.execute("SET profiling_mode='detailed'")
    for q in s.queries:
        text = (s.query_dir / f'q{q["id"]}.sql').read_text()
        latency = []
        phases = {name: [] for name in ("planner", "all_optimizers", "physical_planner")}
        for iteration in range(-s.args.warmups, s.args.runs):
            profile = profiles / f'q{q["id"]}-{iteration}.json'
            con.execute("SET profiling_output=" + "'" + str(profile).replace("'", "''") + "'")
            rows = con.execute(text).fetchall()
            s.check(q, [r[0] for r in rows])
            metrics = json.loads(profile.read_text())
            if metrics["query_name"].strip() != text.strip() or metrics["rows_returned"] != len(rows):
                raise ValueError(f"DuckDB profile does not match query {q['id']}")
            if iteration >= 0:
                latency.append(metrics["latency"] * 1000)
                for name, samples in phases.items():
                    samples.append(metrics[name] * 1000)
        s.add(q, latency, "duckdb_profile_latency", "endpoint_set_every_run", phases=phases)
    con.close()


if __name__ == "__main__":
    from ..workflow import main

    main(default_engine='duckdb')
