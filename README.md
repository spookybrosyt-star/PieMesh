
# PieMesh

Self-hosted, open-source distributed load testing framework.

PieMesh lets machine owners contribute idle bandwidth to performance
tests — but only against targets whose control has been demonstrated
through a DNS TXT ownership challenge, the same mechanism used by
ACME/Let's Encrypt. Nothing ships until the hub can prove who owns
what's being tested.

## Why it's different

| Typical tooling | PieMesh |
|---|---|
| Trust the operator's word | Ownership proven via public DNS |
| Limits configurable server-side | Rate/duration caps compiled into the agent |
| Silent enrollment | Interactive consent gate, versioned, revocable anytime |
| Black-box operation | Every task logged locally + hub-side (`audit.log`) |

## Status
Pre-release. API and wire format will change.
