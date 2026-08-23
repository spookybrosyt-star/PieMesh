import asyncio
import hmac
import json
import secrets
import ssl
import time
import uuid
from collections import deque
from pathlib import Path
from urllib.parse import urlparse

import dns.resolver

import ui

here = Path(__file__).parent
_local = here / "config.local.json"
cfg = (
    json.loads(_local.read_text())
    if _local.exists()
    else json.loads((here / "config.json").read_text())
)
agents = {}
tests = {}
results = deque(maxlen=500)

HELP = """commands:
  agents                          online agents
  run <id> sysinfo|ps|shell <c>   single agent commands
  target add <domain>             register + mint dns challenge
  target verify <domain>          check the txt record
  target remove <domain>
  target list
  test <domain> <url> <secs> [rps]  launch a verified test
  tests                           history
  results [n]
  kick <id>
  quit"""


def log(evt, **kw):
    row = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "event": evt}
    row.update(kw)
    with (here / "audit.log").open("a") as fh:
        fh.write(json.dumps(row) + "\n")


def targets():
    f = here / "targets.json"
    return json.loads(f.read_text()) if f.exists() else {}


def save_targets(t):
    (here / "targets.json").write_text(json.dumps(t, indent=2))


def check_dns(domain, token):
    try:
        ans = dns.resolver.resolve("_piemesh." + domain, "TXT", lifetime=10)
        found = {b"".join(r.strings).decode() for a in ans for r in a}
        return token in found
    except Exception:
        return False


def age(ts):
    return str(int(time.time() - ts)) + "s"


async def readline_any(reader):
    buf = bytearray()
    while True:
        b = await reader.read(1)
        if not b:
            break
        if b == b"\n":
            break
        if b == b"\r":
            continue
        buf += b
    return bytes(buf)


def clamp_test(duration, rps):
    return min(duration, cfg.get("max_test_duration_s", 300)), min(
        rps, cfg.get("max_test_rps", 200)
    )


MEMBER_ALLOWED = {"agents", "target", "test", "tests", "results", "help"}

HELP_MEMBER = """member commands:
  agents                          mesh roster (ids only)
  target add <domain>             register + mint dns challenge
  target verify <domain>          check the txt record
  test <domain> <url> <secs> [rps]  dispatch a verified test
                                  (requires YOUR agent online on this machine)
  tests / results [n]             history
  quit                            leave the shell"""


