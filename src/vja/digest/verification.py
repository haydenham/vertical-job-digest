"""Apply-link verification (D-008): a posting never ships unless its link resolves.

"One fake posting costs more trust than ten real ones earn." A failed check means the
posting is held out of the digest (quarantined), never silently shipped.
"""

from __future__ import annotations

import httpx

_TIMEOUT = 10.0
_USER_AGENT = "vja-job-agent/0.0.1 (+https://github.com/haydenham/vertical-job-digest)"


def verify_apply_url(url: str, client: httpx.Client) -> bool:
    """True iff `url` resolves to a final status < 400.

    Tries a cheap HEAD first (following redirects); if the server rejects the method
    (405/501), retries with GET. Any transport/timeout error counts as a failure —
    when in doubt, don't ship the link.
    """
    try:
        response = client.head(url, follow_redirects=True, timeout=_TIMEOUT)
        if response.status_code in (405, 501):
            response = client.get(url, follow_redirects=True, timeout=_TIMEOUT)
    except httpx.HTTPError:
        return False
    return response.status_code < 400


def default_client() -> httpx.Client:
    """A client with an identifiable User-Agent (politeness — `docs/05`)."""
    return httpx.Client(headers={"User-Agent": _USER_AGENT})
