# SCRP – Supermarket Comparison & Price Scraper

**SCRP** is a python-based tool that scrapes, parses, and compares product prices and promotions from major supermarket chains in Israel. By fetching live price feeds directly from supermarket APIs, SCRP enables users to easily compare prices and find the best deals at nearby stores.

---

## Features

- **Automatic price scraping** from multiple Israeli supermarket chains (Shufersal, Rami Levi, etc.)
- **Product and promotion parsing** into a standardized format
- **Basket comparison:** find the cheapest store for your grocery list
- **Nearby store search** (optional, based on user location)
- **Export data** to CSV, JSON, or other formats

---

## Supported Supermarkets

- Shufersal
- Rami Levi
- [Add others as implemented in `/scraper/`]

---

## How It Works

1. **Select Supermarkets:** Choose which chains to fetch data from.
2. **Fetch Prices:** SCRP downloads official price lists (as required by Israeli law) from each chain.
3. **Parse & Normalize:** The raw data (CSV, XML, JSON) is converted into a unified product format.
4. **Compare:** Automatically compares your basket or selected products across available stores.
5. **Results:** View or export the cheapest options and detailed price breakdowns.

---

## Installation

### Prerequisites

- [Go (Golang)](https://golang.org/doc/install) 1.18+

### Build

Clone and build SCRP:

```bash
git clone https://github.com/Eltzur/scrp.git
cd scrp
go build -o scrp
