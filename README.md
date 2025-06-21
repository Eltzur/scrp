# SCRP – Supermarket Comparison & Price Scraper (Israel)

SCRP is a Python-based web application that scrapes, parses, and compares product prices and promotions from major supermarket chains in Israel. By collecting live price feeds directly from supermarket APIs, SCRP helps users compare prices and discover the most affordable nearby supermarket for their shopping basket.

---

## Features

- **Automatic price scraping** from multiple Israeli supermarket chains (Shufersal, Rami Levi, and others)
- **Product & promotion parsing** into a unified, easy-to-search format
- **Basket comparison** – instantly find the cheapest store for your chosen items
- **"Stores near me" search** (location-aware, optional)
- **User-friendly web interface** for input and results

---

## Supported Supermarkets

- Shufersal
- Rami Levi
- [List other supported supermarkets as implemented]

---

## How It Works

1. **Select supermarkets** or enable "all nearby."
2. **Enter your shopping basket** (manually or upload).
3. **SCRP fetches current price lists** from each chain’s public data feed.
4. **Data is parsed and normalized** into a unified product catalog.
5. **Compare**: Instantly see price comparisons for your basket across stores.
6. **View cheapest store(s) and savings** using a clear, interactive GUI.

---

## Installing & Running

### Prerequisites

- Python 3.8+
- `pip`, `venv`, and common Python libraries

### Setup

1. **Clone this repository:**

   ```bash
   git clone https://github.com/Eltzur/scrp.git
   cd scrp
