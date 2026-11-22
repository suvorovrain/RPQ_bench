#!/usr/bin/env python3
"""Make reproducible bar charts, sample distributions and colored tables.

Green/red means lower/higher mean time than Pathrex for that query.
Native, embedded, JVM and network boundaries remain visible in every report.
"""
import argparse
import base64
import csv
import html
import json
import math
import os
from pathlib import Path
import statistics

os.environ.setdefault("MPLCONFIGDIR","/tmp/rpq-matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import xlsxwriter

LABELS={"larpq":"LA-RPQ","rpqmatrix":"rpq-matrix","rpqmatrixGB":"rpq-matrix_gb",
        "pathrex":"Pathrex","ring":"Ring-RPQ","duckdb":"DuckDB","kuzu":"Kuzu",
        "jena":"Jena TDB2","postgres":"PostgreSQL","millenniumdb":"MillenniumDB",
        "blazegraph":"Blazegraph","virtuoso":"Virtuoso","neo4j":"Neo4j",
        "memgraph":"Memgraph","falkordb":"FalkorDB"}
GREEN="#d9efdb";RED="#f6d7d9";BLUE="#dce8fa"
NOTE="Green = faster than Pathrex, red = slower. Native / embedded / JVM / network timing scopes differ."


def write_csv(path,rows):
    with path.open("w",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def scope_name(scope):
    if scope.startswith("native"):return "native"
    if scope.startswith("client"):return "network"
    if scope.startswith("in_jvm"):return "JVM"
    return "embedded"


def load(folder):
    metadata=json.loads((folder/"metadata.json").read_text());rows=[];raw=[];samples={}
    for engine in metadata["engines"]:
        report=json.loads((folder/f"{engine}.json").read_text())
        if report["status"]!="completed":raise ValueError(f"Incomplete engine: {engine}")
        for q in metadata["queries"]:
            record=report["measurements"][q["id"]];values=record["samples_ms"]
            if record["status"]!="pass" or len(values)!=metadata["runs"]:raise ValueError(f"Bad samples: {engine}/{q['id']}")
            if any(not math.isfinite(x) or x<=0 for x in values):raise ValueError("Invalid duration")
            samples[engine,q["id"]]=values
            mean=statistics.mean(values);sd=statistics.stdev(values) if len(values)>1 else 0
            rows.append({"engine":engine,"query_id":q["id"],"pattern":q["pattern"],
                "scope":record["scope"],"verification":record["verification"],"runs":len(values),
                "mean_ms":mean,"stddev_ms":sd,"median_ms":statistics.median(values),
                "p95_ms":float(np.percentile(values,95)),"min_ms":min(values),"max_ms":max(values),
                "cv_percent":sd/mean*100})
            raw.extend({"engine":engine,"query_id":q["id"],"run":i,"time_ms":x} for i,x in enumerate(values))
    lookup={(r["engine"],r["query_id"]):r for r in rows}
    for row in rows:
        base=lookup["pathrex",row["query_id"]]["mean_ms"]
        row["ratio_to_pathrex"]=row["mean_ms"]/base
        row["speedup_vs_pathrex"]=base/row["mean_ms"]
    return metadata,rows,raw,lookup,samples


def cell_color(engine,ratio):return BLUE if engine=="pathrex" else GREEN if ratio<1 else RED


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input",type=Path);parser.add_argument("--output",type=Path)
    args=parser.parse_args();output=args.output or args.input/"report";output.mkdir(parents=True,exist_ok=True)
    meta,rows,raw,lookup,samples=load(args.input)
    engines=meta["engines"];queries=meta["queries"]
    write_csv(output/"summary.csv",rows);write_csv(output/"samples.csv",raw)
    gm={engine:math.exp(statistics.mean(math.log(lookup[engine,q["id"]]["ratio_to_pathrex"]) for q in queries)) for engine in engines}
    titles={q["id"]:f"Q{q['id']}: {q['pattern']}" for q in queries}
    fig,axes=plt.subplots(2,2,figsize=(18,14),layout="constrained")
    for ax,q in zip(axes.flat,queries):
        data=[lookup[e,q["id"]] for e in engines];means=[r["mean_ms"] for r in data]
        colors=[cell_color(e,r["ratio_to_pathrex"]) for e,r in zip(engines,data)]
        y=np.arange(len(engines));ax.barh(y,means,color=colors,edgecolor="#666",linewidth=.5)
        ax.set_yticks(y,[LABELS[e]+" ["+scope_name(r["scope"])+"]" for e,r in zip(engines,data)],fontsize=9)
        ax.invert_yaxis();ax.set_xscale("log");ax.set_xlabel("Mean query time, ms (log scale)")
        ax.set_title(titles[q["id"]],fontsize=11);ax.grid(axis="x",alpha=.2)
        ax.axvline(lookup["pathrex",q["id"]]["mean_ms"],color="#315d9b",linestyle="--",alpha=.7)
        ax.set_xlim(min(means)*.65,max(means)*4)
        for yy,r in zip(y,data):ax.text(r["mean_ms"]*1.05,yy,f"{r['mean_ms']:.4g}",va="center",fontsize=8)
    fig.suptitle(f"RPQBench 250k · {meta['runs']} measured runs · Pathrex\n"+NOTE,fontsize=12)
    for extension in ["png","svg"]:fig.savefig(output/f"histogram.{extension}",dpi=180)
    plt.close(fig)
    # Real sample distributions in log space, one panel per competitor.
    fig,axes=plt.subplots(5,3,figsize=(18,17),layout="constrained")
    for ax,engine in zip(axes.flat,engines):
        for q in queries:
            values=np.log10(samples[engine,q["id"]]);low,high=min(values),max(values)
            if high==low:low-=.001;high+=.001
            ax.hist(values,bins=np.linspace(low,high,18),alpha=.4,label=f"Q{q['id']}")
        ax.set_title(LABELS[engine]);ax.set_xlabel("log10(time in ms)");ax.set_ylabel("Executions");ax.legend(fontsize=7)
    fig.suptitle(f"Per-query distributions of all {meta['runs']} measured executions",fontsize=14)
    fig.savefig(output/"distributions.png",dpi=150);plt.close(fig)
    headers=["Competitor","Scope"]+[f"Q{q['id']} mean ± SD, ms" for q in queries]+["GM time / Pathrex"]
    table_rows=[];colors=[]
    for engine in engines:
        records=[lookup[engine,q["id"]] for q in queries]
        table_rows.append([LABELS[engine],scope_name(records[0]["scope"])]+[
            f"{r['mean_ms']:.5f} ± {r['stddev_ms']:.5f}" for r in records]+[f"{gm[engine]:.3f}×"])
        colors.append([BLUE if engine=="pathrex" else "white","white"]+[
            cell_color(engine,r["ratio_to_pathrex"]) for r in records]+[cell_color(engine,gm[engine])])
    fig,ax=plt.subplots(figsize=(20,9));ax.axis("off")
    table=ax.table(cellText=table_rows,colLabels=headers,cellColours=colors,loc="center",cellLoc="center",
                   colWidths=[.13,.075,.17,.17,.17,.17,.115])
    table.auto_set_font_size(False);table.set_fontsize(9);table.scale(1,2)
    for column in range(len(headers)):table[0,column].set_facecolor("#24364b");table[0,column].set_text_props(color="white",weight="bold")
    ax.set_title(f"RPQBench 250k · {meta['runs']} runs + {meta['warmups']} warmups per query\n"+NOTE,pad=20)
    fig.savefig(output/"table.png",dpi=180,bbox_inches="tight");plt.close(fig)
    workbook=xlsxwriter.Workbook(output/"table.xlsx")
    sheet=workbook.add_worksheet("Comparison");sheet.freeze_panes(1,2)
    head=workbook.add_format({"bold":True,"bg_color":"#24364b","font_color":"white"})
    formats={c:workbook.add_format({"bg_color":c}) for c in [GREEN,RED,BLUE,"white"]}
    sheet.write_row(0,0,headers,head)
    for i,(values,row_colors) in enumerate(zip(table_rows,colors),1):
        for j,(value,color) in enumerate(zip(values,row_colors)):sheet.write(i,j,value,formats[color])
    sheet.set_column(0,0,22);sheet.set_column(1,1,12);sheet.set_column(2,len(headers)-1,29)
    sheet.write(len(engines)+2,0,NOTE)
    summary=workbook.add_worksheet("Statistics");summary.write_row(0,0,list(rows[0]),head)
    for i,row in enumerate(rows,1):summary.write_row(i,0,list(row.values()))
    summary.freeze_panes(1,2);summary.autofilter(0,0,len(rows),len(rows[0])-1);summary.set_column(0,len(rows[0])-1,19)
    rawsheet=workbook.add_worksheet("Raw samples");rawsheet.write_row(0,0,list(raw[0]),head)
    for i,row in enumerate(raw,1):rawsheet.write_row(i,0,list(row.values()))
    rawsheet.freeze_panes(1,2);rawsheet.set_column(0,3,20);workbook.close()
    # Self-contained HTML includes its overview chart, colored table and methodology.
    parts=['<!doctype html><meta charset="utf-8"><title>RPQ competitor benchmark</title>',
           '<style>body{font:15px system-ui;margin:24px;color:#24364b}table{border-collapse:collapse;width:100%}td,th{padding:10px;border:1px solid #ddd}th{background:#24364b;color:white}img{max-width:100%}code{background:#eee}</style>',
           f'<h1>{len(engines)} competitors · {meta["runs"]} executions per query</h1>',
           '<p>Graph: 24,225 vertices / 61,017 unique edges. Pathrex: RPQMatrix. Values: mean ± sample standard deviation, milliseconds.</p>',
           '<p>Green: lower mean time than Pathrex; red: higher; blue: Pathrex baseline. Colors describe measured means, not statistical significance. GM is the geometric mean of per-query time ratios; lower is faster.</p>',
           '<p><b>Timing boundaries differ:</b> native executors, embedded Python API, an in-JVM TDB2 query and network client roundtrips are recorded separately. Import, startup, index building and correctness verification are excluded. Native parsers/planners and result extraction differ: see summary.csv and README.md. These are observed interface timings, not an isolated algorithm ranking.</p>',
           '<table><tr>'+''.join('<th>'+html.escape(h)+'</th>' for h in headers)+'</tr>']
    for values,row_colors in zip(table_rows,colors):
        parts.append('<tr>'+''.join(f'<td style="background:{c}">{html.escape(str(v))}</td>' for v,c in zip(values,row_colors))+'</tr>')
    parts.append('</table><h2>Mean query times</h2>')
    encoded=base64.b64encode((output/"histogram.png").read_bytes()).decode()
    parts.append(f'<img alt="Query-time bar charts" src="data:image/png;base64,{encoded}">')
    parts.append('<p>Queries:</p><ul>'+''.join('<li>'+html.escape(titles[q['id']])+'</li>' for q in queries)+'</ul>')
    (output/"report.html").write_text("\n".join(parts))
    (output/"summary.json").write_text(json.dumps({"metadata":meta,"statistics":rows,"geomean_time_ratio":gm},indent=2)+"\n")
    print("Report written:",output)


if __name__=="__main__":main()
