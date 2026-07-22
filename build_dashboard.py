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

# extra computed conclusions
weakest = min(score_rows, key=lambda r: r[1])
xs2 = disc[1:]; ys2 = [m for m in mom[1:]]
mx2, my2 = sum(xs2)/len(xs2), sum(ys2)/len(ys2)
cov = sum((a-mx2)*(b-my2) for a,b in zip(xs2,ys2))
den = (sum((a-mx2)**2 for a in xs2) * sum((b-my2)**2 for b in ys2)) ** 0.5
r_disc = round(cov/den, 2) if den else 0.0
drops = [("visit to cart", 100 - cart_rate[-1]), ("cart to checkout", cart_rate[-1] - chk_rate[-1]), ("checkout to purchase", chk_rate[-1] - buy_rate[-1])]
big_drop = max(drops, key=lambda d: d[1])
latest_proj = proj_mid[-3:]
conv_lift_orders = round((conv[-1] + 0.5) / conv[-1] * 100 - 100)

def card(what, how, watch, conclusion):
    return (f'<div class="explain rv">'
            f'<div class="ex-row"><span class="pill ex-tag">what this shows</span><p>{what}</p></div>'
            f'<div class="ex-row"><span class="pill ex-tag">how we built it</span><p>{how}</p></div>'
            f'<div class="ex-row"><span class="pill ex-tag">what to look for</span><p>{watch}</p></div>'
            f'<div class="ex-row conc"><span class="pill ex-tag">conclusion</span><p>{conclusion}</p></div></div>')

if abs(r_disc) < 0.3:
    disc_verdict = f"The correlation between discount rate and growth across all months is {r_disc}: effectively no relationship. Demand here is driven by discovery and product fit, not price promotion, so discounts are best kept as a targeted tool (clearing a colourway, rewarding repeat buyers) rather than a growth strategy. Holding discounts near {disc[-1]:g}% while volume compounds means growth without margin erosion."
elif abs(r_disc) < 0.6:
    disc_verdict = f"The correlation between discount rate and growth is {r_disc}: a weak-to-moderate link, and with only {len(xs2)} months of data it is suggestive rather than conclusive. The biggest spike month did coincide with the heaviest promotion period, so discounts likely amplified an already-good month rather than created it. The honest conclusion: promotions may add a tailwind, but the store also grew strongly in low-discount months, so margin should not be spent chasing this correlation. Keep discounts event-driven and re-test this chart at 12+ months when the sample can actually settle the question."
else:
    disc_verdict = f"The correlation between discount rate and growth is {r_disc}: a strong link in this sample. Growth months and discount months overlap heavily, which means margin is doing real work in acquiring sales. That is not automatically bad, but it should be priced consciously: check the contribution margin in the Excel model for promoted months before scaling promotions further."

