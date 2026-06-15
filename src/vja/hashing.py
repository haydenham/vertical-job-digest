"""Deterministic `content_hash` for the extraction cache (`docs/04` §3).

`content_hash` answers *"did this posting's content change since we last saw it?"*
(distinct from `external_id`, which answers *"is this the same posting?"* — D-016).
Same `external_id` + changed hash ⇒ re-run Layer-2 extraction; same hash ⇒ reuse the
cached extraction for free (D-005 cost discipline). Correctness of this function is
the correctness of the cache, so it is tested hard (`docs/08`).

The hash is taken over the **stable content fields only** — `{title, location,
description}` — so volatile junk (view counts, "updated X ago" strings, tracking
query params, request timestamps) is excluded *by construction*: it is never passed
in. Whitespace and JSON key ordering are normalized away so cosmetic churn does not
masquerade as a content change.
"""

from __future__ import annotations

import hashlib
import json


def _normalize(value: str | None) -> str:
    """Collapse all whitespace runs to single spaces and strip; `None` → empty.

    Makes the hash invariant to cosmetic whitespace differences (reflowed HTML,
    trailing newlines) while preserving case and word content (a real edit still
    changes the hash). `None` and `""` hash identically.
    """
    if value is None:
        return ""
    return " ".join(value.split())


def content_hash(*, title: str, location: str | None, description: str | None) -> str:
    """Return the hex SHA-256 of the canonical stable-content object.

    Deterministic and order-independent: keys are sorted before hashing, so the
    result depends only on the field *values*, never on construction order.
    """
    canonical = json.dumps(
        {
            "title": _normalize(title),
            "location": _normalize(location),
            "description": _normalize(description),
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
