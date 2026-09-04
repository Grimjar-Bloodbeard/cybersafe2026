# What "Tier 1-5" Actually Means

*A plain-language attachment to the CyberSafe 2026 Scope of Engagement. This explains
what each tier does - not in engineering terms, in terms of what it means for you.*

The tiers are **not** a scale from "safe" to "risky." Every tier stays fully within the
boundaries in Section 3 of the scope agreement (no credentials, no exploitation, no
disruption) - all five tiers are passive, read-only, and non-invasive. What changes
between tiers is how *thoroughly and reliably* we can read your public website, not how
aggressively we test it.

| Tier | In plain terms |
|---|---|
| **1** | **A quick look at your public pages.** We read what's already publicly visible on your website - the same information a search engine or any visitor sees. |
| **2** | **A closer look, including anything that loads after the page opens.** Some websites load parts of their content dynamically (a menu, a form, a chat widget). This lets us see that too, the same way a real visitor's browser would - not a different kind of access, just a more complete view of the same public page. |
| **3** | **Checking your whole site efficiently, not one page at a time.** If your website has many pages, this lets us review all of them in one organized pass instead of a slow, page-by-page process. |
| **4** | **Not a separate check - it's how we behave the whole time.** Every tier above respects your site's stated preferences (its `robots.txt` file, if it has one) and never sends more traffic than a single polite visitor would. This is a standard we hold ourselves to throughout, not an extra step. |
| **5** | **AI-assisted reading for pages that don't fit a simple pattern.** Some websites are built in unusual ways that trip up standard automated tools. This lets an AI model read the page more like a person would, so a finding doesn't get missed just because your site's layout is nonstandard. |

**A note on where we actually are right now:** this project is still being built - not
every tier is finished yet. Check the current build status before authorizing a tier
higher than what's actually working:
[the team Battleplan](https://claude.ai/code/artifact/4e1380d0-e875-4f1a-b02f-5d6e9bbeb180)
always reflects the real, current state. Never write down a tier in the scope agreement
that isn't genuinely built yet - if in doubt, authorize Tier 1 and revisit the agreement
once more of the pipeline is ready.
