"""Generate an anonymized public dashboard (dashboard.html) from the CSVs in raw/.

Safe to publish: months are masked to M1..Mn, net sales are indexed to the
first full month = 100, products are renamed A, B, C..., and only rates and
ratios are shown. No currency amounts, SKU names, or customer counts.
"""
import calendar
import json
from datetime import date

import pandas as pd

SHOP_NAME = "SHOP_NAME"  # set your store name here

pnl = pd.read_csv("raw/pnl_monthly.csv")
cust = pd.read_csv("raw/customers_monthly.csv")
fun = pd.read_csv("raw/funnel_monthly.csv")
prod = pd.read_csv("raw/products.csv")

TODAY = date.today()

def is_partial(ym):
    return ym == f"{TODAY.year}-{TODAY.month:02d}"

def runrate(ym, value):
    if not is_partial(ym):
        return value
    y, m = map(int, ym.split("-"))
    return value / max(TODAY.day - 1, 1) * calendar.monthrange(y, m)[1]

# drop the launch partial month (row 0) for indexing; keep from first full month
p = pnl.iloc[1:].reset_index(drop=True)
c = cust.iloc[1:].reset_index(drop=True)
f = fun.iloc[1:].reset_index(drop=True)

base = p.loc[0, "net_sales"]
labels = [f"M{i+1}" + ("*" if is_partial(m) else "") for i, m in enumerate(p["month"])]
idx = [round(runrate(m, v) / base * 100) for m, v in zip(p["month"], p["net_sales"])]
last_partial = is_partial(p["month"].iloc[-1])

conv = [round(v * 100, 1) for v in f["conversion_rate"]]
repeat = [round(v * 100, 1) for v in c["returning_customer_rate"]]

top5 = prod.nlargest(5, "net_sales")
tot = prod["net_sales"].sum()
shares = [round(v / tot * 100, 1) for v in top5["net_sales"]]
shares.append(round(100 - sum(shares), 1))
share_labels = [f"Product {chr(65+i)}" for i in range(5)] + ["All others"]

last_full = p.iloc[-2] if last_partial else p.iloc[-1]
growth_mult = round(last_full["net_sales"] / base, 1)
kpis = [
    ("Net sales growth", f"{growth_mult}x", "first to latest full month"),
    ("Conversion rate", f"{conv[-1]}%", "latest month"),
    ("Repeat customer rate", f"{repeat[-1]}%", f"up from {repeat[0]}% at launch"),
    ("Return rate", f"{round(-p['returns'].iloc[-1] / p['gross_sales'].iloc[-1] * 100, 1)}%", "of gross, latest month"),
]

