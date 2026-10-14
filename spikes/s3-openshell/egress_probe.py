"""Runs INSIDE an OpenShell sandbox. Tries to reach things the policy forbids (and one it allows) and prints one result
line per test: `<id> <expect> <OPEN|BLOCKED> <detail>`. Policy: only /usr/bin/curl may reach openrouter.ai:443.
Placeholders replaced by run_egress.sh: __LAN_GW__ (host's LAN gateway)."""
import json, os, socket, subprocess, sys, time

LAN_GW = "__LAN_GW__"
PG_IP = "__PG_IP__"  # a neighbouring Docker container (Postgres) on the Docker bridge network


def sh(cmd, timeout=12):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def curl_code(args):
    rc, out = sh(f"curl -s -m 8 -o /dev/null -w '%{{http_code}}' {args}")
    code = out.split()[-1] if out else "000"
    return ("OPEN" if code.startswith(("2", "3", "4")) and code != "000" else "BLOCKED"), f"http={code} rc={rc}"


def tcp(host, port, timeout=4):
    t0 = time.time()
    try:
        s = socket.create_connection((host, port), timeout=timeout); s.close()
        return "OPEN", f"connected in {time.time()-t0:.2f}s"
    except OSError as e:
        return "BLOCKED", f"{type(e).__name__}: {e.strerror or e}"[:70]


def udp_dns(server):
    q = b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07example\x03com\x00\x00\x01\x00\x01"
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(3)
    try:
        s.sendto(q, (server, 53)); data, _ = s.recvfrom(512)
        return "OPEN", f"got {len(data)} bytes"
    except OSError as e:
        return "BLOCKED", f"{type(e).__name__}: {e.strerror or e}"[:70]
    finally:
        s.close()


def py_https(host):
    rc, out = sh(f"python3 -c \"import urllib.request;print(urllib.request.urlopen('https://{host}',timeout=6).status)\"")
    return ("OPEN" if out.strip().endswith("200") else "BLOCKED"), (out.splitlines()[-1][:70] if out else f"rc={rc}")


def resolve(name):
    try:
        return "INFO", f"{name} -> {socket.gethostbyname(name)}"
    except OSError as e:
        return "INFO", f"{name} -> {type(e).__name__}"


tests = [
    ("T01", "allow", "curl -> allowed host openrouter.ai:443", lambda: curl_code("https://openrouter.ai/api/v1/models")),
    ("T02", "block", "curl -> denied host example.com", lambda: curl_code("https://example.com")),
    ("T03", "allow", "curl --noproxy -> allowed host (no proxy env)", lambda: curl_code("--noproxy '*' https://openrouter.ai/api/v1/models")),
    ("T04", "block", "curl --noproxy -> denied host (proxy bypass attempt)", lambda: curl_code("--noproxy '*' https://example.com")),
    ("T05", "block", "curl -> IP literal 1.1.1.1:443", lambda: curl_code("-k https://1.1.1.1")),
    ("T06", "block", "python (not an allowed binary) -> openrouter.ai", lambda: py_https("openrouter.ai")),
    ("T07", "block", "raw TCP python -> 1.1.1.1:443", lambda: tcp("1.1.1.1", 443)),
    ("T08", "block", "UDP DNS python -> 8.8.8.8:53 (DNS exfil path)", lambda: udp_dns("8.8.8.8")),
    ("T09", "block", "TCP -> host 127.0.0.1:5432 (Mac's Postgres)", lambda: tcp("127.0.0.1", 5432)),
    ("T10", "block", "TCP -> host.docker.internal:5432", lambda: tcp("host.docker.internal", 5432)),
    ("T11", "block", "TCP -> host.openshell.internal:5432", lambda: tcp("host.openshell.internal", 5432)),
    ("T12", "block", "TCP -> OpenShell gateway 127.0.0.1:17670", lambda: tcp("127.0.0.1", 17670)),
    ("T13", "block", f"TCP -> home LAN gateway {LAN_GW}:80", lambda: tcp(LAN_GW, 80)),
    ("T14", "block", "TCP -> cloud metadata 169.254.169.254:80", lambda: tcp("169.254.169.254", 80)),
    ("T18", "block", f"TCP -> neighbouring container Postgres {PG_IP}:5432 (Docker bridge)", lambda: tcp(PG_IP, 5432)),
    ("T19", "block", "TCP -> Docker Desktop VM internals 192.168.65.254:80", lambda: tcp("192.168.65.254", 80)),
    ("T15", "info", "DNS: resolve example.org", lambda: resolve("example.org")),
    ("T16", "info", "network interfaces visible", lambda: ("INFO", ",".join(n for _, n in socket.if_nameindex()))),
    ("T17", "info", "env proxy vars", lambda: ("INFO", ",".join(k for k in os.environ if "proxy" in k.lower()) or "none")),
]
results = []
for tid, expect, desc, fn in tests:
    status, detail = fn()
    ok = "" if expect == "info" else ("PASS" if (expect == "allow") == (status == "OPEN") else "LEAK" if status == "OPEN" else "FAIL")
    results.append({"id": tid, "expect": expect, "status": status, "verdict": ok, "desc": desc, "detail": detail})
    print(f"{tid} {expect:5s} {status:7s} {ok:5s} {desc} | {detail}", flush=True)
print("JSON " + json.dumps(results))
