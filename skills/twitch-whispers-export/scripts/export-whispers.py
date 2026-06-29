#!/usr/bin/env python3
"""
Export all retained Twitch whispers via the private web GQL API.

The Twitch web inbox lists whisper threads through a single persisted GQL query
(`Whispers_Whispers_UserWhisperThreads`) that *embeds* the messages in each
thread. So one paginated query gets every retained thread + its messages - no
per-thread message fetch needed.

Usage:
  1. Log into twitch.tv, click the whispers/messages icon, open any thread.
  2. DevTools -> Network -> filter "gql" -> click a thread to fire a request.
  3. Right-click the `gql` request -> Copy -> Copy as cURL. Save it to a file.
  4. python3 export-whispers.py <curl-file> [out-dir]   # out-dir defaults to ./whispers

Auth headers + the persisted-query hash are parsed straight out of the cURL, so
nothing is hardcoded. The `client-integrity` token is short-lived (~30-60 min) -
capture a fresh cURL right before running.
"""
import json, os, re, sys, time, urllib.request

GQL = "https://gql.twitch.tv/gql"
PAGE_SIZE = 10  # Twitch returns threads in pages of 10


def parse_curl(text):
    """Pull headers + operationName + persisted-query hash out of a Copy-as-cURL blob."""
    headers = {}
    for h in re.findall(r"-H '([^']*)'", text):
        if ": " in h:
            k, v = h.split(": ", 1)
            headers[k.lower()] = v
    op = sha = None
    m = re.search(r"--data-raw '(.*)'", text, re.S)
    if m:
        try:
            body = json.loads(m.group(1))
            op = body[0]["operationName"]
            sha = body[0]["extensions"]["persistedQuery"]["sha256Hash"]
        except Exception:
            pass
    headers.pop("content-length", None)
    return headers, op, sha


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = sys.argv[2] if len(sys.argv) > 2 else "whispers"
    headers, op, sha = parse_curl(open(sys.argv[1]).read())
    if "authorization" not in headers:
        sys.exit("No authorization header found in the cURL.")
    if not op or not sha:
        sys.exit("Could not read operationName / persistedQuery hash from --data-raw.")

    def post(variables):
        body = [{"operationName": op, "variables": variables,
                 "extensions": {"persistedQuery": {"version": 1, "sha256Hash": sha}}}]
        req = urllib.request.Request(GQL, data=json.dumps(body).encode(),
                                     headers=headers, method="POST")
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())

    # Paginate the thread list. Only the last edge of each page carries a cursor;
    # feed it back as `cursor` until a page is empty / repeats.
    threads, me, cursor, page = {}, None, None, 0
    while True:
        page += 1
        cu = post({} if cursor is None else {"cursor": cursor})[0]["data"]["currentUser"]
        me = cu["id"]
        edges = cu["whisperThreads"]["edges"]
        if not edges:
            break
        for e in edges:
            threads[e["node"]["id"]] = e["node"]
        print(f"page {page}: +{len(edges)}  total {len(threads)}")
        last = edges[-1].get("cursor") or ""
        if not last or last == cursor or len(edges) < PAGE_SIZE:
            break
        cursor = last
        time.sleep(0.4)

    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "_raw.json"), "w") as f:
        json.dump(list(threads.values()), f, indent=2, ensure_ascii=False)

    safe = lambda s: re.sub(r"[^A-Za-z0-9_.-]", "_", s or "") or "unknown"
    index, truncated = [], []
    for node in threads.values():
        parts = node.get("participants", [])
        other = next((p for p in parts if p.get("id") != me), parts[0] if parts else {})
        login = other.get("login", "unknown")
        names = {p["id"]: (p.get("displayName") or p.get("login")) for p in parts}
        msgs = list(reversed([e["node"] for e in node.get("messages", {}).get("edges", [])]))
        if len(msgs) >= 40:  # a round-number wall hints the embedded list was capped
            truncated.append(login)
        lines = [f"# Whisper with {other.get('displayName', login)} (@{login})",
                 f"# thread_id: {node.get('id')} | messages: {len(msgs)}", ""]
        for m in msgs:
            sender = names.get(m.get("from", {}).get("id"), m.get("from", {}).get("id"))
            content = (m.get("content") or {}).get("content", "")
            deleted = " [deleted]" if m.get("deletedAt") else ""
            lines.append(f"[{m.get('sentAt', '')}] {sender}{deleted}: {content}")
        with open(os.path.join(out, f"{safe(login)}.txt"), "w") as f:
            f.write("\n".join(lines) + "\n")
        index.append((msgs[-1]["sentAt"] if msgs else "", login, len(msgs)))

    index.sort(reverse=True)
    with open(os.path.join(out, "INDEX.txt"), "w") as f:
        f.write(f"{len(threads)} whisper threads (newest activity first)\n\n")
        for ts, login, n in index:
            f.write(f"{ts}  {login:<28} {n} msgs\n")

    print(f"\nWrote {len(threads)} transcripts + _raw.json + INDEX.txt to {out}/")
    if truncated:
        print(f"WARNING: >=40 msgs, embedded list may be truncated: {truncated}")


if __name__ == "__main__":
    main()
