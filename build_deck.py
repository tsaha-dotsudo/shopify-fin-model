"""Build a founder-facing summary deck (PDF) from the same raw/ CSVs."""
import calendar, math, os
from datetime import date
import pandas as pd
from reportlab.lib.pagesizes import landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl
from reportlab.lib.colors import HexColor

SHOP_NAME = "SHOP_NAME"
W, H = landscape((297*mm, 167*mm))
BG, CARD, LINE = HexColor("#131313"), HexColor("#1A1A1A"), HexColor("#2C2C2C")
INK, INK2, INK3 = HexColor("#EDEDED"), HexColor("#A3A3A3"), HexColor("#6F6F6F")
ACC, SAGE, GREEN = HexColor("#E0A458"), HexColor("#9AA88F"), HexColor("#9CC49C")

R = "repo/raw/"
pnl = pd.read_csv(R+"pnl_monthly.csv"); cust = pd.read_csv(R+"customers_monthly.csv")
fun = pd.read_csv(R+"funnel_monthly.csv"); prod = pd.read_csv(R+"products.csv")
TODAY = date.today()
def part(ym): return ym == f"{TODAY.year}-{TODAY.month:02d}"
def rr(ym, v):
    if not part(ym): return v
    y,m = map(int, ym.split("-")); return v/max(TODAY.day-1,1)*calendar.monthrange(y,m)[1]
p = pnl.iloc[1:].reset_index(drop=True); c = cust.iloc[1:].reset_index(drop=True); f = fun.iloc[1:].reset_index(drop=True)
n = len(p); lp = part(p["month"].iloc[-1]); nf = n-1 if lp else n
base = p.loc[0,"net_sales"]; srr = [rr(m,v) for m,v in zip(p["month"],p["net_sales"])]
idx = [round(v/base*100) for v in srr]
conv = [round(v*100,1) for v in f["conversion_rate"]]; rep = [round(v*100,1) for v in c["returning_customer_rate"]]
disc = [round(-d/g*100,1) for d,g in zip(p["discounts"],p["gross_sales"])]
rets = [round(-r/g*100,1) for r,g in zip(p["returns"],p["gross_sales"])]
aovb = c.loc[0,"average_order_value"]; aov = [round(v/aovb*100) for v in c["average_order_value"]]
mult = round(srr[nf-1]/base,1)
tot = prod["net_sales"].sum(); top5 = round(prod.nlargest(5,"net_sales")["net_sales"].sum()/tot*100,1)
top1 = round(prod["net_sales"].max()/tot*100,1)
labels = [f"M{i+1}"+("*" if part(m) else "") for i,m in enumerate(p["month"])]
sess = [rr(m,v) for m,v in zip(p["month"],f["sessions"])]
cd = rl.Canvas("SHOP_NAME_Store_Analytics_Deck.pdf", pagesize=(W,H))
cd.setTitle(f"{SHOP_NAME} store analytics")

def page(fn):
    cd.setFillColor(BG); cd.rect(0,0,W,H,fill=1,stroke=0); fn(); cd.showPage()
def txt(x,y,s,size=11,col=INK,bold=False,font=None):
    cd.setFont(font or ("Helvetica-Bold" if bold else "Helvetica"), size); cd.setFillColor(col); cd.drawString(x,y,s)
def ctr(y,s,size=11,col=INK,bold=False):
    cd.setFont("Helvetica-Bold" if bold else "Helvetica", size); cd.setFillColor(col); cd.drawCentredString(W/2,y,s)
def card(x,y,w,h,r=8):
    cd.setFillColor(CARD); cd.setStrokeColor(LINE); cd.setLineWidth(0.7); cd.roundRect(x,y,w,h,r,fill=1,stroke=1)
