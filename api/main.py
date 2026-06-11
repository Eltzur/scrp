"""Israeli Price Comparison API."""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import health, catalog, search, product, basket, saved_baskets, favorites, freshness, coverage, promos

app = FastAPI(
    title="Israeli Price Comparison API",
    version="0.1.0",
    description=(
        "Search and compare grocery prices across Israeli supermarket chains "
        "(Shufersal, Rami Levy, Osher Ad). Data sourced from mandatory Price "
        "Transparency XML files published under the 2014 regulation."
    ),
)

_DEFAULT_ORIGINS = "http://localhost:5173,http://localhost:3000"
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("ALLOWED_ORIGINS", _DEFAULT_ORIGINS).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(catalog.router)
app.include_router(search.router)
app.include_router(product.router)
app.include_router(basket.router)
app.include_router(saved_baskets.router)
app.include_router(favorites.router)
app.include_router(freshness.router)
app.include_router(coverage.router)
app.include_router(promos.router)
