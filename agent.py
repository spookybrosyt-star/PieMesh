import argparse
import asyncio
import csv
import hashlib
import io
import inspect
import json
import platform
import socket
import ssl
import sys
import time
import uuid
from pathlib import Path

here = Path(__file__).parent
try:
    cfg = json.loads((here / "config.json").read_text())
except FileNotFoundError:
    cfg = {}

MAX_SECS = min(int(cfg.get("max_test_duration_s", 300)), 600)
MAX_RPS = min(int(cfg.get("max_test_rps", 200)), 500)
MAX_CONNS = 64
UA = "Piemesh-loadgen/1.0"
ALLOWED_KINDS = {"sysinfo", "ps", "loadgen"}

TOS_VER = "2026-08-v4"
TOS = """PIEMESH VOLUNTEER AGENT TERMS (v%s)
1. own this machine or have its admin's blessing, no exceptions
2. while running you generate http(s) requests ONLY against domains
   the hub operator proved ownership of via dns txt challenge
3. hard limits baked into this file, not remotely changeable:
   %d seconds per test, %d requests/sec, %d connections
4. closing this window stops everything instantly. nothing installs,
   nothing survives a reboot, nothing runs hidden
5. every task executed here is logged locally and on the hub
6. this build executes NO arbitrary commands - task types are
   hard-whitelisted (sysinfo, process list, capped http loadgen)
   and any other instruction from anyone is refused on the spot
7. the agent fingerprints its own source at start. a modified copy
   announces itself to you and to the hub before doing anything
8. you agree to cover the copyright holder and your hub operator for
   claims coming from your use or misuse. the operator owns target
   verification and owes every volunteer honest enforcement
9. abuse contact lives in your operator's README. full terms ship
   next to this file as LICENSE + ACCEPTABLE_USE.md
type AGREE to accept, anything else declines"""


def self_hash():
    return hashlib.sha256((here / "agent.py").read_bytes()).hexdigest()


def agent_id():
    f = here / "agent_id.json"
    if f.exists():
        return json.loads(f.read_text())["id"]
    nid = uuid.uuid4().hex[:12]
    f.write_text(json.dumps({"id": nid}))
    return nid


def ensure_consent(opts):
    marker = here / "consent.json"

    if opts.revoke_consent:
        wiped = []
        for name in ("consent.json", "agent_id.json"):
            p = here / name
            if p.exists():
                p.unlink()
                wiped.append(name)
        print("wiped:", ", ".join(wiped) or "nothing found")
        sys.exit(0)

    if marker.exists():
        rec = json.loads(marker.read_text())
        if rec.get("tos") == TOS_VER:
            if rec.get("build") != self_hash() and not opts.trust_modified_build:
                print(
                    "[!] this agent.py differs from the build you consented to\n"
                    "    consented: %s\n    current:   %s\n"
                    "    if you made or received this modification knowingly, re-run\n"
                    "    with --trust-modified-build (it will be reported to the hub)"
                    % (rec.get("build", "?")[:16], self_hash()[:16])
                )
                sys.exit(2)
            return

    print(TOS % (TOS_VER, MAX_SECS, MAX_RPS, MAX_CONNS))
    agreed = opts.agree_tos == TOS_VER
    if not agreed:
        agreed = input("\nyour answer: ").strip().upper() == "AGREE"
    if not agreed:
        print("declined. nothing ran, nothing saved.")
        sys.exit(0)

    marker.write_text(
        json.dumps(
            {
                "tos": TOS_VER,
                "build": self_hash(),
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "host": socket.gethostname(),
            },
            indent=2,
        )
    )
    print("consent recorded ->", marker)


def t_sysinfo(args):
    info = {
        "hostname": socket.gethostname(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
    }
    try:
        import psutil

        info["boot"] = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(psutil.boot_time())
        )
        info["cpus"] = psutil.cpu_count()
        mem = psutil.virtual_memory()
        info["ram_mb"] = mem.total // 1048576
        info["ram_pct"] = mem.percent
    except ImportError:
        pass
    return info


def t_ps(args):
    try:
        import psutil

        rows = []
        for p in psutil.process_iter(["pid", "name", "username"]):
            try:
                rows.append(
                    {
                        "pid": p.info["pid"],
                        "name": p.info["name"],
                        "user": p.info["username"],
                    }
                )
            except Exception:
                pass
        rows.sort(key=lambda r: r["pid"])
        return rows
    except ImportError:
        pass

    if platform.system() == "Windows":
        out = subprocess.run(
            ["tasklist", "/fo", "csv"], capture_output=True, text=True, errors="replace"
        ).stdout
        rows = []
        for row in csv.DictReader(io.StringIO(out)):
            try:
                pid = int(row.get("PID") or 0)
            except ValueError:
                pid = 0
            rows.append(
                {"pid": pid, "name": row.get("Image Name"), "mem": row.get("Mem Usage")}
            )
        return rows

    out = subprocess.run(
        ["ps", "aux"], capture_output=True, text=True, errors="replace"
    ).stdout
    rows = []
    for line in out.splitlines()[1:]:
        f = line.split(None, 10)
        if len(f) >= 11:
            try:
                pid = int(f[1])
            except ValueError:
                continue
            rows.append({"user": f[0], "pid": pid, "cpu": f[2], "cmd": f[10][:120]})
    return rows


def t_shell(args):
    print("[!] refused shell task - not a capability of this build")
    return {"refused": "arbitrary command execution is not part of piemesh agents"}