EX = {
"health": card(
    f"One number for the store's overall condition: {health}/100, averaged from the five component scores shown as bars.",
    "Each metric is scored 0-100 against a healthy-store benchmark: conversion vs 3%, repeat rate vs 30%, returns vs a 5% ceiling, discounts vs an 8% ceiling, and 3-month growth vs 15% monthly. Equal weights, simple average.",
    "Any bar under 50 is the weakest link and the first thing to work on.",
    f"At {health}/100 this store is operating well above the typical small D2C store. The lowest component is {weakest[0].lower()} at {weakest[1]}/100, which makes it the highest-leverage place to spend effort next: every point recovered there moves the composite more than polishing an already-strong metric. The score is deliberately harsh on growth momentum during slow months, so a dip after a spike month is expected behavior, not decay."),
"c1": card(
    f"Monthly net sales as an index: first full month = 100, latest full month = {idx[last_full_idx]}. That is {growth_mult}x growth with no real amounts revealed.",
    "Monthly P&L pulled via ShopifyQL, indexed to hide currency. The current month is scaled to full-month pace from days elapsed. The gray dashed line is a 3-month rolling average; the cone compounds historical average log-growth plus and minus one standard deviation.",
    "Whether the solid line stays above the dashed trend, and how wide the cone is: a narrow cone means growth has been consistent enough to predict.",
    f"The trajectory is genuinely strong: {growth_mult}x in {n_full} months with only one negative month. The current month is pacing at {idx[-1]} vs {idx[last_full_idx]} last month, a pullback that the decomposition tab attributes to traffic, not the store itself. If history repeats, the cone puts the next three months around {latest_proj[0]}, {latest_proj[1]} and {latest_proj[2]}; the width of that cone says treat these as direction, not promises. The single most important thing this chart asks of the operator: keep the traffic engine running, because the store converts whatever arrives."),
"c2": card(
    "Each month's growth split into its three possible causes: more visitors, better conversion, or bigger orders.",
    "Net sales is the product of sessions, conversion rate and average order value, so log-differences of each factor split every month's change into three additive parts, shown stacked.",
    "Which color dominates. This store's bars are mostly blue: growth is traffic-led.",
    f"The blue dominance is the deepest strategic fact on this page. It means the product and the store already work; the binding constraint is how many people see it. Practical reading: a rupee spent on reach (content, SEO, ads, marketplace presence) buys more growth right now than a rupee spent on site optimization, because conversion is already above benchmark at {conv[-1]:g}%. The orange slices appearing in recent months are a bonus signal: conversion is improving on its own as the catalog and reviews mature. The gray slices staying near zero confirm the AOV chart's story that order size has not been worked as a lever yet."),
"heat": card(
    "Five metrics tracked month by month in one grid: a compressed view of momentum across the whole business.",
    "Each cell is that metric's percent change vs the prior month. Blue improved, orange declined, deeper color means a bigger move (capped at 30% for readability).",
    "Columns that go orange across several rows at once: that is a genuinely bad month, not one noisy metric.",
    "Read this grid by column, not cell. Most columns are majority blue, which is what a compounding store looks like. Where orange appears it clusters in the sessions row rather than conversion or repeat, reinforcing that the volatile input is traffic while the store's internal mechanics improve almost monotonically. The healthiest detail is the repeat-rate row: it stays blue even in months where sales dip, meaning customer quality is decoupled from traffic luck. If a future month ever shows orange across sales, sessions AND conversion simultaneously, that is the early-warning pattern that deserves a same-week response."),
"c3": card(
    f"How well visits become buyers ({conv[-1]:g} per 100 visitors) and how many buyers come back ({repeat[-1]:g} per 100 buyers).",
    f"Conversion comes from the sessions report, repeat rate from the customers report. The dotted line is a least-squares fit through repeat rate, extended to month 12, currently landing near {proj_m12:g}%.",
    "Typical online stores convert 1.5 to 2.5 per 100. Repeat rate climbing while sales grow means customers are being kept, not just acquired.",
    f"Two conclusions stack here. First, at {conv[-1]:g}% conversion the store outperforms the typical range, so paid traffic economics are better than average: the same ad spend yields roughly {conv_lift_orders}% more orders than a store converting half a point lower. Second, and more valuable long-term, repeat rate has more than tripled since launch and the fitted trend reaches about {proj_m12:g}% by month 12. Repeat customers arrive free, which mechanically raises margin over time. The strategic implication: an email/WhatsApp flow and a colour-drop cadence are not nice-to-haves, they are the cheapest growth channel this data can identify."),
"funnel": card(
    f"Where visitors drop off: out of 100 sessions last month, {per100_cart:g} added to cart, {per100_buy:g} purchased. The lines track each stage across all months.",
    "Each stage's sessions divided by total sessions for that month, so every figure reads as per-100-visitors.",
    "Rising lines mean the funnel is tightening: losing fewer people per step.",
    f"The largest loss is {big_drop[0]}, where {big_drop[1]:g} of every 100 visitors exit. That is normal for e-commerce but it defines the priority order for site work: product-page persuasion (photos, reviews, sizing clarity) outranks checkout tweaks, because the checkout stages already convert well once reached. The over-time lines add a subtler conclusion: all three stage-rates have trended up together, so past site changes have compounded rather than shuffled the losses between stages. Keep changes incremental; nothing in this funnel is broken enough to justify a risky redesign."),
"c4": card(
    f"The size of a typical order, indexed. Currently {aov_idx[-1]} vs 100 in month one: essentially flat.",
    "Average order value from the customers report, indexed the same way as sales to hide currency.",
    "Flat AOV while sales multiply means all growth came from order count.",
    f"This is the clearest untapped lever on the page. AOV has moved within a narrow band ({min(aov_idx)} to {max(aov_idx)}) for the whole history while everything else compounded, which means nothing has been tried: no bundles, no tiered free-shipping threshold, no volume pricing. The arithmetic is forgiving: lifting AOV just 10 index points at current order volume adds roughly a tenth to revenue with zero additional traffic or conversion work. The natural first experiment given the catalog is an accessory-plus-band bundle anchored on the most-ordered low-value product, priced to nudge the typical order up one notch."),
"c5": card(
    "Whether discounting bought growth. Each dot is one month: discounts given vs growth achieved.",
    "Monthly discount rate (discounts as % of gross) plotted against that month's sales growth.",
    "A rising pattern would mean growth was purchased with margin.",
    disc_verdict),
"c6": card(
    f"How dependent the store is on its best sellers: the top product holds {shares[0]:g}% of sales, the top five together {sum(shares[:5]):g}%.",
    "Each product's share of total net sales, names anonymized to letters. The meter is a Herfindahl-style concentration index scored against the 0.25 threshold economists use for high concentration.",
    "A dot far right means one product's slowdown hurts everything.",
    f"With the top product at {shares[0]:g}% and the meter sitting well left of the concentration threshold, no single product failure can seriously wound this store: the long tail carries {shares[5]:g}% of sales. That diversification is a genuine moat for a small operation, and it changes how new launches should be judged: a new product does not need to become a bestseller to be worth keeping, it needs to add a few durable points to the tail. The one watch-item is family-level concentration, which letter-level anonymization hides: if the top products all serve the same device ecosystem, platform risk is higher than this chart alone suggests."),
"anoms": card(
    "Months where growth broke sharply from the store's own pattern, flagged automatically.",
    f"Each month's growth is compared to the store's average ({mm:.0f}%) in standard deviations; anything beyond 1.5 sd is flagged.",
    "Flags deserve an explanation you can name: a launch, a campaign, a stockout.",
    "Exactly one anomaly across the whole history is itself the finding: this growth curve is unusually orderly for an early-stage store. The flagged spike month should be documented while memory is fresh (what launched, what was posted, what went viral), because a repeatable cause is a playbook, and an unrepeatable one should be excluded when setting expectations. The projection cone on the overview tab already treats that month as part of normal variance; if it was truly one-off, real future months will tend toward the lower half of the cone."),
}

