# Procfile — Railway process types
# web:  API service (api-super.xxl.co.il backend)
# cron: scraper-cron service (nightly price scrape at 01:00 UTC)
# fetch_off (OpenFoodFacts enrichment) is intentionally NOT defined
# here — abandoned in session 8c due to poor Israeli barcode coverage.
# The script exists in scraper/fetch_off.py for archaeology only.
web: gunicorn -k uvicorn.workers.UvicornWorker api.main:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
cron: python -m scraper.cron_main
