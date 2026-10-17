# Explanation rating sheet (reviewer)

Rate each explanation in `golden/explanations_to_rate.csv` (30 rows) against the **job posting and the full resume**
(both in `golden/packets/<job>.md`). Do not look at `results/judge_scores.csv` or any other system output.

Score each 1-5 and write `golden/explanation_ratings.csv` with header `job,cand,grounded,gaps_correct,actionable,comment`:

- **grounded**: 5 = every "met" claim and quote is true of this resume; 1 = invents or misattributes evidence.
- **gaps_correct**: 5 = the gaps named are really missing from the full resume and none are overlooked; 1 = calls things
  missing that the resume clearly shows, or misses obvious gaps.
- **actionable**: 5 = a recruiter knows what to verify next without opening the resume; 1 = generic.
