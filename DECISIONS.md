# Decision log

1. **Finance & accounting, not software engineering.** The Kaggle resume set has 118 ACCOUNTANT and 118 FINANCE
   resumes that read like their category, and the arshkon postings have ~1,300 accountant-type jobs. A job family where
   real resumes plausibly fit real postings gives the golden set actual positives to find.

2. **Only the brief's two Kaggle datasets.** No synthetic resumes in the evaluation set. Synthetic text exists only in
   the fairness and manipulation suites, where it is an edit of a real resume and is labelled as such.

3. **Checklist, not similarity.** The posting becomes 4–10 checkable requirements (must / nice); each is judged
   met / partial / not met with a quote. A recruiter can audit a checklist line by line; a cosine score can't be
   argued with. Rejected: an embedding "fit" score (no evidence, no gaps) and a single LLM 0–100 rating (no audit trail).

4. **The grader sees retrieved passages, not the whole resume.** BM25 picks the 5 best passages per requirement (with a
   small finance synonym list: AP → accounts payable, ERP → SAP/Oracle/NetSuite…). Quotes stay short and verifiable,
   prompts stay small, and an injected instruction elsewhere in the resume never reaches the grader. Cost: evidence
   phrased with none of the requirement's words can be missed. The LLM judge reads the whole resume to measure that.

5. **Years and degree are computed in code.** The LLM copies role dates and degree levels; code merges overlapping
   roles, drops internships, counts only finance-relevant roles and compares against the posting. Arithmetic is the
   thing LLMs are worst at and auditors care most about.

6. **"Current" means the resume's own era.** The resumes were written years before the 2024 postings. Resolving
   "present" to 2024 would add phantom years to everyone; instead it resolves to the latest date written in that resume.

7. **Every quote is verified.** A met/partial verdict whose quote does not fuzzy-match the resume (partial ratio ≥ 90)
   gets zero credit and the candidate goes to review with `UNVERIFIED_QUOTE`. The model can be wrong; it can't be
   wrong silently.

8. **Score = weighted checklist; must-haves count double.** met 1 / partial 0.5 / not met 0, musts ×2, nice ×1. Simple
   enough to explain in one sentence to a recruiter, and every point traces to a checklist row.

9. **Three lanes, no rejection.** Shortlist (score ≥ line, at most one must-have not fully met, no flags; the
   gap is named as "Ask about: …"; "every must-have met" was v1 and is archived, see REPORT §5), Needs review (anything
   uncertain, with reason codes) and Low priority (low score with a must-have missing; still human-reviewed, just
   later). Only a human can pass on a candidate, and the UI requires a written reason to do so.

10. **Threshold from a cost ratio, tuned on dev jobs only.** Missing a good candidate costs 5, shortlisting a weak one
    costs 1. The line is the cheapest value on the 3 dev jobs (ties → the most conservative); test jobs never touch it.
    Split is by job, so no posting appears in both.

11. **Blocking flags beat the score.** Suspected injection, unverifiable quotes, a thin resume or undatable roles
    always go to review, never low priority, so a manipulated or unreadable resume gets a human's eyes first.

12. **Injection: architecture first, regex second.** Documents are wrapped as untrusted data, the LLM never outputs
    a score or a decision, the grader only sees retrieved passages, and invisible characters are stripped. The regex
    flag is deliberately narrow ("act as Assistant Sales Manager" must not fire, and it did in the first version). A
    deterministic keyword-stuffing check (one line containing ≥ 50% of the requirements) was added after the
    manipulation test showed pasted requirement lists getting shortlisted.

13. **Simple stack, one LLM interface, two providers, one cache.** Flask JSON API, one static Tailwind/vanilla-JS
    page and SQLite: no model weights, no build step, installs in seconds. All LLM calls go through `ask(task, prompt)`,
    which returns schema-validated JSON. During development the prompts were answered by Claude Sonnet agents through
    a queue (no API key was available for headless calls). Production uses Gemini (`LLM_PROVIDER_TALLY=gemini`), set to
    `gemini-3.5-flash-lite` because `3.1-flash-lite` was too often overloaded. The cache key includes the model, so
    answers never mix, and the committed cache makes `make reproduce` offline.

14. **Golden set sampled independently of the system.** Per job: 5 BM25-top, 5 random from the finance pool, 3 from
    near categories (banking, consulting, sales, business development), 2 hard cases (the best-looking non-finance
    resume, and a finance resume whose title matches but BM25 ranks low). Labels were written blind to system output by a person; a blind Claude Sonnet draft was kept as a second rater
    (κ 0.90) rather than discarded, because where the two disagree is itself informative (REPORT §3).

15. **Names are masked before any LLM call.** The Kaggle resumes have no names, but uploads do, and the Gemini
    re-run showed a name in the prompt could flip a decision (REPORT §8). A first line that looks like a person's name
    becomes `[NAME]`; Title Case job titles are kept.