def do_cmd(line, role="operator", ip=""):
    parts = line.split()
    if not parts:
        return True, ""

    c, args = parts[0].lower(), parts[1:]

    if c == "quit":
        return False, "bye"

    if role == "member" and c not in MEMBER_ALLOWED:
        return True, "members can't run '%s' - 'help' lists member commands" % c

    if c == "help":
        return True, HELP_MEMBER if role == "member" else HELP

    if c == "agents":
        if not agents:
            return True, "nobody online"
        rows = []
        for aid, r in agents.items():
            flag = " MODIFIED" if r.get("modified") else ""
            if role == "member":
                rows.append(
                    "  %-14s %-18s seen %s ago%s" % (aid, r["os"], age(r["seen"]), flag)
                )
            else:
                rows.append(
                    "  %-14s %-22s %-18s seen %s ago [%s]%s"
                    % (aid, r["host"], r["os"], age(r["seen"]), r["hash"], flag)
                )
        return True, "\n".join(rows)

    if c == "target":
        if len(args) < 1:
            return True, "target add|verify|remove|list <domain>"
        sub = args[0].lower()

        if sub == "list":
            t = targets()
            out = []
            for dom, rec in t.items():
                ok = rec.get("expires") and rec["expires"] > time.time()
                out.append(
                    "  %-30s %s"
                    % (
                        dom,
                        "verified, %s left" % age(rec["expires"]) if ok else "pending",
                    )
                )
            return True, "\n".join(out) or "no targets"

        if len(args) < 2:
            return True, "missing domain"
        dom = args[1].lower().strip(".")
        t = targets()

        if sub == "add":
            tok = "piemesh-" + secrets.token_hex(16)
            t[dom] = {"token": tok, "expires": None}
            save_targets(t)
            log("target_added", domain=dom)
            return (
                True,
                'add this dns record:\n\n  _piemesh.%s  IN  TXT  "%s"\n\nthen: target verify %s'
                % (dom, tok, dom),
            )

        if sub == "verify":
            rec = t.get(dom)
            if not rec:
                return True, dom + ": not registered, add it first"
            if check_dns(dom, rec["token"]):
                days = cfg.get("verification_valid_days", 30)
                rec["expires"] = time.time() + days * 86400
                save_targets(t)
                log("target_verified", domain=dom)
                return True, "%s verified for %d days" % (dom, days)
            log("target_verify_failed", domain=dom)
            return True, "txt record didn't match for " + dom

        if sub == "remove":
            if role == "member":
                return True, "target removal is operator-only"
            if t.pop(dom, None) is None:
                return True, "unknown domain " + dom
            save_targets(t)
            log("target_removed", domain=dom)
            return True, "dropped " + dom

        return True, "what is '" + sub + "'"

    if c == "test":
        if len(args) < 3:
            return True, "test <domain> <url> <secs> [rps]"
        dom, url = args[0].lower(), args[1]
        try:
            dur = int(args[2])
            rps = int(args[3]) if len(args) > 3 else 50
        except ValueError:
            return True, "secs/rps must be numbers"

        u = urlparse(url)
        if u.scheme not in ("http", "https"):
            return True, "http(s) urls only"
        host = u.hostname or ""
        if host != dom and not host.endswith("." + dom):
            return True, "url host %s isn't under %s" % (host, dom)

        if role == "member":
            contributing = any(r.get("ip") == ip for r in agents.values())
            if not contributing:
                return True, (
                    "participation required: your machine has no agent online - "
                    "start agent.py on this machine before dispatching tests"
                )

        rec = targets().get(dom)
        if not rec or not rec.get("expires") or rec["expires"] <= time.time():
            return True, dom + " has no valid verification"

        dur, rps = clamp_test(dur, rps)
        pool = list(agents)[: cfg.get("max_agents_per_test", 10)]
        if not pool:
            return True, "no agents connected"

        tid = uuid.uuid4().hex[:8]
        tests[tid] = {
            "domain": dom,
            "url": url,
            "started": time.time(),
            "expected": len(pool),
            "done": 0,
            "status": "running",
        }
        for aid in pool:
            agents[aid]["outbox"].append(
                {
                    "task_id": "%s-%s" % (tid, aid),
                    "kind": "loadgen",
                    "args": {
                        "test_id": tid,
                        "url": url,
                        "duration_s": dur,
                        "rate_rps": rps,
                    },
                }
            )
        log(
            "test_started",
            test_id=tid,
            domain=dom,
            url=url,
            secs=dur,
            rps=rps,
            agents=len(pool),
        )
        return True, "test %s dispatched (%s @ %drps, %ds, %d agents)" % (
            tid,
            url,
            rps,
            dur,
            len(pool),
        )

    if c == "tests":
        if not tests:
            return True, "nothing run yet"
        out = []
        for tid, r in tests.items():
            out.append(
                "  %s  %-28s %-8s %d/%d reported"
                % (tid, r["domain"], r["status"], r["done"], r["expected"])
            )
        return True, "\n".join(out)

    if c == "results":
        n = int(args[0]) if args and args[0].isdigit() else 10
        got = list(results)[-n:]
        return True, "\n".join(json.dumps(r)[:400] for r in got) or "empty"

    if c == "kick":
        if not args:
            return True, "kick <id>"
        r = agents.pop(args[0], None)
        if not r:
            return True, "no such agent"
        r["writer"].close()
        log("agent_kicked", agent=args[0])
        return True, "kicked"

    if c == "run":
        if len(args) < 2:
            return True, "run <id> sysinfo|ps|shell <cmd>"
        aid, rest = args[0], args[1:]
        kind = rest[0].lower()
        if kind == "shell":
            if len(rest) < 2:
                return True, "shell needs a command"
            targs = {"cmd": " ".join(rest[1:])}
        elif kind in ("sysinfo", "ps"):
            targs = {}
        else:
            return True, "unknown kind " + kind
        task = {"task_id": str(int(time.time() * 1000)), "kind": kind, "args": targs}
        if aid not in agents:
            return True, "no such agent"
        agents[aid]["outbox"].append(task)
        log("task_issued", agent=aid, task=task)
        return True, "queued %s -> %s" % (kind, aid)

    return True, "try 'help'"