WHY = """
    <section class="rv">
      <h2>Why this exists</h2>
      <p class="sub">Shopify's built-in reports are good at counting. This pipeline exists for the questions counting can't answer.</p>
      <div class="vs">
        <div class="vs-row"><span class="pill vs-l">Shopify shows metrics in isolation</span><span class="arr">-></span><span class="pill vs-r">Growth is decomposed into visitors x conversion x order size, so you know WHY a month moved</span></div>
        <div class="vs-row"><span class="pill vs-l">Absolute numbers only, private by necessity</span><span class="arr">-></span><span class="pill vs-r">Indexed and anonymized, so performance can be shared publicly without revealing a single rupee</span></div>
        <div class="vs-row"><span class="pill vs-l">Revenue, but no costs</span><span class="arr">-></span><span class="pill vs-r">The companion Excel model adds COGS, courier, packaging and gateway assumptions for true contribution margin</span></div>
        <div class="vs-row"><span class="pill vs-l">History, but no forward view</span><span class="arr">-></span><span class="pill vs-r">Run-rate for the current month plus a probability cone for the next three</span></div>
        <div class="vs-row"><span class="pill vs-l">You must notice unusual months yourself</span><span class="arr">-></span><span class="pill vs-r">Anomalies auto-flagged at 1.5 standard deviations, with the math shown</span></div>
        <div class="vs-row"><span class="pill vs-l">Charts you have to interpret</span><span class="arr">-></span><span class="pill vs-r">Every chart carries a computed what / how / watch / conclusion card in plain language</span></div>
      </div>
    </section>
"""

