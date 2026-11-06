# Make it solid: recording-script dry run

Before recording the demo, I ran my exact recording script on the real chat (`python3 -m buddy chat --persona chem_data_s4`) with the real model, then ran it a second time to check that the same input gives the same plan. The numbers below come from those runs (transcripts were kept in `data/logs/dryrun.md`, which is not committed).

## 1. Every step of the script works

All 11 steps passed, and `python3 -m pytest -q` passed (171 tests).

| Step | Result | Seconds | Tokens |
|---|---|---|---|
| 1. Start with `--reset` | pass | 0 | 0 |
| 2. Intake message | pass | 47.6 | 3,564 |
| 3. `/profile` | pass | 0 | 0 |
| 4. "what is rule 8.4(c)?" | pass | 0 | 0 |
| 4b. `/tokens` | pass | 0 | 0 |
| 5. "Change my plan: add MA2206 as an extra course in semester 4." | pass | 94.9 | 3,766 |
| 5b. "Can I also take Numerical Methods this semester?" | pass | 30.5 | 1,698 |
| 6. "Which of my courses covers Python and data analysis?" | pass | 4.2 | 504 |
| 7. `/quit`, then start again without `--reset` | pass | 0 | 0 |
| 8. `pytest -q` | pass | 3.0 | 0 |

What each step showed:

- **Intake** saved what I said as self-declared facts (trust 0.4): a goal, the weaknesses "probability" and "statistics" (matching the knowledge base), and the known topic "basic Python". It said there are no check questions for basic Python yet, so nothing is skipped. It then made a plan for semesters 4 and 5 with no rule broken; every course is tagged "checked, source page N" and every model reason "model guess, unverified".
- **`/profile`** showed my grade record as graded (trust 0.9: CPI 6.4, MA1201 grade DD) and what I said as self-declared (0.4).
- **The rule question** was answered by code with 0 tokens: rule 8.4(c) with its page (4) and the exact quote from the ordinance.
- **Adding MA2206 as an extra course** was routed by code to a plan change. The checker rejected it, showing rule 8.4(c) (extra courses only from semester 5 with CPI at least 8.0; my CPI is 6.4) with page 4 and the quote, and a warning that the IDE-I slot already has CS2207. It then showed a plan the checker approved: MA2206 replaces CS2207. No plan that breaks a rule was shown as accepted.
- **"Can I also take Numerical Methods"** was treated as a plan change, not as a plain question.
- **The Python and data analysis question** answered CS2207 Introduction to Data Science, with its source page (19) and no invented course.
- **Restarting** greeted me with my saved plan version.

Token and time notes: 8 real model calls in total, 28.3 seconds per call on average, 1 call over 60 seconds (the plan change, 94.9 s). Steps answered by code cost 0 tokens.

## 2. The same input gives the same plan

I ran the whole script again, exactly the same way.

| Plan version | Made by | Electives, semester 4 / 5 | Same as the first run? |
|---|---|---|---|
| 1 | first plan after intake | CS2207 / MA3107 | yes |
| 2 | adding MA2206 (after the 8.4(c) rejection) | MA2206 / MA3107 | yes |
| 3 | "also take Numerical Methods" | MA2206 / MA3107 | yes |

The core courses were the same in every version. Every reply was word for word the same, including the rule 8.4(c) rejection with its page and quote. Only the timings, the token counts and the date in the restart greeting differed.

Why: the second run made no new model calls (0 tokens). Every model answer came from the cache, which is keyed by the model, the prompt version and the exact messages, so the same input replays the same answer. Without the cache, the model runs at temperature 0; in my research runs that gave the same course choices with differently worded reasons. Either way, code checks every plan, so a plan that breaks a rule is never accepted.
