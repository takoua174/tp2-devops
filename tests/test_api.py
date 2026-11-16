import app.main as main


# ------------------------------------------------------------ health / items
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_items_returns_seed_data(client):
    r = client.get("/items")
    assert r.status_code == 200
    assert len(r.json()) == 3


def test_get_item_ok(client):
    r = client.get("/items/1")
    assert r.status_code == 200
    assert r.json()["name"] == "Keyboard"


def test_get_item_not_found(client):
    assert client.get("/items/999").status_code == 404


def test_get_item_invalid_id_type(client):
    assert client.get("/items/abc").status_code == 422


def test_create_item_ok(client):
    r = client.post("/items", json={"name": "Webcam", "price": 59.0, "stock": 7})
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == 4 and body["stock"] == 7
    assert client.get(f"/items/{body['id']}").status_code == 200


def test_create_item_default_stock_is_zero(client):
    r = client.post("/items", json={"name": "Cable", "price": 3.0})
    assert r.status_code == 201
    assert r.json()["stock"] == 0


def test_create_item_empty_name_rejected(client):
    assert client.post("/items", json={"name": "", "price": 5}).status_code == 422


def test_create_item_zero_price_rejected(client):
    assert client.post("/items", json={"name": "X", "price": 0}).status_code == 422


def test_create_item_negative_price_rejected(client):
    assert client.post("/items", json={"name": "X", "price": -1}).status_code == 422


def test_create_item_negative_stock_rejected(client):
    r = client.post("/items", json={"name": "X", "price": 1, "stock": -3})
    assert r.status_code == 422


def test_create_item_missing_field_rejected(client):
    assert client.post("/items", json={"name": "X"}).status_code == 422


def test_delete_item_ok(client):
    assert client.delete("/items/1").status_code == 204
    assert client.get("/items/1").status_code == 404


def test_delete_item_not_found(client):
    assert client.delete("/items/999").status_code == 404


# ------------------------------------------------------------------ checkout
def test_checkout_ok_decrements_stock(client):
    r = client.post("/checkout", json={"item_id": 1, "quantity": 2})
    assert r.status_code == 200
    assert r.json() == {"status": "paid", "item_id": 1, "quantity": 2, "total": 99.8}
    assert client.get("/items/1").json()["stock"] == 18


def test_checkout_exact_stock_boundary(client):
    r = client.post("/checkout", json={"item_id": 3, "quantity": 5})
    assert r.status_code == 200
    assert client.get("/items/3").json()["stock"] == 0


def test_checkout_one_over_stock_rejected(client):
    r = client.post("/checkout", json={"item_id": 3, "quantity": 6})
    assert r.status_code == 409


def test_checkout_unknown_item(client):
    r = client.post("/checkout", json={"item_id": 999, "quantity": 1})
    assert r.status_code == 404


def test_checkout_zero_quantity_rejected(client):
    assert client.post("/checkout", json={"item_id": 1, "quantity": 0}).status_code == 422


def test_checkout_negative_quantity_rejected(client):
    assert client.post("/checkout", json={"item_id": 1, "quantity": -2}).status_code == 422


def test_checkout_applies_simulated_delay(client, monkeypatch):
    delays = []

    async def fake_sleep(seconds):
        delays.append(seconds)

    monkeypatch.setenv("CHECKOUT_MIN_DELAY", "0.1")
    monkeypatch.setenv("CHECKOUT_MAX_DELAY", "0.8")
    monkeypatch.setattr(main.asyncio, "sleep", fake_sleep)
    client.post("/checkout", json={"item_id": 1, "quantity": 1})
    assert len(delays) == 1
    assert 0.1 <= delays[0] <= 0.8


# --------------------------------------------------------------------- flaky
def test_flaky_returns_500_when_roll_below_rate(client, monkeypatch):
    monkeypatch.setattr(main, "_roll", lambda: 0.1)
    r = client.get("/flaky")
    assert r.status_code == 500


def test_flaky_returns_200_when_roll_above_rate(client, monkeypatch):
    monkeypatch.setattr(main, "_roll", lambda: 0.9)
    assert client.get("/flaky").status_code == 200


def test_flaky_boundary_roll_equals_rate_succeeds(client, monkeypatch):
    monkeypatch.setattr(main, "_roll", lambda: 0.3)
    assert client.get("/flaky").status_code == 200


def test_flaky_error_rate_configurable(client, monkeypatch):
    monkeypatch.setenv("FLAKY_ERROR_RATE", "1.0")
    assert client.get("/flaky").status_code == 500
    monkeypatch.setenv("FLAKY_ERROR_RATE", "0")
    assert client.get("/flaky").status_code == 200


def test_roll_is_in_unit_interval():
    assert 0 <= main._roll() < 1


# ------------------------------------------------------------------- metrics
def test_metrics_format_and_content_type(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "http_requests_total" in r.text
    assert "http_request_duration_seconds_bucket" in r.text


def test_metrics_records_route_template_not_raw_path(client):
    client.get("/items/1")
    text = client.get("/metrics").text
    assert 'path="/items/{item_id}"' in text
    assert 'path="/items/1"' not in text


def test_metrics_records_error_status(client, monkeypatch):
    monkeypatch.setattr(main, "_roll", lambda: 0.0)
    client.get("/flaky")
    text = client.get("/metrics").text
    assert 'path="/flaky"' in text and 'status="500"' in text


def test_metrics_unknown_route_labelled_unmatched(client):
    assert client.get("/does-not-exist").status_code == 404
    assert 'path="unmatched"' in client.get("/metrics").text