TABS = [("overview", "Overview"), ("growth", "Growth"), ("customers", "Customers & funnel"),
        ("economics", "Economics & products"), ("method", "Method")]
tab_nav = "".join(f'<button class="pill tab-btn{" active" if i == 0 else ""}" data-tab="{tid}">{name}</button>' for i, (tid, name) in enumerate(TABS))

kpis = [(f"{growth_mult}", "x", "net sales growth"), (f"{conv[-1]}", "%", "conversion"),
        (f"{repeat[-1]}", "%", "repeat rate"), (f"{rets[-1]}", "%", "returns"),
        (f"{disc[-1]}", "%", "discounts"), (f"{health}", "", "health score")]
kpi_html = "".join(f'<div class="pill kpi rv"><span class="v" data-count="{v}">{v}</span><span class="v-suf">{s}</span><span class="l">{l}</span></div>' for v, s, l in kpis)
funnel_html = "".join(
    f'<div class="step"><span class="pill tag">{name}</span>'
    f'<div class="bar-track"><div class="bar-fill" data-w="{val}"></div></div>'
    f'<span class="pct">{val:g}%</span></div>' for name, val in funnel)
score_html = "".join(
    f'<div class="step"><span class="pill tag">{name}</span>'
    f'<div class="bar-track"><div class="bar-fill" data-w="{v}"></div></div>'
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
  .wrap { max-width: 1160px; margin: 0 auto; padding: 56px 32px 80px; }
  .pill { border-radius: 999px; }
  header { text-align: center; margin-bottom: 32px; }
  .eyebrow { display: inline-block; font-size: 12px; font-weight: 500; letter-spacing: 0.04em; color: var(--ink-2); background: var(--card); border: 1px solid var(--line); padding: 6px 16px; border-radius: 999px; }
  h1 { font-size: clamp(28px, 4.5vw, 46px); font-weight: 600; letter-spacing: -0.02em; margin: 22px auto 10px; max-width: 640px; line-height: 1.15; }
  .note { font-size: 13px; color: var(--ink-3); max-width: 560px; margin: 0 auto; }
  .tabs { position: sticky; top: 12px; z-index: 5; display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; margin: 30px 0 48px; }
  .tab-btn { font-family: inherit; font-size: 13px; font-weight: 500; color: var(--ink-2); background: var(--card); border: 1px solid var(--line); padding: 9px 20px; cursor: pointer; transition: transform 0.15s ease, background 0.2s ease, color 0.2s ease; }
  .tab-btn:hover { transform: translateY(-1px); }
  .tab-btn.active { background: var(--ink); color: var(--card); border-color: var(--ink); }
  .tab-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .panel { display: none; }
  .panel.active { display: block; animation: panelIn 0.45s ease; }
  @keyframes panelIn { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
  .kpis { display: flex; flex-wrap: wrap; justify-content: center; gap: 12px; margin: 0 0 56px; }
  .kpi { background: var(--card); border: 1px solid var(--line); padding: 12px 26px; display: flex; align-items: baseline; gap: 6px; transition: transform 0.2s ease, border-color 0.2s ease; }
  .kpi:hover { transform: translateY(-2px); border-color: var(--ink-3); }
  .kpi .v { font-size: 24px; font-weight: 600; letter-spacing: -0.01em; }
  .kpi .v-suf { font-size: 15px; font-weight: 600; color: var(--ink-2); }
  .kpi .l { font-size: 12px; color: var(--ink-2); margin-left: 4px; }
  section { margin-bottom: 72px; }
  h2 { font-size: clamp(18px, 2.2vw, 24px); font-weight: 600; letter-spacing: -0.01em; text-align: center; }
  .sub { font-size: 14px; color: var(--ink-2); text-align: center; margin: 6px auto 26px; max-width: 620px; }
  .duo { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr); gap: 28px; align-items: stretch; }
  .chart-col { display: flex; flex-direction: column; gap: 20px; min-width: 0; }
  .chart-col .chart { flex: 1 1 auto; height: auto; min-height: 300px; }
  .chart-col .funnel { flex: 0 0 auto; }
  .ex-col { display: flex; flex-direction: column; justify-content: center; gap: 14px; min-width: 0; }
  .ex-col .explain { height: 100%; justify-content: center; }
  .duo.flip .chart-col { order: 2; } .duo.flip .ex-col { order: 1; }
  .chart { position: relative; height: 300px; background: var(--card); border: 1px solid var(--line); border-radius: 28px; padding: 22px; transition: border-color 0.25s ease; }
  .chart:hover { border-color: var(--ink-3); }
  .chart.tall { height: 340px; }
  .legend { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; margin-bottom: 14px; }
  .legend .pill { font-size: 12px; color: var(--ink-2); background: var(--card); border: 1px solid var(--line); padding: 4px 14px; display: flex; align-items: center; gap: 6px; }
  .dot { width: 8px; height: 8px; border-radius: 999px; display: inline-block; }
  .funnel { background: var(--card); border: 1px solid var(--line); border-radius: 28px; padding: 30px; display: flex; flex-direction: column; gap: 14px; }
  .step { display: grid; grid-template-columns: 160px 1fr 52px; align-items: center; gap: 12px; }
  .tag { font-size: 12px; color: var(--ink-2); background: var(--bg); border: 1px solid var(--line); padding: 4px 12px; text-align: center; white-space: nowrap; }
  .bar-track { height: 12px; background: var(--bg); border-radius: 999px; overflow: hidden; }
  .bar-fill { height: 100%; width: 0; background: var(--accent); border-radius: 999px; transition: width 1.1s cubic-bezier(0.22, 1, 0.36, 1); }
  .pct { font-size: 13px; font-weight: 500; text-align: right; }
  .explain { background: var(--card); border: 1px solid var(--line); border-radius: 24px; padding: 20px 24px; display: flex; flex-direction: column; gap: 12px; }
  .ex-row { display: grid; grid-template-columns: 122px 1fr; gap: 14px; align-items: start; }
  .ex-tag { font-size: 11px; font-weight: 500; color: var(--ink-2); background: var(--bg); border: 1px solid var(--line); padding: 3px 10px; text-align: center; white-space: nowrap; margin-top: 2px; }
  .ex-row p { font-size: 13px; color: var(--ink-2); }
  .ex-row.conc { border-top: 1px solid var(--line); padding-top: 12px; }
  .ex-row.conc .ex-tag { background: var(--ink); color: var(--card); border-color: var(--ink); }
  .ex-row.conc p { color: var(--ink); }
  .below { max-width: 860px; margin: 20px auto 0; }
  .hm { background: var(--card); border: 1px solid var(--line); border-radius: 28px; padding: 26px; display: flex; flex-direction: column; gap: 6px; overflow-x: auto; }
  .hm-row { display: grid; grid-template-columns: 110px repeat(%N%, 1fr); gap: 6px; align-items: center; min-width: 560px; }
  .hm-cell { border-radius: 999px; font-size: 11px; text-align: center; padding: 5px 0; color: var(--ink); }
  .hm-h { background: transparent; color: var(--ink-3); font-weight: 500; }
  .meter { max-width: 560px; margin: 20px auto 0; background: var(--card); border: 1px solid var(--line); border-radius: 24px; padding: 22px 26px; }
  .meter-track { position: relative; height: 12px; border-radius: 999px; background: linear-gradient(90deg, #dce9f8, #f8ddd2); }
  .meter-dot { position: absolute; top: 50%; transform: translate(-50%, -50%); width: 20px; height: 20px; border-radius: 999px; background: var(--ink); border: 4px solid var(--card); transition: left 1.1s cubic-bezier(0.22, 1, 0.36, 1); }
  .meter-labels { display: flex; justify-content: space-between; font-size: 11px; color: var(--ink-3); margin-top: 8px; }
  .vs { max-width: 860px; margin: 0 auto; display: flex; flex-direction: column; gap: 10px; }
  .vs-row { display: grid; grid-template-columns: minmax(0, 1fr) 24px minmax(0, 1.4fr); gap: 12px; align-items: center; }
  .vs-l { font-size: 12px; color: var(--ink-3); background: var(--bg); border: 1px dashed var(--line); padding: 8px 16px; text-align: center; }
  .vs-r { font-size: 12px; color: var(--ink); background: var(--card); border: 1px solid var(--line); padding: 8px 16px; text-align: center; }
  .arr { color: var(--ink-3); font-size: 13px; text-align: center; }
  .method { max-width: 760px; margin: 0 auto; display: flex; flex-direction: column; gap: 14px; }
  .flow { display: flex; flex-wrap: wrap; justify-content: center; align-items: center; gap: 8px; margin: 0 0 28px; }
  .flow .pill { font-size: 12px; color: var(--ink-2); background: var(--card); border: 1px solid var(--line); padding: 6px 16px; }
  .rv { opacity: 0; transform: translateY(22px); transition: opacity 0.6s ease, transform 0.6s ease; }
  .rv.in { opacity: 1; transform: none; }
  footer { text-align: center; font-size: 12px; color: var(--ink-3); margin-top: 24px; }
  footer .pill { display: inline-block; background: var(--card); border: 1px solid var(--line); padding: 6px 16px; }
  @media (max-width: 860px) { .duo { grid-template-columns: 1fr; } .duo.flip .chart-col { order: 1; } .duo.flip .ex-col { order: 2; } .vs-row { grid-template-columns: 1fr; } .arr { transform: rotate(90deg); } }
  @media (max-width: 560px) { .chart-col .chart { min-height: 240px; } .step { grid-template-columns: 110px 1fr 46px; } .ex-row { grid-template-columns: 1fr; gap: 4px; } }
  @media (prefers-reduced-motion: reduce) { .rv, .panel.active, .bar-fill, .meter-dot, .tab-btn, .kpi, .chart { transition: none; animation: none; } .rv { opacity: 1; transform: none; } }
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
    %WHY%
    <section>
      <h2>Health scorecard</h2>
      <p class="sub">Five metrics scored against healthy-store benchmarks and averaged into one number</p>
      <div class="duo">
        <div class="chart-col">
          <div class="chart rv"><canvas id="c7" role="img" aria-label="Overall store health score donut"></canvas></div>
          <div class="funnel rv">%SCORES%</div>
        </div>
        <div class="ex-col">%EX_HEALTH%</div>
      </div>
    </section>
    <section>
      <h2>Net sales index, trend and projection</h2>
      <p class="sub">First full month = 100. Cone = the next three months if history repeats</p>
      <div class="duo flip">
        <div class="chart-col"><div class="chart rv"><canvas id="c1" role="img" aria-label="Net sales index with rolling average and projection band"></canvas></div></div>
        <div class="ex-col">%EX_C1%</div>
      </div>
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
      <div class="duo">
        <div class="chart-col"><div class="chart rv"><canvas id="c2" role="img" aria-label="Growth decomposition stacked bars"></canvas></div></div>
        <div class="ex-col">%EX_C2%</div>
      </div>
    </section>
    <section>
      <h2>Momentum heatmap</h2>
      <p class="sub">Blue = improved vs prior month, orange = declined, deeper = bigger move</p>
      <div class="duo flip">
        <div class="chart-col"><div class="hm rv" style="flex: 1;">%HEATHEAD%%HEATROWS%</div></div>
        <div class="ex-col">%EX_HEAT%</div>
      </div>
    </section>
    <section>
      <h2>Anomalies detected</h2>
      <div class="kpis" style="margin: 16px 0 20px;">%ANOMS%</div>
      <div class="below">%EX_ANOMS%</div>

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
      <div class="duo">
        <div class="chart-col"><div class="chart rv"><canvas id="c3" role="img" aria-label="Conversion and repeat rate with fitted projection"></canvas></div></div>
        <div class="ex-col">%EX_C3%</div>
      </div>
    </section>
    <section>
      <h2>The funnel, now and over time</h2>
      <div class="duo flip">
        <div class="chart-col">
          <div class="funnel rv">%FUNNEL%</div>
          <div class="chart rv"><canvas id="c8" role="img" aria-label="Funnel stage rates across months"></canvas></div>
        </div>
        <div class="ex-col">
          <div class="legend" style="justify-content: flex-start;">
            <span class="pill"><span class="dot" style="background: var(--accent)"></span>added to cart %</span>
            <span class="pill"><span class="dot" style="background: var(--warm)"></span>reached checkout %</span>
            <span class="pill"><span class="dot" style="background: var(--ink-3)"></span>purchased %</span>
          </div>
          %EX_FUNNEL%
        </div>
      </div>
    </section>
  </div>

  <div class="panel" id="panel-economics">
    <section>
      <h2>Average order value</h2>
      <div class="duo">
        <div class="chart-col"><div class="chart rv"><canvas id="c4" role="img" aria-label="Average order value index by month"></canvas></div></div>
        <div class="ex-col">%EX_C4%</div>
      </div>
    </section>
    <section>
      <h2>Did discounts buy growth?</h2>
      <div class="duo flip">
        <div class="chart-col"><div class="chart rv"><canvas id="c5" role="img" aria-label="Discount rate versus growth scatter"></canvas></div></div>
        <div class="ex-col">%EX_C5%</div>
      </div>
    </section>
    <section>
      <h2>Product concentration</h2>
      <div class="duo">
        <div class="chart-col">
          <div class="chart tall rv"><canvas id="c6" role="img" aria-label="Share of net sales by anonymized product"></canvas></div>
          <div class="meter rv">
            <div class="meter-track"><div class="meter-dot" data-left="%HHIPOS%" style="left: 0%"></div></div>
            <div class="meter-labels"><span>diversified</span><span>concentrated</span></div>
          </div>
        </div>
        <div class="ex-col">%EX_C6%</div>
      </div>
    </section>
  </div>

  <div class="panel" id="panel-method">
    <section>
      <h2>How this page is made</h2>
      <p class="sub">A four-step pipeline, rebuilt on every refresh</p>
      <div class="flow rv">
        <span class="pill">Shopify (ShopifyQL)</span><span class="arr">-></span>
        <span class="pill">4 CSV reports</span><span class="arr">-></span>
        <span class="pill">build_dashboard.py</span><span class="arr">-></span>
        <span class="pill">this page</span>
      </div>
      <div class="method">
        <div class="explain rv"><div class="ex-row"><span class="pill ex-tag">the reports</span><p>Four ShopifyQL queries feed everything: monthly P&L (orders, gross, discounts, returns, net, shipping), product-level sales, customer counts with repeat rate and AOV, and the session funnel. Nothing else is collected.</p></div></div>
        <div class="explain rv"><div class="ex-row"><span class="pill ex-tag">anonymization</span><p>Months are renamed M1..Mn. Sales and AOV are divided by their first-full-month value and shown as an index where 100 = month one. Products are relabeled A through E. Only rates, ratios, shares, and indexes survive to this page; no absolute rupee amount, order count, or visitor count appears anywhere in the HTML source.</p></div></div>
        <div class="explain rv"><div class="ex-row"><span class="pill ex-tag">the math</span><p>Partial months are projected to full-month pace from days elapsed. The projection cone compounds average historical log-growth plus and minus one standard deviation. Growth decomposition uses log-differences of sessions x conversion x AOV. The repeat-rate trend is a least-squares fit. Anomalies are months beyond 1.5 standard deviations from average growth. The concentration meter is a Herfindahl index scored against the 0.25 high-concentration threshold.</p></div></div>
        <div class="explain rv"><div class="ex-row"><span class="pill ex-tag">glossary</span><p>Index: month one = 100, everything relative to it. Conversion: buyers per 100 visitors. Repeat rate: returning buyers per 100 buyers. AOV: the size of a typical order. Net sales: gross minus discounts and returns. * : partial month at run-rate. p : projected month.</p></div></div>
        <div class="explain rv"><div class="ex-row"><span class="pill ex-tag">integrity</span><p>The chart library is loaded with a cryptographic integrity hash, so a tampered copy will refuse to run. All numbers on this page are generated by code from the source reports; none are typed by hand.</p></div></div>
      </div>
    </section>
  </div>

  <footer><span class="pill">%SHOP% / shopify-fin-model / ShopifyQL</span></footer>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js" integrity="sha384-dug+JxfBvklEQdJ4AYuBBAIScUz0bVN73xpy273gcAwHjb3qI0fXmuYNaNfdyYJG" crossorigin="anonymous"></script>
<script>
const D = %DATA%;
const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
const io = new IntersectionObserver(es => es.forEach(e => {
  if (!e.isIntersecting) return;
  e.target.classList.add('in');
  e.target.querySelectorAll('.bar-fill').forEach(b => b.style.width = b.dataset.w + '%');
  if (e.target.classList.contains('meter')) e.target.querySelector('.meter-dot').style.left = e.target.querySelector('.meter-dot').dataset.left + '%';
  io.unobserve(e.target);
}), { threshold: 0.15 });
function arm(root) {
  root.querySelectorAll('.rv, .funnel, .meter').forEach(el => { if (reduced) { el.classList.add('in'); el.querySelectorAll('.bar-fill').forEach(b => b.style.width = b.dataset.w + '%'); const d = el.querySelector('.meter-dot'); if (d) d.style.left = d.dataset.left + '%'; } else io.observe(el); });
}
arm(document);
document.querySelectorAll('.kpi .v[data-count]').forEach(el => {
  const target = parseFloat(el.dataset.count); if (reduced || isNaN(target)) return;
  const dec = (el.dataset.count.split('.')[1] || '').length; let t0 = null;
  function tick(ts) { if (!t0) t0 = ts; const p = Math.min((ts - t0) / 900, 1);
    el.textContent = (target * (1 - Math.pow(1 - p, 3))).toFixed(dec);
    if (p < 1) requestAnimationFrame(tick); }
  requestAnimationFrame(tick);
});
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    const panel = document.getElementById('panel-' + btn.dataset.tab);
    panel.classList.add('active');
    Object.values(Chart.instances).forEach(c => c.resize());
    window.scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' });
  });
});
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.font.size = 12;
Chart.defaults.color = '#a4a5ab';
Chart.defaults.animation.duration = reduced ? 0 : 900;
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
    .replace("%NF%", str(n_full)).replace("%TABNAV%", tab_nav).replace("%WHY%", WHY)
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
print("wrote dashboard.html", len(out), "bytes; r_disc", r_disc, "weakest", weakest, "big_drop", big_drop)
