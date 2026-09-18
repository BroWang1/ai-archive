#!/usr/bin/env python3
"""Render the browsable catalog page from the index. Output: docs/catalog.html"""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def collect():
    rows = []
    for p in sorted((ROOT / "index").rglob("*.json")):
        r = json.loads(p.read_text())
        cap = r["captures"][-1]
        lic = cap["license"]
        rows.append({
            "id": r["repo_id"],
            "org": r["canonical_org"],
            "gb": round(cap["weight_bytes"] / 1e9, 1),
            "tag": lic.get("tag") or "none",
            "freedom": lic.get("freedom", "conditional"),
            "note": lic.get("freedom_note", ""),
            "mirrored": bool((cap.get("mirrors") or {}).get("hf")),
            "gated": bool(cap.get("gate_terms_sha256")),
            "rev": cap["revision"][:12],
            "captured": cap["captured_at"][:10],
        })
    return rows


TEMPLATE = r"""<title>AIArchive Catalog</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Zilla+Slab:wght@500;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{
  --paper:#FAFAF7; --ink:#1D2126; --muted:#5C6470; --line:#E3E2DC; --panel:#FFFFFF;
  --seal:#BE3A2B; --free:#2E7D4F; --free-bg:#E7F2EB; --cond:#9A6A14; --cond-bg:#F7EFDD;
  --restr:#A02F27; --restr-bg:#F6E5E2; --unlic:#5C6470; --unlic-bg:#ECECE8;
  --display:'Zilla Slab',Georgia,serif; --body:'IBM Plex Sans',system-ui,sans-serif;
  --mono:'IBM Plex Mono',ui-monospace,monospace;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --paper:#15171C; --ink:#E8E6E0; --muted:#9AA1AC; --line:#2B2F37; --panel:#1C1F26;
  --seal:#E05A47; --free:#5DBA85; --free-bg:#1C2E24; --cond:#D9A84E; --cond-bg:#2E2718;
  --restr:#E07A6E; --restr-bg:#33201D; --unlic:#9AA1AC; --unlic-bg:#23262C;
}}
:root[data-theme="dark"]{
  --paper:#15171C; --ink:#E8E6E0; --muted:#9AA1AC; --line:#2B2F37; --panel:#1C1F26;
  --seal:#E05A47; --free:#5DBA85; --free-bg:#1C2E24; --cond:#D9A84E; --cond-bg:#2E2718;
  --restr:#E07A6E; --restr-bg:#33201D; --unlic:#9AA1AC; --unlic-bg:#23262C;
}
body{background:var(--paper);color:var(--ink);font-family:var(--body);margin:0;
  padding-block:28px 48px;padding-inline:clamp(16px,4vw,40px);font-size:15px;line-height:1.5}
.wrap{max-width:1060px;margin:0 auto}
header{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;border-bottom:3px solid var(--seal);padding-bottom:14px}
h1{font-family:var(--display);font-weight:600;font-size:clamp(26px,4vw,34px);margin:0;text-wrap:balance}
h1 .seal{color:var(--seal)}
.sub{color:var(--muted);font-size:14px}
.picks{margin:24px 0 8px}
.picks h2{font-family:var(--display);font-weight:600;font-size:20px;margin:0 0 2px}
.picks .lede{color:var(--muted);font-size:13.5px;margin:0 0 14px}
.pickgroup{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin:14px 0 8px}
.pickgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px}
.pick{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--seal);border-radius:6px;padding:10px 12px;display:flex;flex-direction:column;gap:3px}
.pick .plabel{font-size:12px;font-weight:600;color:var(--muted)}
.pick .pname{font-weight:600}
.pick .pname a{color:inherit;text-decoration:none}
.pick .pname a:hover{color:var(--seal)}
.pick .pwhy{font-size:12.5px;color:var(--muted)}
.pick .pmir{font-family:var(--mono);font-size:11.5px;color:var(--free)}
.pick .prun{font-size:11.5px;color:var(--muted)}
.pick .prun a{color:inherit}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:22px 0 18px}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:12px 14px;cursor:pointer;text-align:left;font:inherit;color:inherit}
.tile[aria-pressed="true"]{outline:2px solid var(--seal);outline-offset:-1px}
.tile .n{font-family:var(--display);font-size:26px;font-weight:600;font-variant-numeric:tabular-nums}
.tile .lbl{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.tile .tb{font-family:var(--mono);font-size:12px;color:var(--muted)}
.tile.free .n{color:var(--free)} .tile.conditional .n{color:var(--cond)}
.tile.restricted .n{color:var(--restr)} .tile.unlicensed .n{color:var(--unlic)}
.bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:14px}
input[type=search]{flex:1;min-width:180px;background:var(--panel);border:1px solid var(--line);
  border-radius:6px;padding:8px 12px;color:var(--ink);font:inherit}
input[type=search]:focus{outline:2px solid var(--seal)}
.count{color:var(--muted);font-size:13px;font-variant-numeric:tabular-nums}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:6px;background:var(--panel)}
table{border-collapse:collapse;width:100%;min-width:780px}
th{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);
  text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);cursor:pointer;white-space:nowrap}
th.num{text-align:right}
td{padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:none}
.model{font-weight:600}
.model a{color:inherit;text-decoration:none}
.model a:hover{color:var(--seal)}
.model .note{display:block;font-weight:400;font-size:12.5px;color:var(--muted);max-width:52ch}
.org{color:var(--muted);white-space:nowrap}
.gb{font-family:var(--mono);text-align:right;white-space:nowrap;font-size:13.5px}
.badge{display:inline-block;font-size:11.5px;font-weight:600;padding:2px 9px;border-radius:99px;white-space:nowrap}
.b-free{color:var(--free);background:var(--free-bg)} .b-conditional{color:var(--cond);background:var(--cond-bg)}
.b-restricted{color:var(--restr);background:var(--restr-bg)} .b-unlicensed{color:var(--unlic);background:var(--unlic-bg)}
.mir{font-family:var(--mono);font-size:12px;color:var(--free);white-space:nowrap}
.mir a{color:inherit}
.not{font-family:var(--mono);font-size:12px;color:var(--muted);white-space:nowrap}
footer{margin-top:16px;color:var(--muted);font-size:12.5px;display:flex;gap:16px;flex-wrap:wrap}
footer a{color:var(--seal)}
@media (max-width:640px){ .model .note{max-width:none} }
</style>
<div class="wrap">
<header>
  <h1><span class="seal">AI</span>Archive Catalog</h1>
  <span class="sub">Preservation records for frontier open-weight models — filter by license freedom</span>
</header>
<section class="picks">
  <h2>Find your local AI</h2>
  <p class="lede">The best open Chinese model for your setup — evidence-picked, freedom-first, preserved here.</p>
  <div id="pickspanel"></div>
</section>
<div class="tiles" id="tiles"></div>
<div class="bar">
  <input type="search" id="q" placeholder="Search model or lab…" aria-label="Search models">
  <span class="count" id="count"></span>
</div>
<div class="tablewrap"><table>
  <thead><tr>
    <th data-k="id">Model</th><th data-k="org">Lab</th>
    <th data-k="gb" class="num">Weights</th><th data-k="freedom">Freedom</th>
    <th data-k="mirrored">Backup</th>
  </tr></thead>
  <tbody id="rows"></tbody>
</table></div>
<footer>
  <span>Generated __DATE__ · __N__ models · __TB__ TB manifested</span>
  <a href="https://github.com/BroWang1/ai-archive">catalog source &amp; fingerprints</a>
  <a href="https://huggingface.co/AIArchiveInfo">mirror org</a>
</footer>
</div>
<script>
const DATA = __DATA__;
const PICKS = __PICKS__;
const MIRRORED = new Set(DATA.filter(r=>r.mirrored).map(r=>r.id));
function renderPicks(){
  const groups = [["hardware","By your hardware"],["use-case","By the job"]];
  const el = document.getElementById("pickspanel");
  el.innerHTML = groups.map(([g,title])=>{
    const cards = PICKS.filter(p=>p.group===g).map(p=>{
      const mir = MIRRORED.has(p.pick);
      const url = mir ? `https://huggingface.co/AIArchiveInfo/${p.pick.split("/")[1]}`
                      : `https://huggingface.co/${p.pick}`;
      const runners = (p.runners||[]).map(r=>`<a href="https://huggingface.co/${r}" target="_blank" rel="noopener">${r.split("/")[1]}</a>`).join(", ");
      return `<div class="pick"><span class="plabel">${p.label}</span>
        <span class="pname"><a href="${url}" target="_blank" rel="noopener">${p.pick.split("/")[1]}</a></span>
        ${mir?'<span class="pmir">✓ preserved mirror</span>':""}
        <span class="pwhy">${p.why}</span>
        ${runners?`<span class="prun">also: ${runners}</span>`:""}</div>`;
    }).join("");
    return `<div class="pickgroup">${title}</div><div class="pickgrid">${cards}</div>`;
  }).join("");
}
renderPicks();
const TIERS = ["free","conditional","restricted","unlicensed"];
const TIER_LABEL = {free:"Full freedom", conditional:"Strings attached", restricted:"Restricted", unlicensed:"No license"};
const state = { tier:null, q:"", sortK:"freedom", asc:true };
const tierRank = {free:0, conditional:1, restricted:2, unlicensed:3};
const fmt = gb => gb >= 1000 ? (gb/1000).toFixed(2)+" TB" : gb.toFixed(1)+" GB";

function tiles(){
  const el = document.getElementById("tiles"); el.innerHTML = "";
  for(const t of TIERS){
    const rows = DATA.filter(r => r.freedom === t);
    if(!rows.length) continue;
    const tb = rows.reduce((s,r)=>s+r.gb,0)/1000;
    const b = document.createElement("button");
    b.className = "tile "+t;
    b.setAttribute("aria-pressed", state.tier===t);
    b.innerHTML = `<div class="n">${rows.length}</div><div class="lbl">${TIER_LABEL[t]}</div><div class="tb">${tb.toFixed(1)} TB</div>`;
    b.onclick = () => { state.tier = state.tier===t ? null : t; render(); };
    el.appendChild(b);
  }
}
function render(){
  tiles();
  let rows = DATA.slice();
  if(state.tier) rows = rows.filter(r=>r.freedom===state.tier);
  if(state.q){ const q=state.q.toLowerCase(); rows = rows.filter(r=>r.id.toLowerCase().includes(q)); }
  rows.sort((a,b)=>{
    let va=a[state.sortK], vb=b[state.sortK];
    if(state.sortK==="freedom"){ va=tierRank[a.freedom]*1e6-a.gb; vb=tierRank[b.freedom]*1e6-b.gb; }
    return (va<vb?-1:va>vb?1:0)*(state.asc?1:-1);
  });
  document.getElementById("count").textContent = rows.length+" shown";
  document.getElementById("rows").innerHTML = rows.map(r=>`<tr>
    <td class="model"><a href="https://huggingface.co/${r.id}" target="_blank" rel="noopener">${r.id}</a>
      ${r.note?`<span class="note">${r.note}</span>`:""}</td>
    <td class="org">${r.org}</td>
    <td class="gb">${fmt(r.gb)}</td>
    <td><span class="badge b-${r.freedom}">${TIER_LABEL[r.freedom]}</span>${r.gated?' <span class="not">gated</span>':""}</td>
    <td>${r.mirrored?`<span class="mir">✓ <a href="https://huggingface.co/AIArchiveInfo/${r.id.split("/")[1]}" target="_blank" rel="noopener">mirrored</a></span>`
                    :`<span class="not">catalog only</span>`}</td>
  </tr>`).join("");
}
document.getElementById("q").addEventListener("input", e=>{state.q=e.target.value; render();});
document.querySelectorAll("th").forEach(th=>th.onclick=()=>{
  const k=th.dataset.k; if(state.sortK===k) state.asc=!state.asc; else {state.sortK=k; state.asc=true;} render();
});
render();
</script>
"""


def main():
    rows = collect()
    tb = sum(r["gb"] for r in rows) / 1000
    picks = json.loads((ROOT / "config" / "picks.json").read_text())["picks"]
    html = (TEMPLATE
            .replace("__DATA__", json.dumps(rows))
            .replace("__PICKS__", json.dumps(picks))
            .replace("__DATE__", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
            .replace("__N__", str(len(rows)))
            .replace("__TB__", f"{tb:.1f}"))
    out = ROOT / "docs" / "catalog.html"
    out.write_text(html)
    print(f"wrote {out.relative_to(ROOT)}: {len(rows)} models, {tb:.1f} TB")


if __name__ == "__main__":
    main()
