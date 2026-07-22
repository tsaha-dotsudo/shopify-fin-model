"""Generate an anonymized public dashboard (dashboard.html) from the CSVs in raw/.

Safe to publish: months are masked to M1..Mn, net sales and AOV are indexed to
the first full month = 100, products are renamed A, B, C..., and only rates
and ratios are shown. No currency amounts, SKU names, or customer counts.
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

p = pnl.iloc[1:].reset_index(drop=True)
c = cust.iloc[1:].reset_index(drop=True)
f = fun.iloc[1:].reset_index(drop=True)

base = p.loc[0, "net_sales"]
labels = [f"M{i+1}" + ("*" if is_partial(m) else "") for i, m in enumerate(p["month"])]
idx = [round(runrate(m, v) / base * 100) for m, v in zip(p["month"], p["net_sales"])]
last_partial = is_partial(p["month"].iloc[-1])

mom = [None] + [round((idx[i] / idx[i-1] - 1) * 100, 1) for i in range(1, len(idx))]
conv = [round(v * 100, 1) for v in f["conversion_rate"]]
repeat = [round(v * 100, 1) for v in c["returning_customer_rate"]]
aov_base = c.loc[0, "average_order_value"]
aov_idx = [round(v / aov_base * 100) for v in c["average_order_value"]]
disc = [round(-d / g * 100, 1) for d, g in zip(p["discounts"], p["gross_sales"])]
rets = [round(-r / g * 100, 1) for r, g in zip(p["returns"], p["gross_sales"])]

fl = f.iloc[-1]
funnel = [
    ("Visited", 100.0),
    ("Added to cart", round(fl["cart_adds"] / fl["sessions"] * 100, 1)),
    ("Reached checkout", round(fl["reached_checkout"] / fl["sessions"] * 100, 1)),
    ("Purchased", round(fl["completed_checkout"] / fl["sessions"] * 100, 1)),
]

top5 = prod.nlargest(5, "net_sales")
tot = prod["net_sales"].sum()
shares = [round(v / tot * 100, 1) for v in top5["net_sales"]]
shares.append(round(100 - sum(shares), 1))
share_labels = [f"Product {chr(65+i)}" for i in range(5)] + ["All others"]

last_full = p.iloc[-2] if last_partial else p.iloc[-1]
growth_mult = round(last_full["net_sales"] / base, 1)
kpis = [
    (f"{growth_mult}x", "net sales growth"),
    (f"{conv[-1]}%", "conversion"),
    (f"{repeat[-1]}%", "repeat rate"),
    (f"{rets[-1]}%", "returns"),
    (f"{disc[-1]}%", "discounts"),
]

kpi_html = "".join(
    f'<div class="pill kpi"><span class="v">{v}</span><span class="l">{l}</span></div>'
    for v, l in kpis
)
funnel_html = "".join(
    f'<div class="step"><span class="pill tag">{name}</span>'
    f'<div class="bar-track"><div class="bar-fill" style="width:{val}%"></div></div>'
    f'<span class="pct">{val:g}%</span></div>'
    for name, val in funnel
)

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{SHOP_NAME} - store analytics</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {{
    --ink: #111114; --ink-2: #6f7076; --ink-3: #a4a5ab;
    --bg: #fbfbfa; --card: #ffffff; --line: #ececea;
    --accent: #2a78d6; --warm: #eb6834;
  }}
  * {{ box-sizing: border-box; margin: 0; }}
  body {{ background: var(--bg); color: var(--ink); font-family: 'Inter', sans-serif; line-height: 1.6; -webkit-font-smoothing: antialiased; }}
  .wrap {{ max-width: 880px; margin: 0 auto; padding: 64px 24px 72px; }}
  .pill {{ border-radius: 999px; }}
  header {{ text-align: center; margin-bottom: 40px; }}
  .eyebrow {{ display: inline-block; font-size: 12px; font-weight: 500; letter-spacing: 0.04em; color: var(--ink-2); background: var(--card); border: 1px solid var(--line); padding: 6px 16px; border-radius: 999px; }}
  h1 {{ font-size: clamp(26px, 4.5vw, 38px); font-weight: 600; letter-spacing: -0.02em; margin: 20px auto 8px; max-width: 560px; line-height: 1.2; }}
  .note {{ font-size: 13px; color: var(--ink-3); max-width: 520px; margin: 0 auto; }}
  .kpis {{ display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; margin: 36px 0 56px; }}
  .kpi {{ background: var(--card); border: 1px solid var(--line); padding: 10px 22px; display: flex; align-items: baseline; gap: 8px; }}
  .kpi .v {{ font-size: 20px; font-weight: 600; letter-spacing: -0.01em; }}
  .kpi .l {{ font-size: 12px; color: var(--ink-2); }}
  section {{ margin-bottom: 56px; }}
  h2 {{ font-size: 16px; font-weight: 600; letter-spacing: -0.01em; text-align: center; }}
  .sub {{ font-size: 13px; color: var(--ink-2); text-align: center; margin: 4px 0 20px; }}
  .chart {{ position: relative; height: 280px; background: var(--card); border: 1px solid var(--line); border-radius: 24px; padding: 20px; }}
  .chart.tall {{ height: 330px; }}
  .legend {{ display: flex; justify-content: center; gap: 10px; margin-bottom: 14px; }}
  .legend .pill {{ font-size: 12px; color: var(--ink-2); background: var(--card); border: 1px solid var(--line); padding: 4px 14px; display: flex; align-items: center; gap: 6px; }}
  .dot {{ width: 8px; height: 8px; border-radius: 999px; display: inline-block; }}
  .grid2 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }}
  .funnel {{ background: var(--card); border: 1px solid var(--line); border-radius: 24px; padding: 28px; display: flex; flex-direction: column; gap: 14px; }}
  .step {{ display: grid; grid-template-columns: 150px 1fr 52px; align-items: center; gap: 12px; }}
  .tag {{ font-size: 12px; color: var(--ink-2); background: var(--bg); border: 1px solid var(--line); padding: 4px 12px; text-align: center; }}
  .bar-track {{ height: 12px; background: var(--bg); border-radius: 999px; overflow: hidden; }}
  .bar-fill {{ height: 100%; background: var(--accent); border-radius: 999px; }}
  .pct {{ font-size: 13px; font-weight: 500; text-align: right; }}
  footer {{ text-align: center; font-size: 12px; color: var(--ink-3); }}
  footer .pill {{ display: inline-block; background: var(--card); border: 1px solid var(--line); padding: 6px 16px; }}
  @media (max-width: 480px) {{ .step {{ grid-template-columns: 110px 1fr 46px; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <span class="eyebrow">store analytics / anonymized</span>
    <h1>{growth_mult}x net sales in {len(idx) - (1 if last_partial else 0)} months</h1>
    <p class="note">Generated {TODAY.isoformat()}. Indexes and rates only; revenue, volumes, and product names withheld. * marks the current partial month at run-rate.</p>
  </header>

  <div class="kpis">{kpi_html}</div>

  <section>
    <h2>Net sales index</h2>
    <p class="sub">First full month = 100</p>
    <div class="chart"><canvas id="c1" role="img" aria-label="Net sales index by month"></canvas></div>
  </section>

  <section>
    <h2>Month over month growth</h2>
    <p class="sub">Change in net sales index vs prior month</p>
    <div class="chart"><canvas id="c2" role="img" aria-label="Month over month growth in percent"></canvas></div>
  </section>

  <section>
    <h2>Conversion and repeat rate</h2>
    <div class="legend">
      <span class="pill"><span class="dot" style="background: var(--accent)"></span>conversion</span>
      <span class="pill"><span class="dot" style="background: var(--warm)"></span>repeat rate (dashed)</span>
    </div>
    <div class="chart"><canvas id="c3" role="img" aria-label="Conversion rate and repeat customer rate by month"></canvas></div>
  </section>

  <section>
    <h2>Where sessions go</h2>
    <p class="sub">Latest month, each stage as a share of all sessions</p>
    <div class="funnel">{funnel_html}</div>
  </section>

  <section>
    <h2>Order economics</h2>
    <div class="legend">
      <span class="pill"><span class="dot" style="background: var(--accent)"></span>AOV index</span>
      <span class="pill"><span class="dot" style="background: var(--warm)"></span>discount rate %</span>
      <span class="pill"><span class="dot" style="background: var(--ink-3)"></span>return rate %</span>
    </div>
    <div class="grid2">
      <div class="chart"><canvas id="c4" role="img" aria-label="Average order value index by month"></canvas></div>
      <div class="chart"><canvas id="c5" role="img" aria-label="Discount rate and return rate by month"></canvas></div>
    </div>
  </section>

  <section>
    <h2>Product concentration</h2>
    <p class="sub">Share of net sales, top five products anonymized</p>
    <div class="chart tall"><canvas id="c6" role="img" aria-label="Share of net sales by anonymized product"></canvas></div>
  </section>

  <footer><span class="pill">{SHOP_NAME} / shopify-fin-model / ShopifyQL</span></footer>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const L = {json.dumps(labels)};
const IDX = {json.dumps(idx)};
const MOM = {json.dumps(mom)};
const CONV = {json.dumps(conv)};
const REP = {json.dumps(repeat)};
const AOV = {json.dumps(aov_idx)};
const DISC = {json.dumps(disc)};
const RETS = {json.dumps(rets)};
const SHARES = {json.dumps(shares)};
const SLAB = {json.dumps(share_labels)};
const PARTIAL = {str(last_partial).lower()};
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.font.size = 12;
Chart.defaults.color = '#a4a5ab';
const GRID = {{ color: '#f1f1ef' }};
const NOGRID = {{ display: false }};
function line(id, datasets, yFmt) {{
  new Chart(document.getElementById(id), {{ type: 'line',
    data: {{ labels: L, datasets }},
    options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }},
      tooltip: yFmt ? {{ callbacks: {{ label: c => yFmt(c.parsed.y) }} }} : undefined }},
      scales: {{ x: {{ ticks: {{ autoSkip: false }}, grid: NOGRID, border: {{ display: false }} }},
        y: {{ grid: GRID, border: {{ display: false }}, ticks: yFmt ? {{ callback: v => yFmt(v) }} : undefined }} }} }} }});
}}
line('c1', [{{ data: IDX, borderColor: '#2a78d6', backgroundColor: 'rgba(42,120,214,0.07)', fill: true, borderWidth: 2, pointRadius: 3, tension: 0.35,
  segment: {{ borderDash: ctx => (PARTIAL && ctx.p1DataIndex === L.length - 1) ? [6, 4] : undefined }} }}]);
new Chart(document.getElementById('c2'), {{ type: 'bar',
  data: {{ labels: L, datasets: [{{ data: MOM, backgroundColor: MOM.map(v => v !== null && v < 0 ? '#eb6834' : '#2a78d6'), borderRadius: 999, maxBarThickness: 18 }}] }},
  options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }},
    tooltip: {{ callbacks: {{ label: c => (c.parsed.y > 0 ? '+' : '') + c.parsed.y + '%' }} }} }},
    scales: {{ x: {{ ticks: {{ autoSkip: false }}, grid: NOGRID, border: {{ display: false }} }},
      y: {{ grid: GRID, border: {{ display: false }}, ticks: {{ callback: v => v + '%' }} }} }} }} }});
line('c3', [
  {{ data: CONV, borderColor: '#2a78d6', borderWidth: 2, pointRadius: 3, tension: 0.35 }},
  {{ data: REP, borderColor: '#eb6834', borderWidth: 2, borderDash: [6, 4], pointRadius: 3, pointStyle: 'rect', tension: 0.35 }}
], v => v.toFixed(1) + '%');
line('c4', [{{ data: AOV, borderColor: '#2a78d6', borderWidth: 2, pointRadius: 3, tension: 0.35 }}]);
line('c5', [
  {{ data: DISC, borderColor: '#eb6834', borderWidth: 2, pointRadius: 3, tension: 0.35 }},
  {{ data: RETS, borderColor: '#a4a5ab', borderWidth: 2, borderDash: [4, 4], pointRadius: 3, pointStyle: 'rect', tension: 0.35 }}
], v => v.toFixed(1) + '%');
new Chart(document.getElementById('c6'), {{ type: 'bar',
  data: {{ labels: SLAB, datasets: [{{ data: SHARES,
    backgroundColor: SLAB.map(l => l === 'All others' ? '#dcdcd8' : '#2a78d6'), borderRadius: 999, maxBarThickness: 18 }}] }},
  options: {{ indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }},
    tooltip: {{ callbacks: {{ label: c => c.parsed.x.toFixed(1) + '% of net sales' }} }} }},
    scales: {{ x: {{ grid: GRID, border: {{ display: false }}, ticks: {{ callback: v => v + '%' }} }},
      y: {{ grid: NOGRID, border: {{ display: false }} }} }} }} }});
</script>
</body>
</html>"""

open("dashboard.html", "w").write(html)
print("wrote dashboard.html")
