"""Shared Muse fixtures for the G-MUS tests (P08)."""

PARENT = "01a1d722-3e08-78b3-8ef6-9624efa87d7e"
FORK = "00000000-0000-7e89-a143-57729763e0d9"

# A fake `muse` executable. `serve` speaks newline-delimited JSON-RPC the way
# Muse 1.4.20 did in the P08 probes: `initialize`, then the `initialized`
# notification, then `session/fork` and `session/leave`. FAKE_MUSE_MODE picks
# a behavior; every message received is appended to FAKE_MUSE_LOG.
FAKE_MUSE = r"""#!/usr/bin/env python3
import json, os, sys, time
mode = os.environ.get("FAKE_MUSE_MODE", "ok")
log = os.environ.get("FAKE_MUSE_LOG")
args = sys.argv[1:]
if args == ["--version"]:
    print(os.environ.get("FAKE_MUSE_VERSION", "Muse Code 1.4.20 (1.4.20-R8619.1)"))
    sys.exit(0)
if args == ["--help"]:
    print(os.environ.get("FAKE_MUSE_HELP",
        "Commands:\n  resume  Resume a previous session\n  serve  Serve an MSP session host"))
    sys.exit(0)
if args == ["sessions", "--json"]:
    print(os.environ.get("FAKE_MUSE_SESSIONS", '{"sessions":[]}'))
    sys.exit(0)
if args != ["serve"]:
    sys.exit(64)
fork_id = os.environ.get("FAKE_MUSE_FORK_ID", "00000000-0000-7e89-a143-57729763e0d9")
def out(obj):
    sys.stdout.write(json.dumps(obj) + "\n"); sys.stdout.flush()
for line in sys.stdin:
    message = json.loads(line)
    if log:
        with open(log, "a") as handle:
            handle.write(json.dumps(message) + "\n")
    method, ident = message.get("method"), message.get("id")
    if method == "initialize":
        if mode == "exit":
            sys.exit(3)
        out({"jsonrpc": "2.0", "id": ident, "result": {"serverInfo": {"name": "muse"}}})
    elif method == "session/fork":
        if mode == "error":
            out({"jsonrpc": "2.0", "id": ident,
                 "error": {"code": -32011, "message": "session not found"}})
        elif mode == "malformed":
            sys.stdout.write("not-json\n"); sys.stdout.flush()
        elif mode == "hang":
            time.sleep(30)
        elif mode == "big":
            sys.stdout.write("x" * 3_000_000); sys.stdout.flush()
        else:
            out({"jsonrpc": "2.0", "method": "session/started", "params": {}})
            sid = "not a uuid; rm -rf" if mode == "badid" else fork_id
            out({"jsonrpc": "2.0", "id": ident, "result": {
                "session": {"sessionId": sid, "workspaceRoot": "/parent",
                            "forkedFrom": {"sessionId": message["params"]["sessionId"]}},
                "history": {}, "pendingRequests": [], "viewCursor": "v"}})
    elif method == "session/leave":
        out({"jsonrpc": "2.0", "id": ident, "result": {"status": "accepted"}})
if mode == "linger":
    time.sleep(30)
"""
