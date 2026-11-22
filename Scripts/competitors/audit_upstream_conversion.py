#!/usr/bin/env python3
"""Repeat the author's RPQBench conversion and compare with existing matrices."""
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]


def readmap(path):
    return {int(line.rsplit(maxsplit=1)[1]):line.rsplit(maxsplit=1)[0].strip("<>")
            for line in path.read_text().splitlines()}


def edges(path):
    vertices=readmap(path/"vertices.txt")
    result=set()
    for label_id,name in readmap(path/"edges.txt").items():
        lines=[line for line in (path/f"{label_id}.txt").read_text().splitlines()
               if line and not line.startswith("%")]
        for line in lines[1:]:
            source,target,*_=line.split()
            result.add((vertices[int(source)],name,vertices[int(target)]))
    return result


def main():
    out=ROOT/"Results/contract/upstream-rpq250k"
    out.mkdir(parents=True,exist_ok=True)
    scripts=ROOT/"vendor/larpq/Scripts"
    def capture(args,path):
        with path.open("w") as dst:
            subprocess.run(list(map(str,args)),stdout=dst,check=True)
    capture([sys.executable,scripts/"truncate",ROOT/"Datasets/rpqbench_250k/rpqbench_250k.n3",
             "--s=^(<http://localhost|_)","--p=.*","--o=^(<http://localhost|_)"],out/"truncated.nt")
    capture([sys.executable,scripts/"deprefix-nt",out/"truncated.nt"],out/"short.nt")
    capture([sys.executable,scripts/"remove-dups",out/"short.nt"],out/"unique.nt")
    if not (out/"mm").exists():
        subprocess.run([sys.executable,str(scripts/"nt-to-mm"),str(out/"unique.nt"),str(out/"mm")],check=True)
    actual=edges(out/"mm")
    original=ROOT/"Datasets/rpqbench_250k/pathrex"
    assert actual==edges(original),"Upstream pipeline differs from existing matrix edge set"
    record={"pipeline":"RPQBench truncate flags -> deprefix-nt -> remove-dups -> nt-to-mm",
            "source_rows":len((out/"short.nt").read_text().splitlines()),"unique_edges":len(actual),
            "existing_matrix_edge_set_equal":True,
            "vertex_id_maps_equal":readmap(out/"mm/vertices.txt")==readmap(original/"vertices.txt")}
    (ROOT/"Databases/guides/conversion-audit.json").write_text(json.dumps(record,indent=2)+"\n")
    print(record)


if __name__=="__main__": main()
