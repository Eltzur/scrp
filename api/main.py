"""Israeli Price Comparison API."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import health, catalog, search, product

app = FastAPI(
    title="Israeli Price Comparison API",
    version="0.1.0",
    description=(
        "Search and compare grocery prices across Israeli supermarket chains "
        "(Shufersal, Rami Levy, Osher Ad). Data sourced from mandatory Price "
        "Transparency XML files published under the 2014 regulation."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten for production
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(catalog.router)
app.include_router(search.router)
app.include_router(product.router)
