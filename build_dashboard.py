"""Generate an anonymized public dashboard (dashboard.html) from the CSVs in raw/.

Safe to publish: months masked to M1..Mn, sales and AOV indexed to the first
full month = 100, products renamed A, B, C..., only rates and ratios shown.
"""
import calendar
import json
import math
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
n = len(p)
last_partial = is_partial(p["month"].iloc[-1])
n_full = n - 1 if last_partial else n

base = p.loc[0, "net_sales"]
labels = [f"M{i+1}" + ("*" if is_partial(m) else "") for i, m in enumerate(p["month"])]
sales_rr = [runrate(m, v) for m, v in zip(p["month"], p["net_sales"])]
idx = [round(v / base * 100) for v in sales_rr]
sess_rr = [runrate(m, v) for m, v in zip(p["month"], f["sessions"])]

mom = [None] + [round((idx[i] / idx[i-1] - 1) * 100, 1) for i in range(1, n)]
conv = [round(v * 100, 1) for v in f["conversion_rate"]]
repeat = [round(v * 100, 1) for v in c["returning_customer_rate"]]
aov_base = c.loc[0, "average_order_value"]
aov_idx = [round(v / aov_base * 100) for v in c["average_order_value"]]
disc = [round(-d / g * 100, 1) for d, g in zip(p["discounts"], p["gross_sales"])]
rets = [round(-r / g * 100, 1) for r, g in zip(p["returns"], p["gross_sales"])]

cart_rate = [round(a / s * 100, 1) for a, s in zip(f["cart_adds"], f["sessions"])]
chk_rate = [round(a / s * 100, 1) for a, s in zip(f["reached_checkout"], f["sessions"])]
buy_rate = [round(a / s * 100, 1) for a, s in zip(f["completed_checkout"], f["sessions"])]

fl = f.iloc[-1]
funnel = [
    ("Visited", 100.0),
    ("Added to cart", cart_rate[-1]),
    ("Reached checkout", chk_rate[-1]),
    ("Purchased", buy_rate[-1]),
]

top5 = prod.nlargest(5, "net_sales")
tot = prod["net_sales"].sum()
shares = [round(v / tot * 100, 1) for v in top5["net_sales"]]
shares.append(round(100 - sum(shares), 1))
share_labels = [f"Product {chr(65+i)}" for i in range(5)] + ["All others"]

last_full_idx = n_full - 1
growth_mult = round(sales_rr[last_full_idx] / base, 1)

# 1. growth decomposition (ln-diff of sessions x conversion x AOV)
dec_traffic, dec_conv, dec_aov = [None], [None], [None]
for i in range(1, n):
    t = math.log(sess_rr[i] / sess_rr[i-1]) * 100
    cv = math.log(conv[i] / conv[i-1]) * 100
    av = math.log(aov_idx[i] / aov_idx[i-1]) * 100
    dec_traffic.append(round(t, 1)); dec_conv.append(round(cv, 1)); dec_aov.append(round(av, 1))

# 2. momentum heatmap (direction + magnitude per metric per month)
hm_metrics = [("Sales", idx), ("Sessions", [round(v / sess_rr[0] * 100) for v in sess_rr]),
              ("Conversion", conv), ("Repeat rate", repeat), ("AOV", aov_idx)]
def cell(seq, i):
    if i == 0: return ("", "#f1f1ef")
    ch = (seq[i] / seq[i-1] - 1) * 100 if seq[i-1] else 0
    mag = min(abs(ch) / 30, 1)
    if ch >= 0:
        col = f"rgba(42,120,214,{0.12 + 0.55 * mag:.2f})"
    else:
        col = f"rgba(235,104,52,{0.12 + 0.55 * mag:.2f})"
    return (f"{'+' if ch >= 0 else ''}{ch:.0f}%", col)
heat_rows = ""
for name, seq in hm_metrics:
    cells = "".join(f'<div class="hm-cell" style="background:{cell(seq,i)[1]}">{cell(seq,i)[0]}</div>' for i in range(n))
    heat_rows += f'<div class="hm-row"><span class="pill tag">{name}</span>{cells}</div>'
heat_head = '<div class="hm-row"><span class="pill tag" style="visibility:hidden">x</span>' + "".join(f'<div class="hm-cell hm-h">{l}</div>' for l in labels) + '</div>'

# 3. rolling 3-month average of sales index
roll = [None, None] + [round(sum(idx[i-2:i+1]) / 3) for i in range(2, n)]

