---
name: reddit
description: Read or research anything on Reddit - subreddits, a post + its comments, search across reddit or inside a sub, or a user's activity. Uses Reddit's .rss feeds, which still work where the .json / old.reddit API now returns 403. Distills feeds to compact text and writes the full thread to a temp file so big threads don't blow up context. Use whenever researching a topic that has Reddit discussion, gathering opinions/sentiment, reading a reddit.com URL, or when a web search surfaces Reddit links.
user-invocable: true
---

# Reddit (via .rss)

Reddit's `.json` and `old.reddit.com` APIs now return **403** for anonymous requests, so don't reach for them. Every Reddit URL still serves an Atom feed if you append `.rss` - that's the reliable path. This skill wraps that: fetch → parse → strip to plain text → print a compact preview → write the **full** distilled output to a temp file.

## Usage

```bash
python3 ~/.claude/skills/reddit/scripts/reddit-rss.py <target> [options]
```

`<target>` is a reddit URL, `r/sub`, or `u/user`. Common recipes:

```bash
# Subreddit - defaults to TOP of the MONTH (good for research)
reddit-rss.py r/reactnative
reddit-rss.py r/reactnative --sort hot            # what's active right now
reddit-rss.py r/reactnative --sort top -t year    # widen the window

# A post + its comments (defaults: sort=top, 255 comments)
reddit-rss.py "https://www.reddit.com/r/reactnative/comments/1ska1cv/...."

# Search inside a sub, or across all of reddit
reddit-rss.py -q "expo router" r/reactnative
reddit-rss.py -q "best local-first db" --sort top -t year

# A user's recent posts + comments
reddit-rss.py u/spez
```

## How to use the output without blowing up context

- **stdout is a preview**: a header plus the first `--show` items (30 comments / 40 listing entries), each body clipped to `--width`. Read this first.
- The script always writes the **full, untruncated** thread to `$TMPDIR/reddit-rss/<slug>.txt` and prints the path. The `[N]` indices in the preview match the file.
- To go deeper, **don't re-fetch and don't dump the whole file** - `grep -n "keyword"` it, or `Read` it with an offset. Pull only the comments you need.
- `--full` prints everything untruncated (use sparingly - that's the context bomb you're avoiding).

## Options

| flag | meaning | default |
|------|---------|---------|
| `--sort` | comments: top/new/best/controversial/old/qa · listing: hot/new/top/rising · search: relevance/top/new/comments | top (comments/listing), relevance (search) |
| `-t, --time` | window for `top`: hour/day/week/month/year/all | `month` |
| `-n, --limit` | how many to **fetch** | 255 comments, 100 else |
| `--show` | how many to **print** | 30 comments, 40 else |
| `--width` | chars per body in the preview | 500 comments, 240 else |
| `--no-restrict` | search all of reddit even when a sub is given | off |
| `--full` | print everything, untruncated | off |
| `--url` | just print the resolved `.rss` URL and exit | off |

## Limitations (RSS, not the script)

- **No score/vote numbers** - they don't exist in the feed. `--sort top` still orders by popularity; you just won't see the points.
- **Comments are flat** - no thread nesting / parent-child structure.
- Listings hard-cap at **100** per request; comment feeds go higher (255+ fine).
- Good for: discovery, sentiment, reading discussion. Not for: exact vote ranking or reconstructing deep reply trees.

## Rate limiting

Reddit rate-limits anonymous RSS aggressively. **Make calls one at a time, never in parallel.** The script retries 429s with backoff; if it still fails, wait ~30s before the next call.
