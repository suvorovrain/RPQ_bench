#!/usr/bin/env python3
"""Convert resource edges from N3/NT/Turtle into all competitor graph layouts.

Full RDF term identities are mapped to safe vN/relN names without local-name
collisions. Does not overwrite an output directory. Uses the author's nt-to-mm.
This is an in-memory converter for graphs that fit in RAM, not an RDF store.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
BASE = "http://rpqbench.local/"


def write_csv(path, header, rows):
    with path.open("w",newline="") as stream:
        writer=csv.writer(stream);writer.writerow(header);writer.writerows(rows)


def main():
    from rdflib import Graph, URIRef, BNode
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path)
    parser.add_argument("output",type=Path)
    parser.add_argument("--format",choices=["n3","nt","turtle"],required=True)
    args=parser.parse_args()
    if args.output.exists(): parser.error("Output directory already exists; choose a new directory")
    graph=Graph().parse(args.source,format=args.format)
    triples=[(s,p,t) for s,p,t in graph if isinstance(s,(URIRef,BNode)) and isinstance(t,(URIRef,BNode))]
    if not triples: parser.error("No resource-to-resource edges in input")
    nodes=sorted({x for s,p,t in triples for x in (s,t)},key=lambda x:x.n3())
    predicates=sorted({p for s,p,t in triples},key=str)
    names={node:f"v{i}" for i,node in enumerate(nodes,1)}
    labels={p:f"rel{i}" for i,p in enumerate(predicates,1)}
    out=args.output.resolve();out.mkdir(parents=True)
    for directory in ["rdf","csv","matrix"]:(out/directory).mkdir()
    canonical=out/"rdf/graph.nt"
    canonical.write_text("".join(f"<{BASE}{names[s]}> <{BASE}{labels[p]}> <{BASE}{names[t]}> .\n"
                                  for s,p,t in sorted(triples,key=lambda row:tuple(x.n3() for x in row))))
    mm=out/"pathrex"
    subprocess.run([sys.executable,str(ROOT/"vendor/larpq/Scripts/nt-to-mm"),str(canonical),str(mm)],check=True)
    # One shared numbering from the author's converter; safely shorten only our
    # own collision-free normalized base, never original RDF local names.
    def shorten(path):
        rows=[]
        for line in path.read_text().splitlines():
            iri,number=line.rsplit(maxsplit=1)
            rows.append((int(number),iri.strip("<>").removeprefix(BASE)))
        path.write_text("".join(f"<{name}> {number}\n" for number,name in rows))
        return dict(rows)
    vertices=shorten(mm/"vertices.txt");preds=shorten(mm/"edges.txt")
    vertex_ids={name:i for i,name in vertices.items()};predicate_ids={name:i for i,name in preds.items()}
    edges=sorted((vertex_ids[names[s]],predicate_ids[labels[p]],vertex_ids[names[t]]) for s,p,t in triples)
    write_csv(out/"csv/nodes.csv",["id","name","iri"],((i,n,BASE+n) for i,n in vertices.items()))
    write_csv(out/"csv/vertices.csv",["id"],((i,) for i in vertices))
    write_csv(out/"csv/edges.csv",["src","pid","dst"],edges)
    for pid,name in preds.items():
        write_csv(out/f"csv/edges_{name}.csv",["src","dst"],((s,t) for s,p,t in edges if p==pid))
    dat=out/"matrix/graph.dat"
    dat.write_text("".join(f"{s} {p} {t}\n" for s,p,t in edges))
    Path(str(dat)+".SO").write_text("".join(f"{i} <{name}>\n" for i,name in vertices.items()))
    Path(str(dat)+".P").write_text("".join(f"{i} <{name}>\n" for i,name in preds.items()))
    subprocess.run([sys.executable,str(ROOT/"Scripts/converters/rpqmatrixGB/matrix_market.py"),str(mm),
                    "--output-base",str(out/"matrix-gb/graph.dat"),"--copy"],check=True)
    manifest={"source":str(args.source.resolve()),"source_sha256":hashlib.sha256(args.source.read_bytes()).hexdigest(),
              "format":args.format,"source_rdf_triples":len(graph),"edges":len(edges),"vertices":len(vertices),
              "base_iri":BASE,"labels":preds,"projection":"resource endpoints only; RDF set semantics; collision-free names",
              "dropped_literal_triples":len(graph)-len(triples),
              "node_mapping":[{"rdf_term":node.n3(),"name":names[node],"id":vertex_ids[names[node]]} for node in nodes],
              "predicate_mapping":[{"iri":str(p),"name":labels[p],"id":predicate_ids[labels[p]]} for p in predicates]}
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print(f"Prepared {len(vertices)} vertices, {len(preds)} labels, {len(edges)} resource edges in {out}")


if __name__=="__main__":main()