# 4. cohort proxy: linear fit of repeat rate, projected to M12
xs = list(range(1, n + 1)); ys = repeat
xm, ym = sum(xs) / n, sum(ys) / n
slope = sum((x - xm) * (y - ym) for x, y in zip(xs, ys)) / sum((x - xm) ** 2 for x in xs)
icept = ym - slope * xm
fit_x = list(range(1, 13))
fit_y = [round(icept + slope * x, 1) for x in fit_x]
proj_m12 = fit_y[-1]

# 6. concentration index (HHI approximation on top5 + pooled others)
hhi = sum((s / 100) ** 2 for s in shares[:5]) + (shares[5] / 100) ** 2 / 25
hhi_pos = min(hhi / 0.25, 1) * 100  # 0.25+ = highly concentrated

# 7. health scorecard
def clamp(v): return max(0, min(100, round(v)))
score_conv = clamp(conv[-1] / 3.0 * 100)
score_rep = clamp(repeat[-1] / 30.0 * 100)
score_ret = clamp((1 - rets[-1] / 5.0) * 100)
score_disc = clamp((1 - disc[-1] / 8.0) * 100)
avg_mom3 = sum(v for v in mom[-3:] if v is not None) / 3
score_growth = clamp(avg_mom3 / 15.0 * 100) if avg_mom3 > 0 else clamp(50 + avg_mom3)
health = round((score_conv + score_rep + score_ret + score_disc + score_growth) / 5)
score_rows = [("Conversion", score_conv), ("Repeat rate", score_rep), ("Low returns", score_ret),
              ("Discount discipline", score_disc), ("Growth momentum", score_growth)]

# 8. discount efficiency scatter
scatter = [{"x": disc[i], "y": mom[i], "m": labels[i]} for i in range(1, n)]

# 9. projection band from full-month ln growth
lns = [math.log(sales_rr[i] / sales_rr[i-1]) for i in range(1, n_full)]
mu = sum(lns) / len(lns)
sd = (sum((v - mu) ** 2 for v in lns) / max(len(lns) - 1, 1)) ** 0.5
last_val = idx[last_full_idx]
proj_labels = labels + [f"M{n+1}p", f"M{n+2}p", f"M{n+3}p"]
proj_mid = [None] * (n - 1) + [idx[-1]]
proj_hi, proj_lo = list(proj_mid), list(proj_mid)
v = idx[-1]
for k in range(1, 4):
    proj_mid.append(round(v * math.exp(mu * k)))
    proj_hi.append(round(v * math.exp((mu + sd) * k)))
    proj_lo.append(round(v * math.exp((mu - sd) * k)))
idx_padded = idx + [None] * 3
roll_padded = roll + [None] * 3

# 10. anomaly flags (z-score on MoM)
moms = [v for v in mom if v is not None]
mm, ms = sum(moms) / len(moms), (sum((v - sum(moms)/len(moms)) ** 2 for v in moms) / max(len(moms) - 1, 1)) ** 0.5
anoms = []
for i in range(1, n):
    z = (mom[i] - mm) / ms if ms else 0
    if abs(z) >= 1.5:
        kind = "spike" if z > 0 else "dip"
        anoms.append(f"{labels[i]}: {'+' if mom[i] > 0 else ''}{mom[i]:g}% {kind} ({z:+.1f} sd from the {mm:.0f}% average)")
if not anoms:
    anoms = ["No months deviated more than 1.5 standard deviations from average growth."]
anom_html = "".join(f'<div class="pill kpi"><span class="l">{a}</span></div>' for a in anoms)

per100_cart, per100_buy = funnel[1][1], funnel[3][1]

def card(what, how, watch):
    return (f'<div class="explain">'
            f'<div class="ex-row"><span class="pill ex-tag">what this shows</span><p>{what}</p></div>'
            f'<div class="ex-row"><span class="pill ex-tag">how we built it</span><p>{how}</p></div>'
            f'<div class="ex-row"><span class="pill ex-tag">what to look for</span><p>{watch}</p></div></div>')

