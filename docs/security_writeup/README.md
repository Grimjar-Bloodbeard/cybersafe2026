# `docs/security_writeup/` - the documents you actually hand to a business

If you're doing outreach and need the paperwork, not the code, this is the folder.
Everything here is written for a business owner to read, not a developer.

## What's here

| Document | What it's for | When you need it |
|---|---|---|
| [**Scope of Engagement**](scope_of_engagement_template.md) | The actual legal authorization a business signs before we touch their website. Covers what we will and won't do, how long it lasts, and what they get back. | Once a business has said yes and you're ready to make it official - fill in the blanks (see its own "How to fill this out" section), get it signed, then tell whoever's handling the backend so the matching `engagements` row can be marked `authorized`. |
| [**Tier Explainer**](tier_explainer_one_pager.md) | A plain-language, one-page description of what "Tier 1-5" actually means - referenced by the Scope of Engagement's max-tier field. | Hand this alongside the Scope of Engagement, or use it earlier if a business asks "wait, what exactly are you going to do?" during outreach. |

## The short version, if you're in a hurry

1. Business says yes → open the [Scope of Engagement](scope_of_engagement_template.md).
2. Fill in the blanks (business name, contact, in-scope website, tier - check the
   [Tier Explainer](tier_explainer_one_pager.md) and the
   [Battleplan](https://claude.ai/code/artifact/4e1380d0-e875-4f1a-b02f-5d6e9bbeb180)
   for what's actually built before picking a tier).
3. Get both sides to sign.
4. Get the row moved to `status='authorized'` in the database - nothing scans until
   that happens, by design.

**Before any of this touches a real business for the first time:** this needs a review
pass from your instructor/program. That hasn't happened yet as of this writing - check
with your team before using it for a real signature.