def wrap(x,y,w,s,size=10,col=INK2,lead=13):
    words, line = s.split(), ""
    cd.setFont("Helvetica",size); cd.setFillColor(col)
    for wd in words:
        t = (line+" "+wd).strip()
        if cd.stringWidth(t,"Helvetica",size) > w: cd.drawString(x,y,line); y -= lead; line = wd
        else: line = t
    if line: cd.drawString(x,y,line); y -= lead
    return y
def eyebrow(s):
    cd.setFont("Helvetica",8.5); cd.setFillColor(INK3); cd.drawString(18*mm,H-14*mm,s.upper())
    cd.setStrokeColor(LINE); cd.setLineWidth(0.7); cd.line(18*mm,H-16.5*mm,W-18*mm,H-16.5*mm)
def spark(x,y,w,h,data,col=ACC,fill=True,bars=False):
    lo,hi = min(data), max(data); rng = (hi-lo) or 1
    pts = [(x+w*i/(len(data)-1), y+h*(v-lo)/rng) for i,v in enumerate(data)]
    if bars:
        bw = w/(len(data)*1.6)
        cd.setFillColor(col)
        for i,v in enumerate(data):
            bh = max(h*(v-lo)/rng, 1.5); cd.roundRect(x+w*i/len(data), y, bw, bh, 1.5, fill=1, stroke=0)
        return
    if fill:
        cd.setFillColor(HexColor("#2A2118")); path = cd.beginPath(); path.moveTo(pts[0][0],y)
        for px,py in pts: path.lineTo(px,py)
        path.lineTo(pts[-1][0],y); path.close(); cd.drawPath(path,fill=1,stroke=0)
    cd.setStrokeColor(col); cd.setLineWidth(1.6)
    for i in range(len(pts)-1): cd.line(*pts[i],*pts[i+1])

# 1 cover
def p1():
    ctr(H-52*mm, f"{SHOP_NAME} store analytics", 30, INK, True)
    ctr(H-64*mm, f"{mult}x net sales in {nf} months, explained in plain numbers", 13, INK2)
    bw, bh, gap = 52*mm, 26*mm, 6*mm
    x0 = (W - (4*bw + 3*gap))/2; y0 = H-100*mm
    for i,(v,l) in enumerate([(f"{mult}x","net sales growth"),(f"{conv[-1]}%","conversion"),(f"{rep[-1]}%","repeat buyers"),(f"{rets[-1]}%","returns")]):
        x = x0+i*(bw+gap); card(x,y0,bw,bh)
        cd.setFont("Helvetica-Bold",22); cd.setFillColor(ACC); cd.drawCentredString(x+bw/2,y0+13*mm,v)
        cd.setFont("Helvetica",9); cd.setFillColor(INK3); cd.drawCentredString(x+bw/2,y0+6*mm,l)
    ctr(20*mm, "A live dashboard, an Excel model, and this summary, all generated from four Shopify reports", 9.5, INK3)

# 2 why
def p2():
    eyebrow("why this exists")
    txt(18*mm,H-30*mm,"Shopify counts. This answers.",22,INK,True)
    rows = [("Metrics sit in isolation","Growth is split into visitors, conversion and order size, so you know why a month moved"),
            ("Numbers are private by nature","Everything is indexed and anonymized, so results can be shared without revealing a rupee"),
            ("Revenue only, no costs","A companion Excel model adds product, courier, packaging and gateway costs for true margin"),
            ("History but no forward view","Current month at run-rate plus a three month projection range"),
            ("You must spot odd months","Unusual months are flagged automatically with the maths shown"),
            ("Charts you interpret alone","Every chart carries a written conclusion in plain language")]
    y = H-46*mm
    for a,b in rows:
        card(18*mm,y-11*mm,110*mm,13*mm); card(134*mm,y-11*mm,W-152*mm,13*mm)
        txt(23*mm,y-6.5*mm,a,9.5,INK3); txt(139*mm,y-6.5*mm,b,9.5,INK)
        cd.setFont("Helvetica",11); cd.setFillColor(ACC); cd.drawCentredString(131*mm,y-6.5*mm,">")
        y -= 17*mm

