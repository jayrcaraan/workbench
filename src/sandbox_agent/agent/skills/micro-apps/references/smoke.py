"""
Smoke test for an app you just started, in ONE command (replaces start-wait-curl-retry loops).

    python smoke.py <port> [route ...]          e.g.  python smoke.py 8000 /health /items

Waits up to 30 s for the port to answer, then GETs each route (default "/") and prints
status + the first 200 characters. Exit code 0 only if every route returned < 400.
Run it inside the sandbox; it talks to localhost.
"""

import sys
import time
import urllib.error
import urllib.request


def get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status, r.read(200).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(200).decode("utf-8", "replace")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    port, routes = sys.argv[1], sys.argv[2:] or ["/"]
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    while True:
        try:
            get(base + "/")
            break
        except OSError as e:
            if time.time() > deadline:
                print(f"FAIL: nothing is listening on :{port} after 30s ({e}). Read the app's log file.")
                return 1
            time.sleep(1)
    bad = 0
    for route in routes:
        status, body = get(base + route)
        flag = "ok  " if status < 400 else "FAIL"
        bad += status >= 400
        print(f"{flag} {status} {route}  {body!r}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
