# Careers, companies, and markets

Distilled from Agent-Reach `references/career.md` and `references/finance.md` at
the pin in `resources.toml`. Read-only.

## LinkedIn

The upstream `@latest` MCP command is **not** an approved route. LinkedIn may
enter only as a disabled, pinned MCP server vetted by `skill-scout` and recorded
in `.agents/mcp/`. When such a route is enabled, its read commands are:

```bash
mcporter call linkedin.get_person_profile linkedin_username="username" sections="experience,education"
mcporter call linkedin.search_people keywords="AI engineer" location="Shanghai"
mcporter call linkedin.get_company_profile company_name="openai" sections="posts,jobs"
mcporter call linkedin.search_jobs keywords="software engineer" location="Remote" max_pages=2
```

Do not run `uvx mcp-server-linkedin@latest --login`; that is an unpinned install
and a login action. If the pinned route is disabled, use the public-page
fallback for a profile the user may view:

```bash
curl -s "https://r.jina.ai/https://linkedin.com/in/username"
```

Many profiles and job pages are login-walled; an empty or challenge response
means unavailable, not "the person or job does not exist". Minimise data about
private individuals.

## Xueqiu (public quotes and market discussion)

Use an existing login; never run `opencli xueqiu login`.

```bash
opencli xueqiu whoami -f yaml
opencli xueqiu search "英伟达" -f yaml
opencli xueqiu stock NVDA -f yaml
opencli xueqiu hot -f yaml
opencli xueqiu hot-stock -f yaml
opencli xueqiu --help
```

Quotes may be delayed and are not investment advice. HTTP 400 usually means a
missing or expired session or minimal cookie, not that a ticker does not exist.
If `whoami` succeeds but `stock`/`hot` fails, report an adapter or API problem,
not a login problem.

If the user explicitly wants to store only the `xq_a_token` for an existing
Xueqiu session, that is their action. This skill does not read browser stores
itself and does not automate a login.

## Out of scope

The Boss Zhipin CDP runbook is not adopted: it requires login automation,
profile reuse, and anti-bot handling that conflict with this kit's boundaries.
Its upstream runbook is linked from `resources.toml` for an owner who decides to
review it separately. Do not improvise a Boss route here.

Success means a non-empty profile, job list, quote, or content list. An exit
code alone is not evidence.