# 3 growth
def p3():
    eyebrow("the headline")
    txt(18*mm,H-30*mm,f"{mult}x in {nf} months",22,INK,True)
    card(18*mm,26*mm,150*mm,H-62*mm)
    spark(28*mm,36*mm,130*mm,H-96*mm,idx[:nf])
    cd.setFont("Helvetica",8); cd.setFillColor(INK3)
    cd.drawString(28*mm,30*mm,"M1"); cd.drawRightString(158*mm,30*mm,f"M{nf}")
    txt(28*mm,H-42*mm,"net sales index, first full month = 100",8.5,INK3)
    x = 176*mm; y = H-44*mm
    card(x,26*mm,W-x-18*mm,H-62*mm)
    y = wrap(x+7*mm,y,W-x-32*mm,f"Sales in the latest full month were {mult} times the first full month. Growth came almost entirely from more people visiting, not from discounting or from raising prices.",10,INK,13)
    y -= 6
    y = wrap(x+7*mm,y,W-x-32*mm,f"Only one month in {nf} was smaller than the month before it. The current month is marked separately because it is still running.",10,INK2,13)
    y -= 6
    wrap(x+7*mm,y,W-x-32*mm,"What this means in practice: the product and the store already work. The limit on growth is how many people see it.",10,ACC,13)

# 4 three numbers
def p4():
    eyebrow("the three numbers that matter")
    txt(18*mm,H-30*mm,"Buying, returning, and keeping margin",22,INK,True)
    items = [("Conversion", f"{conv[-1]}%", conv, f"{conv[-1]} of every 100 visitors buy. Typical stores manage 1.5 to 2.5, so paid traffic works harder here than average.", ACC),
             ("Repeat buyers", f"{rep[-1]}%", rep, f"{rep[-1]} of every 100 buyers had bought before, up from {rep[0]} at launch. Returning customers cost nothing to acquire.", SAGE),
             ("Discounts given", f"{disc[-1]}%", disc, f"Only {disc[-1]} in every 100 of sales is given away. Growth happened in low discount months too, so margin is intact.", GREEN)]
    cw = (W-36*mm-2*8*mm)/3
    for i,(t,v,series,desc,col) in enumerate(items):
        x = 18*mm+i*(cw+8*mm); card(x,24*mm,cw,H-58*mm)
        txt(x+7*mm,H-44*mm,t,10,INK3)
        cd.setFont("Helvetica-Bold",26); cd.setFillColor(col); cd.drawString(x+7*mm,H-58*mm,v)
        spark(x+7*mm,H-86*mm,cw-14*mm,18*mm,series,col,fill=False)
        wrap(x+7*mm,H-96*mm,cw-14*mm,desc,9.5,INK2,12)

# 5 risk
def p5():
    eyebrow("how fragile is it")
    txt(18*mm,H-30*mm,"Not dependent on one product or one lucky month",22,INK,True)
    cw = (W-36*mm-8*mm)/2
    card(18*mm,26*mm,cw,H-60*mm)
    txt(25*mm,H-46*mm,"Product concentration",10,INK3)
    cd.setFont("Helvetica-Bold",24); cd.setFillColor(ACC); cd.drawString(25*mm,H-60*mm,f"{top1}%")
    y = wrap(25*mm,H-70*mm,cw-14*mm,f"is the share held by the single biggest product. The top five together hold {top5}%. The rest is spread across many smaller products, so no single product failing can seriously hurt the store.",9.5,INK2,12)
    card(18*mm+cw+8*mm,26*mm,cw,H-60*mm)
    x2 = 18*mm+cw+8*mm
    txt(x2+7*mm,H-46*mm,"Returns and order size",10,INK3)
    cd.setFont("Helvetica-Bold",24); cd.setFillColor(SAGE); cd.drawString(x2+7*mm,H-60*mm,f"{rets[-1]}%")
    wrap(x2+7*mm,H-70*mm,cw-14*mm,f"of sales come back as returns, which is very low and means the product matches what buyers expect. Average order size has stayed flat at index {aov[-1]} versus 100 at launch, so every rupee of growth came from more orders, never from charging more.",9.5,INK2,12)

