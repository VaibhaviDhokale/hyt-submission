# Labelling notes (J01-J12)

Labels drafted by a Sonnet session from the packet text and rubric only, without looking at any system output. **A person still needs to review them.** The report should say the labels were drafted by a model and then reviewed.

## Distribution (180 pairs)
- relevance 0: 45, 1: 52, 2: 43, 3: 40
- ideal = shortlist: 55 (all 40 of the relevance-3 pairs plus 15 relevance-2 pairs); review: 125
- jd_gold.json: 12 jobs. extraction_gold.json: 21 distinct resumes. Three resumes are the "first two" in two packets (C21830565 in J03/J05, C26231609 in J09/J11, C23734441 in J04/J12), so 24 slots map to 21 entries.

## Conventions I used (check these first)
- Degree "in accounting/finance" accepted business administration or an MBA in the field as met unless a posting was strict; a pure non-finance degree counted as missing.
- Foreign credentials/standards (ACCA, Philippine CPA, IFRS, local payroll) were not penalised for location, only for not matching a named requirement such as US CPA, GAAP or SOX.
- "CPA candidate" counts as not holding the credential.
- Overqualified candidates (directors for associate roles) kept relevance 3 where every must-have is shown; the "overqualified" note is in the row.
- Resumes with a finance title but non-finance duties were labelled by duties (e.g. J05 C38225199, J11 C28939941).
- Resumes appear in several packets with different labels because the postings differ.

## Pairs I was unsure about
- J05 C26530575 (2 vs 1): NY CPA, PwC and regional-firm supervising auditor, but no estate/gift/trust tax. I gave 2, review.
- J05 C84356308 (1 vs 2): ex-Big 4 audit manager and CFO, non-US CPA memberships, no US tax.
- J05 C12071138 (1 vs 2): nonprofit CFO who prepared 990-T and charitable trust returns, no CPA.
- J09 C26530575 (2 shortlist): closest audit fit, but only about 1 year at a Big 4 firm and little SOX or public-company work.
- J09 C26231609 and C84356308 (2 review): audit backgrounds without a US CPA or clear SOX/PCAOB detail.
- J01 C10554236, C81677620, C30813919 (2 review): strong accounting careers but no bachelor's or over-senior for a staff role.
- J01 C12442909, C21763056, C15717923 (2 shortlist): GAAP/SOX and Excel not stated.
- J02 C27637576 and C14470533 (2 review): long careers but no bachelor's degree; C14470533 lists "CPA" under certifications without support.
- J03 C27409087 (3) vs C24294778 (2): payroll depth and non-US payroll rules.
- J06 C14181049, C98513424, C15011085 (3): heavily overqualified directors for an associate analyst role.
- J07 C29998869 (3): health-insurance finance director, closest to the insurance posting.
- J08 C38907798 (3): degree is finance/MBA rather than the accounting degree the posting prefers. C28758002 (3): bachelor's field not stated.
- J08 C66741193 (2): CPA FP&A director whose AR/AP depth is not shown.
- J11 C26231609 (2) and C78229715, C36425270, C13701259 (1): sound accountants with no manufacturing cost accounting or SAP.
- J12: nobody holds a stated professional accreditation except C19147603 (Philippine CPA, 3). Candidates who are CPA candidates or have equivalent diplomas (C28969385, C15289348, C23416654, C27409087) got 2 review.
- J04 C14722634 (2 review): finance director, strong content match but far over-senior for an associate AR role.

## Extraction gold estimates to verify
- finance_years is a rough count of finance/accounting/payroll/banking-ops years up to the latest date in each resume; overlapping or undated roles make these approximate: C10554236 (19.5), C17407184 (5.0, the accounting share of a mixed role is unclear), C29050809 (24.0), C14181049 (19.0, undated roles), C38225199 (set to 0 because the "Finance Operations" title sits over call-centre/collections duties), C95519832 (7.3 banking ops).
- C28139742: a Ph.D. is listed without dates, so education_level is master.
- C23734441: MS in progress, so highest held is bachelor.
- Software lists are tools named in the resume; skill-section-only tools are included.

## Process notes
- jd_gold.json entries were written before reading each job's candidates.
- Several resumes repeat across packets; I reused my earlier reading rather than re-reading them.
