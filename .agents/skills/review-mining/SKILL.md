---
name: review-mining
description: >-
  Reads what a product's real users say in public reviews — your own
  product's feedback when there is no reference, or a reference product's
  reviews when you clone one — and ranks what they hate, what is missing and
  what is unsolved, in their own words. Every quote is real, verbatim and
  linked; nothing is invented. Original mode scopes the goal from VISION.md
  or the accepted design, asking the owner one blocking question when the
  product or its sources are missing. Turns the evidence into a fix plan and
  a positioning angle. Use when the user says "what do users hate about X",
  "read the reviews", "positioning", or "what should we fix".
---

# review-mining

Two modes, one goal: know what real users hate, in their own words, before
you build. **Reference mode** (cloning a product you studied) reads the scope
in `reference/recon.md` (product-recon), so the mining stays inside the slice
being built. **Original mode** (your own product, no reference) has no
`reference/recon.md`: scope the mining from the owner's goal instead —
VISION.md or the accepted design brief, the category, the comparable
products — and work under `docs/research/`. Before launch your product has
no reviews yet: the comparables carry the run. Never invent a competitor. If the
product or its sources are missing, ask the owner the one blocking question
that unblocks them. When run, write the scope record (goal, category,
comparables, sources, date) to `docs/research/review-scope.md`; create it
only then, never as a placeholder. Never require product-recon, and never force a full
product-kickoff when the user already brought a feedback task.

One variable picks the mode's folder, so the command keeps the same shape:

```bash
RESEARCH_DIR=reference   # reference mode; docs/research in original mode
mkdir -p "$RESEARCH_DIR"
python3 .agents/skills/review-mining/reviews.py "$RESEARCH_DIR/reviews.csv" --out "$RESEARCH_DIR/feedback.md"
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

Each row in `$RESEARCH_DIR/reviews.csv`: `source,url,date,rating,text`, text
copied exactly. Read the 3 and 4 star reviews too. "Love it, but..." is where
the best fixes hide.

## Step 2: rank

```bash
python3 .agents/skills/review-mining/reviews.py "$RESEARCH_DIR/reviews.csv" --out "$RESEARCH_DIR/feedback.md"
```

A quote cut for length is marked `[excerpt]`, a rating outside 1 to 5 is
reported, and the same words under different links count as different users.
It sorts reviews into themes (`themes.json` in this folder, edit it for the
product's category), weights low ratings and recent reviews higher, marks
themes with fewer than 3 reviews or only one source as thin, lists every
request in the users' own words, and surfaces low ratings that matched no
theme. Read that last list by hand. It is often the best part.

## Step 3: three lists

From `$RESEARCH_DIR/feedback.md`, write three ranked lists. Each item: the
problem in one line, how many reviews, how many sources, one or two linked
quotes. In original mode the lists are your own product's users, and they
become its plan.

1. **What they hate.** Complaints about things the product does.
2. **What is missing.** Features people ask for by name.
3. **What is unsolved.** Whole jobs or groups the product ignores ("not built
   for teams", "useless for therapists"). These become positioning.

Thin themes are listed as thin. Do not present three angry Reddit comments as
a trend.

## Step 4: the fix plan

Pick the top 5 to 8 by evidence times how cheaply you can fix them. For each:
what to build or change, size (S, M, L), which step of the build loop takes
it, and the evidence. Append each one to `docs/product/features.csv` with
`status` `no` and `source` `review-mining` (evidence in `acceptance`) only
when that product matrix exists and the fix plan is approved; parity-check
lists these as improvements, not parity, and `make next` queues them. With no
appropriate matrix or no approval, propose the issues to the owner for the
WAL instead of a tracked live backlog. Pricing and billing complaints feed
the angle as much as the fix plan.

## Step 5: the angle

Three positioning options, each grounded in a top theme:

```
For {{who}} who {{hate this about the product, in plain words}},
{{your build}} {{does this instead}}.
Evidence: {{theme}}, {{n}} reviews across {{n}} sources.
```

Recommend one. It drives brand-sweep's name and voice. Do not put the
reference product's name in your app name, ads or store listing. A factual
comparison page is a legal question for a lawyer in your country.

## Output

`$RESEARCH_DIR/reviews.csv`, `$RESEARCH_DIR/feedback.md`,
`$RESEARCH_DIR/fixes.md` (three lists, fix plan, angle), rows in
`docs/product/features.csv` when the matrix exists and the plan is approved,
and a summary that states the sample size. brand-sweep only when the angle
is used or the product is being rebranded — not every review request.
