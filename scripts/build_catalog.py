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


def collect_news(limit=40):
    """Derive the news feed from what the automation already records.
    Every event carries an action link — information you can act on."""
    events = []
    mirror_of = {}
    for p in sorted((ROOT / "index").rglob("*.json")):
        r = json.loads(p.read_text())
        rid = r["repo_id"]
        for cap in r["captures"]:
            hf = (cap.get("mirrors") or {}).get("hf")
            if hf:
                mirror_of[rid] = f"https://huggingface.co/{hf['repo']}"
        for cap in r["captures"]:
            lic = cap["license"]
            tier = lic.get("freedom", "unclassified")
            url = mirror_of.get(rid, f"https://huggingface.co/{rid}")
            events.append({"at": cap["captured_at"], "kind": "capture",
                           "text": f"Captured {rid} — {cap['weight_bytes']/1e9:.0f} GB manifested, license: {tier}",
                           "url": url, "action": "download" if rid in mirror_of else "view / download"})
            hf = (cap.get("mirrors") or {}).get("hf")
            if hf and hf.get("mirrored_at"):
                events.append({"at": hf["mirrored_at"], "kind": "mirror",
                               "text": f"Preserved {rid} — byte-identical mirror live, {hf.get('verified_files', '?')} files verified",
                               "url": f"https://huggingface.co/{hf['repo']}", "action": "download preserved copy"})
    liv = ROOT / "state" / "liveness.json"
    if liv.exists():
        for rid, entry in json.loads(liv.read_text()).get("repos", {}).items():
            for h in entry.get("history", []):
                if h.get("from") and h["from"] != h["to"]:
                    if rid in mirror_of:
                        url, action = mirror_of[rid], "original changed — get the preserved copy"
                    else:
                        url, action = f"https://github.com/BroWang1/ai-archive/blob/main/index/{rid}.json", "view archived record"
                    events.append({"at": h["at"], "kind": "alert",
                                   "text": f"Upstream change: {rid} went {h['from']} → {h['to']}",
                                   "url": url, "action": action})
    tr = ROOT / "state" / "trending_seen.json"
    if tr.exists():
        for e in json.loads(tr.read_text()).get("log", []):
            events.append({"at": e["at"], "kind": "trending",
                           "text": f"Trending outside tracked labs: {e['id']} ({e.get('downloads', 0):,} downloads)",
                           "url": f"https://huggingface.co/{e['id']}", "action": "view"})
    dg = ROOT / "state" / "digests.json"
    if dg.exists():
        for e in json.loads(dg.read_text()).get("digests", []):
            events.append({"at": e["at"], "kind": "digest", "text": e["text"],
                           "url": e.get("url"), "action": e.get("action", "read more")})
    rd = ROOT / "state" / "radar.json"
    if rd.exists():
        for e in json.loads(rd.read_text()).get("log", []):
            events.append({"at": e["at"], "kind": e["kind"], "text": e["text"],
                           "url": e.get("url"), "action": "read" if e["kind"] == "paper" else "discussion"})
    gh = ROOT / "state" / "github_watch.json"
    if gh.exists():
        for e in json.loads(gh.read_text()).get("log", []):
            events.append({"at": e["at"], "kind": "radar",
                           "text": f"New lab code: {e['id']} — {e.get('desc', '')}".rstrip(" —"),
                           "url": f"https://github.com/{e['id']}", "action": "view code"})
    events.sort(key=lambda e: e["at"], reverse=True)
    return events[:limit]


def write_json_feed(events):
    (ROOT / "docs" / "feed.json").write_text(json.dumps({
        "version": "https://jsonfeed.org/version/1.1",
        "title": "AIArchive — model preservation news",
        "home_page_url": "https://aiarchive.info",
        "feed_url": "https://aiarchive.info/feed.json",
        "description": "Captures, mirrors, takedown alerts and radar signals for open-weight AI models",
        "items": [{
            "id": f"{e['at']}-{abs(hash(e['text'])) & 0xffffffff}",
            "title": e["text"],
            "date_published": e["at"],
            "url": e.get("url") or "https://aiarchive.info",
            "content_text": e["text"],
        } for e in events],
    }, indent=1) + "\n")


