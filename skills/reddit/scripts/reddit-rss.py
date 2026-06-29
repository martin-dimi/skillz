#!/usr/bin/env python3
"""Fetch and distill Reddit via .rss feeds.

Reddit's .json / old.reddit API now returns 403 for anonymous requests, but the
.rss feed on every URL still works. This fetches that feed, parses the Atom XML,
strips it to plain text, prints a compact preview and writes the FULL distilled
thread to a temp file so large threads never blow up the context window.

Examples:
  reddit-rss.py r/reactnative                     # top posts this month
  reddit-rss.py r/reactnative --sort hot          # what's hot right now
  reddit-rss.py <post-url>                         # post + top 255 comments
  reddit-rss.py -q "expo router" r/reactnative     # search inside a sub
  reddit-rss.py -q "best orm" --sort top -t year   # search all of reddit
  reddit-rss.py u/spez                            # a user's recent activity

Notes / limitations of RSS (document, don't fight):
  - No vote/score numbers exist in the feed. --sort top still orders by
    popularity, you just don't see the points.
  - Comments come back flat (no thread nesting).
"""
import argparse
import html
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ATOM = "{http://www.w3.org/2005/Atom}"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 reddit-rss-skill/1.0"
LISTINGS = {"hot", "new", "top", "rising", "controversial", "best"}
TAG_RE = re.compile(r"<[^>]+>")


def sub_from(target):
    t = re.sub(r"\.(rss|json)$", "", target.strip("/"))
    if t.startswith("http"):
        t = urllib.parse.urlparse(t).path.strip("/")
    m = re.match(r"r/([^/]+)", t)
    return m.group(1) if m else t.split("/")[0]


def build_url(target, q, sort, t, limit, restrict):
    base = "https://www.reddit.com"
    if q:
        sub = sub_from(target) if target else None
        path = f"/r/{sub}/search" if sub else "/search"
        p = {"q": q, "sort": sort or "relevance", "limit": limit, "t": t,
             "include_over_18": "on", "self": "on"}
        if sub and restrict:
            p["restrict_sr"] = "1"
        return f"{base}{path}.rss?{urllib.parse.urlencode(p)}", ("search", sub or "all")

    path = target
    if target.startswith("http"):
        path = urllib.parse.urlparse(target).path
    path = "/" + path.strip("/")
    path = re.sub(r"\.(rss|json)$", "", path)
    segs = [s for s in path.split("/") if s]

    if "comments" in segs:
        i = segs.index("comments")
        pid = segs[i + 1] if len(segs) > i + 1 else "post"
        url = f"{base}{path}.rss?" + urllib.parse.urlencode({"sort": sort or "top", "limit": limit})
        return url, ("comments", pid)

    if segs and segs[0] in ("u", "user"):
        name = segs[1]
        url = f"{base}/user/{name}.rss?" + urllib.parse.urlencode({"sort": sort or "new", "limit": limit})
        return url, ("user", name)

    sub = sub_from(path)
    listing = sort or (segs[2] if len(segs) >= 3 and segs[0] == "r" and segs[2] in LISTINGS else "top")
    p = {"limit": limit}
    if listing in ("top", "controversial"):
        p["t"] = t
    url = f"{base}/r/{sub}/{listing}.rss?" + urllib.parse.urlencode(p)
    return url, ("listing", sub)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/atom+xml"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            if data:
                return data
        except urllib.error.HTTPError as e:
            if e.code == 429:
                if attempt < 3:
                    time.sleep((attempt + 1) * 5)
                    continue
                sys.exit("HTTP 429: Reddit is rate-limiting. Wait ~30s and space requests out "
                         "(make Reddit calls one at a time, never in parallel).")
            body = e.read()[:200].decode("utf-8", "replace")
            sys.exit(f"HTTP {e.code} fetching feed.\n{body}")
        except urllib.error.URLError as e:
            sys.exit(f"network error: {e.reason}")
        time.sleep((attempt + 1) * 3)
    sys.exit("empty response after retries (rate limited - wait a few seconds and retry)")