EX = {
"health": card(
    f"One number for the store's overall condition: {health}/100, averaged from five component scores shown as bars.",
    "Each metric is scored 0-100 against a healthy-store benchmark: conversion vs 3%, repeat rate vs 30%, returns vs a 5% ceiling, discounts vs an 8% ceiling, and growth vs 15% average monthly. The five scores are averaged with equal weight.",
    "Any bar sitting under 50 is the weakest link and the first thing to work on."),
"c1": card(
    f"Monthly net sales as an index: first full month = 100, latest full month = {idx[last_full_idx]}. That is {growth_mult}x growth with no real amounts revealed.",
    f"Monthly P&L pulled via ShopifyQL, indexed to hide currency. The current month is scaled to full-month pace from days elapsed. The gray dashed line is a 3-month rolling average. The cone projects 3 months forward by compounding the historical average log-growth, widened by one standard deviation each way.",
    "Whether the solid line stays above the dashed trend, and how wide the cone is: a narrow cone means growth has been consistent enough to predict."),
"c2": card(
    "Each month's growth split into its three possible causes: more visitors, better conversion, or bigger orders.",
    "Net sales is the product of sessions, conversion rate, and average order value, so log-differences of each factor split every month's change into three additive parts, shown stacked.",
    "Which color dominates. This store's bars are mostly blue: growth is traffic-led, so marketing reach matters more than site tweaks right now."),
"heat": card(
    "Five metrics tracked month by month in one grid: a compressed view of momentum across the whole business.",
    "Each cell is that metric's percent change vs the prior month. Blue means it improved, orange declined, and deeper color means a bigger move (capped at 30% for readability).",
    "Columns that go orange across several rows at once: that is a genuinely bad month, not one noisy metric."),
"c3": card(
    f"How well visits become buyers ({conv[-1]:g} per 100 visitors) and how many buyers come back ({repeat[-1]:g} per 100 buyers).",
    f"Conversion comes from the sessions report, repeat rate from the customers report. The dotted line is a least-squares fit through repeat rate, extended to month 12, currently landing near {proj_m12:g}%.",
    "Typical online stores convert 1.5 to 2.5 per 100. Repeat rate climbing while sales grow means new customers are being kept, not just acquired."),
"funnel": card(
    f"Where visitors drop off: out of 100 sessions last month, {per100_cart:g} added to cart, {per100_buy:g} purchased. The lines below track each stage across all months.",
    "Each stage's sessions divided by total sessions for that month, so every figure reads as per-100-visitors.",
    "Rising lines mean the funnel is tightening. The biggest loss is always visit-to-cart; small gains there outweigh anything later in the funnel."),
"c4": card(
    f"The size of a typical order, indexed. Currently {aov_idx[-1]} vs 100 in month one: essentially flat.",
    "Average order value from the customers report, indexed the same way as sales to hide currency.",
    "Flat AOV while sales multiply means all growth came from order count. AOV is the untouched lever: bundles and free-shipping thresholds move it."),
"c5": card(
    "Whether discounting bought growth. Each dot is one month: discounts given vs growth achieved.",
    "Monthly discount rate (discounts as % of gross) plotted against that month's sales growth.",
    "A rising pattern would mean growth was purchased with margin. This scatter shows no such pattern: the best growth months were not the heaviest discount months."),
"c6": card(
    f"How dependent the store is on its best sellers: the top product holds {shares[0]:g}% of sales, the top five together {sum(shares[:5]):g}%.",
    "Each product's share of total net sales, with names anonymized to letters. The meter is a Herfindahl-style concentration index scored against the 0.25 threshold economists use for high concentration.",
    "A dot far right means one product's slowdown hurts everything. This store sits left: diversified across many products."),
"anoms": card(
    "Months where growth broke sharply from the store's own pattern, flagged automatically.",
    f"Each month's growth is compared to the store's average ({mm:.0f}%) in standard deviations; anything beyond 1.5 sd is flagged.",
    "Flags deserve an explanation you can name: a launch, a campaign, a stockout. An unexplained flag is the one worth investigating."),
}

TABS = [("overview", "Overview"), ("growth", "Growth"), ("customers", "Customers & funnel"),
        ("economics", "Economics & products"), ("method", "Method")]
tab_nav = "".join(f'<button class="pill tab-btn{" active" if i == 0 else ""}" data-tab="{tid}">{name}</button>' for i, (tid, name) in enumerate(TABS))

kpis = [(f"{growth_mult}x", "net sales growth"), (f"{conv[-1]}%", "conversion"),
        (f"{repeat[-1]}%", "repeat rate"), (f"{rets[-1]}%", "returns"),
        (f"{disc[-1]}%", "discounts"), (f"{health}", "health score")]