def write_rss(events):
    items = "".join(
        f"<item><title>{e['text']}</title><pubDate>{e['at']}</pubDate>"
        f"<guid isPermaLink='false'>{e['at']}-{hash(e['text']) & 0xffffffff}</guid></item>"
        for e in events)
    (ROOT / "docs" / "news.xml").write_text(
        "<?xml version='1.0' encoding='UTF-8'?><rss version='2.0'><channel>"
        "<title>AIArchive — model preservation news</title>"
        "<link>https://aiarchive.info</link>"
        "<description>Captures, mirrors, takedown alerts and trending models, generated by the archive's automation</description>"
        f"{items}</channel></rss>")


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
.news{margin:22px 0 4px}
.news h2{font-family:var(--display);font-weight:600;font-size:18px;margin:0 0 8px;display:flex;align-items:baseline;gap:10px}
.news h2 a{font-family:var(--mono);font-size:11.5px;font-weight:400;color:var(--seal);text-decoration:none}
.newslist{display:flex;flex-direction:column;gap:0;border:1px solid var(--line);border-radius:6px;background:var(--panel);max-height:190px;overflow-y:auto}
.newsitem{display:flex;gap:10px;padding:7px 12px;border-bottom:1px solid var(--line);font-size:13px;align-items:baseline}
.newsitem:last-child{border-bottom:none}
.newsitem .nd{font-family:var(--mono);font-size:11.5px;color:var(--muted);white-space:nowrap}
.newsitem .nk{font-size:10.5px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;padding:1px 7px;border-radius:99px;white-space:nowrap}
.nk-capture{color:var(--cond);background:var(--cond-bg)} .nk-mirror{color:var(--free);background:var(--free-bg)}
.nk-alert{color:var(--restr);background:var(--restr-bg)} .nk-trending{color:var(--seal);background:var(--unlic-bg)}
.nk-radar{color:var(--muted);background:var(--unlic-bg)}
.nk-paper{color:var(--cond);background:var(--unlic-bg)} .nk-buzz{color:var(--seal);background:var(--unlic-bg)}
.nk-digest{color:#fff;background:var(--seal)}
.newsitem .na{margin-left:auto;font-family:var(--mono);font-size:11.5px;color:var(--seal);text-decoration:none;white-space:nowrap}
.newsitem .na:hover{text-decoration:underline}
.wizard{background:var(--panel);border:1px solid var(--line);border-top:3px solid var(--seal);border-radius:6px;padding:18px;margin:24px 0 6px}
.wizard h2{font-family:var(--display);font-weight:600;font-size:22px;margin:0 0 12px}
.wizrow{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px}
.wizfield{display:flex;flex-direction:column;gap:4px;flex:1;min-width:200px}
.wizfield label{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}
.wizfield select{background:var(--paper);border:1px solid var(--line);border-radius:6px;padding:9px 10px;color:var(--ink);font:inherit}
.wizfield select:focus{outline:2px solid var(--seal)}
.wizresult{display:flex;flex-direction:column;gap:6px;border-top:1px dashed var(--line);padding-top:12px}
.wizresult .wname{font-family:var(--display);font-size:22px;font-weight:600}
.wizresult .wname a{color:var(--seal);text-decoration:none}
.wizresult .wmeta{font-family:var(--mono);font-size:12.5px;color:var(--muted)}
.wizresult .wwhy{font-size:14px}
.wizresult .wrun{font-size:13px;color:var(--muted);line-height:1.6}
.wizresult .wrun b{color:var(--ink)}
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
<section class="news">
  <h2>Latest from the archive <a href="/news.xml">RSS</a></h2>
  <div class="newslist" id="newslist"></div>
</section>
<section class="wizard">
  <h2>Which model should I run?</h2>
  <div class="wizrow">
    <div class="wizfield"><label for="wmachine">Your machine</label>
      <select id="wmachine">
        <option value="0">Phone or tablet</option>
        <option value="1" selected>Basic laptop (8GB RAM)</option>
        <option value="2">Decent laptop / PC (16–32GB RAM)</option>
        <option value="3">Gaming PC (24GB+ GPU)</option>
        <option value="4">Workstation / 96–128GB Mac</option>
        <option value="5">Mac Studio 256GB+ / small server</option>
        <option value="6">Multi-GPU server</option>
      </select></div>
    <div class="wizfield"><label for="wtask">What you want to do</label>
      <select id="wtask">
        <option value="general" selected>General chat &amp; assistant</option>
        <option value="coding">Coding</option>
        <option value="vision">Understand images / screenshots</option>
        <option value="ocr">Read documents (OCR)</option>
        <option value="math">Math &amp; hard reasoning</option>
        <option value="longdocs">Very long documents</option>
        <option value="translation">Translation</option>
        <option value="stt">Speech → text</option>
        <option value="tts">Text → speech</option>
        <option value="images">Generate / edit images</option>
        <option value="video">Generate video</option>
        <option value="rag">Search my documents (RAG)</option>
        <option value="safety">Filter / moderate content</option>
        <option value="decisions">Instant decisions / classification</option>
      </select></div>
  </div>
  <div class="wizresult" id="wizresult"></div>
</section>
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
const NEWS = __NEWS__;
document.getElementById("newslist").innerHTML = NEWS.map(e=>
  `<div class="newsitem"><span class="nd">${e.at.slice(0,10)}</span>` +
  `<span class="nk nk-${e.kind}">${e.kind}</span><span>${e.text}</span>` +
  (e.url ? `<a class="na" href="${e.url}" target="_blank" rel="noopener">${e.action} →</a>` : "")
  ).join("");
const MIRRORED = new Set(DATA.filter(r=>r.mirrored).map(r=>r.id));
const LADDERS = {
  general: [[0,"openbmb/MiniCPM5-2B","2.5B that beats 4B-class models; official phone builds"],
            [1,"Qwen/Qwen3.5-9B","The most-downloaded model on Hugging Face; multimodal"],
            [2,"Qwen/Qwen3.6-35B-A3B","Flagship-adjacent quality at small-model speed (3B active)"],
            [3,"zai-org/GLM-4.7-Flash","MIT; strongest 30B-class, built for agents and tools"],
            [4,"Qwen/Qwen3.5-122B-A10B","Frontier-company benchmarks in 96–128GB of memory"],
            [5,"zai-org/GLM-5.3-Flash","MIT 320B MoE; best capability-per-byte in its class"],
            [6,"deepseek-ai/DeepSeek-V4-Pro-0813","#1 open-weight model in the world right now"]],
  coding: [[0,"openbmb/MiniCPM5-2B","LiveCodeBench 69.1 from a 2.5B — remarkable for a phone"],
           [1,"Qwen/Qwen3.5-9B","Solid coding in 8GB"],
           [2,"Qwen/Qwen3.6-35B-A3B","SWE-bench 73.4 — near-flagship coding, runs fast"],
           [3,"Qwen/Qwen3.8-27B","The Sept-2026 local coding default; 4-bit matches full quality"],
           [5,"zai-org/GLM-5.3-Flash","Tops open-weight coding boards"],
           [6,"deepseek-ai/DeepSeek-V4-Pro-0813","Maximum open coding ability"]],
  vision: [[0,"openbmb/MiniCPM-V-4","4.1B vision model for phones and 8GB machines"],
           [1,"Qwen/Qwen3.5-9B","Natively multimodal (MMMU 78.4)"],
           [3,"Qwen/Qwen3.8-27B","Same download as the coding pick — it sees images natively"]],
  ocr: [[0,"zai-org/GLM-OCR","1.3B, MIT, 94.6% OmniDocBench — beats frontier closed models, runs on CPU"]],
  math: [[0,"openbmb/MiniCPM5-2B","AIME 86.5 at 2.5B"],
         [1,"Qwen/Qwen3.5-9B","Strong reasoner for 8GB"],
         [3,"Qwen/Qwen3.8-27B","Only frontier-adjacent reasoning that fits 24GB"],
         [6,"deepseek-ai/DeepSeek-Math-V2","Maximum accuracy (96% AIME-class); server only"]],
  longdocs: [[1,"Qwen/Qwen3.5-9B","262K context natively, extendable to 1M"],
             [3,"Qwen/Qwen3.8-27B","262K context with strong recall"],
             [5,"zai-org/GLM-5.3-Flash","True 1,048,576-token window, verified from config"]],
  translation: [[0,"tencent/Hy-MT2-1.8B","Purpose-built 2B translator from the WMT-winning line; CPU-friendly"]],
  stt: [[0,"Qwen/Qwen3-ASR-1.7B","Top-20 speech recognition on all of HF by adoption"]],
  tts: [[0,"openbmb/VoxCPM2","Tokenizer-free TTS, 30 languages, runs on CPU"],
        [1,"Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice","Most-adopted open TTS with voice cloning"]],
  images: [[2,"zai-org/GLM-Image","6.9B, MIT, best at legible in-image text, low VRAM"],
           [3,"Qwen/Qwen-Image-Edit-2511","Top open image family: generation + editing in ~16GB"]],
  video: [[1,"Wan-AI/Wan2.1-T2V-1.3B","The lowest-VRAM open video model"],
          [2,"Wan-AI/Wan2.2-TI2V-5B","720p video on 8–24GB with offloading"],
          [3,"Wan-AI/Wan2.2-I2V-A14B","The community flagship — image-to-video, deepest LoRA ecosystem (civitai.com/ecosystems/wan)"]],
  rag: [[0,"Qwen/Qwen3-Embedding-0.6B","The RAG default (8.5M downloads/mo); runs on CPU; pair with Qwen3-Reranker-4B"],
        [3,"Qwen/Qwen3-Embedding-8B","The open-weight retrieval quality ceiling (MTEB 70.6)"]],
  safety: [[0,"Qwen/Qwen3Guard-Gen-4B","Top open guard in independent benchmarks; classifies input and output"]],
  decisions: [[0,"MoritzLaurer/deberta-v3-large-zeroshot-v2.0","Millisecond classification on a CPU — invent your own labels; for custom typed outputs use a small Qwen + Outlines"]],
};
const BYID = Object.fromEntries(DATA.map(r=>[r.id,r]));
function renderWizard(){
  const tier = +document.getElementById("wmachine").value;
  const task = document.getElementById("wtask").value;
  const ladder = LADDERS[task];
  let best = null;
  for(const [min, repo, note] of ladder) if(min <= tier) best = [min, repo, note];
  const el = document.getElementById("wizresult");
  if(!best){
    const [, repo, note] = ladder[0];
    el.innerHTML = `<span class="wwhy">This job really wants a bigger machine — the smallest good option is
      <a href="https://huggingface.co/${repo}" target="_blank" rel="noopener">${repo.split("/")[1]}</a> (${note}).</span>`;
    return;
  }
  const [, repo, note] = best;
  const row = BYID[repo];
  const name = repo.split("/")[1];
  const url = row && row.mirrored ? `https://huggingface.co/AIArchiveInfo/${name}` : `https://huggingface.co/${repo}`;
  const size = row ? (row.gb >= 1000 ? (row.gb/1000).toFixed(2)+" TB" : row.gb.toFixed(1)+" GB") : "";
  el.innerHTML = `
    <span class="wname"><a href="${url}" target="_blank" rel="noopener">${name}</a></span>
    <span class="wmeta">${repo} · original weights ${size} · quantized versions are typically ¼–½ of that${row && row.mirrored ? " · ✓ preserved in this archive" : ""}</span>
    <span class="wwhy">${note}.</span>
    <span class="wrun"><b>Run it:</b> 1) install <b>LM Studio</b> (lmstudio.ai) or <b>Ollama</b> (ollama.com) —
    both free · 2) search for “${name}” inside the app · 3) pick the largest quantized version that fits your
    memory, and you're chatting locally.</span>`;
}
document.getElementById("wmachine").addEventListener("change", renderWizard);
document.getElementById("wtask").addEventListener("change", renderWizard);
renderWizard();
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
    news = collect_news()
    write_rss(news)
    write_json_feed(news)
    (ROOT / "docs" / "news.json").write_text(json.dumps(news, indent=1) + "\n")
    html = (TEMPLATE
            .replace("__DATA__", json.dumps(rows))
            .replace("__PICKS__", json.dumps(picks))
            .replace("__NEWS__", json.dumps(news))
            .replace("__DATE__", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
            .replace("__N__", str(len(rows)))
            .replace("__TB__", f"{tb:.1f}"))
    out = ROOT / "docs" / "catalog.html"
    out.write_text(html)
    print(f"wrote {out.relative_to(ROOT)}: {len(rows)} models, {tb:.1f} TB")


if __name__ == "__main__":
    main()
