"""Digest layer — assemble what changed, verify apply links, render, and send.

P3B1 builds the digest contents + the verification gate (this package's `assembly` +
`verification`); rendering and the Resend send path land in later Phase-3 blocks.
"""
