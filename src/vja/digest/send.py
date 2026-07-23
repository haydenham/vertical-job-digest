"""Send the digest via Resend (D-013) and drive the `digests` row lifecycle.

The orchestrator `send_digest` is the standalone step run after the nightly `vja-run`:
build contents (with the D-008 verification gate) → skip if nothing changed (D-028) →
render → write a `pending` row → POST to Resend → finalize `sent`/`failed`.

Config comes from the environment (a local `.env` is loaded for the cron runtime, D-012):
- `RESEND_API_KEY` — required to send. The provided `.env` may name it `resend-api-key`;
  both spellings are accepted (hyphenated names can't be shell-exported, only dotenv-loaded).
- `VJA_DIGEST_FROM` — sender; defaults to the Resend sandbox `onboarding@resend.dev`, which
  delivers only to your own Resend account email (D-029). Set a verified domain to send anywhere.
- `VJA_DIGEST_RECIPIENT` — the **ops/alert** recipient (where nightly failure-alerts go). As of
  P5.4 the *digest* recipient is the matched profile's `user_email`, not this env var (D-027/D-037):
  a digest is per (vertical, profile), addressed to whoever owns that resume.
- `VJA_PUBLIC_BASE_URL` — the public origin for the no-login unsubscribe link + RFC-8058 one-click
  headers (D-094). Unset (dev) ⇒ the email ships without footer/headers — never a localhost link.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from dotenv import load_dotenv
from sqlalchemy import Engine

from vja.db import digests as digests_repo
from vja.db.employers import distinct_active_verticals
from vja.db.engine import begin, get_engine
from vja.db.profiles import Profile, active_profiles
from vja.db.users import get_user_by_email
from vja.digest.assembly import build_digest
from vja.digest.render import RenderedEmail, contents_to_dict, render_digest
from vja.digest.unsubscribe import make_unsubscribe_token, unsubscribe_url

_RESEND_ENDPOINT = "https://api.resend.com/emails"
_SANDBOX_SENDER = "onboarding@resend.dev"
_TIMEOUT = 15.0


class ConfigError(RuntimeError):
    """Required send configuration (API key / recipient) is missing from the environment."""


class SendError(RuntimeError):
    """The Resend API call did not succeed (transport error or non-2xx response)."""


@dataclass(frozen=True)
class DigestConfig:
    api_key: str
    sender: str
    recipient: str  # ops/alert recipient — the digest recipient is the profile's email (D-037)
    # Public origin for unsubscribe links/headers (D-094); None (dev) ⇒ no footer/headers.
    public_base_url: str | None = None


@dataclass(frozen=True)
class DigestSendResult:
    vertical: str
    recipient: str
    status: str  # "sent" | "failed" | "skipped" | "paused"
    digest_id: int | None
    new: int
    closed: int
    quarantined: int
    error: str | None = None


def load_config() -> DigestConfig:
    """Load send config from the environment (loading `.env` first for the local runtime)."""
    load_dotenv()
    # The provided `.env` names the key `resend-api-key`; accept it verbatim (it can't be
    # shell-exported, only dotenv-loaded), alongside the canonical uppercase form.
    api_key = os.environ.get("RESEND_API_KEY") or os.environ.get("resend-api-key")  # noqa: SIM112
    if not api_key:
        raise ConfigError("RESEND_API_KEY is not set (checked RESEND_API_KEY and resend-api-key)")
    recipient = os.environ.get("VJA_DIGEST_RECIPIENT")
    if not recipient:
        raise ConfigError("VJA_DIGEST_RECIPIENT is not set")
    sender = os.environ.get("VJA_DIGEST_FROM", _SANDBOX_SENDER)
    return DigestConfig(
        api_key=api_key,
        sender=sender,
        recipient=recipient,
        public_base_url=os.environ.get("VJA_PUBLIC_BASE_URL"),
    )


def send_email(
    config: DigestConfig,
    rendered: RenderedEmail,
    *,
    recipient: str | None = None,
    headers: dict[str, str] | None = None,
) -> None:
    """POST one email to Resend; raise `SendError` on any transport error or non-2xx response.

    `recipient` defaults to the config's ops/alert recipient (used by the nightly failure alert);
    digest sends pass the profile's `user_email` explicitly (D-037). `headers` become custom email
    headers on the Resend payload (the RFC-8058 unsubscribe pair, D-094).
    """
    payload: dict[str, object] = {
        "from": config.sender,
        "to": [recipient or config.recipient],
        "subject": rendered.subject,
        "html": rendered.html,
        "text": rendered.text,
    }
    if headers:
        payload["headers"] = headers
    try:
        response = httpx.post(
            _RESEND_ENDPOINT,
            json=payload,
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise SendError(f"Resend returned {exc.response.status_code}: {exc.response.text}") from exc
    except httpx.HTTPError as exc:
        raise SendError(f"Resend request failed: {exc!r}") from exc


def send_digest(
    engine: Engine,
    vertical: str,
    profile: Profile,
    *,
    now: datetime | None = None,
    config: DigestConfig | None = None,
    verify: Callable[[str], bool] | None = None,
) -> DigestSendResult:
    """(Skip if paused) → build → (skip if empty) → render → persist → send → finalize,
    per (vertical, profile).

    The digest is addressed to `profile.user_email` and carries that profile's match rationale
    (D-027/D-037); `config` is only the transport (api key/sender) + ops/alert recipient.
    """
    stamp = now or datetime.now(UTC)
    recipient = profile.user_email

    # Paused check first (D-094): the person opted out of the email, so skip everything —
    # including the D-008 verification gate's network cost. No `digests` row (the D-028 pattern),
    # so the `since` window doesn't advance and a future resume gets the accumulated diff.
    user = get_user_by_email(engine, recipient)
    if user is not None and user.digest_paused:
        print(f"[{vertical}→{recipient}] paused: digest email disabled by user", file=sys.stderr)
        return DigestSendResult(
            vertical=vertical,
            recipient=recipient,
            status="paused",
            digest_id=None,
            new=0,
            closed=0,
            quarantined=0,
        )

    contents = build_digest(engine, vertical, profile=profile, now=stamp, verify=verify)
    n_new, n_closed, n_quar = len(contents.new), len(contents.closed), len(contents.quarantined)

    def result(status: str, digest_id: int | None, error: str | None = None) -> DigestSendResult:
        return DigestSendResult(
            vertical=vertical,
            recipient=recipient,
            status=status,
            digest_id=digest_id,
            new=n_new,
            closed=n_closed,
            quarantined=n_quar,
            error=error,
        )

    if not contents.new and not contents.closed:
        # Nothing to ship (D-028). Surface quarantines so an all-quarantine night isn't silent.
        if contents.quarantined:
            print(
                f"[{vertical}→{recipient}] skipped: 0 new, 0 closed, "
                f"but {n_quar} quarantined (dead apply links)",
                file=sys.stderr,
            )
        return result("skipped", None)

    cfg = config or load_config()

    # Footer link + RFC-8058 headers (D-094) need both a public origin and a `users` row to key
    # the token on; a dev run (no base URL) or a pre-login seed profile sends without them.
    unsub_url: str | None = None
    headers: dict[str, str] | None = None
    if cfg.public_base_url and user is not None:
        token = make_unsubscribe_token(user.id, user.email)
        unsub_url = unsubscribe_url(cfg.public_base_url, token)
        headers = {
            "List-Unsubscribe": f"<{unsub_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }
    rendered = render_digest(contents, unsubscribe_url=unsub_url)

    with begin(engine) as conn:
        digest_id = digests_repo.create_pending(
            conn, recipient=recipient, vertical=vertical, contents=contents_to_dict(contents)
        )

    try:
        send_email(cfg, rendered, recipient=recipient, headers=headers)
    except SendError as exc:
        with begin(engine) as conn:
            digests_repo.mark_failed(conn, digest_id, error=str(exc))
        return result("failed", digest_id, error=str(exc))

    with begin(engine) as conn:
        digests_repo.mark_sent(conn, digest_id, sent_at=stamp)
    return result("sent", digest_id)


def send_main(argv: list[str] | None = None) -> int:
    """CLI: `vja-digest [--vertical V]` — assemble and send the digest(s) via Resend."""
    parser = argparse.ArgumentParser(
        prog="vja-digest", description="Assemble and send the bare digest via Resend."
    )
    parser.add_argument("--vertical", default=None, help="limit to one vertical (default: all)")
    args = parser.parse_args(argv)

    engine = get_engine()
    verticals = [args.vertical] if args.vertical else distinct_active_verticals(engine)
    if not verticals:
        print("no active verticals to send", file=sys.stderr)
        return 0

    config = load_config()
    failed = False
    for vertical in verticals:
        for profile in active_profiles(engine, vertical):
            result = send_digest(engine, vertical, profile, config=config)
            suffix = f" (digest {result.digest_id})" if result.digest_id is not None else ""
            print(
                f"[{result.vertical}→{result.recipient}] {result.status}: new={result.new} "
                f"closed={result.closed} quarantined={result.quarantined}{suffix}"
            )
            if result.status == "failed":
                failed = True
                print(f"  ! {result.error}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(send_main())