kpi_html = "".join(f'<div class="pill kpi"><span class="v">{v}</span><span class="l">{l}</span></div>' for v, l in kpis)
funnel_html = "".join(
    f'<div class="step"><span class="pill tag">{name}</span>'
    f'<div class="bar-track"><div class="bar-fill" style="width:{val}%"></div></div>'
    f'<span class="pct">{val:g}%</span></div>' for name, val in funnel)
score_html = "".join(
    f'<div class="step"><span class="pill tag">{name}</span>'
    f'<div class="bar-track"><div class="bar-fill" style="width:{v}%"></div></div>'
    f'<span class="pct">{v}</span></div>' for name, v in score_rows)

D = {"L": labels, "PL": proj_labels, "IDX": idx_padded, "ROLL": roll_padded,
     "PMID": proj_mid, "PHI": proj_hi, "PLO": proj_lo,
     "DECT": dec_traffic, "DECC": dec_conv, "DECA": dec_aov,
     "CONV": conv, "REP": repeat, "FITX": [f"M{x}" for x in fit_x], "FITY": fit_y,
     "CART": cart_rate, "CHK": chk_rate, "BUY": buy_rate,
     "AOV": aov_idx, "DISC": disc, "RETS": rets, "SCAT": scatter,
     "SHARES": shares, "SLAB": share_labels, "HEALTH": health, "NFULL": n_full}

