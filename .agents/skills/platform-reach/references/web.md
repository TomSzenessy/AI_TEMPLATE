# Web: search, read a page, feeds

## Search

Use the first route that is available:

1. **Exa MCP** (`.agents/mcp/`), tool `web_search_exa`
   (`query`, `numResults: 5`). It is strong on English and technical content.
   To find official docs or code examples, phrase the query as
   `"<framework> <API> example"`. For exact matches inside repositories, use
   GitHub code search ([dev](dev.md)).
2. **The host's built-in web search.**
3. **Exa through `mcporter`**, when that CLI is configured:
   `mcporter call exa.web_search_exa query="..." numResults=5`.

For Chinese-language results, add a Chinese-language search source if the
user has one. Exa skews toward English.

## Read any page

| Need | Route |
| --- | --- |
| Most article and doc pages, as Markdown | `curl -s "https://r.jina.ai/<URL>"` (Jina Reader) |
| The host's fetch tool, when present | WebFetch or an equivalent |
| JavaScript-rendered pages, or pages behind the user's own login | Playwright MCP: navigate, then snapshot |
| Raw HTML or JSON APIs | `curl -sL -A "Mozilla/5.0" "<URL>"` |

Jina Reader sends the URL to a third party, `r.jina.ai`. Do not route
private, intranet or signed URLs through it.

Failure signs: an empty body, a cookie wall or a "verify you are human"
page. Try the next route once. If the page needs a login you do not have,
report it.

## RSS / Atom feeds

```bash
# feedparser, when installed
python3 -c "
import feedparser, sys
for e in feedparser.parse(sys.argv[1]).entries[:5]:
    print(e.get('published', ''), e.title, '-', e.link)
" "FEED_URL"
```

Without feedparser, fetch the feed with `curl -sL` and read the
`<item>`/`<entry>` elements with `xml.etree.ElementTree` from the standard
library. Feeds suit blogs, news sources, changelogs and podcasts.
