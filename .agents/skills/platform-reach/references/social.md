# Social and community platforms

Distilled from Agent-Reach `references/social.md` at the pin in
`resources.toml`. Read-only. Never post, reply, like, follow, or message.

## Before a login-backed route

Say which backend you are using and whether it reuses an existing Chrome
session. OpenCLI may use a session the user already controls; this skill does
not log in, read a cookie store, or import cookies. If no session exists, the
route is unavailable.

## XiaoHongShu

```bash
# Search
opencli xiaohongshu search "query" -f yaml

# Note body and engagement; use the full URL from a search result
opencli xiaohongshu note "NOTE_URL" -f yaml

# Comments, including replies
opencli xiaohongshu comments NOTE_ID -f yaml

# Home feed and a user's public notes
opencli xiaohongshu feed -f yaml
opencli xiaohongshu user USER_ID -f yaml
```

The `xsec_token` is part of the URL. A bare note id is not a valid read. Space
requests by 2–3 seconds; a CAPTCHA is a platform limit, never something to
bypass.

## X/Twitter

Prefix the one command with the tokens; do not export them for the session,
which would leave the secret in the shell environment:

```bash
TWITTER_AUTH_TOKEN="..." TWITTER_CT0="..." twitter search "query" -n 10
```

Shapes of the stable and unstable commands, and the retry chain. Prefix
**every** `twitter` command below with the same two assignments (the first two
show the form; the rest omit it for readability):

```bash
TWITTER_AUTH_TOKEN="..." TWITTER_CT0="..." twitter feed -n 20
TWITTER_AUTH_TOKEN="..." TWITTER_CT0="..." twitter tweet URL_OR_ID
twitter article URL_OR_ID
twitter user-posts @username -n 20
twitter user @username
twitter search "query" -n 10
twitter likes
```

Search may 404 when the GraphQL endpoint moves. Retry once; then upgrade an
existing pinned install; then `opencli twitter search "query" -f yaml`; then
use a stable route (`feed`, `user-posts`). Never run `pipx install
twitter-cli@latest` as a shortcut.

## Bilibili

```bash
bili search "query" --type video -n 5
bili hot -n 10
bili video BVxxx
opencli bilibili subtitle BVxxx
```

See [`video.md`](video.md) for the transcript and API fallbacks; never use
`yt-dlp` for Bilibili.

## V2EX (public API, no auth)

```bash
curl -s "https://www.v2ex.com/api/topics/hot.json" -H "User-Agent: platform-reach/1.0"
curl -s "https://www.v2ex.com/api/topics/show.json?node_name=python&page=1" -H "User-Agent: platform-reach/1.0"
curl -s "https://www.v2ex.com/api/topics/show.json?id=TOPIC_ID" -H "User-Agent: platform-reach/1.0"
curl -s "https://www.v2ex.com/api/replies/show.json?topic_id=TOPIC_ID&page=1" -H "User-Agent: platform-reach/1.0"
curl -s "https://www.v2ex.com/api/members/show.json?username=USERNAME" -H "User-Agent: platform-reach/1.0"
```

Node names are listed at <https://www.v2ex.com/planes>.

## Reddit

There is no anonymous path: the public `.json` endpoints are blocked and a new
API credential usually requires approval. Use an existing login only.

```bash
opencli reddit search "query" -f yaml
opencli reddit read POST_ID -f yaml
opencli reddit subreddit LocalLLaMA -f yaml
opencli reddit hot -f yaml
opencli reddit popular -f yaml
opencli reddit subreddit-info LocalLLaMA -f yaml
```

Legacy `rdt` routes (`rdt search`, `rdt read`, `rdt sub`, `rdt popular`) are
allowed only when the user already has an authenticated `rdt`; do not run its
login or install it unpinned.

## Facebook and Instagram

```bash
opencli facebook search "query" -f yaml
opencli facebook profile zuck -f yaml
opencli facebook feed --limit 10 -f yaml
opencli facebook groups --limit 20 -f yaml

opencli instagram search "query" -f yaml
opencli instagram profile nasa -f yaml
opencli instagram user nasa --limit 12 -f yaml
opencli instagram explore --limit 20 -f yaml
opencli instagram saved --limit 20 -f yaml
```

Facebook Groups exposes only the groups and recent activity visible to the
account; do not promise arbitrary group posts. Instagram `search` finds users,
not posts; resolve a username first. On a 429 or "login required", stop and ask
the user to restore their own session; never retry in a loop.

## Output and evidence

Use YAML or JSON where the CLI offers it (`-f yaml`, `--json`) so results are
structured. Success means non-empty result content, not only a zero exit code.
Keep media and temporary files in `/tmp/`.