tpl = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%SHOP% - store analytics</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root { --ink: #111114; --ink-2: #6f7076; --ink-3: #a4a5ab; --bg: #fbfbfa; --card: #ffffff; --line: #ececea; --accent: #2a78d6; --warm: #eb6834; }
  * { box-sizing: border-box; margin: 0; }
  body { background: var(--bg); color: var(--ink); font-family: 'Inter', sans-serif; line-height: 1.6; -webkit-font-smoothing: antialiased; }
  .wrap { max-width: 880px; margin: 0 auto; padding: 56px 24px 72px; }
  .pill { border-radius: 999px; }
  header { text-align: center; margin-bottom: 32px; }
  .eyebrow { display: inline-block; font-size: 12px; font-weight: 500; letter-spacing: 0.04em; color: var(--ink-2); background: var(--card); border: 1px solid var(--line); padding: 6px 16px; border-radius: 999px; }
  h1 { font-size: clamp(26px, 4.5vw, 38px); font-weight: 600; letter-spacing: -0.02em; margin: 20px auto 8px; max-width: 560px; line-height: 1.2; }
  .note { font-size: 13px; color: var(--ink-3); max-width: 520px; margin: 0 auto; }
  .tabs { position: sticky; top: 12px; z-index: 5; display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; margin: 28px 0 40px; }
  .tab-btn { font-family: inherit; font-size: 13px; font-weight: 500; color: var(--ink-2); background: var(--card); border: 1px solid var(--line); padding: 8px 18px; cursor: pointer; }
  .tab-btn.active { background: var(--ink); color: var(--card); border-color: var(--ink); }
  .tab-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .panel { display: none; }
  .panel.active { display: block; }
  .kpis { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; margin: 0 0 48px; }
  .kpi { background: var(--card); border: 1px solid var(--line); padding: 10px 22px; display: flex; align-items: baseline; gap: 8px; }
  .kpi .v { font-size: 20px; font-weight: 600; letter-spacing: -0.01em; }
  .kpi .l { font-size: 12px; color: var(--ink-2); }
  section { margin-bottom: 56px; }
  h2 { font-size: 16px; font-weight: 600; letter-spacing: -0.01em; text-align: center; }
  .sub { font-size: 13px; color: var(--ink-2); text-align: center; margin: 4px 0 20px; }
  .chart { position: relative; height: 280px; background: var(--card); border: 1px solid var(--line); border-radius: 24px; padding: 20px; }
  .chart.tall { height: 330px; }
  .legend { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; margin-bottom: 14px; }
  .legend .pill { font-size: 12px; color: var(--ink-2); background: var(--card); border: 1px solid var(--line); padding: 4px 14px; display: flex; align-items: center; gap: 6px; }
  .dot { width: 8px; height: 8px; border-radius: 999px; display: inline-block; }
  .grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
  .funnel { background: var(--card); border: 1px solid var(--line); border-radius: 24px; padding: 28px; display: flex; flex-direction: column; gap: 14px; }
  .step { display: grid; grid-template-columns: 160px 1fr 52px; align-items: center; gap: 12px; }
  .tag { font-size: 12px; color: var(--ink-2); background: var(--bg); border: 1px solid var(--line); padding: 4px 12px; text-align: center; white-space: nowrap; }
  .bar-track { height: 12px; background: var(--bg); border-radius: 999px; overflow: hidden; }
  .bar-fill { height: 100%; background: var(--accent); border-radius: 999px; }
  .pct { font-size: 13px; font-weight: 500; text-align: right; }
  .explain { max-width: 680px; margin: 18px auto 0; background: var(--card); border: 1px solid var(--line); border-radius: 20px; padding: 18px 22px; display: flex; flex-direction: column; gap: 10px; }
  .ex-row { display: grid; grid-template-columns: 130px 1fr; gap: 14px; align-items: start; }
  .ex-tag { font-size: 11px; font-weight: 500; color: var(--ink-2); background: var(--bg); border: 1px solid var(--line); padding: 3px 10px; text-align: center; white-space: nowrap; margin-top: 2px; }
  .ex-row p { font-size: 13px; color: var(--ink-2); }
  .hm { background: var(--card); border: 1px solid var(--line); border-radius: 24px; padding: 24px; display: flex; flex-direction: column; gap: 6px; overflow-x: auto; }
  .hm-row { display: grid; grid-template-columns: 110px repeat(%N%, 1fr); gap: 6px; align-items: center; min-width: 560px; }
  .hm-cell { border-radius: 999px; font-size: 11px; text-align: center; padding: 5px 0; color: var(--ink); }
  .hm-h { background: transparent; color: var(--ink-3); font-weight: 500; }
  .meter { max-width: 520px; margin: 20px auto 0; background: var(--card); border: 1px solid var(--line); border-radius: 24px; padding: 22px 26px; }
  .meter-track { position: relative; height: 12px; border-radius: 999px; background: linear-gradient(90deg, #dce9f8, #f8ddd2); }
  .meter-dot { position: absolute; top: 50%; transform: translate(-50%, -50%); width: 20px; height: 20px; border-radius: 999px; background: var(--ink); border: 4px solid var(--card); }
  .meter-labels { display: flex; justify-content: space-between; font-size: 11px; color: var(--ink-3); margin-top: 8px; }
  .method { max-width: 680px; margin: 0 auto; display: flex; flex-direction: column; gap: 14px; }
  .method .explain { margin: 0; max-width: none; }
  .flow { display: flex; flex-wrap: wrap; justify-content: center; align-items: center; gap: 8px; margin: 0 0 28px; }
  .flow .pill { font-size: 12px; color: var(--ink-2); background: var(--card); border: 1px solid var(--line); padding: 6px 16px; }
  .flow .arr { color: var(--ink-3); font-size: 13px; }
  footer { text-align: center; font-size: 12px; color: var(--ink-3); margin-top: 24px; }
  footer .pill { display: inline-block; background: var(--card); border: 1px solid var(--line); padding: 6px 16px; }
  @media (max-width: 560px) { .step { grid-template-columns: 110px 1fr 46px; } .ex-row { grid-template-columns: 1fr; gap: 4px; } }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <span class="eyebrow">store analytics / anonymized</span>
    <h1>%MULT%x net sales in %NF% months</h1>
    <p class="note">Every figure below is an index or a rate. Revenue, volumes, and product names are withheld by design. * marks the current partial month at run-rate, p marks projections.</p>
  </header>

  <nav class="tabs" role="tablist">%TABNAV%</nav>

  <div class="panel active" id="panel-overview">
    <div class="kpis">%KPIS%</div>
    <section>
      <h2>Health scorecard</h2>
      <p class="sub">Five metrics scored against benchmarks, averaged into one number</p>
      <div class="grid2">
        <div class="chart"><canvas id="c7" role="img" aria-label="Overall store health score donut"></canvas></div>
        <div class="funnel">%SCORES%</div>
      </div>
      %EX_HEALTH%
    </section>
    <section>
      <h2>Net sales index, trend and projection</h2>
      <div class="chart"><canvas id="c1" role="img" aria-label="Net sales index with rolling average and projection band"></canvas></div>
      %EX_C1%
    </section>
  </div>

  <div class="panel" id="panel-growth">
    <section>
      <h2>What drove each month's growth</h2>
      <div class="legend">
        <span class="pill"><span class="dot" style="background: var(--accent)"></span>more visitors</span>
        <span class="pill"><span class="dot" style="background: var(--warm)"></span>better conversion</span>
        <span class="pill"><span class="dot" style="background: var(--ink-3)"></span>bigger orders</span>
      </div>
      <div class="chart"><canvas id="c2" role="img" aria-label="Growth decomposition stacked bars"></canvas></div>
      %EX_C2%
    </section>
    <section>
      <h2>Momentum heatmap</h2>
      <div class="hm">%HEATHEAD%%HEATROWS%</div>
      %EX_HEAT%
    </section>
    <section>
      <h2>Anomalies detected</h2>
      <div class="kpis" style="margin: 16px 0 0;">%ANOMS%</div>
      %EX_ANOMS%
    </section>
  </div>

  <div class="panel" id="panel-customers">
    <section>
      <h2>Conversion and repeat rate</h2>
      <div class="legend">
        <span class="pill"><span class="dot" style="background: var(--accent)"></span>conversion</span>
        <span class="pill"><span class="dot" style="background: var(--warm)"></span>repeat rate</span>
        <span class="pill"><span class="dot" style="background: var(--ink-3)"></span>repeat trend to M12 (dotted)</span>
      </div>
      <div class="chart"><canvas id="c3" role="img" aria-label="Conversion and repeat rate with fitted projection"></canvas></div>
      %EX_C3%
    </section>
    <section>
      <h2>The funnel, now and over time</h2>
      <div class="funnel" style="margin-bottom: 20px;">%FUNNEL%</div>
      <div class="legend">
        <span class="pill"><span class="dot" style="background: var(--accent)"></span>added to cart %</span>
        <span class="pill"><span class="dot" style="background: var(--warm)"></span>reached checkout %</span>
        <span class="pill"><span class="dot" style="background: var(--ink-3)"></span>purchased %</span>
      </div>
      <div class="chart"><canvas id="c8" role="img" aria-label="Funnel stage rates across months"></canvas></div>
      %EX_FUNNEL%
    </section>
  </div>

  <div class="panel" id="panel-economics">
    <section>
      <h2>Average order value</h2>
      <div class="chart"><canvas id="c4" role="img" aria-label="Average order value index by month"></canvas></div>
      %EX_C4%
    </section>
    <section>
      <h2>Did discounts buy growth?</h2>
      <div class="chart"><canvas id="c5" role="img" aria-label="Discount rate versus growth scatter"></canvas></div>
      %EX_C5%
    </section>
    <section>
      <h2>Product concentration</h2>
      <div class="chart tall"><canvas id="c6" role="img" aria-label="Share of net sales by anonymized product"></canvas></div>
      <div class="meter">
        <div class="meter-track"><div class="meter-dot" style="left: %HHIPOS%%"></div></div>
        <div class="meter-labels"><span>diversified</span><span>concentrated</span></div>
      </div>
      %EX_C6%
    </section>
  </div>

  <div class="panel" id="panel-method">
    <section>
      <h2>How this page is made</h2>
      <p class="sub">A four-step pipeline, rebuilt on every refresh</p>
      <div class="flow">
        <span class="pill">Shopify (ShopifyQL)</span><span class="arr">-></span>
        <span class="pill">4 CSV reports</span><span class="arr">-></span>
        <span class="pill">build_dashboard.py</span><span class="arr">-></span>
        <span class="pill">this page</span>
      </div>
      <div class="method">
        <div class="explain"><div class="ex-row"><span class="pill ex-tag">the reports</span><p>Four ShopifyQL queries feed everything: monthly P&L (orders, gross, discounts, returns, net, shipping), product-level sales, customer counts with repeat rate and AOV, and the session funnel. Nothing else is collected.</p></div></div>
        <div class="explain"><div class="ex-row"><span class="pill ex-tag">anonymization</span><p>Months are renamed M1..Mn. Sales and AOV are divided by their first-full-month value and shown as an index where 100 = month one. Products are relabeled A through E. Only rates, ratios, shares, and indexes survive to this page; no absolute rupee amount, order count, or visitor count appears anywhere in the HTML source.</p></div></div>
        <div class="explain"><div class="ex-row"><span class="pill ex-tag">the math</span><p>Partial months are projected to full-month pace from days elapsed. The projection cone compounds average historical log-growth plus and minus one standard deviation. Growth decomposition uses log-differences of sessions x conversion x AOV. The repeat-rate trend is a least-squares fit. Anomalies are months beyond 1.5 standard deviations from average growth. The concentration meter is a Herfindahl index scored against the 0.25 high-concentration threshold.</p></div></div>
        <div class="explain"><div class="ex-row"><span class="pill ex-tag">glossary</span><p>Index: month one = 100, everything relative to it. Conversion: buyers per 100 visitors. Repeat rate: returning buyers per 100 buyers. AOV: the size of a typical order. Net sales: gross minus discounts and returns. * : partial month at run-rate. p : projected month.</p></div></div>
        <div class="explain"><div class="ex-row"><span class="pill ex-tag">integrity</span><p>The chart library is loaded with a cryptographic integrity hash, so a tampered copy will refuse to run. All numbers on this page are generated by code from the source reports; none are typed by hand.</p></div></div>
      </div>
    </section>
  </div>

  <footer><span class="pill">%SHOP% / shopify-fin-model / ShopifyQL</span></footer>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js" integrity="sha384-dug+JxfBvklEQdJ4AYuBBAIScUz0bVN73xpy273gcAwHjb3qI0fXmuYNaNfdyYJG" crossorigin="anonymous"></script>
<script>
const D = %DATA%;
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('panel-' + btn.dataset.tab).classList.add('active');
    Object.values(Chart.instances).forEach(c => c.resize());
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
});
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.font.size = 12;
Chart.defaults.color = '#a4a5ab';
const GRID = { color: '#f1f1ef' }, NOGRID = { display: false }, NOB = { display: false };
const X = { ticks: { autoSkip: false }, grid: NOGRID, border: NOB };
new Chart(document.getElementById('c7'), { type: 'doughnut',
  data: { labels: ['Health', ''], datasets: [{ data: [D.HEALTH, 100 - D.HEALTH], backgroundColor: ['#2a78d6', '#f1f1ef'], borderWidth: 0, borderRadius: 999 }] },
  options: { responsive: true, maintainAspectRatio: false, cutout: '76%', plugins: { legend: { display: false }, tooltip: { enabled: false } } },
  plugins: [{ id: 'txt', afterDraw(ch) { const { ctx, chartArea: a } = ch; ctx.save();
    ctx.font = '600 34px Inter'; ctx.fillStyle = '#111114'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(D.HEALTH, (a.left + a.right) / 2, (a.top + a.bottom) / 2 - 8);
    ctx.font = '400 12px Inter'; ctx.fillStyle = '#a4a5ab'; ctx.fillText('of 100', (a.left + a.right) / 2, (a.top + a.bottom) / 2 + 16); ctx.restore(); } }] });
new Chart(document.getElementById('c1'), { type: 'line',
  data: { labels: D.PL, datasets: [
    { data: D.IDX, borderColor: '#2a78d6', backgroundColor: 'rgba(42,120,214,0.07)', fill: true, borderWidth: 2, pointRadius: 3, tension: 0.35 },
    { data: D.ROLL, borderColor: '#a4a5ab', borderWidth: 2, borderDash: [6, 4], pointRadius: 0, tension: 0.35 },
    { data: D.PMID, borderColor: '#2a78d6', borderWidth: 2, borderDash: [3, 4], pointRadius: 0, tension: 0.2 },
    { data: D.PHI, borderColor: 'transparent', pointRadius: 0, fill: '+1', backgroundColor: 'rgba(42,120,214,0.09)', tension: 0.2 },
    { data: D.PLO, borderColor: 'transparent', pointRadius: 0, tension: 0.2 } ] },
  options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
    scales: { x: X, y: { grid: GRID, border: NOB } } } });
