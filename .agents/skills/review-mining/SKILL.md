---
name: review-mining
description: >-
  Reads what a product's real users say in public reviews (App Store, Google
  Play, G2, Capterra, Trustpilot, Reddit, Hacker News, its own feature-request
  board), ranks what they hate, what is missing and what is unsolved, and turns
  it into a fix plan and a positioning angle. Every quote is real, verbatim
  and linked. Use when the user says "what do users hate about X", "read the
  reviews", "positioning", or "what should we fix".
---

# review-mining

A straight copy of a product has no reason to exist. This skill finds the
reason: what the reference product's users hate, in their own words, and what
your build does instead. Reads the scope in `reference/recon.md`
(product-recon), so the mining stays inside the slice being built.

Tool in this folder (command runs from the project root):

```bash
python3 .agents/skills/review-mining/reviews.py reference/reviews.csv --out reference/feedback.md
```

## The rules, which are not negotiable

- **Never fabricate.** No invented reviews, quotes, ratings, counts, users or
  sources. If a source cannot be reached, say so and move on. If there are 14
  reviews, say 14.
- **Every quote is verbatim and linked.** Copied exactly from the page, with
  the URL of the review or thread. `reviews.py` drops any row without a link.
- **Reading, not scraping.** Read review pages the way a person does, in the
  browser, and copy rows into the sheet. No scraping libraries against stores
  or review sites whose terms forbid it. Official public feeds and APIs are
  fine within their terms: Apple's customer reviews RSS feed
  (`https://itunes.apple.com/us/rss/customerreviews/id=<APP_ID>/sortBy=mostRecent/json`),
  the Hacker News Algolia API (`hn.algolia.com/api/v1/search?query=...`),
  Reddit's official API under its terms.
- **No fake reviews, ever.** Not for your app, not against theirs. It is
  illegal in the US (the FTC's 2024 rule) and in many other places.
- **Reviewers are not your testimonials.** Their words are research. Do not
  put them on your landing page.

## Step 1: collect

Aim for 100+ reviews across at least three sources, recent first:

| source | where |
| --- | --- |
| App Store | the app page, Ratings and Reviews, See All; or the RSS feed above |
| Google Play | the listing, See all reviews, sort by newest |
| G2, Capterra, Trustpilot | the product's review pages, filter to 1 to 3 stars too |
| Reddit | search "X alternative", "switched from X", "X sucks", "X vs" |
| Hacker News | the Algolia API or site search, same queries |
| its own board | its public roadmap or feature-request board (Canny and similar) and the vote counts |
| its changelog | what it shipped, so you do not "fix" what is already fixed |

Each row in `reference/reviews.csv`: `source,url,date,rating,text`, text
copied exactly. Read the 3 and 4 star reviews too. "Love it, but..." is where
the best fixes hide.

## Step 2: rank

```bash
python3 .agents/skills/review-mining/reviews.py reference/reviews.csv --out reference/feedback.md
```

It sorts reviews into themes (`themes.json` in this folder, edit it for the
product's category), weights low ratings and recent reviews higher, marks
themes with fewer than 3 reviews or only one source as thin, lists every
request in the users' own words, and surfaces low ratings that matched no
theme. Read that last list by hand. It is often the best part.

## Step 3: three lists

From `reference/feedback.md`, write three ranked lists. Each item: the problem
in one line, how many reviews, how many sources, one or two linked quotes.

1. **What they hate.** Complaints about things the product does.
2. **What is missing.** Features people ask for by name.
3. **What is unsolved.** Whole jobs or groups the product ignores ("not built
   for teams", "useless for therapists"). These become positioning.

Thin themes are listed as thin. Do not present three angry Reddit comments as
a trend.

## Step 4: the fix plan

Pick the top 5 to 8 by evidence times how cheaply you can fix them. For each:
what to build or change, size (S, M, L), which step of the build loop takes
it, and the evidence. Add each one to `reference/features.csv` as a row with
`original` set to `no`. Pricing and billing complaints feed the angle as much
as the fix plan.

## Step 5: the angle

Three positioning options, each grounded in a top theme:

```
For {{who}} who {{hate this about the reference product, in plain words}},
{{your app}} {{does this instead}}.
Evidence: {{theme}}, {{n}} reviews across {{n}} sources.
```

Recommend one. It drives brand-sweep's name and voice. Do not put the
reference product's name in your app name, ads or store listing. A factual
comparison page is a legal question for a lawyer in your country.

## Output

`reference/reviews.csv`, `reference/feedback.md`, `reference/fixes.md` (three
lists, fix plan, angle), new rows in `reference/features.csv`, and a summary
that states the sample size. Then brand-sweep. Remember: `reference/` must be
registered in `project.toml` (see product-recon).

## Source

Adapted from the upstream skill in https://github.com/Jakeschincariol/replica-skill (MIT, © 2026 Jake Schincariol), revision 77c9436fb3d18c3d58169efb8caf4fe906b0dc51.
