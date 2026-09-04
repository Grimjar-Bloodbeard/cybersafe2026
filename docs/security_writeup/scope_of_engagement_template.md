# Scope of Engagement — CyberSafe 2026 Security Assessment

*This document authorizes the CyberSafe 2026 team to perform a limited, passive
security reconnaissance assessment of the business named below. It is a template —
fill in every bracketed field before use, and have both sides sign before any scan
runs against a live target. This is a student capstone project, not a licensed
professional penetration test; treat it accordingly and keep the scope conservative.*

---

## 1. Parties

**Business:** [Legal business name]
**Business contact:** [Name, title, phone, email]
**CyberSafe 2026 team members on this engagement:** [Names]
**Course/institution:** [Instructor name, institution]

## 2. What we will do (in scope)

- Passively review your public-facing website(s) listed below using automated tools
  we built ourselves — reading pages, following links, and observing how your site
  responds to normal traffic.
- Check HTTP security headers (e.g. HTTPS enforcement, content-security-policy).
- Identify publicly visible technology (CMS, server software, plugin versions) from
  what your site already discloses in its headers and page content.
- Cross-reference identified technology against public vulnerability databases
  (e.g. NVD) to flag *known, published* vulnerabilities that may be relevant.
- Check your site's TLS/certificate configuration.
- Look for publicly-reachable but unintended paths (e.g. exposed `.git` or `.env`
  files, default admin login pages) — we will note that a path *exists and responds*,
  we will not attempt to log in, guess credentials, or access its contents.

**In-scope hosts/domains:** [list every domain/subdomain covered — nothing outside
this list is authorized]

**Maximum tier authorized:** [1-5, per the project's complexity ladder — see attached
one-page tier explainer]

## 3. What we will NOT do (out of scope)

- No attempt to guess, crack, or use credentials of any kind.
- No exploitation of any vulnerability we find — findings are reported, never used.
- No denial-of-service, load testing, or anything intended to slow or disrupt your
  site.
- No social engineering, phishing simulations, or contacting your staff/customers.
- No physical security testing.
- No testing of anything not explicitly listed as an in-scope host above.

If we find something that suggests a *serious, active* problem (e.g. a clearly
exposed customer database), we stop immediately and contact you directly rather than
investigating further.

## 4. How we test, responsibly

- All automated requests identify themselves with a descriptive User-Agent string
  naming this project and a contact email — nothing is disguised as a real visitor.
- We follow your site's `robots.txt` and apply our own rate limiting regardless of
  what your site allows, so this assessment does not add meaningful load.
- Testing window: [start date] to [end date]. Outside this window, no further
  testing occurs without a new signed agreement.

## 5. What you get

- A private report, delivered only to the contact above, written in plain language —
  what we found, why it matters, and what we'd recommend. We do not publish, share,
  or present your specific findings publicly without your separate, written consent.
- An explicit list of what was *not* tested, so you know the boundaries of what this
  report does and doesn't cover.

## 6. Data handling

- Findings are stored only for the purpose of producing your report and are not
  shared with any other business.
- We may reference this engagement anonymously (e.g. "a local retail business") in
  our course presentation, with no identifying details, unless you separately agree
  to be named.

## 7. Either party can stop this at any time

You may revoke this authorization at any time, for any reason, by contacting any
team member listed above — we stop immediately. We may also pause or end the
engagement if we believe continuing risks harm to your systems.

## 8. Acknowledgment

This is student coursework, performed on a best-effort basis using tools we built
ourselves. It is **not** a substitute for a professional, licensed penetration test
or compliance audit, and we make no guarantee that it identifies every vulnerability
present. By signing below, you confirm you are authorized to approve this
assessment on behalf of the business named above.

**Business signature:** _______________________  **Date:** _________

**Printed name/title:** _______________________

**CyberSafe 2026 team signature:** _______________________  **Date:** _________