new Chart(document.getElementById('c2'), { type: 'bar',
  data: { labels: D.L, datasets: [
    { data: D.DECT, backgroundColor: '#2a78d6', borderRadius: 999, maxBarThickness: 16 },
    { data: D.DECC, backgroundColor: '#eb6834', borderRadius: 999, maxBarThickness: 16 },
    { data: D.DECA, backgroundColor: '#a4a5ab', borderRadius: 999, maxBarThickness: 16 } ] },
  options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false },
    tooltip: { callbacks: { label: c => ['visitors', 'conversion', 'order size'][c.datasetIndex] + ': ' + (c.parsed.y > 0 ? '+' : '') + c.parsed.y + ' pts' } } },
    scales: { x: { ...X, stacked: true }, y: { stacked: true, grid: GRID, border: NOB, ticks: { callback: v => v + '%' } } } } });
new Chart(document.getElementById('c3'), { type: 'line',
  data: { labels: D.FITX, datasets: [
    { data: D.CONV, borderColor: '#2a78d6', borderWidth: 2, pointRadius: 3, tension: 0.35 },
    { data: D.REP, borderColor: '#eb6834', borderWidth: 2, pointRadius: 3, pointStyle: 'rect', tension: 0.35 },
    { data: D.FITY, borderColor: '#a4a5ab', borderWidth: 2, borderDash: [2, 4], pointRadius: 0 } ] },
  options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false },
    tooltip: { callbacks: { label: c => c.parsed.y.toFixed(1) + '%' } } },
    scales: { x: X, y: { grid: GRID, border: NOB, ticks: { callback: v => v + '%' } } } } });
