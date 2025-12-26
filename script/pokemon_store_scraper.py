"""
Scrape the Pokémon Card official event search results and export the list of
authorized stores to a CSV spreadsheet.

Usage example:
    python script/pokemon_store_scraper.py \
        --url "https://www.pokemon-card.com/event/search/?keyword=..." \
        --output stores.csv

Notes
-----
* Run a search on the official site first, then pass the results page URL.
* Pagination is followed automatically when a "next" link is present.
* The scraper tries multiple selectors to adapt to minor HTML changes. If no
  rows are found, re-run with ``--save-html`` to inspect the downloaded page and
  adjust the selectors.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from typing import Iterable, List, Optional

import requests
from bs4 import BeautifulSoup


@dataclass
class StoreRow:
    name: str
    address: str
    phone: str
    homepage: Optional[str] = None

    def to_csv_row(self) -> List[str]:
        return [self.name, self.address, self.phone, self.homepage or ""]


def clean_text(text: str) -> str:
    return " ".join(text.split())


def extract_store_rows(soup: BeautifulSoup) -> List[StoreRow]:
    selectors = [
        "li.shopList__item",
        "li.shoplist__item",
        "div.shopListBox__item",
        "div.shoplist__item",
        "li.event-shop",
    ]

    rows: List[StoreRow] = []
    for selector in selectors:
        for node in soup.select(selector):
            name = clean_text(node.select_one(".shop-name, .shopName, .shoplist__name, .ttl").get_text()) if node.select_one(
                ".shop-name, .shopName, .shoplist__name, .ttl"
            ) else ""
            address = clean_text(node.select_one(".shop-address, .adress, .address").get_text()) if node.select_one(
                ".shop-address, .adress, .address"
            ) else ""
            phone = clean_text(node.select_one(".shop-tel, .tel, .phone").get_text()) if node.select_one(
                ".shop-tel, .tel, .phone"
            ) else ""
            homepage_node = node.select_one("a[href]")
            homepage = homepage_node["href"] if homepage_node else None
            if name or address or phone:
                rows.append(StoreRow(name=name, address=address, phone=phone, homepage=homepage))

        if rows:
            break

    if rows:
        return rows

    for tr in soup.select("table tr"):
        cells = [clean_text(td.get_text()) for td in tr.find_all(["td", "th"])]
        if len(cells) >= 3 and any(cells):
            homepage = None
            link = tr.find("a", href=True)
            if link:
                homepage = link["href"]
            rows.append(StoreRow(name=cells[0], address=cells[1], phone=cells[2], homepage=homepage))

    return rows


def find_next_page(soup: BeautifulSoup, current_url: str) -> Optional[str]:
    link = soup.find("a", attrs={"rel": "next"})
    if not link:
        link_texts = {"次のページ", "次へ", "next", "Next"}
        for anchor in soup.find_all("a", href=True):
            if clean_text(anchor.get_text()) in link_texts:
                link = anchor
                break

    if link and link.get("href"):
        return requests.compat.urljoin(current_url, link["href"])
    return None


def fetch_page(url: str) -> BeautifulSoup:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; pokemon-store-scraper/1.0)"}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def scrape_stores(start_url: str, save_html: Optional[str] = None) -> Iterable[StoreRow]:
    url = start_url
    while url:
        soup = fetch_page(url)
        if save_html:
            with open(save_html, "w", encoding="utf-8") as fp:
                fp.write(soup.prettify())
        for row in extract_store_rows(soup):
            yield row
        url = find_next_page(soup, url)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Event search result URL from pokemon-card.com")
    parser.add_argument("--output", default="pokemon_stores.csv", help="CSV file path to write")
    parser.add_argument(
        "--save-html",
        dest="save_html",
        default=None,
        help="Optional path to save the first downloaded HTML for debugging selectors",
    )
    return parser.parse_args(argv)


def write_csv(rows: Iterable[StoreRow], output: str) -> None:
    with open(output, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["name", "address", "phone", "homepage"])
        for row in rows:
            writer.writerow(row.to_csv_row())


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        store_rows = list(scrape_stores(args.url, save_html=args.save_html))
    except requests.HTTPError as exc:
        sys.stderr.write(f"Failed to fetch {args.url}: {exc}\n")
        return 1
    except requests.RequestException as exc:
        sys.stderr.write(f"Request error: {exc}\n")
        return 1

    if not store_rows:
        sys.stderr.write("No stores found. Try using --save-html to inspect the page.\n")
        return 2

    write_csv(store_rows, args.output)
    print(f"Saved {len(store_rows)} stores to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
