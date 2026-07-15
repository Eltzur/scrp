# Amendment 13 (Tikun 13) Compliance Checklist — Portal

**NOT LEGAL ADVICE.** Drafted by the chat architect (AI) as a working checklist. Every item marked NEEDS COUNSEL must be confirmed by an Israeli privacy attorney before this is treated as final. Last updated: July 12, 2026 (session XXL-1.0.1).

## Data inventory

**Live today:** none — DB is empty, zero registered users.

**Planned (not yet built):** email, hashed password (Supabase-managed), full name, phone number, ID number (תעודת זהות), home address, payment activity (via third-party PCI-DSS gateway — XXL never stores card PAN/CVV). Plus already-scoped: favorites, saved baskets, flight alerts/searches (behavioral data tied to an identified user), GA4 analytics (device/browser, approximate location).

## Threshold assessment

| Obligation | Applies? | Basis |
|---|---|---|
| Database registration (>10,000 people, primary purpose = transfer to others) | Likely NO | XXL is not a data broker — we don't sell/transfer user data as a business activity. NEEDS COUNSEL to confirm once real volume exists. |
| Notification duty (>100,000 people, highly sensitive data) | Not yet — revisit at scale | Financial/payment data (once live) falls under Amendment 13's "Highly Sensitive Data" category (salary/financial activity). Revisit once user count approaches six figures. |
| Mandatory DPO appointment | LIKELY YES once payment launches | DPO is required for databases primarily processing sensitive/highly-sensitive data, or systematic monitoring at scale. Payment/financial activity data pushes this from "maybe" to "probably." GA4 usage is a secondary contributing factor (systematic monitoring). NEEDS COUNSEL to confirm exact trigger point and timing (before or at payment launch). |
| Data Security Regulations tier (basic/intermediate/high) | Likely intermediate, trending to high at scale | ID number + financial data + address pushes past "basic." High tier applies at >100,000 people or >100 access authorizations. NEEDS COUNSEL / security consultant once real record counts exist. |
| Data subject rights (access/correction/deletion) | YES, applies now | Build requirement regardless of size — must be able to fulfill for any account, whenever accounts exist. |
| Breach notification procedure | YES, applies now | Need an internal procedure to detect/assess/notify PPA and affected users, ready before any PII is live. |
| Consent standard (explicit, granular, documented) | YES, applies now | Addressed this session — cookie banner reworked to explicit accept/reject (was implicit X-dismiss). |

## Payment architecture (locked decision, XXL-1.0.1)

Third-party PCI-DSS certified, tokenized gateway. XXL infrastructure never touches raw card PAN/CVV. Bit/Paybox via their own app-redirect flows — same rule. This significantly limits PCI-DSS scope on XXL's own infrastructure but does NOT remove Amendment 13 obligations — XXL remains the data controller and is responsible for the gateway vendor's compliance.

## Action items (owner: Dude)

1. Engage an Israeli privacy attorney to review the drafted privacy policy and disclaimer text (web/src/pages/PrivacyPolicyPage.tsx, DisclaimerPage.tsx) before go-live.
2. Decide on DPO appointment timing — before or at payment launch — with counsel.
3. Select the PCI-DSS payment gateway vendor; re-run the security-tier assessment once selected (vendor's own certifications matter).
4. Create a dedicated privacy@xxl.co.il inbox (currently policy points to info@xxl.co.il).
5. Once real signups exist, periodically re-check counts against the 10,000 / 100,000 thresholds above.
6. Follow-up session: link fly.xxl.co.il (xxl-flights repo, separate codebase) footer to the privacy/disclaimer pages built here.

## Sources

- [gov.il — Amendment 13 professional guide (PDF)](https://www.gov.il/BlobFolder/reports/guide_tikon13_professional/he/tikun%2013%20_170825.pdf)
- [o-n.law — Amendment 13 overview](https://o-n.law/privacy-protection-law-amendment-no-13/)
- [Herzoglaw — Amendment 13 summary](https://herzoglaw.co.il/en/news-and-insights/amendment-no-13-to-the-israeli-privacy-protection-law/)
- [Gornitzky GNY — 10 steps to navigate Amendment 13](https://www.gornitzky.com/privacy-protection-in-2025-10-steps-to-navigate-the-implementation-of-obligations/)
- [IAPP — Israel marks a new era in privacy law](https://iapp.org/news/a/israel-marks-a-new-era-in-privacy-law-amendment-13-ushers-in-sweeping-reform)
- [Chamber of Commerce TA — Data Security Regulations](https://www.chamber.org.il/serviceslobby/legal/74023/76704/)