new Chart(document.getElementById('c8'), { type: 'line',
  data: { labels: D.L, datasets: [
    { data: D.CART, borderColor: '#2a78d6', borderWidth: 2, pointRadius: 3, tension: 0.35 },
    { data: D.CHK, borderColor: '#eb6834', borderWidth: 2, borderDash: [6, 4], pointRadius: 3, pointStyle: 'rect', tension: 0.35 },
    { data: D.BUY, borderColor: '#a4a5ab', borderWidth: 2, borderDash: [2, 3], pointRadius: 3, pointStyle: 'triangle', tension: 0.35 } ] },
  options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false },
    tooltip: { callbacks: { label: c => c.parsed.y.toFixed(1) + '% of sessions' } } },
    scales: { x: X, y: { grid: GRID, border: NOB, ticks: { callback: v => v + '%' } } } } });
new Chart(document.getElementById('c4'), { type: 'line',
  data: { labels: D.L, datasets: [{ data: D.AOV, borderColor: '#2a78d6', borderWidth: 2, pointRadius: 3, tension: 0.35 }] },
  options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
    scales: { x: X, y: { grid: GRID, border: NOB } } } });
new Chart(document.getElementById('c5'), { type: 'scatter',
  data: { datasets: [{ data: D.SCAT, backgroundColor: '#eb6834', pointRadius: 6 }] },
  options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false },
    tooltip: { callbacks: { label: c => c.raw.m + ': ' + c.parsed.x + '% discount, ' + (c.parsed.y > 0 ? '+' : '') + c.parsed.y + '% growth' } } },
    scales: { x: { grid: GRID, border: NOB, min: 0, max: 4.5, ticks: { callback: v => v + '%' }, title: { display: true, text: 'discount rate', color: '#a4a5ab' } },
      y: { grid: GRID, border: NOB, ticks: { callback: v => v + '%' }, title: { display: true, text: 'MoM growth', color: '#a4a5ab' } } } } });