async def agent_conn(reader, writer):
    peer = writer.get_extra_info("peername")
    try:
        hello = json.loads(await asyncio.wait_for(reader.readline(), 15))
    except Exception:
        writer.close()
        return

    if hello.get("type") != "hello" or not hmac.compare_digest(
        str(hello.get("token", "")), cfg["enrollment_token"]
    ):
        log("auth_denied", peer=str(peer))
        writer.close()
        await writer.wait_closed()
        return

    aid = str(hello.get("id"))[:64]
    code_hash = str(hello.get("code_hash", ""))[:64]
    modified = bool(hello.get("modified"))
    agents[aid] = {
        "writer": writer,
        "host": hello.get("hostname", "?"),
        "os": hello.get("os", "?"),
        "since": time.time(),
        "seen": time.time(),
        "outbox": [],
        "hash": code_hash[:12],
        "modified": modified,
        "ip": peer[0],
    }
    log(
        "agent_connected",
        agent=aid,
        hostname=hello.get("hostname"),
        code_hash=code_hash[:16],
        modified=modified,
    )
    tag = " MODIFIED-BUILD" if modified else ""
    ui.ok(
        "agent %s (%s) from %s%s"
        % (aid, hello.get("hostname"), peer[0], ui.paint(tag, ui.RED))
    )
    writer.write(b'{"type":"welcome"}\n')
    await writer.drain()

    try:
        while True:
            raw = await reader.readline()
            if not raw:
                break
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if msg.get("type") == "heartbeat":
                agents[aid]["seen"] = time.time()
                items = agents[aid]["outbox"]
                agents[aid]["outbox"] = []
                writer.write(
                    (json.dumps({"type": "tasks", "items": items}) + "\n").encode()
                )
                await writer.drain()
            elif msg.get("type") == "result":
                entry = {
                    "ts": time.strftime("%H:%M:%S"),
                    "agent": aid,
                    "task_id": msg.get("task_id"),
                    "kind": msg.get("kind"),
                    "ok": msg.get("ok", False),
                    "data": msg.get("data"),
                }
                results.append(entry)
                if entry["kind"] == "loadgen" and isinstance(entry["data"], dict):
                    tid = str(entry["data"].get("test_id", ""))[:8]
                    if tid in tests:
                        tests[tid]["done"] += 1
                        if tests[tid]["done"] >= tests[tid]["expected"]:
                            tests[tid]["status"] = "complete"
                            log("test_completed", test_id=tid)
                ui.res(
                    entry["agent"],
                    entry["task_id"],
                    json.dumps(entry["data"])[:300],
                    ok=entry["ok"],
                )
    except (ConnectionResetError, asyncio.IncompleteReadError):
        pass
    finally:
        agents.pop(aid, None)
        log("agent_disconnected", agent=aid)
        ui.info("agent " + aid + " gone")


