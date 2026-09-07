"""Declarative adapter for the public Books to Scrape demonstration site."""

from price_monitor.scrapers.spec import SelectorRule, SiteSpec

BOOKS_TO_SCRAPE_V1 = SiteSpec(
    key="books_to_scrape",
    revision="1",
    allowed_hosts=("books.toscrape.com",),
    product_container="article.product_page",
    name=(
        SelectorRule(selector=".product_main h1"),
        SelectorRule(selector="h1"),
    ),
    price=(SelectorRule(selector=".product_main .price_color"),),
    availability=(SelectorRule(selector=".product_main .availability"),),
    external_product_id=(SelectorRule(selector="table.table-striped tr:first-of-type td"),),
    currency_symbol_map={"£": "GBP"},
    in_stock_terms=("in stock",),
    out_of_stock_terms=("out of stock", "unavailable"),
    preorder_terms=("pre-order", "preorder"),
)

# Short alias used by simple registry code and examples.
SPEC = BOOKS_TO_SCRAPE_V1