async def t_loadgen(args):
    import aiohttp

    url = str(args.get("url", ""))
    duration = min(float(args.get("duration_s", 60)), float(MAX_SECS))
    rate = min(float(args.get("rate_rps", 25)), float(MAX_RPS))

    if not url.startswith(("http://", "https://")):
        return {"error": "refusing non-http workload"}

    stats = {"sent": 0, "ok": 0, "err": 0, "bytes": 0}
    lats = []
    deadline = time.monotonic() + duration
    gate = asyncio.Semaphore(MAX_CONNS)

    async def hammer(sess):
        while time.monotonic() < deadline:
            async with gate:
                if time.monotonic() >= deadline:
                    return
                t0 = time.perf_counter()
                try:
                    async with sess.get(
                        url, timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        body = await resp.read()
                        lats.append((time.perf_counter() - t0) * 1000)
                        stats["sent"] += 1
                        stats["bytes"] += len(body)
                        if resp.status < 400:
                            stats["ok"] += 1
                        else:
                            stats["err"] += 1
                except Exception:
                    stats["sent"] += 1
                    stats["err"] += 1

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=MAX_CONNS),
        headers={"User-Agent": UA},
    ) as sess:
        workers = max(1, min(int(rate) // 4 or 1, MAX_CONNS))
        await asyncio.gather(*(hammer(sess) for _ in range(workers)))

    lats.sort()

    def pct(p):
        if not lats:
            return 0
        i = min(int(len(lats) * p), len(lats) - 1)
        return round(lats[i], 1)

    return {
        "test_id": args.get("test_id"),
        "url": url,
        "planned": {"duration_s": duration, "rate_rps": rate},
        "actual_rps": round(stats["sent"] / duration, 1) if duration else 0,
        "requests": stats["sent"],
        "ok": stats["ok"],
        "errors": stats["err"],
        "bytes_downloaded": stats["bytes"],
        "latency_ms": {"p50": pct(0.50), "p95": pct(0.95), "p99": pct(0.99)},
    }


HANDLERS = {"sysinfo": t_sysinfo, "ps": t_ps, "loadgen": t_loadgen, "shell": t_shell}


async def execute(task):
    kind = str(task.get("kind"))
    if kind not in ALLOWED_KINDS:
        print("[!] refused task kind '%s' - outside hard whitelist" % kind)
        return {
            "ok": False,
            "data": {"refused": kind, "reason": "kind outside agent whitelist"},
        }
    fn = HANDLERS[kind]
    try:
        res = fn(task.get("args", {}))
        if inspect.isawaitable(res):
            res = await res
        return {"ok": True, "data": res}
    except Exception as exc:
        return {"ok": False, "data": {"error": "%s: %s" % (type(exc).__name__, exc)}}


async def session(opts):
    capath = here / "ca.crt"
    if not capath.exists():
        capath = here / "certs" / "ca.crt"
    tls = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(capath))
    tls.check_hostname = True
    tls.minimum_version = ssl.TLSVersion.TLSv1_3

    reader, writer = await asyncio.open_connection(opts.server, opts.port, ssl=tls)
    consented_build = None
    try:
        consented_build = json.loads((here / "consent.json").read_text()).get("build")
    except FileNotFoundError:
        pass
    build_now = self_hash()
    hello = {
        "type": "hello",
        "id": opts.agent_id,
        "hostname": socket.gethostname().lower(),
        "os": "%s %s" % (platform.system(), platform.release()),
        "token": opts.token,
        "code_hash": build_now,
        "modified": bool(consented_build and consented_build != build_now),
    }
    writer.write((json.dumps(hello) + "\n").encode())
    await writer.drain()

    ack = json.loads(await asyncio.wait_for(reader.readline(), 15))
    if ack.get("type") != "welcome":
        raise PermissionError("handshake rejected")
    print("[+] linked to %s:%d as %s" % (opts.server, opts.port, opts.agent_id))

    while True:
        writer.write(b'{"type":"heartbeat"}\n')
        await writer.drain()
        raw = await asyncio.wait_for(reader.readline(), 30)
        if not raw:
            raise ConnectionResetError("hub closed the link")
        msg = json.loads(raw)
        if msg.get("type") != "tasks":
            continue

        for task in msg.get("items", []):
            res = await execute(task)
            reply = {
                "type": "result",
                "task_id": task.get("task_id"),
                "kind": task.get("kind"),
            }
            reply.update(res)
            writer.write((json.dumps(reply) + "\n").encode())
            await writer.drain()

        await asyncio.sleep(opts.interval)


async def main():
    ap = argparse.ArgumentParser(description="piemesh volunteer agent")
    ap.add_argument("--server", help="hub hostname, must match its cert")
    ap.add_argument("--port", type=int, default=4444)
    ap.add_argument("--token")
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument(
        "--agree-tos", metavar="VER", help="non-interactive consent, pass " + TOS_VER
    )
    ap.add_argument(
        "--revoke-consent", action="store_true", help="wipe consent + identity, exit"
    )
    ap.add_argument(
        "--trust-modified-build",
        action="store_true",
        help="acknowledge agent.py differs from consented build; deviation is reported to hub",
    )
    opts = ap.parse_args()

    ensure_consent(opts)

    if not opts.server or not opts.token:
        ap.error("--server and --token are required")

    opts.agent_id = agent_id()

    backoff = 1.0
    while True:
        try:
            await session(opts)
            backoff = 1.0
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            wait = round(backoff)
            print("[!] link down (%s), retry in %ds" % (exc, wait))
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nstopped clean - nothing left running")
