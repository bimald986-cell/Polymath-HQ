#!/usr/bin/env python3
"""Deterministic AstroLab deep-reading QA.

Run this inside a checkout where ../astrolab-v6 is available, or set
ASTROLAB_REPO. It generates synthetic charts/readings with AstroLab itself,
then measures whether materially different charts receive materially
different Life Guidance and Timing text.

No external LLM is required. Astrology is not scientifically established;
this validates internal Jyotish fidelity, evidence linkage, consistency and
personalisation against AstroLab's declared calculation method.
"""
from __future__ import annotations
import argparse, difflib, hashlib, importlib, json, os, re, sys
from itertools import combinations
from pathlib import Path

HERE=Path(__file__).resolve().parent
HQ=HERE.parents[1]
ASTRO=Path(os.getenv("ASTROLAB_REPO", HQ.parent/"astrolab-v6")).resolve()
if not ASTRO.exists():
    raise SystemExit(f"AstroLab checkout not found: {ASTRO}. Set ASTROLAB_REPO.")
sys.path.insert(0,str(ASTRO))

from engine.chart_calc import calculate_chart
from engine.report import build_report

PROFILES=[
("U01",1991,11,15,3,5,"Kathmandu","Nepal"),
("U02",1984,2,29,0,1,"London","United Kingdom"),
("U03",2001,7,4,23,59,"New York","United States"),
("U04",1975,12,21,12,0,"Delhi","India"),
("U05",1998,5,10,6,30,"Tokyo","Japan"),
("U06",1960,1,1,18,45,"Sydney","Australia"),
("U07",2012,9,17,9,15,"Dubai","United Arab Emirates"),
("U08",1989,3,22,14,5,"Toronto","Canada"),
("U09",1995,8,30,4,40,"Singapore","Singapore"),
("U10",1970,6,11,20,20,"Paris","France"),
("U11",2005,10,5,11,55,"Cape Town","South Africa"),
("U12",1952,4,14,2,10,"Buenos Aires","Argentina"),
]
# Expand deterministically without inventing random test data.
for i in range(13,51):
    base=PROFILES[(i-13)%12]
    name=f"U{i:02d}"; y=1948+((i*7)%70); m=((i*5)%12)+1; d=((i*11)%27)+1
    hh=(i*3)%24; mm=(i*13)%60
    PROFILES.append((name,y,m,d,hh,mm,base[6],base[7]))

def norm(s):
    return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9\s]"," ",(s or "").lower())).strip()

def sections(report):
    if isinstance(report,str): return {"report":report}
    out={}
    def walk(v,path=""):
        if isinstance(v,str) and len(v)>120: out[path or "report"]=v
        elif isinstance(v,dict):
            for k,x in v.items(): walk(x,f"{path}.{k}".strip("."))
        elif isinstance(v,list):
            for j,x in enumerate(v): walk(x,f"{path}[{j}]")
    walk(report)
    return out

def signature(chart):
    planets=chart.get("planets",{})
    if isinstance(planets,list):
        p=[(x.get("name"),x.get("sign"),x.get("house")) for x in planets if isinstance(x,dict)]
    else:
        p=sorted((k,(v or {}).get("sign"),(v or {}).get("house")) for k,v in planets.items())
    return {"lagna":chart.get("lagna_sign") or chart.get("lagna"),
            "moon":chart.get("moon_sign"),"nakshatra":chart.get("nakshatra"),"planets":p}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--output",default=str(HERE/"results"))
    args=ap.parse_args(); out=Path(args.output); out.mkdir(parents=True,exist_ok=True)
    rows=[]; failures=[]
    for p in PROFILES:
        name,y,m,d,hh,mm,city,country=p
        try:
            chart,status=calculate_chart(y,m,d,hh,mm,city,country)
            if status!="OK" or not chart: failures.append({"profile":name,"status":status}); continue
            report=build_report(chart,name)
            sec=sections(report)
            wanted={k:v for k,v in sec.items() if any(q in k.lower() for q in ("life","guid","tim","chapter","outlook"))}
            if not wanted: wanted=sec
            rows.append({"profile":name,"birth":[y,m,d,hh,mm,city,country],
                         "evidence":signature(chart),"sections":wanted})
        except Exception as e: failures.append({"profile":name,"status":type(e).__name__,"detail":str(e)[:200]})
    pairs=[]
    for a,b in combinations(rows,2):
        ta=norm("\n".join(a["sections"].values())); tb=norm("\n".join(b["sections"].values()))
        sim=difflib.SequenceMatcher(None,ta,tb,autojunk=False).ratio() if ta and tb else 0
        same=a["evidence"]==b["evidence"]
        if sim>=.70 or (not same and sim>=.55):
            pairs.append({"a":a["profile"],"b":b["profile"],"similarity":round(sim,4),
                          "same_evidence_signature":same})
    pairs.sort(key=lambda x:x["similarity"],reverse=True)
    result={"profiles_attempted":len(PROFILES),"profiles_generated":len(rows),
            "failures":failures,"flagged_pairs":pairs,"profiles":rows}
    (out/"astrolab_deep_reading_matrix.json").write_text(json.dumps(result,indent=2,default=str),encoding="utf-8")
    md=["# AstroLab Deep Reading QA","",
        f"- Profiles attempted: {len(PROFILES)}",f"- Successful: {len(rows)}",
        f"- Failures: {len(failures)}",f"- Flagged similarity pairs: {len(pairs)}","",
        "## Highest similarity pairs","",
        "| A | B | Similarity | Same evidence signature |","|---|---|---:|---|"]
    for x in pairs[:30]: md.append(f"| {x['a']} | {x['b']} | {x['similarity']:.1%} | {x['same_evidence_signature']} |")
    md += ["","## Interpretation","",
      "A high text-similarity score is a review flag, not proof of a defect. Shared chart evidence can justify overlap. Materially different evidence with highly similar personalised prose requires manual evidence-chain review.",
      "This QA tests internal consistency/personalisation; it does not scientifically validate astrology or future-event prediction."]
    (out/"astrolab_deep_reading_report.md").write_text("\n".join(md),encoding="utf-8")
    print("\n".join(md[:12]))
    return 1 if not rows else 0
if __name__=="__main__": raise SystemExit(main())
