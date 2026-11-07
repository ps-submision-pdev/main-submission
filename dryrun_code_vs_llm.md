# Recording-script dry run: code vs model split

Who answered each step of the dry run (first run, real model). "Code" means no model call and 0 tokens.
Source: `data/logs/dryrun.md` (which calls each turn made) and the timings in `make_it_solid.md`.

| Step | Answered by | Model calls | Seconds | Tokens |
|---|---|---|---|---|
| 1. Start with `--reset` | code | none | 0 | 0 |
| 2. Intake message | model | intake, choose | 47.6 | 3,564 |
| 3. `/profile` | code | none | 0 | 0 |
| 4. "what is rule 8.4(c)?" | code | none | 0 | 0 |
| 4b. `/tokens` | code | none | 0 | 0 |
| 5. Add MA2206 as an extra course | model | revise | 94.9 | 3,766 |
| 5b. "Can I also take Numerical Methods this semester?" | model | revise | 30.5 | 1,698 |
| 6. "Which of my courses covers Python and data analysis?" | model | route, answer | 4.2 | 504 |
| 7. `/quit`, restart without `--reset` | code | none | 0 | 0 |
| 8. `pytest -q` | code | none | 3.0 | 0 |

## Totals

| | Steps | Model calls | Tokens |
|---|---|---|---|
| Code only | 6 of 10 | 0 | 0 |
| Model | 4 of 10 | 8 | 9,532 |

## Notes

- Code still works inside the model steps: it routes the change request by course code, checks the change as
  asked (rule 8.4(c) with page and quote) before any model proposal, and checks every plan the model proposes.
  The model only proposes plans and words the answer.
- Rule questions, `/profile`, `/tokens` and restarts never use the model.
- The repeat run made 0 real model calls: all answers came from the cache.
