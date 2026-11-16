"""Catalog microservice (FastAPI) exposing Prometheus metrics.

Special endpoints for the SRE part of the TP:
  - POST /checkout : simulated slow processing
  - GET  /flaky    : intermittent HTTP 500 errors
  - GET  /metrics  : Prometheus exposition format
"""
import asyncio
import os
import random
import time

from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field

app = FastAPI(title="Catalog Service", version="1.0.0")

# ---------------------------------------------------------------- metrics
REQUESTS = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "path", "status"]
)
LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    # 0.2 s bucket is required to compute the latency SLO (p95 <= 200 ms)
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1, 2.5, 5),
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    path = route.path if route else "unmatched"  # avoids label cardinality explosion
    LATENCY.labels(request.method, path).observe(time.perf_counter() - start)
    REQUESTS.labels(request.method, path, str(response.status_code)).inc()
    return response


# ---------------------------------------------------------------- models
class ItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    price: float = Field(gt=0)
    stock: int = Field(default=0, ge=0)


class CheckoutIn(BaseModel):
    item_id: int
    quantity: int = Field(ge=1)


# ---------------------------------------------------------------- storage
ITEMS: dict[int, dict] = {}
_next_id = 1


def reset_store() -> None:
    """(Re)initialise the in-memory catalog with seed data."""
    global _next_id
    ITEMS.clear()
    ITEMS.update(
        {
            1: {"id": 1, "name": "Keyboard", "price": 49.9, "stock": 20},
            2: {"id": 2, "name": "Mouse", "price": 19.5, "stock": 50},
            3: {"id": 3, "name": "Monitor", "price": 189.0, "stock": 5},
        }
    )
    _next_id = 4


reset_store()


def _roll() -> float:
    """Random draw in [0, 1) - isolated so tests can control it."""
    return random.random()


# ---------------------------------------------------------------- endpoints
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/items")
async def list_items():
    return list(ITEMS.values())


@app.get("/items/{item_id}")
async def get_item(item_id: int):
    if item_id not in ITEMS:
        raise HTTPException(status_code=404, detail="Item not found")
    return ITEMS[item_id]


@app.post("/items", status_code=201)
async def create_item(item: ItemIn):
    global _next_id
    new = {"id": _next_id, **item.model_dump()}
    ITEMS[_next_id] = new
    _next_id += 1
    return new


@app.delete("/items/{item_id}", status_code=204)
async def delete_item(item_id: int):
    if item_id not in ITEMS:
        raise HTTPException(status_code=404, detail="Item not found")
    del ITEMS[item_id]


@app.post("/checkout")
async def checkout(order: CheckoutIn):
    """Simulated slow payment processing (delay configurable via env)."""
    low = float(os.getenv("CHECKOUT_MIN_DELAY", "0.1"))
    high = float(os.getenv("CHECKOUT_MAX_DELAY", "0.8"))
    await asyncio.sleep(random.uniform(low, high))

    item = ITEMS.get(order.item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    if order.quantity > item["stock"]:
        raise HTTPException(status_code=409, detail="Insufficient stock")
    item["stock"] -= order.quantity
    return {
        "status": "paid",
        "item_id": item["id"],
        "quantity": order.quantity,
        "total": round(item["price"] * order.quantity, 2),
    }


@app.get("/flaky")
async def flaky():
    """Fails with HTTP 500 with probability FLAKY_ERROR_RATE (default 30 %)."""
    rate = float(os.getenv("FLAKY_ERROR_RATE", "0.3"))
    if _roll() < rate:
        raise HTTPException(status_code=500, detail="Simulated intermittent failure")
    return {"status": "ok"}
