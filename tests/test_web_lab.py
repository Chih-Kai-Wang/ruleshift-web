from fastapi.testclient import TestClient

from ruleshift.web_lab import Lab, create_app, verify_snapshot


def test_http_cache_publication_and_commit_race():
    client = TestClient(create_app())
    first = client.get("/site/policies/discount")
    assert first.status_code == 200
    p1, etag1 = first.json(), first.headers["etag"]
    assert first.headers["cache-control"] == "public, max-age=120"
    assert client.get("/site/policies/discount", headers={"If-None-Match": etag1}).status_code == 304

    unrelated = client.post("/research/publish", json={"scope": "shipping", "rule": {"free_threshold": 80}})
    assert unrelated.status_code == 200
    assert client.get("/site/policies/discount", headers={"If-None-Match": etag1}).status_code == 304

    changed = client.post("/research/publish", json={"scope": "discount", "rule": {"eligible": False, "percent": 0}})
    assert changed.status_code == 200
    p2 = client.get("/site/policies/discount", headers={"If-None-Match": etag1})
    assert p2.status_code == 200 and p2.headers["etag"] != etag1
    stale = client.post("/site/purchases", json={"expected_policy_revision": p1["revision"]})
    assert stale.status_code == 409 and stale.json()["error"] == "policy_revision_changed"
    blocked = client.post("/site/purchases", json={"expected_policy_revision": p2.json()["revision"]})
    assert blocked.status_code == 409 and blocked.json()["error"] == "policy_block"
    assert client.get("/research/snapshot").json()["state"]["purchases"] == []

    # A successful revalidation is not a guarantee at commit time.
    client.post("/research/publish", json={"scope": "discount", "rule": {"eligible": True, "percent": 5}})
    raced = client.post("/site/purchases", json={"expected_policy_revision": p2.json()["revision"]})
    assert raced.status_code == 409 and raced.json()["error"] == "policy_revision_changed"
    p3 = client.get("/site/policies/discount").json()
    accepted = client.post("/site/purchases", json={"expected_policy_revision": p3["revision"]})
    assert accepted.status_code == 201 and accepted.json()["purchase"]["paid"] == 95
    assert client.get("/research/replay").json()["verified"]


def test_reversion_and_invalid_publication_do_not_mutate_state():
    client = TestClient(create_app())
    original = client.get("/site/policies/discount")
    etag = original.headers["etag"]
    assert client.post("/research/publish", json={"scope": "discount", "rule": {"eligible": False, "percent": 0}}).status_code == 200
    assert client.post("/research/publish", json={"scope": "discount", "rule": {"eligible": True, "percent": 10}}).status_code == 200
    assert client.get("/site/policies/discount", headers={"If-None-Match": f"W/{etag}"}).status_code == 304
    before = client.get("/research/snapshot").json()["state"]
    invalid = client.post("/research/publish", json={"scope": "discount", "rule": {"eligible": True, "percent": 101}})
    assert invalid.status_code == 422
    assert client.get("/research/snapshot").json()["state"] == before
    assert client.get("/research/replay").json()["verified"]


def test_reverted_identical_policy_accepts_content_equivalent_old_revision():
    client = TestClient(create_app())
    original = client.get("/site/policies/discount").json()
    assert client.post("/research/publish", json={"scope": "discount", "rule": {"eligible": False, "percent": 0}}).status_code == 200
    assert client.post("/research/publish", json={"scope": "discount", "rule": {"eligible": True, "percent": 10}}).status_code == 200
    accepted = client.post("/site/purchases", json={"expected_policy_revision": original["revision"]})
    assert accepted.status_code == 201
    assert accepted.json()["purchase"]["paid"] == 90
    assert client.get("/research/replay").json()["verified"]


def test_exported_trace_replays_and_detects_tampering():
    lab = Lab()
    lab.read("discount", None)
    snapshot = lab.snapshot()
    assert verify_snapshot(snapshot)["verified"]
    snapshot["events"][0]["status"] = 304
    assert verify_snapshot(snapshot)["error"] == "event_mismatch"
    snapshot = lab.snapshot()
    snapshot["state"]["inventory"]["notebook"] = 999
    assert verify_snapshot(snapshot)["error"] == "final_state_mismatch"


def test_retail_return_shipping_and_address_under_changed_rules():
    client = TestClient(create_app())
    cases = [
        ("returns", "RET-001", "refund", {"window_days": 14, "accept_opened": False}, "too_old"),
        ("fulfillment", "SHIP-001", "ship", {"max_quantity": 6, "destinations": ["mainland"]}, "destination"),
        ("changes", "ADDR-001", "address", {"max_age_hours": 18, "allow_express": False}, "locked"),
    ]
    for scope, order_id, operation, changed_rule, reason in cases:
        first = client.get(f"/site/policies/{scope}")
        order = client.get(f"/site/orders/{order_id}")
        assert first.status_code == order.status_code == 200
        assert order.json()["order"]["kind"] == scope
        prior_order = order.json()["order"]
        assert client.post("/research/publish", json={"scope": scope, "rule": changed_rule}).status_code == 200
        payload = {"expected_policy_revision": first.json()["revision"], "address": "20 New Street"}
        stale = client.post(f"/site/orders/{order_id}/{operation}", json=payload)
        assert stale.status_code == 409 and stale.json()["error"] == "policy_revision_changed"
        current = client.get(f"/site/policies/{scope}").json()
        payload["expected_policy_revision"] = current["revision"]
        denied = client.post(f"/site/orders/{order_id}/{operation}", json=payload)
        assert denied.status_code == 409 and denied.json()["reason"] == reason
        assert client.get(f"/site/orders/{order_id}").json()["order"] == prior_order
    assert client.get("/research/replay").json()["verified"]


def test_retail_transaction_commits_under_current_policy_once():
    client = TestClient(create_app())
    scopes = [("returns", "RET-001", "refund"), ("fulfillment", "SHIP-001", "ship"),
              ("changes", "ADDR-001", "address")]
    for scope, order_id, operation in scopes:
        rule = client.get(f"/site/policies/{scope}").json()
        payload = {"expected_policy_revision": rule["revision"], "address": "20 New Street"}
        accepted = client.post(f"/site/orders/{order_id}/{operation}", json=payload)
        assert accepted.status_code == 200
        assert accepted.json()["order"]["status"] in ("refunded", "shipped", "address_changed")
        duplicate = client.post(f"/site/orders/{order_id}/{operation}", json=payload)
        assert duplicate.status_code == 409 and duplicate.json()["error"] == "invalid_status"
    state = client.get("/research/snapshot").json()["state"]
    assert state["inventory"]["notebook"] == 101
    assert state["inventory"]["lamp"] == 98
    assert state["orders"]["ADDR-001"]["address"] == "20 New Street"
    assert client.get("/research/replay").json()["verified"]
