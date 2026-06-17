"""Digest layer — assemble what changed, verify apply links, render, and send.

P3B1 built the digest contents + the verification gate (`assembly` + `verification`);
P3B2 adds `render` (HTML/text + audit JSON) and `send` (Resend + the `digests` row lifecycle).
"""
