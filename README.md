# Shopify Financial Model Pipeline

Pulls 4 reports from Shopify, stores them as CSV, and builds an Excel financial model with a live formula layer and cost assumptions.

## Reports used
1. Monthly P&L: orders, gross, discounts, returns, net, shipping, taxes, total
2. Product-level sales (top 30 by net sales)
3. Customers: total, returning, returning rate, AOV
4. Funnel: sessions, cart adds, checkout reached/completed, conversion

## ShopifyQL queries
```
FROM sales SHOW orders, gross_sales, discounts, returns, net_sales, shipping_charges, taxes, total_sales TIMESERIES month SINCE 2025-10-01 UNTIL today
FROM sales SHOW orders, gross_sales, discounts, returns, net_sales GROUP BY product_title SINCE 2025-10-01 UNTIL today ORDER BY net_sales DESC LIMIT 30
FROM sales SHOW customers, returning_customers, returning_customer_rate, average_order_value TIMESERIES month SINCE 2025-10-01 UNTIL today
FROM sessions SHOW sessions, sessions_with_cart_additions, sessions_that_reached_checkout, sessions_that_completed_checkout, conversion_rate TIMESERIES month SINCE 2025-10-01 UNTIL today
```

## Usage
1. Export the 4 queries from Shopify as CSV into `raw/` (headers must match the filenames in `raw/README.md`)
2. Set `SHOP_NAME` at the top of `build_model.py`
3. `pip install openpyxl pandas`
4. `python build_model.py`

Output: `<SHOP_NAME>_Financial_Model.xlsx` with data sheets, an Assumptions sheet (fill the yellow cells with real COGS, courier, packaging, gateway costs), a formula-driven monthly model, and an insights sheet.

Real store CSVs and generated xlsx files are gitignored.
