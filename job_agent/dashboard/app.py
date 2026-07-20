"""Local web dashboard (FastAPI).

Imported lazily by the CLI so the core package has no hard dependency on FastAPI.
Serves a single self-contained page (no external assets) plus a JSON API. The
page offers search, stage filtering, a status bar chart, and tables for recent
jobs, applications, and statistics.
"""

from __future__ import annotations

from typing import Any

from job_agent.analytics.analytics import Analytics
from job_agent.config.settings import get_settings
from job_agent.database.base import Database
from job_agent.database.repository import Repository


def _collect() -> dict[str, Any]:
    settings = get_settings()
    db = Database(settings.storage.sqlite_path)
    db.create_all()
    with db.session_scope() as session:
        repo = Repository(session)
        stats = Analytics(repo).compute()
        jobs = []
        for job in repo.list_jobs(limit=500):
            score = repo.get_classifier(job.id)
            resume = repo.latest_resume(job.id)
            cover = repo.latest_cover_letter(job.id)
            jobs.append(
                {
                    "id": job.id[:8],
                    "company": job.company_name,
                    "title": job.title,
                    "location": job.location or "",
                    "remote": job.remote,
                    "source": job.source,
                    "state": job.state,
                    "score": round(score.overall_score, 3) if score else None,
                    "recommendation": score.recommendation.value if score else "",
                    "resume": f"v{resume.version}" if resume else "",
                    "cover": f"v{cover.version}" if cover else "",
                    "url": job.url,
                }
            )
        applications = []
        for app in repo.list_applications():
            j = repo.get_job(app.job_id)
            applications.append(
                {
                    "company": j.company_name if j else "",
                    "title": j.title if j else "",
                    "status": app.status,
                    "stage": app.stage,
                }
            )
    return {"stats": stats.as_dict(), "jobs": jobs, "applications": applications}


def create_app():  # type: ignore[no-untyped-def]
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse

    app = FastAPI(title="Job Agent Dashboard")

    @app.get("/api/data")
    def data() -> JSONResponse:  # pragma: no cover - requires server
        return JSONResponse(_collect())

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:  # pragma: no cover - requires server
        return _PAGE

    return app


_PAGE = """
<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job Agent Dashboard</title>
<style>
  :root { color-scheme: light dark; --bg:#0b1220; --card:#111a2e; --fg:#e5e7eb; --mut:#94a3b8; --acc:#38bdf8; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: ui-sans-serif, system-ui, sans-serif; background:var(--bg); color:var(--fg); }
  header { padding:20px 24px; border-bottom:1px solid #1e293b; }
  h1 { margin:0; font-size:20px; } .mut { color:var(--mut); }
  main { padding:24px; max-width:1200px; margin:0 auto; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:24px; }
  .kpi { background:var(--card); border:1px solid #1e293b; border-radius:12px; padding:16px; }
  .kpi b { font-size:26px; } .kpi span { display:block; color:var(--mut); font-size:12px; margin-top:4px; }
  .bar { height:22px; background:var(--acc); border-radius:4px; }
  .barrow { display:flex; align-items:center; gap:8px; margin:4px 0; font-size:13px; }
  .barrow .label { width:180px; color:var(--mut); } .barrow .val { width:36px; }
  input, select { background:var(--card); color:var(--fg); border:1px solid #334155; border-radius:8px; padding:8px; }
  table { width:100%; border-collapse:collapse; margin-top:12px; font-size:13px; }
  th, td { text-align:left; padding:8px 10px; border-bottom:1px solid #1e293b; }
  th { color:var(--mut); position:sticky; top:0; background:var(--bg); }
  .pill { padding:2px 8px; border-radius:999px; font-size:11px; background:#1e293b; }
  a { color:var(--acc); }
  .tblwrap { overflow-x:auto; }
</style></head><body>
<header><h1>Job Agent Dashboard</h1><div class="mut">SQLite is the source of truth — this view is read-only.</div></header>
<main>
  <div class="grid" id="kpis"></div>
  <h3>Pipeline status</h3><div id="chart"></div>
  <h3 style="margin-top:24px">Jobs</h3>
  <div style="display:flex; gap:8px; flex-wrap:wrap; margin:8px 0">
    <input id="search" placeholder="Search company or title..." oninput="render()" style="flex:1; min-width:200px">
    <select id="stateFilter" onchange="render()"><option value="">All states</option></select>
  </div>
  <div class="tblwrap"><table id="jobs"><thead><tr>
    <th>Company</th><th>Position</th><th>Loc</th><th>Source</th><th>State</th><th>Score</th><th>Rec</th><th>Resume</th><th>Cover</th><th>Link</th>
  </tr></thead><tbody></tbody></table></div>
</main>
<script>
let DATA = {jobs:[], stats:{}, applications:[]};
async function load(){ DATA = await (await fetch('/api/data')).json(); initStates(); renderKpis(); renderChart(); render(); }
function initStates(){ const sel=document.getElementById('stateFilter'); const seen=new Set();
  DATA.jobs.forEach(j=>{ if(!seen.has(j.state)){ seen.add(j.state); const o=document.createElement('option'); o.value=o.textContent=j.state; sel.appendChild(o);} }); }
function renderKpis(){ const s=DATA.stats; const items=[['Discovered',s.jobs_discovered],['Classified',s.jobs_classified],
  ['Prepared',s.applications_prepared],['Submitted',s.applications_submitted],['Interviews',s.interviews],['Offers',s.offers],
  ['Avg score',(s.avg_classifier_score||0).toFixed(2)],['Interview rate',((s.interview_rate||0)*100).toFixed(0)+'%']];
  document.getElementById('kpis').innerHTML = items.map(([k,v])=>`<div class="kpi"><b>${v}</b><span>${k}</span></div>`).join(''); }
function renderChart(){ const bs=DATA.stats.by_state||{}; const max=Math.max(1,...Object.values(bs));
  document.getElementById('chart').innerHTML = Object.entries(bs).sort((a,b)=>b[1]-a[1]).map(([k,v])=>
    `<div class="barrow"><span class="label">${k}</span><div class="bar" style="width:${(v/max)*260}px"></div><span class="val">${v}</span></div>`).join(''); }
function render(){ const q=(document.getElementById('search').value||'').toLowerCase(); const st=document.getElementById('stateFilter').value;
  const rows=DATA.jobs.filter(j=>(!st||j.state===st) && (j.company+j.title).toLowerCase().includes(q));
  document.querySelector('#jobs tbody').innerHTML = rows.map(j=>`<tr>
    <td>${esc(j.company)}</td><td>${esc(j.title)}</td><td>${esc(j.location)}</td><td>${esc(j.source)}</td>
    <td><span class="pill">${j.state}</span></td><td>${j.score??'-'}</td><td>${esc(j.recommendation)}</td>
    <td>${j.resume}</td><td>${j.cover}</td><td><a href="${j.url}" target="_blank">open</a></td></tr>`).join(''); }
function esc(s){ return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }
load();
</script></body></html>
"""
