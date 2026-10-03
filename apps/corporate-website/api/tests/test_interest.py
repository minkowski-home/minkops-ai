import pytest
from fastapi.testclient import TestClient
from minkops_platform.interest_delivery import DeliveryError, InterestSubmission

from minkops_corporate_website_api import main


@pytest.fixture
def client(monkeypatch):
    main.app.state.interest_limiter = main.SlidingWindowLimiter()
    delivered = []

    async def fake_deliver(submission):
        delivered.append(submission)

    monkeypatch.setattr(main, "deliver_interest", fake_deliver)
    return TestClient(main.app), delivered


def valid_payload(**overrides):
    return {
        "name": "Alex Visitor",
        "email": "alex@example.com",
        "company": "Example Co",
        "interest": "operations",
        "message": "We need help with <reports>.",
        **overrides,
    }


def test_valid_submission_passes_validated_data_to_application_layer(client):
    test_client, delivered = client

    response = test_client.post("/api/interest", json=valid_payload())

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert delivered == [
        InterestSubmission(
            name="Alex Visitor",
            email="alex@example.com",
            company="Example Co",
            interest="operations",
            message="We need help with <reports>.",
        )
    ]


def test_invalid_fields_are_rejected_before_delivery(client):
    test_client, delivered = client

    response = test_client.post("/api/interest", json=valid_payload(email="not-an-email"))

    assert response.status_code == 422
    assert delivered == []


def test_honeypot_returns_quiet_acceptance_without_delivery(client):
    test_client, delivered = client

    response = test_client.post("/api/interest", json=valid_payload(website="bot.example"))

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert delivered == []


def test_delivery_failure_reports_safe_actionable_error(client, monkeypatch):
    test_client, _ = client

    async def fail(_submission):
        raise DeliveryError("private diagnostic")

    monkeypatch.setattr(main, "deliver_interest", fail)
    response = test_client.post("/api/interest", json=valid_payload())

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "We couldn't send your note yet. Please try again or email info@minkops.com."
    )
    assert "private diagnostic" not in response.text


def test_uncertain_delivery_tells_visitor_not_to_retry(client, monkeypatch):
    test_client, _ = client

    async def uncertain(_submission):
        raise DeliveryError("private diagnostic", ambiguous=True)

    monkeypatch.setattr(main, "deliver_interest", uncertain)
    response = test_client.post("/api/interest", json=valid_payload())

    assert response.status_code == 503
    assert "Please don't submit it again" in response.json()["detail"]
    assert "private diagnostic" not in response.text


def test_rate_limit_applies_before_validation_and_honeypot(client):
    test_client, delivered = client

    for _ in range(5):
        assert test_client.post("/api/interest", json=valid_payload(email="invalid")).status_code == 422
    limited = test_client.post("/api/interest", json=valid_payload(website="bot.example"))

    assert limited.status_code == 429
    assert delivered == []


def test_cors_allows_local_frontend_submission(client):
    test_client, _ = client

    response = test_client.options(
        "/api/interest",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_health_endpoint_is_transport_only():
    response = TestClient(main.app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "corporate-website"}
