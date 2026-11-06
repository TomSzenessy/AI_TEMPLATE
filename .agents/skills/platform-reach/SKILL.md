---
name: platform-reach
description: >-
  Read-only research routes for public web and the platforms agents usually
  improvise or give up on: web search, any page, RSS, GitHub, YouTube,
  Bilibili, X/Twitter, Reddit, Facebook, Instagram, LinkedIn, V2EX,
  XiaoHongShu and Xueqiu. Use when the user asks to research, search, look
  something up, or see what people say; when they share a URL; or when they
  name one of these platforms.
---

# platform-reach

One reviewed read-only route per platform, with a fallback chain for each.
The routes and commands are distilled from
[Panniantong/Agent-Reach](https://github.com/Panniantong/Agent-Reach) at the
pin recorded in `resources.toml`; the installer, doctor, cookie importer,
update nag, Boss Zhipin CDP runbook, and Xiaoyuzhou transcription are **not**
adopted and must not be run from here.

## Boundaries

These are rules, not suggestions.

- **Read-only.** Search, list, read, and download public content. Never post,
  reply, like, follow, message, or change an account.
- **No login automation and no browser cookie-store reads.** Do not drive a
  login form, solve or bypass a CAPTCHA, decrypt a browser profile, or read
  Chrome/Safari/Firefox cookie databases. OpenCLI may reuse an existing Chrome
  session only when the user explicitly controls it; it does not read or export
  a cookie store. A manual Cookie-Editor export the user performs is their
  action, not this skill's.
- **Credentials only as environment variables, for one command.** Never write
  a token to a file, log, issue, commit, or report. Export it in the child
  environment and do not echo it.
- **No unpinned installs.** Never run `npx ...@latest`, `uvx ...@latest`,
  `pipx install <moving-ref>`, or a remote install script. If a tool is
  missing, name the pinned version and ask the owner before installing.
- **LinkedIn** may enter only as a disabled, pinned MCP route vetted by the
  `skill-scout` role; never `@latest`.
- **Transcription** goes to one named provider. Do not fall back to a second
  provider without explicit consent, because the audio leaves the machine
  again.
- **People are not the dataset.** Collect the minimum about private
  individuals, never compile profiles, and follow
  [`../../../docs/privacy.md`](../../../docs/privacy.md).

## Before you start

1. Say which platform and route you will use, for example "using platform-reach:
   V2EX public API".
2. Check the tool exists (`command -v gh`, `command -v yt-dlp`, ...). A missing
   tool is a setup question, not a reason to invent a scraper.
3. Run only the read-only commands in the matching reference. If a route needs
   a login the user already has, ask them to establish it; never do it for
   them.
4. On failure, follow that reference's retry chain. Stop when you have
   non-empty content; an exit code or a version probe is not evidence of
   content.
5. Keep temporary output in `/tmp/`; never write research artifacts into the
   repository unless the brief asks for them.

## Routing table

| The user wants | Read |
|---|---|
| Web or code search | [references/web.md](references/web.md) |
| Any page, article, or RSS feed | [references/web.md](references/web.md) |
| GitHub repositories, issues, PRs, CI | [references/dev.md](references/dev.md) |
| YouTube or Bilibili metadata, subtitles, comments | [references/video.md](references/video.md) |
| XiaoHongShu, X/Twitter, Bilibili, V2EX, Reddit, Facebook, Instagram | [references/social.md](references/social.md) |
| LinkedIn profiles, jobs, companies, or Xueqiu quotes | [references/career-finance.md](references/career-finance.md) |

For broad research, combine routes in parallel (a web search plus one
discussion platform plus one regional platform), then synthesize. State which
platforms actually returned content and which did not.

## Zero-config commands

```bash
# Web search (Exa MCP, when the route is configured)
mcporter call exa.web_search_exa query="query" numResults=5

# Read any public page
curl -s "https://r.jina.ai/URL"

# GitHub search (read-only)
gh search repos "query" --sort stars --limit 10

# YouTube subtitles, no video download
yt-dlp --write-sub --write-auto-sub --sub-lang "zh-Hans,zh,en" --skip-download -o "/tmp/%(id)s" "URL"

# V2EX hot topics (public API, no auth)
curl -s "https://www.v2ex.com/api/topics/hot.json" -H "User-Agent: platform-reach/1.0"

# Bilibili search (bili-cli, read-only, no login)
bili search "query" --type video -n 5
```

Never use `yt-dlp` for Bilibili: it is blocked with 412. Use `bili` or
OpenCLI as the reference says.

## Environment and setup

There is no bundled installer or `doctor`. Check each tool directly:

```bash
for tool in gh yt-dlp bili opencli twitter mcporter curl; do
  command -v "$tool" >/dev/null 2>&1 && echo "$tool: present" || echo "$tool: missing"
done
```

A route is usable only when its tool is present **and** the read command
returns non-empty content. When a tool is missing or a login is absent, say
which route is unavailable and offer the fallback in that reference; do not
install anything without the owner's approval.

The pinned upstream record and its linked Boss Zhipin/Xiaoyuzhou files are
listed by `make upstream ID=agent-reach`; pull one of those files only when the
need named in its `when` trigger is real.

## Special cases

- **OpenCLI** uses a Chrome session the user already controls. If none exists,
  do not automate a login; report the route unavailable.
- **XiaoHongShu** needs the full URL or ID from a search result (the
  `xsec_token` is part of it); a bare note id is not a valid route.
- **Reddit** has no anonymous path. Both routes need an existing login; do not
  recommend creating API credentials for a new user.
- **X/Twitter** takes `TWITTER_AUTH_TOKEN` and `TWITTER_CT0` in the child
  environment only. A search may fail even when the timeline works; follow the
  retry chain.
- **Boss Zhipin** and **Xiaoyuzhou** are deliberately out of scope. Their
  upstream runbooks are linked from `resources.toml`, not copied here, because
  they require login automation or a transcription provider decision.
