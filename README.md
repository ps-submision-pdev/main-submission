# Buddy Zero: a small learning buddy for IIT Patna

Buddy Zero helps one IIT Patna B.Tech student pick courses for the coming semesters.

I tested it on one made-up student: a 2nd-year Chemical Engineering student who must finish the normal
coursework, wants to build computing and data skills for process data and simulations, and is weak in maths.

The buddy reads only a small knowledge base (KB). While it runs, it never goes to the web. The only outside
call is to the model provider, and that goes through one file, `buddy/llm.py`.

## Read these first

| File | What it is |
|---|---|
| `data/demo/chem_data_s4.slice.json` | the KB the buddy reads for this student |
| `data/demo/chem_data_s4.review.md` | what the model chose for the KB, and why |
| `data/demo/chem_data_s4.decisions.jsonl` | every model decision, with code's verdict on it |
| `buddy/rules.py` and `tests/` | the rule checks and the tests that catch bad plans |
| `data/demo/token_summary.md` | token use of every model call |
| `build_log.txt` | my build log, in my own words |
| `log.md` | the coding agent's run log: what it built, what broke, what it fixed |

## How it works

1. Download the public IIT Patna PDFs (`ingest/fetch.py`). Every source is listed in `ingest/sources.yaml`.
2. Extract the text, then turn it into course records (`ingest/extract.py`, `ingest/parse.py`).
3. Fill the slots (HSS, IDE, DE) and settle clashes between sources (`ingest/slots.py`, `ingest/resolve.py`).
   The result is the **database**: 1180 courses, no student in it (`data/db/`).
4. Read the persona, find what this student may actually take, and cut the database down to a **KB slice**
   (`buddy/kb_build/`). This is where code and the model work together.
5. The buddy loads the slice and nothing else.

The database holds every course. The KB holds only what one student needs.

## What code does and what the model does

The rule I followed: if the model can be wrong and code can check it, code checks it.

| The model | Code |
|---|---|
| ranks the elective options for this student | checks every course code exists |
| suggests prerequisites, with a quote from the course text | checks the quote is really in the text, and that there is no cycle |
| suggests courses that help with each weak topic | checks the course is allowed in that slot |
| | does all credit, contact-hour and rule checks |
| | decides if a plan is valid |

Anything the model says is stored as `llm_inferred`, trust 0.3, `verified: false`.
Facts that came straight from a source page are stored with trust 0.9 and the page, quote and link.

## The rules in the KB

All four are from the B.Tech Ordinance, each with page, clause and the exact line:
https://academics.iitp.ac.in/images/regulation/B.Tech_Ordinance_2019_onwards.pdf

- 8.4(a): pass all first-year courses before registering for third-year courses.
- 8.4(c): from semester 5, a student with CPI of at least 8.0 may take one extra course, with approval.
- 8.4(b): at most 32 contact hours per week.
- 12.1(a): CPI below 5.0 gives a warning, and two such semesters in a row may end continuation.

Two things I looked for and did not find on public pages: a per-semester credit limit on the new scale,
and who may take a Minor. They are listed in the slice as open limits, not guessed.

## Token use

Every model call is logged by `buddy/llm.py` (no keys, no full prompts) and summed by `scripts/token_summary.py`.

- 9 calls: 5 real, 4 answered from the cache, 0 failures.
- About 41,000 tokens in total (prompt plus completion), all on a free OpenRouter model.
- The biggest call was the prerequisite step (about 18,000 tokens), because the model writes a quote for each edge.
- Full table: `data/demo/token_summary.md`.

## What is checked, and what is not

- The slice has 14 full course records. Size, course-exists and slot-membership checks pass.
- 115 tests (last run). They include tests that reject made-up course codes and courses outside the allowed slot.
- Nothing in the slice is marked `verified: true` yet. I have not spot-checked it by hand.

## Honest limits

- Some courses have no description text. I only downloaded the syllabi of departments this student would
  realistically use. Courses from the others (for example HSS, Civil, Physics) have a code and title but no
  text. The model is told this and says so; code also flags them. A full system would hold all departments.
- The prerequisite check does not look at semester order. So it let through "MA2206 (sem 4) needs MA3107 (sem 5)".
- The quote check accepts very short quotes such as "ODE", which appear in the text but do not prove a dependency.
- The model once called a course a "lab course" with no text to support it. Code now drops that kind of claim
  when the course has no practical hours.
- The rules come from the 2019-onwards ordinance. I have not confirmed it is the latest one.
- Still to do: the buddy itself (profile store, planner, memory), and my own hand-check of the KB.