kpi_html = "".join(
    f'<div class="kpi"><span class="kpi-label">{l}</span>'
    f'<span class="kpi-value">{v}</span><span class="kpi-sub">{s}</span></div>'
    for l, v, s in kpis
)

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{SHOP_NAME} - store performance</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500&family=IBM+Plex+Sans+Condensed:wght@500;600&display=swap" rel="stylesheet">
<style>
  :root {{
    --ink: #16181d; --ink-2: #5b6069; --ink-3: #8a8f98;
    --paper: #f6f6f3; --card: #ffffff; --line: #e3e3dd;
    --signal: #2a78d6; --ember: #eb6834;
  }}
  * {{ box-sizing: border-box; margin: 0; }}
  body {{ background: var(--paper); color: var(--ink); font-family: 'IBM Plex Sans', sans-serif; line-height: 1.6; }}
  .wrap {{ max-width: 960px; margin: 0 auto; padding: 48px 24px 64px; }}
  header {{ border-bottom: 2px solid var(--ink); padding-bottom: 20px; margin-bottom: 8px; }}
  .eyebrow {{ font-family: 'IBM Plex Mono', monospace; font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-2); }}
  h1 {{ font-family: 'IBM Plex Sans Condensed', sans-serif; font-weight: 600; font-size: clamp(28px, 5vw, 44px); line-height: 1.1; margin-top: 6px; }}
  .note {{ font-size: 13px; color: var(--ink-3); margin: 12px 0 36px; }}
  .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1px; background: var(--line); border: 1px solid var(--line); margin-bottom: 44px; }}
  .kpi {{ background: var(--card); padding: 18px 20px; display: flex; flex-direction: column; gap: 2px; }}
  .kpi-label {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--ink-2); }}
  .kpi-value {{ font-family: 'IBM Plex Mono', monospace; font-weight: 500; font-size: 32px; }}
  .kpi-sub {{ font-size: 12px; color: var(--ink-3); }}
  section {{ margin-bottom: 44px; }}
  h2 {{ font-family: 'IBM Plex Sans Condensed', sans-serif; font-weight: 500; font-size: 20px; margin-bottom: 4px; }}
  .sub {{ font-size: 13px; color: var(--ink-2); margin-bottom: 16px; }}
  .chart {{ position: relative; height: 300px; background: var(--card); border: 1px solid var(--line); padding: 16px; }}
  .chart.tall {{ height: 340px; }}
  .legend {{ display: flex; gap: 18px; font-size: 12px; color: var(--ink-2); margin-bottom: 10px; font-family: 'IBM Plex Mono', monospace; }}
  .sw {{ display: inline-block; width: 10px; height: 10px; margin-right: 5px; vertical-align: -1px; }}
  footer {{ border-top: 1px solid var(--line); padding-top: 16px; font-size: 12px; color: var(--ink-3); font-family: 'IBM Plex Mono', monospace; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <span class="eyebrow">store performance / anonymized</span>
    <h1>{growth_mult}x in {len(idx) - (1 if last_partial else 0)} months, without a single discount war</h1>
  </header>
  <p class="note">Generated {TODAY.isoformat()} by build_dashboard.py. All figures are indexes and rates; absolute revenue, volumes, and product names are withheld by design. * = partial month at run-rate.</p>

  <div class="kpis">{kpi_html}</div>

  <section>
    <h2>Net sales index</h2>
    <p class="sub">First full month = 100. The dashed segment is the current partial month projected at run-rate.</p>
    <div class="chart"><canvas id="c1" role="img" aria-label="Line chart of net sales index over {len(idx)} months"></canvas></div>
  </section>

  <section>
    <h2>Conversion and repeat rate</h2>
    <p class="sub">Both climbing: the store converts visitors better and brings more of them back.</p>
    <div class="legend">
      <span><span class="sw" style="background: var(--signal)"></span>conversion rate</span>
      <span><span class="sw" style="background: var(--ember); height: 3px;"></span>repeat customer rate (dashed)</span>
    </div>
    <div class="chart"><canvas id="c2" role="img" aria-label="Conversion rate and repeat customer rate by month"></canvas></div>
  </section>

  <section>
    <h2>Product concentration</h2>
    <p class="sub">Share of net sales held by the top five products, anonymized.</p>
    <div class="chart tall"><canvas id="c3" role="img" aria-label="Share of net sales by anonymized product"></canvas></div>
  </section>

  <footer>{SHOP_NAME} / shopify-fin-model / data via ShopifyQL</footer>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const L = {json.dumps(labels)};
const IDX = {json.dumps(idx)};
const CONV = {json.dumps(conv)};
const REP = {json.dumps(repeat)};
const SHARES = {json.dumps(shares)};
const SLAB = {json.dumps(share_labels)};
const PARTIAL = {str(last_partial).lower()};
Chart.defaults.font.family = "'IBM Plex Mono', monospace";
Chart.defaults.color = '#8a8f98';
new Chart(document.getElementById('c1'), {{
  type: 'line',
  data: {{ labels: L, datasets: [{{ data: IDX, borderColor: '#2a78d6', backgroundColor: 'rgba(42,120,214,0.08)', fill: true, borderWidth: 2, pointRadius: 3,
    segment: {{ borderDash: ctx => (PARTIAL && ctx.p1DataIndex === L.length - 1) ? [6, 4] : undefined }} }}] }},
  options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }},
    scales: {{ x: {{ ticks: {{ autoSkip: false }}, grid: {{ display: false }} }}, y: {{ grid: {{ color: '#eeeee8' }} }} }} }}
}});
new Chart(document.getElementById('c2'), {{
  type: 'line',
  data: {{ labels: L, datasets: [
    {{ data: CONV, borderColor: '#2a78d6', borderWidth: 2, pointRadius: 3 }},
    {{ data: REP, borderColor: '#eb6834', borderWidth: 2, borderDash: [6, 4], pointRadius: 3, pointStyle: 'rect' }} ] }},
  options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }},
    tooltip: {{ callbacks: {{ label: c => c.parsed.y.toFixed(1) + '%' }} }} }},
    scales: {{ x: {{ ticks: {{ autoSkip: false }}, grid: {{ display: false }} }},
      y: {{ ticks: {{ callback: v => v + '%' }}, grid: {{ color: '#eeeee8' }} }} }} }}
}});
new Chart(document.getElementById('c3'), {{
  type: 'bar',
  data: {{ labels: SLAB, datasets: [{{ data: SHARES,
    backgroundColor: SLAB.map(l => l === 'All others' ? '#c9c9c2' : '#2a78d6'), borderRadius: 3, maxBarThickness: 22 }}] }},
  options: {{ indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }},
    tooltip: {{ callbacks: {{ label: c => c.parsed.x.toFixed(1) + '% of net sales' }} }} }},
    scales: {{ x: {{ ticks: {{ callback: v => v + '%' }}, grid: {{ color: '#eeeee8' }} }}, y: {{ grid: {{ display: false }} }} }} }}
}});
</script>
</body>
</html>"""

open("dashboard.html", "w").write(html)
print("wrote dashboard.html")
