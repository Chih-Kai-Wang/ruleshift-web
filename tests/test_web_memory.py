from types import SimpleNamespace

from fastapi.testclient import TestClient

from ruleshift.web_lab import create_app
from ruleshift.web_memory import PolicyFetchError, PolicyMemory


def test_relevant_source_validation_and_unrelated_control():
    client = TestClient(create_app())
    memory = PolicyMemory()
    first = memory.for_action(client, "refund", 0, "source_dependent")
    assert first[0]["source_url"] == "/site/policies/returns"
    assert first[0]["depends_on"] == ["/site/policies/returns"]
    old = first[0]["revision"]
    memory.for_action(client, "ship", 1, "source_dependent")
    client.post("/research/publish", json={"scope": "fulfillment", "rule": {"max_quantity": 2, "destinations": ["mainland"]}})
    unchanged = memory.for_action(client, "refund", 2, "source_dependent")
    assert unchanged[0]["revision"] == old
    assert memory.history[-1]["outcome"] == "validated_304"
    assert memory.entries["fulfillment"].last_validated_at == 1
    memory.for_action(client, "refund", 3, "conditional_all")
    assert memory.entries["fulfillment"].last_validated_at == 3


def test_stale_retrieval_and_changed_source_detection():
    client = TestClient(create_app())
    memory = PolicyMemory()
    old = memory.for_action(client, "refund", 0, "retrieval")[0]
    client.post("/research/publish", json={"scope": "returns", "rule": {"window_days": 14, "accept_opened": False}})
    assert memory.for_action(client, "refund", 1, "retrieval")[0]["revision"] == old["revision"]
    new = memory.for_action(client, "refund", 2, "source_dependent")[0]
    assert new["revision"] != old["revision"]
    assert new["observed_at"] == 2


def test_http_failure_does_not_validate_stale_evidence():
    client = TestClient(create_app())
    memory = PolicyMemory()
    memory.for_action(client, "refund", 0, "source_dependent")
    old_validation = memory.entries["returns"].last_validated_at

    class BrokenClient:
        def get(self, url, *, headers=None):
            raise OSError("network down")

    try:
        memory.for_action(BrokenClient(), "refund", 1, "source_dependent")
    except PolicyFetchError:
        pass
    else:
        raise AssertionError("Network failure must block action")
    assert memory.entries["returns"].last_validated_at == old_validation
    assert memory.history[-1]["outcome"] == "transport_error"


def test_no_etag_falls_back_to_full_content_comparison():
    origin = TestClient(create_app())

    class NoValidatorClient:
        def __init__(self):
            self.requests = []

        def get(self, url, *, headers=None):
            self.requests.append(dict(headers or {}))
            response = origin.get(url, headers=headers)
            return SimpleNamespace(status_code=response.status_code, headers={}, json=response.json)

    client = NoValidatorClient()
    memory = PolicyMemory()
    first = memory.for_action(client, "refund", 0, "source_dependent")[0]
    assert first["etag"] is None
    same = memory.for_action(client, "refund", 1, "source_dependent")[0]
    assert same["revision"] == first["revision"]
    assert same["observed_at"] == 0 and same["last_validated_at"] == 1
    assert memory.history[-1]["outcome"] == "validated_content_equal"
    origin.post("/research/publish", json={"scope": "returns", "rule": {"window_days": 14, "accept_opened": False}})
    changed = memory.for_action(client, "refund", 2, "source_dependent")[0]
    assert changed["revision"] != first["revision"]
    assert changed["observed_at"] == 2
    assert all("If-None-Match" not in headers for headers in client.requests)
