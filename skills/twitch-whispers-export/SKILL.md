---
name: twitch-whispers-export
description: Use when the user wants to export, download, back up, archive or scrape their Twitch whispers (private DMs) - e.g. "save all my twitch whispers", "export my twitch DMs to a folder", "back up my whisper history". Pulls every retained whisper thread + its messages from Twitch's private web GQL API and writes one readable transcript per conversation plus a raw JSON backup.
---

Exports a Twitch user's whispers (private DMs) to local files. There is no official Twitch export, so this drives the same private GQL API the web inbox uses.

## How it works

The web whisper inbox loads threads through one persisted GraphQL query,
`Whispers_Whispers_UserWhisperThreads`, against `https://gql.twitch.tv/gql`.
Two things make this easy:

- The thread-list query **embeds the messages** inside each thread node (newest-first), so you don't need a separate per-thread fetch.
- Threads come in **pages of 10**. Only the *last* edge of each page carries a `cursor`; feed it back as the `cursor` variable to get the next page, until a page is empty or returns < 10.

Every request needs the user's live auth headers (`authorization: OAuth ...`,
`client-id`, and `client-integrity`). These are session-bound and can't be
minted - they must be captured from the user's logged-in browser.

## Steps

1. **Capture a request.** Ask the user to:
   - Open `twitch.tv`, click the whispers/messages icon, open any thread.
   - Open DevTools -> **Network** -> filter `gql`.
   - Click a thread so a request fires -> right-click the `gql` request -> **Copy -> Copy as cURL**.
   - Paste it back (or save it to a file).

   > Note: in this harness, browsers are granted **read-only** (screenshot only) and the `auth-token` cookie is httpOnly, so you can't lift credentials yourself - the user must do this one capture step.

2. **Save the cURL** to a file, e.g. `curl.txt` in the scratchpad.

3. **Run the exporter:**
   ```bash
   python3 scripts/export-whispers.py <curl-file> [out-dir]
   ```
   `out-dir` defaults to `./whispers`. The script parses the auth headers and the
   persisted-query hash straight out of the cURL (nothing hardcoded), derives the
   user's own id from the response, paginates all threads, then writes:
   - `<login>.txt` - readable transcript per conversation, chronological, `[timestamp] sender: message`
   - `INDEX.txt` - all threads sorted by most recent activity
   - `_raw.json` - full raw API data (nothing lost)

## Caveats - tell the user

- **Retention.** Twitch does not keep whispers forever. You only get what's still
  in the inbox; older threads have aged out server-side. "All" = all currently retained.
- **Short-lived token.** The `client-integrity` token expires in ~30-60 min.
  Re-running later needs a fresh cURL capture.
- **Truncation guard.** Embedded messages are plenty for normal threads. If any
  thread has >=40 messages the script warns it *might* be capped; if so, that
  thread needs a separate paginated message fetch (not yet implemented - capture
  the in-thread scroll request and extend the script).
- **Personal data.** Output contains private DMs + user ids. If the out-dir is
  inside a git repo, add it to `.gitignore`. Don't commit it.
