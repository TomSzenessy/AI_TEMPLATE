# Social: X/Twitter, Reddit, Facebook, Instagram, V2EX, XiaoHongShu

**OpenCLI** (npm `@jackwener/opencli` plus its Chrome extension) drives the
user's open, logged-in Chrome. On a desktop it is the main backend for the
login-backed platforms here. It uses only a session the user already has.
Never log in on their behalf. Run `opencli list` and `opencli <site> --help`
to discover commands. A listed command proves only that the adapter exists,
not that it works, so verify the content (SKILL step 4).

Ask every CLI for structured output: `-f yaml` for OpenCLI, `--yaml` or
`--json` for `twitter` and `rdt`.

## X / Twitter

| Backend | Needs |
| --- | --- |
| `opencli twitter ...` | user's Chrome logged in to x.com |
| `twitter` CLI (pipx `twitter-cli` ≥ 0.8.5) | `TWITTER_AUTH_TOKEN` and `TWITTER_CT0` set by the user in this command's environment; never echo or store them |

```bash
twitter feed -n 20                  # home timeline (most stable)
twitter tweet URL_OR_ID             # one post with replies
twitter article URL_OR_ID           # long-form / X Article
twitter user-posts @username -n 20
twitter user @username
twitter search "query" -n 10        # unstable: GraphQL endpoints change
```

Search fallback chain: retry once; then run `pipx upgrade twitter-cli` and
retry (this needs approval); then `opencli twitter search "query" -f yaml`;
then work around it with `user-posts` or `feed`. Do not call it often from a
datacenter IP, because the account may be suspended. You can read only your
own likes.

## Reddit

There is no anonymous route: the `.json` endpoints return 403, and new API
apps are rarely approved.

```bash
# OpenCLI (Chrome logged in to reddit.com)
opencli reddit search "query" -f yaml
opencli reddit read POST_ID -f yaml          # post plus comments
opencli reddit subreddit LocalLLaMA -f yaml
opencli reddit subreddit-info LocalLLaMA -f yaml
opencli reddit hot -f yaml

# rdt-cli (server fallback; unmaintained since 2026-03; needs `rdt login`)
rdt search "query" --limit 10
rdt read POST_ID
rdt sub python --limit 20
```

Use PRAW with the official API only if the user already has script-app
credentials. Do not suggest that new users sign up for it.

## Facebook, Instagram (OpenCLI only)

```bash
opencli facebook search "query" -f yaml
opencli facebook profile NAME -f yaml
opencli facebook feed --limit 10 -f yaml
opencli facebook groups --limit 20 -f yaml     # groups this account sees

opencli instagram search "query" -f yaml       # searches USERS, not posts
opencli instagram profile nasa -f yaml
opencli instagram user nasa --limit 12 -f yaml # one user's recent posts
opencli instagram explore --limit 20 -f yaml
```

Do not default to the Graph API, Jina or instaloader here. For an Instagram
`429` or "login required", have the user log in again in Chrome, then slow
down.

## V2EX (public API, no auth)

```bash
H='User-Agent: platform-reach/1.0'   # V2EX wants a non-empty UA
curl -s "https://www.v2ex.com/api/topics/hot.json" -H "$H"
curl -s "https://www.v2ex.com/api/topics/show.json?node_name=python&page=1" -H "$H"
curl -s "https://www.v2ex.com/api/topics/show.json?id=TOPIC_ID" -H "$H"
curl -s "https://www.v2ex.com/api/replies/show.json?topic_id=TOPIC_ID&page=1" -H "$H"
curl -s "https://www.v2ex.com/api/members/show.json?username=NAME" -H "$H"
```

The topic ID comes from the URL (`/t/1234567`). The node list is at
https://www.v2ex.com/planes.

## XiaoHongShu (RedNote)

```bash
# OpenCLI (desktop; existing Chrome session only)
opencli xiaohongshu search "query" -f yaml
opencli xiaohongshu note "FULL_NOTE_URL" -f yaml   # URL from search results
opencli xiaohongshu comments NOTE_ID -f yaml
opencli xiaohongshu user USER_ID -f yaml

# xiaohongshu-mcp (server; first call downloads a ~150 MB browser, so use a long timeout)
mcporter call xiaohongshu.check_login_status --timeout 120000
mcporter call xiaohongshu.search_feeds keyword="query" --timeout 120000
mcporter call xiaohongshu.get_feed_detail feed_id="..." xsec_token="..." --timeout 120000
```

- **xsec_token:** you cannot read a note from a bare note ID. Search or open
  the feed first, then use the full URL or token from that result.
- For server use, the user exports xiaohongshu.com cookies by hand with
  Cookie-Editor and loads them into xiaohongshu-mcp as its README describes
  (upstream used its own `agent-reach configure xhs-cookies`, not adopted).
  Then run `check_login_status` before any search.
- Pace requests 2–3 s apart. Batch searches and deep comment paging trigger
  CAPTCHAs, and you must not bypass them.