async def op_conn(reader, writer):
    peer = writer.get_extra_info("peername")

    def send(t):
        writer.write((t.replace("\n", "\r\n") + "\r\n").encode())

    send("piemesh shell\ntoken: ")
    await writer.drain()

    role = None
    op_secret = str(cfg.get("operator_token", ""))
    for attempt in range(3):
        try:
            raw = await asyncio.wait_for(readline_any(reader), 45)
        except (asyncio.TimeoutError, ConnectionResetError):
            break
        supplied = raw.decode(errors="replace").strip()
        if hmac.compare_digest(supplied, op_secret) or (
            op_secret.startswith("CHANGE-ME")
            and hmac.compare_digest(supplied, cfg["enrollment_token"])
        ):
            role = "operator"
        elif hmac.compare_digest(supplied, cfg["enrollment_token"]):
            role = "member"
        if role:
            break
        log("op_auth_failed", peer=str(peer), attempt=attempt + 1)
        send("denied\ntoken: ")
        await writer.drain()

    if not role:
        log("op_locked_out", peer=str(peer))
        send("locked out")
        writer.close()
        return

    log("op_connected", peer=str(peer), role=role)
    ui.ok("%s session from %s:%s" % (role, peer[0], peer[1]))
    send(
        (
            "operator session. 'help' lists commands.\n> "
            if role == "operator"
            else "member session. contribute an agent, run verified tests. 'help' lists commands.\n> "
        )
    )
    await writer.drain()

    try:
        while True:
            try:
                raw = await asyncio.wait_for(readline_any(reader), 600)
            except (asyncio.TimeoutError, ConnectionResetError):
                break
            if not raw:
                break
            line = raw.decode(errors="replace").strip()
            keep, out = do_cmd(line, role, peer[0])
            log("op_command", peer=str(peer), role=role, command=line[:200])
            if out:
                send(out)
            if not keep:
                break
            send("> ")
            await writer.drain()
    finally:
        log("op_disconnected", peer=str(peer), role=role)
        ui.info("%s left" % role)
        writer.close()


async def local_console(loop):
    while True:
        try:
            line = await loop.run_in_executor(None, input, ui.prompt())
        except EOFError:
            await asyncio.sleep(3600)
            continue
        keep, out = do_cmd(line, "operator", "127.0.0.1")
        if out:
            print(out)
        if not keep:
            for r in agents.values():
                r["writer"].close()
            log("server_shutdown")
            ui.warn("hub shut down - audit trail in audit.log")
            loop.stop()
            return


async def main():
    certs = here / "certs"
    for f in ("ca.crt", "server.crt", "server.key"):
        if not (certs / f).exists():
            raise SystemExit("certs missing, run gencert.py first")

    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.minimum_version = ssl.TLSVersion.TLSv1_3
    tls.load_cert_chain(certs / "server.crt", certs / "server.key")

    ap = await asyncio.start_server(agent_conn, "0.0.0.0", cfg["listen_port"], ssl=tls)
    op = await asyncio.start_server(
        op_conn, cfg.get("operator_bind", "127.0.0.1"), cfg.get("operator_port", 4443)
    )

    solo = str(cfg.get("operator_token", "")).startswith("CHANGE-ME")
    ui.banner(
        "PieMesh hub",
        [
            ("agents port", ":%d (TLS 1.3)" % cfg["listen_port"]),
            (
                "shell port",
                ":%s on %s"
                % (
                    cfg.get("operator_port", 4443),
                    cfg.get("operator_bind", "127.0.0.1"),
                ),
            ),
            ("mode", "solo (join token = operator)" if solo else "member mesh"),
            (
                "caps",
                "%ds/test, %d rps, %d nodes/test"
                % (
                    cfg.get("max_test_duration_s", 300),
                    cfg.get("max_test_rps", 200),
                    cfg.get("max_agents_per_test", 10),
                ),
            ),
            ("audit trail", "audit.log"),
        ],
    )
    ui.info("'help' lists commands")
    loop = asyncio.get_running_loop()
    log("server_start", port=cfg["listen_port"])
    asyncio.create_task(local_console(loop))
    async with ap, op:
        await asyncio.gather(ap.serve_forever(), op.serve_forever())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError:
        pass