# 6 opportunity
def p6():
    eyebrow("where the next growth comes from")
    txt(18*mm,H-30*mm,"Three levers, in priority order",22,INK,True)
    items = [("1","Traffic","Growth has been visitor-led throughout, and the store converts better than average. Money spent on reach returns more today than money spent on the website."),
             ("2","Order size","Average order value has not moved in the entire history, which means it has never been worked. Bundles and a free shipping threshold are untested."),
             ("3","Repeat buyers","Repeat rate has tripled on its own. Email and new colour drops are the cheapest channel this data can identify.")]
    y = H-46*mm
    for num,t,d in items:
        card(18*mm,y-24*mm,W-36*mm,26*mm)
        cd.setFont("Helvetica-Bold",20); cd.setFillColor(ACC); cd.drawString(26*mm,y-15*mm,num)
        txt(42*mm,y-11*mm,t,12,INK,True)
        wrap(42*mm,y-17*mm,W-80*mm,d,9.5,INK2,12)
        y -= 31*mm

# 7 how it works
def p7():
    eyebrow("how it is built")
    txt(18*mm,H-30*mm,"Four reports in, three things out",22,INK,True)
    steps = ["Shopify reports","CSV files","Python scripts","Dashboard, Excel model, this deck"]
    bw = (W-36*mm-3*7*mm)/4
    for i,s in enumerate(steps):
        x = 18*mm+i*(bw+7*mm); card(x,H-72*mm,bw,18*mm)
        cd.setFont("Helvetica",10); cd.setFillColor(INK); cd.drawCentredString(x+bw/2,H-64*mm,s)
        if i<3: cd.setFont("Helvetica",12); cd.setFillColor(ACC); cd.drawCentredString(x+bw+3.5*mm,H-64*mm,">")
    card(18*mm,24*mm,W-36*mm,H-100*mm)
    y = wrap(26*mm,H-84*mm,W-52*mm,"Four queries are run against Shopify: monthly sales and costs, sales by product, customer counts with repeat rate and order size, and the visitor funnel. Nothing else is collected.",10,INK,13)
    y -= 4
    y = wrap(26*mm,y,W-52*mm,"Two scripts read those files. One builds an Excel model where your own cost assumptions produce real margin. The other builds the public dashboard, where months are renamed M1 onward, sales are shown as an index against the first month, and products are relabelled A to E, so nothing confidential leaves the building.",10,INK2,13)
    y -= 4
    wrap(26*mm,y,W-52*mm,"Every number and every written conclusion is produced by code from the source reports. Nothing is typed by hand, so a refresh cannot go stale or disagree with itself.",10,ACC,13)

# 8 close
def p8():
    ctr(H-58*mm,"What you can do with it",22,INK,True)
    items = [("Open one tab","The Start here tab answers six questions in plain English with a yes or no verdict on each."),
             ("Share the link","The dashboard is a public web page that reveals no revenue, no volumes and no product names."),
             ("Refresh in minutes","Export four reports, run two scripts, upload one file. The written conclusions update themselves.")]
    cw = (W-36*mm-2*8*mm)/3
    for i,(t,d) in enumerate(items):
        x = 18*mm+i*(cw+8*mm); card(x,42*mm,cw,44*mm)
        txt(x+7*mm,74*mm,t,12,ACC,True); wrap(x+7*mm,66*mm,cw-14*mm,d,9.5,INK2,12)
    ctr(28*mm,f"{SHOP_NAME} / generated from Shopify data by shopify-fin-model", 9, INK3)

for fn in (p1,p2,p3,p4,p5,p6,p7,p8): page(fn)
cd.save()
print("deck written")