def to_text(raw):
    if not raw:
        return ""
    s = re.sub(r"<!--.*?-->", "", raw, flags=re.S)
    s = re.sub(r"(?i)</(p|div|li|tr|h[1-6]|blockquote|pre)>", "\n", s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)<li[^>]*>", "\n- ", s)
    s = TAG_RE.sub("", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = "\n".join(line.strip() for line in s.splitlines())
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def clean_snippet(s):
    s = re.sub(r"submitted by\s+/u/\S+.*", "", s, flags=re.S)
    return s.replace("[link]", "").replace("[comments]", "").strip()


def rel_age(iso):
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso or "?"
    secs = (datetime.now(timezone.utc) - dt).total_seconds()
    for unit, n in (("y", 31536000), ("mo", 2592000), ("d", 86400), ("h", 3600), ("m", 60)):
        if secs >= n:
            return f"{int(secs // n)}{unit}"
    return "now"


def parse(data):
    root = ET.fromstring(data)
    feed_title = (root.findtext(ATOM + "title") or "").strip()
    entries = []
    for e in root.findall(ATOM + "entry"):
        eid = e.findtext(ATOM + "id") or ""
        kind = "post" if eid.startswith("t3_") else "comment" if eid.startswith("t1_") else "other"
        link = ""
        for l in e.findall(ATOM + "link"):
            href = l.get("href", "")
            if l.get("rel") is None:
                link = href
                break
            if l.get("rel") == "alternate" and not link:
                link = href
        entries.append({
            "kind": kind,
            "author": (e.findtext(f"{ATOM}author/{ATOM}name") or "").lstrip("/").replace("u/", "u/"),
            "title": (e.findtext(ATOM + "title") or "").strip(),
            "age": rel_age(e.findtext(ATOM + "updated") or ""),
            "link": link.split("?")[0],
            "text": to_text(e.findtext(ATOM + "content") or ""),
        })
    return feed_title, entries


def clip(s, n):
    s = s.strip()
    if n is None or len(s) <= n:
        return s
    return s[:n].rstrip() + f" …(+{len(s) - n} chars)"


def indent(s):
    return "\n".join("    " + ln for ln in s.splitlines())


def render(mode, ident, feed_title, entries, width, show, full_path, total):
    if full:
        width, show = None, None
    out = []
    if mode == "comments":
        post = next((e for e in entries if e["kind"] == "post"), None)
        comments = [e for e in entries if e["kind"] == "comment"]
        out.append(f"# {feed_title}")
        if post:
            out.append(f"OP {post['author']} · {post['age']} · {post['link']}")
            body = clip(clean_snippet(post["text"]), None if width is None else width * 3)
            if body:
                out.append(indent(body))
        out.append("")
        shown = comments if show is None else comments[:show]
        out.append(f"{len(comments)} comments · sorted by popularity (RSS has no score numbers)"
                   f" · showing {len(shown)} of {len(comments)}")
        out.append("─" * 60)
        for i, c in enumerate(comments, 1):
            if show is not None and i > show:
                break
            out.append(f"[{i}] {c['author']} · {c['age']}")
            out.append(indent(clip(c["text"], width)))
            out.append("")
    else:
        label = {"listing": f"r/{ident}", "search": f"search: {ident}", "user": f"u/{ident}"}[mode]
        out.append(f"# {feed_title} — {label} · {total} items · showing "
                   f"{total if show is None else min(show, total)}")
        out.append("─" * 60)
        for i, e in enumerate(entries, 1):
            if show is not None and i > show:
                break
            head = e["title"] or "(comment)"
            out.append(f"[{i}] {head}")
            out.append(f"    {e['author']} · {e['age']} · {e['link']}")
            snip = clean_snippet(e["text"])
            if snip:
                out.append(indent(clip(snip, width)))
            out.append("")
    out.append(f"full distilled output ({total} items): {full_path}")
    return "\n".join(out)


def write_full(mode, ident, feed_title, entries, path):
    lines = [f"# {feed_title}  [{mode}: {ident}]  ({len(entries)} entries)", ""]
    if mode == "comments":
        post = next((e for e in entries if e["kind"] == "post"), None)
        comments = [e for e in entries if e["kind"] == "comment"]
        if post:
            lines += [f"OP {post['author']} · {post['age']} · {post['link']}",
                      clean_snippet(post["text"]), "", "=" * 60, ""]
        for i, c in enumerate(comments, 1):
            lines += [f"[{i}] {c['author']} · {c['age']} · {c['link']}", c["text"], ""]
    else:
        for i, e in enumerate(entries, 1):
            body = clean_snippet(e["text"]) if mode != "user" else e["text"]
            lines += [f"[{i}] {e['title'] or '(comment)'}",
                      f"    {e['author']} · {e['age']} · {e['link']}", body, ""]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description="Fetch & distill Reddit via .rss")
    ap.add_argument("target", nargs="?", default="", help="reddit URL, r/sub, or u/user")
    ap.add_argument("-q", "--search", default="", help="search query (target = sub to restrict to)")
    ap.add_argument("--sort", default=None, help="comments: top/new/best/controversial/old/qa · "
                                                 "listing: hot/new/top/rising · search: relevance/top/new/comments")
    ap.add_argument("-t", "--time", default="month", help="window for top: hour/day/week/month/year/all (default month)")
    ap.add_argument("-n", "--limit", type=int, default=None, help="how many to fetch (comments 255, else 100)")
    ap.add_argument("--show", type=int, default=None, help="how many to print (comments 30, else 40)")
    ap.add_argument("--width", type=int, default=None, help="chars per body in preview (default 500/240)")
    ap.add_argument("--no-restrict", action="store_true", help="search all of reddit even when a sub is given")
    ap.add_argument("--full", action="store_true", help="print everything, untruncated")
    ap.add_argument("--url", action="store_true", help="just print the resolved .rss url and exit")
    args = ap.parse_args()

    if not args.target and not args.search:
        ap.error("give a target (r/sub, u/user, or a reddit URL) or -q QUERY")

    global full
    full = args.full

    probe_url, (mode, _) = build_url(args.target, args.search, args.sort, args.time, 1, not args.no_restrict)
    is_comments = mode == "comments"
    limit = args.limit if args.limit is not None else (255 if is_comments else 100)
    show = args.show if args.show is not None else (30 if is_comments else 40)
    width = args.width if args.width is not None else (500 if is_comments else 240)

    url, (mode, ident) = build_url(args.target, args.search, args.sort, args.time, limit, not args.no_restrict)
    if args.url:
        print(url)
        return

    feed_title, entries = parse(fetch(url))
    if not entries:
        sys.exit(f"feed had no entries: {url}")

    slug = re.sub(r"[^a-z0-9]+", "-", f"{mode}-{ident}".lower()).strip("-")
    full_path = os.path.join(tempfile.gettempdir(), "reddit-rss", f"{slug}.txt")
    write_full(mode, ident, feed_title, entries, full_path)

    total = sum(1 for e in entries if e["kind"] == "comment") if is_comments else len(entries)
    print(render(mode, ident, feed_title, entries, width, show, full_path, total))


if __name__ == "__main__":
    main()
