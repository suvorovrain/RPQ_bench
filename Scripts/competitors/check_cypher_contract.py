#!/usr/bin/env python3
"""Read Cypher contract differences on the check_contract.py fixture.

Creates only labelled rpq-contract-* containers, stops them after each check.
The commands and replies are separate from the 250k smoke evidence.
"""
import argparse
import json
import subprocess
import time
from check_contract import ROOT, OUT, NAMES, EDGES


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("engine",choices=["neo4j","memgraph","falkordb"])
    engine=parser.parse_args().engine
    OUT.mkdir(parents=True,exist_ok=True)
    lock=json.loads((ROOT/"Databases/guides/runtime-lock.json").read_text())
    name="rpq-contract-"+engine
    port={"neo4j":18687,"memgraph":18688,"falkordb":17389}[engine]
    tag={"neo4j":"neo4j:5.26-community","memgraph":"memgraph/memgraph:latest","falkordb":"falkordb/falkordb:latest"}[engine]
    image=lock["images"][tag]
    existing=subprocess.run(["docker","inspect",name],capture_output=True,text=True)
    if existing.returncode==0:
        state=json.loads(existing.stdout)[0]
        if state["State"]["Running"] or state["Config"].get("Labels",{}).get("rpq-bench.contract")!="true":
            raise RuntimeError("Existing container is running or not owned by this probe")
        subprocess.run(["docker","rm",name],check=True,capture_output=True)
    command=["docker","run","-d","--name",name,"--label","rpq-bench.contract=true","--memory","2g","--cpus","2",
             "-p",f"127.0.0.1:{port}:{6379 if engine=='falkordb' else 7687}"]
    if engine=="neo4j":
        command.extend(["-e","NEO4J_AUTH=none","-e","NEO4J_server_memory_heap_max__size=512m",
                        "-e","NEO4J_server_memory_heap_initial__size=256m","-e","NEO4J_server_memory_pagecache_size=256m"])
    command.append(image)
    subprocess.run(command,check=True,capture_output=True)
    driver=None
    report={"engine":engine,"image":image,"queries":{}}
    try:
        if engine=="falkordb":
            import redis
            driver=redis.Redis(host="127.0.0.1",port=port,socket_timeout=20)
            def query(text):
                result=driver.execute_command("GRAPH.QUERY","contract",text,"--compact")
                if len(result)<3: return []  # CREATE returns statistics only.
                return [[cell[1].decode() if isinstance(cell[1],bytes) else cell[1] for cell in row] for row in result[1]]
            ready=driver.ping
        else:
            from neo4j import GraphDatabase
            driver=GraphDatabase.driver(f"bolt://127.0.0.1:{port}",auth=None,connection_timeout=2)
            def query(text):
                with driver.session() as session: return [list(row.values()) for row in session.run(text)]
            ready=driver.verify_connectivity
        for attempt in range(50):
            try: ready(); break
            except Exception:
                if attempt==49: raise
                time.sleep(1)
        for vertex in NAMES: query(f"CREATE (:Node {{name:'{vertex}'}})")
        for s,p,t in EDGES: query(f"MATCH (s:Node {{name:'{s}'}}),(t:Node {{name:'{t}'}}) CREATE (s)-[:{p}]->(t)")
        queries={
            "repeat_edge":"MATCH (s:Node {name:'F'})-[:p]->()-[:q]->()-[:p]->(t) RETURN DISTINCT t.name",
            "repeat_edge_split_match":"MATCH (s:Node {name:'F'})-[:p]->(u) MATCH (u)-[:q]->(v) MATCH (v)-[:p]->(t) RETURN DISTINCT t.name",
            "diamond":"MATCH (s:Node {name:'A'})-[:p]->()-[:p]->(t) RETURN DISTINCT t.name",
            "any_con":"MATCH (s)-[:p]->(t:Node {name:'D'}) RETURN DISTINCT s.name",
            "any_any":"MATCH (s)-[:p]->(t) RETURN DISTINCT s.name,t.name",
            "same_variable":"MATCH (s)-[:p]->(s) RETURN DISTINCT s.name",
            "zero_length":"MATCH (s:Node {name:'E'})-[:p*0..]->(t) RETURN DISTINCT t.name",
        }
        for key,text in queries.items():
            try: report["queries"][key]={"query":text,"rows":query(text)}
            except Exception as error: report["queries"][key]={"query":text,"error":str(error)}
    finally:
        if driver: driver.close()
        subprocess.run(["docker","stop","-t","5",name],check=True,capture_output=True)
        logs=subprocess.run(["docker","logs",name],capture_output=True,text=True)
        (OUT/f"{engine}-server.log").write_text(logs.stdout+logs.stderr)
    path=ROOT/"Databases/guides"/f"contract-{engine}.json"
    path.write_text(json.dumps(report,indent=2)+"\n")
    print(engine,{key:result.get("rows",result.get("error")) for key,result in report["queries"].items()})


if __name__=="__main__": main()