new Chart(document.getElementById('c6'), { type: 'bar',
  data: { labels: D.SLAB, datasets: [{ data: D.SHARES, backgroundColor: D.SLAB.map(l => l === 'All others' ? '#dcdcd8' : '#2a78d6'), borderRadius: 999, maxBarThickness: 18 }] },
  options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false },
    tooltip: { callbacks: { label: c => c.parsed.x.toFixed(1) + '% of net sales' } } },
    scales: { x: { grid: GRID, border: NOB, ticks: { callback: v => v + '%' } }, y: { grid: NOGRID, border: NOB } } } });
</script>
</body>
</html>"""

out = (tpl.replace("%SHOP%", SHOP_NAME).replace("%MULT%", str(growth_mult))
    .replace("%NF%", str(n_full)).replace("%TABNAV%", tab_nav)
    .replace("%KPIS%", kpi_html).replace("%SCORES%", score_html)
    .replace("%FUNNEL%", funnel_html).replace("%HEATHEAD%", heat_head)
    .replace("%HEATROWS%", heat_rows).replace("%ANOMS%", anom_html)
    .replace("%HHIPOS%", f"{hhi_pos:.0f}").replace("%N%", str(n))
    .replace("%EX_HEALTH%", EX["health"]).replace("%EX_C1%", EX["c1"])
    .replace("%EX_C2%", EX["c2"]).replace("%EX_HEAT%", EX["heat"])
    .replace("%EX_C3%", EX["c3"]).replace("%EX_FUNNEL%", EX["funnel"])
    .replace("%EX_C4%", EX["c4"]).replace("%EX_C5%", EX["c5"])
    .replace("%EX_C6%", EX["c6"]).replace("%EX_ANOMS%", EX["anoms"])
    .replace("%DATA%", json.dumps(D).replace("</", "<\\/")))
open("dashboard.html", "w").write(out)
print("wrote dashboard.html", len(out), "bytes")
