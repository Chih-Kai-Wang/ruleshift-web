"""Agent-visible HTTP evidence records for RuleShift-Web v2.

This module never reads research snapshots, future events, or evaluator scores.
Callers must stop the action when verification raises PolicyFetchError.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, Protocol

ACTION_SOURCES = {
    "purchase": ("discount",),
    "refund": ("returns",),
    "ship": ("fulfillment",),
    "address": ("changes",),
}


class PolicyFetchError(RuntimeError):
    """Policy validity is unknown; action must not be attempted."""


class HttpClient(Protocol):
    def get(self, url: str, *, headers: dict[str, str] | None = None) -> Any: ...


@dataclass
class Evidence:
    scope: str
    source_url: str
    observed_at: float
    etag: str | None
    revision: str
    body: dict
    depends_on: tuple[str, ...]
    last_validated_at: float | None = None

    def agent_view(self) -> dict:
        return {
            "scope": self.scope,
            "source_url": self.source_url,
            "observed_at": self.observed_at,
            "etag": self.etag,
            "revision": self.revision,
            "policy": copy.deepcopy(self.body),
            "depends_on": list(self.depends_on),
            "last_validated_at": self.last_validated_at,
        }


class PolicyMemory:
    def __init__(self, base_url: str = ""):
        self.base_url = base_url.rstrip("/")
        self.entries: dict[str, Evidence] = {}
        self.history: list[dict] = []

    def url(self, scope: str) -> str:
        return f"{self.base_url}/site/policies/{scope}"

    def acquire(self, client: HttpClient, scope: str, now: float, *, conditional: bool) -> Evidence:
        previous = self.entries.get(scope)
        headers = {"If-None-Match": previous.etag} if conditional and previous and previous.etag else {}
        url = self.url(scope)
        try:
            response = client.get(url, headers=headers)
        except Exception as exc:
            self.history.append({"scope": scope, "source_url": url, "outcome": "transport_error"})
            raise PolicyFetchError(f"Policy fetch failed for {scope}") from exc
        if response.status_code == 304 and previous:
            previous.last_validated_at = now
            self.history.append({"scope": scope, "source_url": url, "outcome": "validated_304"})
            return previous
        if response.status_code != 200:
            self.history.append({"scope": scope, "source_url": url, "outcome": f"http_{response.status_code}"})
            raise PolicyFetchError(f"Policy fetch returned HTTP {response.status_code} for {scope}")
        etag = response.headers.get("etag")
        try:
            body = response.json()
            if body["scope"] != scope or not isinstance(body["revision"], str):
                raise ValueError("Unexpected policy representation")
        except (ValueError, KeyError, TypeError) as exc:
            self.history.append({"scope": scope, "source_url": url, "outcome": "invalid_body"})
            raise PolicyFetchError(f"Invalid policy response for {scope}") from exc
        if (not etag and previous and not previous.etag
                and json.dumps(previous.body, sort_keys=True) == json.dumps(body, sort_keys=True)):
            previous.last_validated_at = now
            self.history.append({"scope": scope, "source_url": url,
                                 "outcome": "validated_content_equal"})
            return previous
        entry = Evidence(
            scope=scope,
            source_url=url,
            observed_at=now,
            etag=etag,
            revision=body["revision"],
            body=copy.deepcopy(body),
            depends_on=(url,),
            last_validated_at=now,
        )
        self.entries[scope] = entry
        self.history.append({"scope": scope, "source_url": url,
                             "outcome": "fetched_200" if etag else "fetched_200_no_etag"})
        return entry

    def for_action(self, client: HttpClient, action: str, now: float, strategy: str) -> list[dict]:
        if action not in ACTION_SOURCES:
            raise ValueError(f"Unknown action: {action}")
        if strategy not in ("retrieval", "always_refresh", "conditional_all",
                            "source_dependent", "v1_selective"):
            raise ValueError(f"Unknown strategy: {strategy}")
        relevant = ACTION_SOURCES[action]
        if strategy == "conditional_all":
            scopes = tuple(dict.fromkeys((*self.entries, *relevant)))
        else:
            scopes = relevant
        for scope in scopes:
            if strategy in ("retrieval", "v1_selective") and scope in self.entries:
                self.history.append({"scope": scope, "source_url": self.url(scope), "outcome": "reused_unchecked"})
                continue
            self.acquire(client, scope, now, conditional=strategy in ("conditional_all", "source_dependent"))
        return [self.entries[scope].agent_view() for scope in relevant]
