# PieMesh

Self-hosted, open-source distributed load testing framework.

PieMesh lets machine owners contribute idle bandwidth to performance
tests — but only against targets whose control has been demonstrated
through a DNS TXT ownership challenge, the same mechanism used by
ACME/Let's Encrypt. Nothing ships until the hub can prove who owns
what's being tested.

**Reciprocal by design — no spectators:** everyone who runs PieMesh
runs an agent. There is no download-and-watch tier: the tool IS the
mesh, so having it means being part of it. Contribute capacity, earn
test capability — and every test, yours included, still requires
verified ownership of the target.

## Why it's different

| Typical tooling | PieMesh |
|---|---|
| Trust the operator's word | Ownership proven via public DNS |
| Limits configurable server-side | Rate/duration caps compiled into the agent |
| Silent enrollment | Interactive consent gate, versioned, revocable anytime |
| Black-box operation | Every task logged locally + hub-side (`audit.log`) |

## How authorization works

```
1. Operator:   target add acme.com            -> hub mints a challenge token
2. DNS owner:  _piemesh.acme.com  IN  TXT  "piemesh-<token>"
3. Operator:   target verify acme.com         -> hub resolves and matches
4. Only now can tests target acme.com. Valid 30 days.
No TXT match = no test. Not "warns" - refuses.
```

## Quick start (hub operator)

```bash
pip install -r requirements.txt
python gencert.py                 # generates certs/ (never commit these)
# edit config.json -> enrollment_token
python server.py                  # agents :4444 TLS 1.3 | operator shell :4443
```

Operator console (local or via KiTTY/PuTTY raw to port 4443).
Two token roles:

- `operator_token` — full control: agents, targets, tests, kick, shell
- `enrollment_token` — the public join token: members connect to the same shell and may run target/test/results commands only. Every member must also be running an agent node.

If `operator_token` is left as its CHANGE-ME placeholder, the hub runs
in solo mode (join token = operator). Set it before inviting members.

```
agents                          online agents
target add/verify/list/remove   target ownership workflow
test <domain> <url> <secs> [rps]  dispatch a verified test
tests / results [n]             history
kick <id>                       drop an agent
```

For remote operator access use an SSH tunnel:
`ssh -L 4443:127.0.0.1:4443 user@hub` — never expose 4443 publicly.

## Volunteer agent

```bash
python agent.py --server <hub-hostname> --token <enrollment-token>
```

- First run shows consent terms; type `AGREE` or pass `--agree-tos 2026-08-v4`
- Hard limits baked in: 300 s per test, 200 req/s, 64 connections
- A tray icon appears near the clock: node status, **Pause load generation**,
  per-node load limit, **Start with Windows**, and **Exit**
- Closing the window (or tray **Exit**) stops the running node instantly
- `python agent.py --revoke-consent` wipes identity + consent records

### Start with Windows (optional autostart)

Autostart is **off by default** and opt-in. Enable it two ways:

```bash
# from the tray: toggle "Start with Windows"
# or from the CLI (server + token required, then it exits):
python agent.py --server <hub> --token <enrollment-token> --install-autostart
```

Once enabled, the agent launches on every boot — **your machine
rejoins the mesh and contributes load-testing capacity automatically
at startup, without prompting again.** What that means concretely:

- It registers under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`
  (key `PiemeshAgent`) and starts via `pythonw.exe` — **no console
  window**, but the **tray icon still shows** so the node is never hidden
- It reuses your recorded consent for the same terms version; it does
  **not** re-prompt on each boot. If `agent.py` was modified since you
  consented, it refuses to start until you re-run with
  `--trust-modified-build`
- Exiting or closing only stops the *current* session — it will start
  again on the next boot until you turn autostart off

Turn it off with the tray **Start with Windows** toggle, or:

```bash
python agent.py --uninstall-autostart
```

Autostart persists load generation across reboots — enable it only on
a machine you own and want contributing to the mesh unattended.

Distribute `agent.py`, `certs/ca.crt`, and this repo's LICENSE +
ACCEPTABLE_USE.md to volunteers. The agent reads no config on their
machines - defaults hold.

## Legal

Licensed for **authorized security testing only** — see
[LICENSE](./LICENSE) and [ACCEPTABLE_USE.md](./ACCEPTABLE_USE.md).

- Hub operators are responsible for target verification on their deployments
- Unauthorized load generation voids the license automatically
- Provided AS-IS with no warranty; liability limited to the maximum extent permitted by law

**Abuse contact:** spookybrosyt@gmail.com

## How membership works

| Rule | Meaning |
|---|---|
| Everyone is an agent | Every person running PieMesh contributes a node — testers, members, even hub operators on their own deployments |
| Join to use | Test capability is earned by participation; there is no read-only tier. Dispatching a test requires YOUR agent online on the machine you're dispatching from |
| Verified targets only | Agents execute workloads solely against domains proven via DNS TXT challenge — never arbitrary targets |
| Limits travel with you | 300 s per test, 200 req/s, 64 connections — compiled into the agent, impossible to raise remotely |
| Leaving is instant | Close the window or hit tray **Exit** to stop the running node; `--revoke-consent` wipes identity and consent records |
| Autostart is opt-in | Off by default. If you enable **Start with Windows**, the node rejoins the mesh on every boot until you turn it off (`--uninstall-autostart`) |
| Everything is logged | Every task your node runs is recorded locally and in the hub's `audit.log` |

Joining does **not** expose your machine to other members. Nodes
receive only workloads dispatched by their own hub, and only for
domains whose ownership was verified on that hub.

## Authorized testing only

Every test requires proven ownership of the target domain before a
single request is dispatched. Using PieMesh against systems you do
not own or lack prior written authorization to test voids the license
(see [LICENSE](./LICENSE) §2) and violates
[ACCEPTABLE_USE.md](./ACCEPTABLE_USE.md). This applies to every
member equally — contributing capacity earns you capability, never
exemption.

## Status

Pre-release. API and wire format will change.
