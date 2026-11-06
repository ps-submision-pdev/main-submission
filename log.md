# Agent run log

Factual log of what the coding agent (Claude Code) ran in this repo, why, and what came out.
Written for the student's own LLM to read. Not the build log: `build_log.txt` is the student's.
Newest entries at the bottom. Commands are run from the repo root.

---

## 2026-11-05/06: earlier sessions (summary, reconstructed)

- `python3 -I ingest/fetch.py`, `python3 -I ingest/extract.py`: downloaded and extracted the 7 sources
  in `ingest/sources.yaml`. The agent ran these itself, although CLAUDE.md step 0 says the student runs them.
- Added `.docx` support to fetch and extract, because the Chemical syllabus (`cbe_btech`) is published
  only as a Word file. The PDF output was checked to be identical to the earlier run.
- Wrote `ingest/parse.py` and `tests/test_parse.py` (8 tests).
  Result: `data/db/courses.json` (1138 courses) and `reports/parse_quality.md` (152 issues).
- Parser bugs found on real data and fixed:
  - placeholder codes were reported as rows without a code;
  - the "Core V" title prefix was kept;
  - `ME2102-Thermodynamics` was not matched;
  - the Engineering Mechanics block was lost;
  - en-dash credits were not read;
  - project credits were flagged as mismatches.

## 2026-11-06: Step 1, elective slot and owner

- New `ingest/slots.py`. It walks every table row and writes `data/db/list_entries.json` (3222 entries).
  Each entry has these fields: owner_department, level, slot_type, slot_number, eligibility_note,
  is_placeholder, in_scope.
- Ran `python3 -I ingest/slots.py` several times. Bugs found and fixed:
  - Chemical semesters 1-2 showed DE/IDE slots. These came from the M.Tech table, so `level` was added.
  - Department names wrapped onto two lines were cut short ("Civil and"). The next line is now joined.
  - The first version of that join also swallowed "B. Tech. in Chemical Engineering..." and,
    as a test later showed, a semester heading. The rule is now: join only if the next line is
    words and "&", at most 40 characters, and not a semester heading.
- Result:
  - Chemical B.Tech optional slots, the same in 3 documents: S3 HSS-I; S4 IDE-I; S5 IDE-II;
    S6 DE-I; S7 DE-II, DE-III, IDE-III, HSS-II; S8 DE-IV, DE-V, DE-VI.
  - 18 distinct eligibility notes, kept verbatim.

## 2026-11-06: Student decisions after Step 1, applied

- Year kept: planning from semester 5.
- `minor` kept as a slot type. Open question added to CLAUDE.md: may a Chemical student take a Minor?
- Owner is null where the page has no "Programme from the Department of" line. It is never inferred from the code.
- Added `in_scope`: false for placeholders, slot-less rows, and M.Tech / M.Sc. / dual-degree tables.
- CB4298 checked in `btech_program_nep2020` p3: the row `CB4298 DE-VI` is a slot placeholder.
  Placeholder rows get `code: null`, and their code moves to `slot_code`.
  - A second pass keeps real courses written with a slot label (`EC2102 Minor I` is Signals and Systems).
  - 4 placeholders have real-looking codes: CB4298, MM2290, MM3190, MM4123.
- IDE list rows get `semester: null`.
  - `slot_semester()` places them in the student's own table: IDE-I → 4, IDE-II → 5, IDE-III → 7 for Chemical.
- One report file with a section per stage.
  - `parse.py` gained `write_report_section()`, plus a one-line change to use it.

## 2026-11-06: Step 2, resolve

- New `ingest/source_priority.yaml`, which holds the priority order and owner_sources.
  The order is curriculum_nep2020, cbe_btech, cse_btech, cse_aids_btech, math_btech_mc, btech_program_nep2020.
- New `ingest/resolve.py`:
  - `resolve_claims()` returns value, chosen, conflict, and all claims; nothing is dropped.
  - `resolve(course_id, db)` also resolves the owner (from the NEP documents only),
    copies `lists` unresolved, and sets `in_scope`.
- Ran `python3 -I ingest/resolve.py`. Output: `data/db/resolved.json`.
  - Conflicts: title 72, ltpc 11, outcomes 11, owner 0.
  - Example: PH1101 resolves to 3-1-3-5.5 (curriculum p1), conflict true; math_btech_mc p9 says 3-1-0-4.
- Tests: `tests/test_resolve.py` (4) and `tests/test_slots.py` (4). `python3 -I -m pytest tests -q`: 16 passed.
- Findings raised with the student:
  - CS3202's wrong prerequisite "offline" is the same in both CSE PDFs, so resolve sees no conflict.
    A checker is needed for that.
  - `btech_program_nep2020` numbers electives differently (CB3211-14 vs CB3206-09, CS2209 vs CS2207,
    MA2251 vs MA2206). Added to the CLAUDE.md open questions.
  - MA4107 has two different L-T-P-C values, and the Maths syllabus calls Number Theory MA4112.

## 2026-11-06: Student decision: "don't keep any conflict" (option C)

- The student chose option C: a course with a conflict on a key field (title, ltpc, prerequisite,
  owner_department) stays in the database but gets `in_scope: false` and `excluded_for_conflict: [fields]`.
  Conflicts on text fields (objectives, outcomes, ...) are flagged only.
- `resolve.same()` now ignores formatting: case, spacing, punctuation, bullets, list numbers, and a "(Minor I)" suffix.
  - Reason: under the old comparison, 72 courses were "conflicted", mostly by noise such as
    "M e chanical" and "• To understand". That would have excluded MA1201, CS1101 and CS1201.
- Result: 54 courses excluded for conflict; 432 in scope (was 473).
  - Persona-relevant losses: PH1101 (3-1-3-5.5 vs 3-1-0-4) and ME4103
    ("Nonlinear Dynamics and Chaos" vs "Industrial Automation"). Both are real conflicts.
- Tests: 2 added to `tests/test_resolve.py` (formatting noise is not a conflict; a key-field conflict excludes
  and a text-field conflict does not). 18 passed.

## 2026-11-06: Step 3, quality report

- New `ingest/check_db.py`. It writes the "check" section of `reports/parse_quality.md` (flag only) and prints
  10 random in-scope records (seed 7) with source, page, raw line and URL for checking by hand.
- Ran `python3 -I ingest/check_db.py`. Results:
  - no L-T-P-C: 0
  - credits != L+T+P/2: 0 (23 projects and internships are listed separately)
  - one code used for different courses: 49
  - one title under different codes: 102. Mostly legitimate: each department has its own
    "Fluid Mechanics", and 60 rows involve postgraduate codes. 21 rows involve codes that appear only in
    btech_program_nep2020's renumbering.
  - spans not found in page text: 0 (every stored quote was found)
  - excluded for conflict: 54; flagged text conflicts: 9
  - prerequisite naming no course code: 1 (CS3202 "offline"). ": NIL" was first counted here and then
    treated as "no prerequisite".
- Sample of 10: CB3208, CB4202, CE2101, CE4110, CS4103, CS4213, EC3203, MA2105, ME2204, PH4213.
- Found: the Senate document's DE lists ("1. Catalysis Science and Engineering (CB3211)", code after the title)
  are not parsed, so CB3211-CB3214 are not in the database at all.

## 2026-11-06: Task A: code-after-title rows (Senate DE lists)

- Format: "DE-I 1. Catalysis Science and Engineering (CB3211)". Found only in btech_program_nep2020 pp3-4
  (24 lines, all Chemical: DE-I..DE-VI lists plus the IDE list). These lines have no L-T-P-C.
- `parse.py`: new pattern `CODE_AFTER_TITLE`. These rows are stored with `ltpc: None`, and `merge` skips a
  missing L-T-P-C.
- `slots.py`:
  - the same pattern;
  - the slot number of a "DE-I 1. ..." group is carried to the rows below it (CB4220 on p4 stays in DE-VI);
  - new post-pass `place_department_electives()`: a DE list row gets its semester from the slot's position
    in the owning department's semester table (DE-I → 6, DE-II/III → 7, DE-IV..VI → 8). This also fills
    the semester of cbe_btech's own DE lists (CB4102 → 7).
- Re-ran parse → slots → resolve → check_db: 1162 courses (+24), 3246 list entries.
  - "No L-T-P-C" is 24: exactly these rows.
  - "One title under different codes" rose from 102 to 124: the new Senate codes duplicate the cbe_btech
    codes (CB3211 = CB3206 "Catalysis Science and Engineering").
  - These Senate-only codes are in scope; this is not resolved yet.
- Tests: 1 in test_parse.py, 1 in test_slots.py (real lines). 20 passed.
- The 49 "one code used for different courses" cases, grouped by cause (no data changed):
  - A, same course with different spelling: 10
  - B, slot label captured as the title ("Minor I", "IDE II"): 9
  - C, a note appended to the title ("(Pre-requisite IIM Mumbai)"): 4
  - D, parser junk from wrapped PDF rows: 3
  - E, the Senate document gives a different course for the code: 13
  - F, the code is reused for different courses in other documents: 10
    (B.Tech vs M.Sc./M.Tech/dual: 7; within the same programme: ME4103, CS4105, MA4212)

## 2026-11-06: Task B: rule candidates (plain code, no LLM)

- Scope (student's decision): btech_ordinance, curriculum_nep2020, btech_program_nep2020, cbe_btech.
- New `ingest/rule_candidates.py`, which writes `reports/rule_candidates.md`. Paragraphs are verbatim, with
  source id, page and clause number.
  - Ordinance paragraphs come from the stored page tables ([clause, text] rows). The PDF centres the clause
    number beside its text, so plain text cannot show where a clause starts.
  - Docx: one line per paragraph. PDFs: lines are joined until "." or ":" or a marker.
  - Course table rows and course syllabus pages are skipped.
- Topics 1-4, the student's 10 extra keywords, sub-question checks, and two flags (per-semester scale,
  degree scale). Identical paragraphs repeated in a document are merged, with their "also pages" kept.
- Bugs found while checking the output, and fixed:
  - "Course Title L T P C" (a column header) marked curriculum p40 as a syllabus page, so the Minor in
    Business Studies heading was skipped. Syllabus pages are now detected by "Course Number" only.
  - The degree-total pattern also read Minor totals ("Total credits: 17"). It now reads only
    "Total Credits (including ...)".
  - The degree-scale flag read "Page 20 of 195" footers as 195 credits. Footers are now removed first.
  - The first scale flag missed ordinance 7.2/7.4 ("between 280 and 300"). A degree-scale flag was added.
- Result: 2000 paragraphs searched.
  - Topic hits: credits 20, CPI 15 (all ordinance), minor 57 (mostly list headings), registration 34.
  - No paragraph says who may take a Minor (except "Minor in Business Studies: (Only open to B. Tech. /
    BS-MBA Dual Degree)", curriculum p40).
  - No Minor CPI, no probation clause, no "honours".
  - First-year before third-year: only ordinance 8.4(a), p4.
  - Flags: ordinance 8.4(b) 30-50 credits per semester vs NEP semester totals 16-23.5; ordinance 7.2/7.4
    280-300 degree credits vs NEP 166 (Chemical).
- Found: CLAUDE.md says the degree total is 167, but cbe_btech and curriculum_nep2020 say 166 for Chemical.
  Not changed; raised with the student.

## 2026-11-06: Task C: Senate code duplicates (marked only)

- Student: be relaxed about academic rules (they do not affect the product much). Task B's output is final as is.
- `resolve.py`: new `mark_possible_aliases()`, a post-pass.
  - A code that only btech_program_nep2020 has, that is in scope, and whose title matches (by `same()`) a
    title claim from any other document gets `possible_alias_of: [other codes]`.
  - Each other code gets the Senate code back.
  - `in_scope` is not changed and nothing is chosen.
- New report section "Possible aliases" in the resolve part of `reports/parse_quality.md`. It has 57 pairs,
  each with the page and verbatim line from both documents.
  - 46 Senate-only in-scope codes; 45 have a match, MA4152 "Mathematical relativity" has none.
  - 10 match more than one code (e.g. MA4114 Deep Learning → CS3202 and MA4104;
    CB4116 Nanomaterials → CB4106 and MM4107). Postgraduate matches (MA5103, EE6107, ...) are listed too.
- Bug fixed: the table's "other line" showed the first non-Senate title claim even when that claim
  disagreed (MA4116 → MA5105 showed "Fundamentals of Block Chain"). It now shows the claim that matched.
- Test added: `test_senate_only_code_is_marked_as_possible_alias_not_chosen`. 21 passed.
- Group E (Senate gives a different course for the same code), filtered to those a Chemical student could
  take (an IDE list open to other departments, a Chemical list, or a Minor list):
  - CS4109: in the Senate's IDE-III list (p12/p15) vs DE-III in cse_btech, cse_aids_btech and the curriculum.
  - MA4113: in math_btech_mc's IDE-III list "(Available to students other than Dept. of M&C)" p5.
  - None involve Chemical. The other 11 are DE or core courses of CE/CS/EE/MA, are not on any IDE or
    Minor list, and are not open to a Chemical student.
  - CS4109 and MA4113 are already excluded under option C (title conflict).

## 2026-11-06: Rule records, rule checker, degree total

- CLAUDE.md degree total corrected from 167 to 166 for Chemical, after confirming:
  - cbe_btech p3 "Total Credits (including B. Tech. first year): 166", and its 8 semester TOTAL rows sum to 166.0;
  - the same in curriculum_nep2020 p4 and btech_program_nep2020 p3.
- New `ingest/build_rules.py`, which writes `data/kb/rules.json`. It has 4 rules chosen by the student:
  ord-8.4a-first-year-before-third-year, ord-8.4c-overload, ord-12.1a-low-cpi, ord-8.4b-contact-hours
  (second sentence only, with a note that the 30-50 credit sentence is on an old scale).
  - Each rule record has id, kind, text, parameters, provenance {source_id, url, clause, page, quote},
    fetched_at and sha256 from the manifest, and verified=false.
  - Quotes are checked against the stored page text with whitespace collapsed. All 4 were found;
    a one-number change ("32" to "34") is not found.
  - Open limits recorded in the same file: no per-semester credit limit on the NEP scale, and no
    Minor eligibility rule.
- New `buddy/` package and `buddy/rules.py`: `check_plan(plan, profile, programme, catalog, rules)` returns
  findings {rule_id, semester, severity violation|warning, message}.
  - Every number comes from the rule's parameters.
  - An unknown course code gives a "kb-course-exists" violation.
  - A rule without a checker raises an error.
- Tests written first (`tests/test_rules.py`, 8 tests, real rules.json). They failed before the module existed.
  - One test was wrong: 8 courses are also 33 contact hours, so 8.4(b) correctly fires as well.
    The test now expects both violations.
  - 29 passed in total.

## 2026-11-06: Task D: buddy/llm.py

- The module was explained to the student in plain words before any code was written.
- Tests were written first: `tests/test_llm.py`, 9 tests with a fake LiteLLM (no key, no network).
  They raise real `litellm.RateLimitError` and `litellm.Timeout`, which can be created offline (litellm 1.108.0).
  - Cases: rate limit then success; timeout then success; retries exhausted (4 calls, sleeps 1, 2, 4);
    broken JSON then repaired; broken JSON twice (clear error, no crash); cache hit makes no second call;
    a new prompt version is not a cache hit; a token log line is written and the key is not in it;
    missing LLM_MODEL gives a clear error.
  - The tests failed before the module existed.
- New `buddy/llm.py`, with class `LLMClient` and method `ask_json(messages, schema, prompt_version)`, which returns
  {ok, data, cached} or {ok: False, error} and never raises.
  - Reads LLM_MODEL, LLM_API_KEY and LLM_API_BASE from the environment; it does not read .env.
  - temperature 0 and a timeout.
  - Retries RateLimitError, Timeout, APIConnectionError, InternalServerError and ServiceUnavailableError,
    with backoff min(2**attempt, 8) and max_retries 3.
  - The schema is a dict mapping key to Python type, checked in plain code (no pydantic).
  - One repair call.
  - Cache at data/cache/llm/<sha256 of model, prompt_version and messages>.json, written only on success.
  - Log at data/logs/llm_calls.jsonl, one line per call, failures and cache hits included.
- 38 tests pass in total.
- Not changed, reported to the student:
  - chat.py and test.py (see the message);
  - requirements.txt does not list litellm or pytest;
  - .gitignore ignores data/cache/, but CLAUDE.md wants cached outputs for the demo;
  - data/logs/ is not ignored.

## 2026-11-06: requirements, .gitignore, demo folder, token summary

- Scanned the imports in ingest/, buddy/ and tests/ with `ast`. Third-party packages: litellm, pdfplumber, requests,
  PyYAML, and pytest as the runner. The .docx support uses only the standard library (zipfile, xml.etree).
  - Added to requirements.txt: `litellm>=1.108` and `pytest>=8.0`. The other three were already listed.
- Fresh venv (Python 3.11.17; 3.10 is not installed on this machine), created in the session scratchpad:
  `pip install -r requirements.txt`, then `python -I -m pytest tests -q` with LLM_* unset.
  Result: 38 passed, then 41 after the token-summary tests were added.
- .gitignore: data/cache/ kept, data/logs/ added. data/demo/ is committed, with a one-line README.md and no
  content yet. Checked with `git check-ignore`.
- New `scripts/token_summary.py`: a table per (prompt_version, purpose) of calls, cache hits, failures, and
  average prompt/completion tokens over successful real calls. It prints only counts and call-type names.
- New `tests/test_token_summary.py` (3 tests, fake log):
  - the counts and averages are right;
  - a line with a fake key and a full prompt prints neither;
  - a missing log file is not an error.
- 41 tests pass.

## 2026-11-06: KB builder Step 1: persona loader

- Told the student: CLAUDE.md says to build Phase 2 after the buddy works. The student's instruction is followed.
- New `config/trust.yaml`, the single place for trust numbers (CLAUDE.md):
  - evidence: graded 0.9, tested 0.7, self_declared 0.4
  - kb: explicit 0.9, inferred 0.3, llm_inferred 0.3, self_declared 0.4
- New package `buddy/kb_build/`. `__init__.py` holds the PRINCIPLE text from the student.
- New `buddy/kb_build/persona.py`: `load_persona(path, db=None)` raises PersonaError naming the bad field.
  - Exactly 12 fields; types; planning_semester 1-8; year = (planning_semester+1)//2.
  - programme_id must be a syllabus source in sources.yaml (the department is read from there).
  - Constraint keys are checked.
  - Evidence trust must equal config/trust.yaml.
  - With a db, already_done and not_together codes must exist.
  - persona_id is limited to a-z, 0-9 and _, because it becomes part of file names.
- New `personas/chem_ml_demo.json` (synthetic): cbe_btech, year 3, planning semester 5.
  - already_done: 22 codes (Chemical semesters 1-4 core; the HSS-I and IDE-I picks are unknown, so left out).
  - Evidence: CPI 6.4 and MA1201 grade DD (graded); 2 known topics and 1 weakness (self_declared).
- Tests first: `tests/test_persona.py` (9). They failed before the module existed; 50 pass in total.
- Note: `python3 -I -c` cannot import `buddy` (-I keeps the current folder off sys.path). The CLI
  `python3 -m buddy.kb_build` has no -I.

## 2026-11-06: Full elective list for Chemical; 4 slots.py bugs found and fixed

- The student asked for every elective a Chemical student can take, for all years. It was built from data/db by an
  analysis script in the session scratchpad (not repo code), then checked against the raw page text.
- Bugs found in `ingest/slots.py` while building it, each fixed with a test using real lines (53 tests pass):
  1. A sub-heading ("HSS Elective-I", "IDE-I") wiped the eligibility note of its parent list. The whole institute
     HSS list and several IDE lists were therefore out of scope. Now a same-type sub-heading keeps the parent's note.
  2. `in_scope` looked for "B. Tech" with a space. The HSS IDE heading says "B.Tech.". Now `B\.\s*Tech`.
  3. After joining a wrapped heading, the continuation line ("of HSS)") was read again as a heading of its own.
     Now it is skipped. Also, `slot_type_of` checks IDE before HSS, because "IDE ... other than Dept. of HSS"
     is an IDE list.
  4. The BS Economics specialisation electives (HS4101-HS4112, HS4201-HS4211, curriculum p39) were taken as HSS
     IDE-III. A "List of ..." line that names no slot type now closes the current list.
- Pipeline re-run (slots, resolve, check_db). The database check counts are unchanged, and so is the Chemical
  slot table.
- Parser gap found, not fixed: curriculum p48 Mechanical IDE row "ME2205 Manufacturing Processes for" /
  "1. 3 0 0 3" / "Metallic Materials" (code on the line above the numbered row). ME2205 is not in the database.
  Listed by hand in the answer.
- Result for Chemical: DE 21 (own department); HSS-I 11, HSS-II 7; IDE-I 13, IDE-II 14, IDE-III 11 usable,
  plus Mechanical and Materials IDE lists with no slot number. Minors are listed with eligibility unknown.

## 2026-11-06: Parser fix: code above the credits row

- Layout (curriculum p48): "ME2205 Manufacturing Processes for" / "1. 3 0 0 3" / "Metallic Materials".
- `parse.py`: new helper `code_above_row(lines, i)`, used by both `parse_rows` and `slots.walk`.
  - A line that is only a serial number plus L T P C, under a line "CODE title-start", is one row.
  - The next line is joined onto the title only if it is plain words (no digits), at most 60 characters,
    and not a heading. So the "Page 48 of 195" footer is not joined to ME3104.
- Tests: 1 in test_parse.py (ME2205 with a title end, ME3104 with a footer) and 1 in test_slots.py
  (ME2205 keeps the ME IDE note). 55 pass.
- Re-run: 1180 courses (+18), 3314 list entries (+68). All 72 rows in this layout have complete, correct titles.
  - Title conflicts rose from 49 to 54; excluded from 54 to 59. The new conflicts are real:
    - CE6114, CE6211, CE6102: spelling (postgraduate, out of scope);
    - CE4212, CE4213, MA4112: the Senate document gives a different course for the code.
  - MA4112 (Maths IDE-III "Number Theory and Algebra"; Senate p27 "Cryptography and Network Security")
    is now excluded.
- ME2205: IDE, in scope, note "other than Dept. of ME". ME3104: minor (Thermal Engineering) and lab.

## 2026-11-06: KB builder Step 2: shortlist

- New `buddy/kb_build/shortlist.py`: `shortlist(persona, db, limit=40)`, code only.
  - in_scope only. Terms are goal_keywords, weaknesses and known_topics, lowercased and de-duplicated.
  - Whole-word or phrase match with an optional plural, over the resolved title, objectives, outcomes
    and description.
  - Score: +1 per term, +1 per term in the title. Sorted by score, then code. Score 0 is dropped.
    Each result lists the matched terms and the fields they were found in.
- Tests first: `tests/test_shortlist.py` (5).
  - My first expected order was wrong: MA1201 scores 3 and ties CS3103. Fixed in the test before
    writing the module.
  - 60 tests pass in total.
- Demo persona: 13 terms, 500 in-scope courses searched, top 40 shown to the student.
  - The 40-course limit cuts inside the score-2 tie (alphabetical cut); see the message.

## 2026-11-06: Correction before Step 3: available set, slot-based shortlist, slot membership

- New `buddy/kb_build/available.py`: `available_for(persona, list_entries, db)`.
  - Slots come from the persona's own B.Tech semester-table placeholders, kept from planning_semester to 8.
  - Options: own-department DE-n; HSS-n open to B.Tech; other departments' IDE-n whose note allows the student.
  - `note_verdict`: "other than Dept. of X" excludes the list's owner; "not applicable for B. Tech. <programme>"
    excludes that programme; "for all approved / open to B. Tech." allows; anything else is unknown.
    Excluded beats allowed, which beats unknown. Unknown is listed separately, never as an option.
  - Senate duplicates are dropped within a slot across allowed and unknown, keeping the higher-priority source.
  - Allowed IDE lists with no slot number (ME, MME) go to `unplaced`. Minors are returned as eligibility
    unknown, with identical printings merged.
  - Core courses in the window are returned separately as fixed.
- `shortlist(persona, db, available, limit=40)` now searches only slot options.
  - Ties break by slot (semester, then label), then code.
  - Returns {results, matched, cut, cut_inside_tie}.
  - Bug caught by a test: a per-course rank was used instead of the slot's position.
- Slice format recorded in the `buddy/kb_build/__init__.py` docstring: core {sem: [codes]} plus
  slots [{slot, semester, options}].
- `buddy/rules.py`: new KB check "kb-slot-membership". A planned course must be core for its semester or an option
  of a slot in that semester.
  - A test caught a real bug: after a JSON round trip every semester/year key becomes a string, which broke
    courses_by_year, courses_per_semester and core. `check_plan` now converts plan and programme keys to int.
  - Rule-test fixtures updated: the overload "extra course" is now CS3106, a real sem-5 IDE-II option.
- Tests: test_available.py (9), test_shortlist.py (rewritten, 6), test_rules.py (+4). 74 pass.
- Demo persona: 9 slots in S5-S8, 51 options.
  - unknown: CH3104 (no note), MA4151 and MA4152 (Senate-only; the department codes MA4107/MA4112 are
    excluded for conflicts).
  - Core: S5 5, S6 5, S7 2 (internship, project), S8 1 (project).
  - Unplaced: 5. Minors: 17 groups.
  - Shortlist: 10 options match; no cut.
- CLAUDE.md conflict raised, not changed: it says planning from S5 "covers 8 of the 10 slots"; the data says
  12 optional slots in total, 9 of them in S5-S8.

## 2026-11-06: KB builder Step 3: eligibility filter

- CLAUDE.md corrected (student said yes): 12 optional slots in total; planning from S5 covers 9 of them (listed).
- `available.py` additions:
  - per slot `eligibility: {code: why allowed}` (own department DE list, or the note's wording);
  - `core_before_window: {sem: [codes]}`;
  - `excluded_unplaced`: courses excluded by a note on a list without slot numbers. Chemical's own IDE list
    was previously skipped silently.
- New `buddy/kb_build/eligibility.py`: `filter_available(persona, available, db)` returns {available, removed}.
  - available: a copy, with already_done removed from options and core. The input is not changed.
  - removed: [{code, slot, category, reason}], sorted, for review report Section C. Categories: already done,
    ineligible, alias, out of scope, eligibility unknown, core outside window.
- Pipeline order is now persona -> available -> eligibility -> shortlist.
- Tests first: `tests/test_eligibility.py` (6). 80 tests pass.
- Demo persona: 41 removed.
  - alias 26, ineligible 6 (Chemical's own IDE list in both numberings), out of scope 6, eligibility unknown 3.
  - already done 0 and core outside window 0: all 22 earlier core courses are in already_done, and none of
    the window's courses are.
  - 51 options remain; the shortlist matches 10, with no cut.

## 2026-11-06: KB builder Step 4: rank (model, ids only)

- Told the student: the 51 options are electives only; the 13 compulsory courses of S5-S8 go into the slice
  as `core` and are not ranked. Raised that 13 core + 51 electives far exceeds the brief's 8-15-course KB.
  Proposed `options_per_slot` (default 2, i.e. 18 electives), plus a possible core-only-as-codes option.
- `buddy/llm.py` extended, not rewritten: `ask_json` now also returns `usage` {attempts, prompt_tokens,
  completion_tokens, total_tokens} for that one question. The cache hit gives zeros. A test was added first.
- New `config/kb_build.yaml` (options_per_slot 2, description_chars 240) and
  `buddy/kb_build/prompts/rank_v1.md`, whose file name is the prompt_version.
- New `buddy/kb_build/rank.py`: `rank(persona, available, shortlisted, db, llm, settings)`.
  - Candidates are all slot options. Each sends code, title, credits, owner, slot, semester, the first
    240 characters of the description, and the keyword score and matched terms as hints.
  - Code checks each item: an object, a candidate code, not a duplicate, a non-empty reason, and under the
    slot budget. Each verdict is recorded.
  - Slots the model leaves short are topped up from the fallback order (score, slot, code).
  - With no model, a failed call or no valid item, the whole ranking is the fallback (rank_source "fallback").
  - Returns by_slot, decisions (step, said, verdict, evidence, tokens) and usage.
- Tests first: `tests/test_rank.py` (7) and 1 in test_llm.py. 88 pass.
- Demo with --no-llm: fallback picks per slot shown to the student.
  - A real run would send 51 candidates, about 16.5k characters (~4.1k tokens).
  - No real model call yet: the settings are only in .env, which the agent does not open. The CLI
    (Step 11/12) will load .env through python-dotenv.
- Found: many candidates have no description text, because their department's syllabus was never
  downloaded, so the model sees only the title. Counts in the message.

## 2026-11-06: Change before Step 5: horizon, size check, text report

- `config/kb_build.yaml`: kb_horizon_semesters 2, options_per_slot 2, kb_min_courses 8, kb_max_courses 15,
  description_chars 240.
- New `buddy/kb_build/horizon.py`:
  - `split_horizon` returns inside (core and slots of S5-S6, which get full records and ranking),
    later_slots ({slot, semester, options} only) and later_core (codes only);
  - `full_record_count`;
  - `text_report`: per horizon course, whether it has description/objectives/outcomes; with none, the
    department syllabus it would come from (a sources.yaml id, or "not in ingest/sources.yaml (<dept>)").
- New `buddy/kb_build/checks.py`: `check_size` warns with the count outside 8-15 and never trims.
  The other KB checks come in Step 11.
- Tests first: `tests/test_horizon.py` (4). 92 pass.
- Demo persona (no model call):
  - horizon S5-S6; core 10; slots IDE-II (14 options) and DE-I (4); expected full records 10 + 2 + 2 = 14,
    size OK; 18 candidates to rank.
  - Later: 7 slots plus core S7 (CB4198, CB4199) and S8 (CB4299) as codes.
  - Text: 17 of 28 horizon courses have text; 11 have none, all IDE-II options from Civil, Chemistry,
    Electrical, HSS (6) and Physics (2).
- Manual check, not repo code: Word files of each department's B.Tech syllabus, downloaded to the session
  scratchpad during the earlier elective research. Only CH3106 (Chemistry), EC3106 (ECE) and PH3102
  (Physics) have a course page there. CE3105, PH3101 and the 6 HSS IDE-II courses have none: the HSS file
  is the BS Economics syllabus and lists them only in a table.

## 2026-11-06: First real model call (preview, student asked "what does the model recommend")

- The student wanted to see the model's recommendation, so one real ranking call was made over all 51 elective
  options (S5-S8). It is a preview, not the slice; the slot cap was lifted to show the full order.
- Script in the session scratchpad (not repo code): loads .env inside the Python process with python-dotenv.
  The agent did not open .env, and only the model name was printed. Timeout raised to 120 s for this call.
- Model: openrouter/nvidia/nemotron-3-ultra-550b-a55b:free. 1 attempt; 4670 prompt + 3962 completion = 8632 tokens.
  51 items, all accepted by code (no unknown codes, duplicates or empty reasons).
- Model's overall top 5: CS4113 (IDE-III S7), CS3106 (IDE-II S5), CB4103 (DE-II S7), CB4102 (DE-II S7),
  CB4207 (DE-VI S8). MA3107 is #10. 7 of the top 9 are in S7-S8.
- The answer is now cached in data/cache/llm/; the same input will not call the model again.
- Spot check of the reasons against the course text: see the message (they are unverified model claims).

## 2026-11-06: New persona chem_data_s4; rank_v1 vs rank_v2 compared on real model calls

- New `personas/chem_data_s4.json`, as specified by the student. `personas/chem_ml_demo.json` is unchanged.
  - synthetic; cbe_btech; year 2; planning_semester 4; goal: computing and data skills for process data
    and simulations; weak maths.
  - already_done: semester 1-3 core plus HS2113 (18 codes). known_topics: basic Python, data structures.
  - Evidence: CPI 6.4 and MA1201 DD (graded 0.9); 2 known topics and 1 weakness (self_declared 0.4).
- Tests first: 1 in test_persona.py (the new persona loads with the db) and 2 in test_rank.py.
  rank_v2 sends no score/matched and its prompt has no keyword wording; v1 stays the default. 95 pass.
- New prompt `buddy/kb_build/prompts/rank_v2.md`: like v1, but without keyword hints, and it asks the model
  to say when it judged a course by title only. `rank.py`: new `prompt_version` argument ("rank_v1"
  default); SENDS_HINTS decides whether score and matched are sent.
- Pipeline, no model (kb_horizon_semesters 2, options_per_slot 2):
  - window S4-S8; horizon S4-S5; core 10; IDE-I 13 options; IDE-II 14 options;
  - full records 14 (size OK); 46 removed before the model (alias 30, ineligible 6, out of scope 7,
    eligibility unknown 3);
  - 21 horizon options have no text; the keyword shortlist matches only 3 options.
- Real calls (model openrouter/nvidia/nemotron-3-ultra-550b-a55b:free; .env loaded in-process, not opened):
  - rank_v1: 4750 tokens; rank_v2: 5023 tokens. 1 attempt each, 27/27 items accepted each.
  - The top 5 are identical in both: CS2207, MA2206, MA3107, CS3106, MA3106. The slice keeps the same 4
    either way: IDE-I CS2207 and MA2206, IDE-II MA3107 and CS3106. Lower positions differ (e.g. MA2207
    6 vs 13, PH2203 7 vs 16).
  - Nothing was chosen for the student. Reason checks are in the message.
- Reason spot checks by code:
  - rank_v2 said "judged by title only" for MA2207, but MA2207 has a description. That is a wrong claim.
    It said so correctly for all 21 real title-only courses.
  - rank_v1 called CH3106 "a chemistry lab course", but CH3106 is 3-0-0-3 (no practical hours) and has no
    text. That is an invented claim.
  - Model reasons are unverified (llm_inferred) and must be shown as such.

## 2026-11-06: rank_v2 default; text_available; prerequisites; foundations; rules; first slice and review (chem_data_s4)

- config/kb_build.yaml: `rank_prompt_version: rank_v2` (rank_v1.md kept).
- rank.py:
  - code sets text_available per candidate (description/objectives/outcomes non-empty), stores it on each
    decision, and never sends it, so the messages are unchanged and the cached v2 answer is reused;
  - a leading "judged by title only" is removed from the stored reason; a wrong claim (the course has text)
    is recorded as a mismatch in the decision;
  - model reasons are stored with reason_source llm_inferred, trust 0.3 from config/trust.yaml, and basis
    text or title-based;
  - a reason claiming lab/practical work on a course with P = 0 is flagged "contradicted" and dropped.
    A bare "practical" is not a claim (the real MA2206 reason says "practical tools for simulations");
    tests cover both cases.
- New prereqs.py and prompts/prereq_v1.md.
  - Database codes become source explicit (0.9); "Nil" counts as an explicit none.
  - One model call for the remaining courses that have text, naming only slice or already_done codes.
  - Code drops unknown, not-allowed and self edges, duplicates, and edges that would create a cycle.
  - A verbatim quote found in the course text gives source inferred (0.3); otherwise llm_inferred, verified false.
  - No-text courses are not asked.
  - Note: this follows the student's new instruction (store edges without a quote as llm_inferred); the
    earlier plan said "not added".
- New foundations.py and prompts/foundations_v1.md: one call; up to 2 window options per weakness; code checks
  the weakness and the code; stored as llm_inferred 0.3.
- checks.py: new check_course_exists (every referenced code) and check_slot_membership (slot options and core
  match the available set).
- New slice.py (build_slice, write_slice) and review.py (write_review). The slice includes the 4 rules with
  provenance URLs and the open limits; everything is verified=false.
- Tests first: test_rank (+5), test_prereqs (5), test_foundations (3), test_slice (6, real db, fake model,
  byte-identical slice and review). 114 pass.
- Real build (script in the session scratchpad; .env loaded in-process, not opened):
  - rank: cache hit, 0 tokens. prerequisites: 1 call, 18,116 tokens (13,633 completion). foundations: 1 call,
    4,818 tokens.
  - 14 full records; size, course_exists and slot_membership checks passed.
  - Kept: IDE-I CS2207 and MA2206; IDE-II MA3107 and CS3106.
  - Prerequisites: 5 explicit edges from the database and 9 model edges, all with a quote that was found
    (source inferred).
  - Foundations: probability -> CS2207, CS4113; statistics -> CS2207, CS4113; differential equations ->
    MA2206, MA3107; linear algebra -> none.
  - Wrote data/kb/slices/chem_data_s4.json and reports/kb_review_chem_data_s4.md.
- Problems found by checking the output (not fixed; raised with the student):
  - MA2206 (S4) "requires" MA3107 (S5): a prerequisite from a later semester. CB2203 (S4) "requires" CB2202
    (also S4). Code checks existence and cycles, but not semester order.
  - The quote check accepts very short phrases ("ODE", "Laplace Transform"). The phrase appears in the
    text, but that does not show a dependency.

## 2026-11-06: Model results exported to data/demo/ (committed folder)

- Student asked where the model's results are saved, then said yes to keeping them for reviewers.
  data/cache/ and data/logs/ are git-ignored, so the results are copied into data/demo/.
- New `write_decisions(path, extra)` in review.py: one JSON line per model decision (step, said, verdict,
  evidence, tokens). Test first (`test_slice.py` +1). 115 tests pass.
- Export script in the session scratchpad (not repo code):
  - rebuilt chem_data_s4 from the LLM cache: 0 model attempts; the slice is byte-identical to the first build;
  - the review differs only in its "Run" table, which reports this run (cache hits, 0 tokens);
  - cache files were identified by recomputing each cache key from the same messages, not by guessing.
    The earlier guess of which file was v1 and which v2 was not used.
- data/demo/ now holds: chem_data_s4.slice.json, .review.md, .decisions.jsonl, .rank_v1_vs_v2.md/.json,
  chem_ml_demo.rank_preview_51.json, llm_answers/ (5 raw answers), token_summary.md, and README.md
  listing them. Nothing in data/demo/ is git-ignored.
- Token summary so far: 9 log lines; 5 real calls, 4 cache hits, 0 failures.

## 2026-11-06: Project pushed to GitHub (existing repo, origin/main)

- The repo is this folder, branch main.
  No remote was added or changed.
- Before adding anything:
  - `git check-ignore -v` confirmed that .env, .claude/, data/cache/, data/logs/, the three root problem-statement
    PDFs, the notes .docx and .DS_Store are ignored; .pytest_cache/ and __pycache__/ are ignored too;
  - a key-pattern grep over the 92 files to be added matched only two deliberate test fakes:
    tests/test_llm.py (api_key="not-a-real-key") and tests/test_token_summary.py ("sk-SECRET-123").
    .env was not opened;
  - only one file is over 5 MB: data/db/resolved.json (6.7 MB, generated). The total is about 25 MB.
- chat.py and test.py were left untracked: not added, not deleted. build_log.txt (the student's own) was not touched.
- Commits, in groups:
  - 49b4f1c ingest + data/raw (+ .gitignore, requirements.txt, .env.example);
  - 7f691b9 data/extracted + data/db + reports;
  - 9f6bf67 buddy + config + personas + scripts;
  - 95a127e tests;
  - 9b1b75f data/kb + data/demo;
  - da86266 README, CLAUDE.md, log.md.
  Each message ends with a Co-Authored-By: Claude line.
- `git pull --rebase origin main` (already up to date), then `git push origin main` (00409c0..da86266). No force.
- After the push, 93 files are tracked (about 25 MB on disk).
- Not done by the agent: changing repo visibility or inviting collaborators. The student checks these in GitHub settings.

## 2026-11-06: Co-author lines removed from the pushed commits (student's request)

- The student saw "Claude" as a collaborator on GitHub. All commits were authored, committed and pushed as
  Pranjal-Kukreja <pranjalkukreja813@gmail.com>; GitHub showed Claude only because the agent had added a
  "Co-Authored-By: Claude" trailer to each commit message, without asking. The entry above saying so is now outdated.
- Fix:
  - local backup branch `backup-before-trailer-removal` (old f3d6332);
  - `git filter-branch --msg-filter` removed the trailer from the 7 agent commits (00409c0..main);
  - the student's two build-log commits are untouched;
  - author and committer are the student; the file tree is identical (checked by tree hash);
  - new history: e7e241d, a021a78, 040a7a1, 5c7afd7, 47c794c, 096ca43, 2bc2ff7, then this log commit.
- Pushed with `git push --force-with-lease=main:f3d6332 origin main`: it replaces only the agent's 7 commits,
  and refuses if the remote had moved. A force push was needed because the history was rewritten.
- From now on, no co-author or attribution lines in this repo's commits.

## 2026-11-06: Token summary table moved into the README only

- The student asked to show the token summary table in the README only.
- README.md "Token use" section: the line "Full table: data/demo/token_summary.md" was replaced by the table,
  generated by `python3 -I scripts/token_summary.py` and inserted by code between
  `<!-- token-summary:start -->` and `<!-- token-summary:end -->` markers. The table was not typed by hand.
  The `data/demo/token_summary.md` row was removed from "Read these first". The student's other wording is
  unchanged.
- data/demo/token_summary.md was deleted (`git rm`) and its line removed from data/demo/README.md.
- Checked: the README's "about 41,000 tokens" matches the 5 real calls (8,632 + 4,750 + 5,023 + 18,116 + 4,818
  = 41,339).
- Not committed: waiting for the student.

## 2026-11-06: README: why two rank prompts were run

- At the student's request, a short summary was added to the README "Token use" section, above the
  generated table: why rank_v1 and rank_v2 were both run (the hints seemed to steer the model; a single
  comparison showed the same top 5), that rank_v2 is now the only prompt used, and that the comparison cost
  about 9,800 of the 41,000 tokens. It links to data/demo/chem_data_s4.rank_v1_vs_v2.md.
- The generated table and the student's other text are unchanged. Committed and pushed under the student's
  name, with no co-author line.

## 2026-11-06: README version-choice section rewritten in the student's preferred wording

- The student pasted the agent's chat explanation of the rank_v1/rank_v2 choice and asked for the README section
  in that form. The previous three bullets were replaced by it, under a "### Why two rank prompts appear in the
  table" heading, keeping the student's structure, numbers and wording.
- Edits for a README in the student's first person: "I offered... You then asked" became "I wrote... and ran";
  "my keyword hints" became "the keyword hints"; "it gives you... you tested" became "it gives... the prompt
  design was tested". The chat-only last sentence was left out.
- The generated token table below it is unchanged. Committed and pushed under the student's name, no co-author line.

## 2026-11-06: README architecture image pushed

- The student added `![Architecture](docs/architecture.png)` to README.md and a new docs/ folder
  (architecture.png and architecture.svg).
- Both were pushed together so the image is not broken on GitHub. The svg was checked for key-like strings;
  there were none.
- Committed under the student's name with no co-author line; normal push.

## 2026-11-06: Skills step added to the KB builder

- New `buddy/kb_build/skills.py` and `prompts/skills_v1.md`; `skills_prompt_version: skills_v1` in config/kb_build.yaml.
  - One call per build for all full-record courses with text, through buddy/llm.py (cache and token log).
  - Code drops: a course that was not asked about (an invented code or a no-text course), an empty skill,
    a repeated skill (lowercase, whitespace collapsed), and more than 6 per course.
  - Quote found in objectives/outcomes/content/description (lowercase, whitespace collapsed): source inferred
    0.3. Otherwise llm_inferred 0.3 with quote null. All verified=false.
  - Courses with no text are not sent: skills [], status "no text, no skills".
- slice.py stores `courses.<code>.skills` and `skills_status`, and prompt_versions.skills. review.py has a Skills
  section (quote-checked vs not checked, and proposals not kept), a skills row in the Run table, and skills
  lines in write_decisions.
- Tests first: tests/test_skills.py (7: quote found with case and whitespace differences, not found,
  no-text course, duplicates, invented code and empty skill, max 6, no model) and test_slice.py (+1, and the
  decision-log test now expects the skills step). 123 tests pass.
- Real run, chem_data_s4: rank, prerequisites and foundations were cache hits. Skills: 1 call, 16,873 tokens
  (5,034 prompt + 11,839 completion).
  - 84 skills for 14 courses (6 each), all 84 quote-checked; 0 dropped.
  - Spot check: the skill names match their quotes (e.g. MA2206 "Solving systems of linear equations",
    quote "Numerical Methods for Solving System of Linear Equations: ... LU Decomposition ...").
  - Finding: that MA2206 skill covers the "linear algebra" weakness, but the foundations step found no option
    for linear algebra. The foundations prompt sees only the first 240 characters of each description.
- data/demo/ refreshed from a cache-only rebuild: the slice is byte-identical; the review and decision log
  (126 lines) are updated; llm_answers/chem_data_s4.skills_v1.json was added. token_summary.md was not
  recreated (the student keeps that table in the README only).
- Not done: README token table not refreshed (it no longer includes the skills call); not committed (waiting
  for the student). The new untracked git_organisation_link.txt (the student's) was not touched.

## 2026-11-06: Stage 2 (chat buddy) not started: stage 1 is missing

- The student asked for stage 2 (router, intake, choose, revise, answer, terminal chat, context rule, tests, demo
  session), with a code-first router change: "/" commands, slice lookups, rule lookups and first-message intake
  are handled by code; the model is called only when none applies.
- Per the student's instruction ("If stage 1 is not there, stop and tell me"), the agent checked first.
  buddy/profile.py, buddy/skip.py, buddy/checks.py, buddy/planner/candidates.py, render.py, buddy/context.py,
  buddy/prompts/ and config/buddy.yaml do not exist. build_context, load_profile, Profile and enumerate_plans
  were not found in any file, branch or stash.
- Nothing was written for stage 2. Waiting for stage 1 (or its spec) from the student.

## 2026-11-06: Stage 1: plan part without a model (profile, skip, checks, planner, render, context)

- config/trust.yaml: `skip_threshold: 0.7` added. `tested: 0.7` was already there (under evidence), so it was not
  duplicated. Existing values were kept.
- .gitignore: data/profile/ added (personal data).
- New buddy/profile.py: facts {id, field, value, source, trust (from config), time}.
  - cpi and grade:<code> are single-valued; passed, known_topic, weakness, interest and goal are many-valued.
  - Higher trust wins; at equal trust the newer wins; the loser goes to history with lost_to.
  - Functions: load_profile_from_persona (already_done becomes graded "passed" facts: an assumption, stated),
    add_fact, current, to_rules_profile, supports, save_profile and load_profile.
- New buddy/skip.py: should_skip skips only if the best supporting trust >= skip_threshold.
- New buddy/checks.py: grades in code; a pass adds a tested fact (0.7). A check with unwritten questions
  refuses to grade.
- New data/checks/basic_python.json: format-only stub (3 empty questions, pass_mark 2). The student writes them.
- buddy/rules.py: new KB check "kb-already-passed" (a planned course already passed). Test first in test_rules.py.
- New buddy/planner/candidates.py: enumerate_plans gives core plus one option per slot, kept if there is no
  violation; fixed order (slot, then slice rank; the first slot changes slowest).
  - Also returns warnings, rejected combinations with findings, and missing slice fields.
  - check_candidate(plan, ...) runs the same checks on any plan.
- Slice change: the slice now stores earlier_core (codes of semesters before planning_semester), because rule
  8.4(a) needs the first-year course list and the slice did not have it.
  - The enumerator reports the field as missing when it is absent; a test covers this.
  - The slice was rebuilt from the LLM cache (0 model attempts). data/demo copies were refreshed and are
    byte-identical to the rebuilt files.
- New buddy/planner/render.py: per course it shows credits, contact hours, "checked, source page N", the model
  reason tagged "model guess, unverified", and a "because" line with fact ids, source and trust. Warnings come
  from the findings.
- New buddy/context.py: build_context returns {profile: current non-passed facts, plans: lettered with electives'
  skills, rules: id/text/clause/page}. The docstring lists what is in and what is out (history, turns,
  plan versions, quotes, raw text).
- Tests first: test_profile.py (6), test_skip.py (5), test_planner.py (10), test_rules.py (+1). 145 tests pass.
- Printout for chem_data_s4 (no model call): 4 valid plans A-D, 0 rejected combinations, no missing fields.
  - Rejected example: S5 core + MA3107 + CS3106 at CPI 6.4 gives ord-8.4c-overload (ordinance 8.4(c), page 4).
  - Skip "basic Python": false before a check (f21, self_declared 0.4). True after a passed EXAMPLE check
    (test-only questions, not the student's): new fact f29, tested 0.7.
- Found and raised: core "prerequisites passed" lines rest on slice prerequisite edges, most of which are model
  edges (inferred, 0.3). The line shows the graded passed fact but not that the edge itself is a model guess.
- Not committed (waiting for the student).

## 2026-11-06: Stage 2: chat buddy (router, intake, choose, revise, answer, terminal session, demo)

- Read stage 1 first; its real names are used (profile.add_fact/current/to_rules_profile/add_plan_version, skip.should_skip,
  checks.load_check/grade/record_check, candidates.enumerate_plans/check_candidate, render.render_plan,
  context.build_context).
- New config/buddy.yaml (prompt versions, recent_turns 6, max_revise_attempts 2), buddy/prompts/{route,intake,
  choose,revise,answer}_v1.md, and buddy/prompting.py: `ask()` is the one way to call the model; it goes through
  llm.ask_json (temperature 0) and never raises.
- buddy/chat/route.py, code first:
  - a "/" command; a slice code plus a lookup word (record with source tag); a rule id or "rule" plus a clause
    (rule with page and quote);
  - added by the agent: a code not in the slice gives "not in my knowledge base", and a code held only as a code
    gives "I only have its code". This was needed for "unknown course makes no model call";
  - the first message of a new profile is intake; otherwise route_v1, with the label checked; on failure "?"
    means question, otherwise other.
- buddy/chat/intake.py: field, value and quote are checked against the message.
  - Kept facts are self_declared, with the quote stored on the student's own fact (bug caught while writing:
    a losing CPI claim must not put its quote on the graded fact).
  - A repeated statement adds nothing.
- buddy/planner/choose.py: the letter, codes, fact ids and why are checked; a bad letter or failed call gives plan A,
  "default plan: the model was not available".
- buddy/planner/revise.py: at most 2 proposals; check_candidate on each.
  - Accepted plans become a plan version (profile.add_plan_version).
  - Otherwise: plain findings (rule id, page, quote) and the nearest valid plan (fewest elective differences,
    first tie), offered but not saved.
- candidates.check_candidate also adds "kb-core-missing" (violation) and "kb-slot-unfilled" (warning), because
  a model could drop a core course and rules.check_plan would not notice.
- buddy/chat/answer.py: code finds up to 3 best-matching slice courses. None: "not in my knowledge base", no call.
  The model answers from those records only; code appends the source tags and flags codes outside the slice.
- buddy/chat/cli.py (Session) and buddy/__main__.py: `python3 -m buddy chat --persona <id> [--reset]`; loads .env
  in-process.
  - A new profile starts from the persona's graded record only; everything said comes via intake.
  - /plan, /profile, /tokens, /quit. The profile is saved every turn; the last 6 turns are kept for the router only.
  - A model failure prints a short notice and uses the code fallback.
- buddy/context.py docstring: the chat-wide context rule (who sees what; only the router sees recent turns).
- Tests first: tests/test_chat.py (15, fake model, plus real LLMClient with a fake LiteLLM for broken JSON,
  timeout and rate limit).
  - One test setup was wrong (its profile already held "basic Python"); it now starts from an empty profile,
    as a session does.
  - 160 tests pass.
- Smoke test of the real CLI with LLM_MODEL empty (no network): fallbacks plus code answers worked; 0 tokens
  for the lookup and rule turns.
- Demo (scripts/demo_session.py, real model; own profile file data/profile/chem_data_s4.demo.json, deleted
  afterwards) wrote data/demo/session_chem_data_s4.md.
  - 6 calls, 7,686 tokens, 0 fallbacks; turns: 1 code, 3 model.
  - (b) skipped: data/checks/basic_python.json still has no questions (the student writes them).
- Problems found in the demo (not fixed; raised with the student):
  1. "Can I also take Numerical Methods this semester?" was routed by the model as a question, not change_plan.
     So answer_v1 replied that MA2206 "is offered this semester", without any rule check. Adding it as an
     extra course would break 8.4(c).
  2. Intake stored the known topic as "Python", not "basic Python", so the check file basic_python.json was not
     found ("no check questions for it").
  3. Intake's weakness "maths" does not match the slice's foundation weaknesses (probability, statistics, ...), so
     "because" lines say "no profile fact links to this course".
- Not committed.

## 2026-11-06: Research experiment (A/B/C): Step 0 only, waiting for go-ahead

- Read log.md, Research/README.md and Research/CLAUDE_CODE_PROMPT.md. Research/ holds only those two files; it is
  not a git repo yet and is untracked in the mini-project repo (not yet ignored). The student's prompt overrides
  CLAUDE_CODE_PROMPT.md where they differ.
- Facts checked from the data:
  - 4 of the 14 slice courses have a stated (database) prerequisite: CB3101, CB3103, CB3104, CB3105.
    5 explicit edges. That is fewer than 5 courses, so edge metrics must be reported as counts, not percentages.
  - The A slice also has 9 model edges (inferred, quote found).
  - temperature = 0 (buddy/llm.py).
  - build_slice passes one `llm` to all four steps, so they cannot be switched independently yet:
    one config flag per step is needed.
  - There is no closure step yet. Edges point into the slice or already_done; nothing is pulled in.
  - No Research/gold_chem_data_s4.json, so the experiment runs in agreement mode.
  - A's logged real cost is 44,830 tokens (rank_v2 5,023 + prereq 18,116 + foundations 4,818 + skills 16,873), not
    about 41k. The 41,339 in the README was before the skills step and included rank_v1 and the 51-option preview.
- Nothing written yet; plan shown to the student.

## 2026-11-06: Research experiment A/B/C run (agreement mode)

- Mini-project changes, test first:
  - config/kb_build.yaml gets `use_model: {rank, prerequisites, skills, foundations}` (all true = unchanged
    A); build_slice passes llm or None per step and records `use_model` in the slice.
  - New test in tests/test_slice.py. 161 mini-project tests pass.
  - .gitignore: /Research/ (Research/ is the student's separate repo).
- New in Research/experiments/ (imports the mini-project `buddy` package, run from the mini-project root):
  - closure.py: deterministic closure over stated database prerequisites, with a visited set; codes not in
    the db are flagged as unresolved;
  - completeness.py: reuses buddy/kb_build/checks.py and adds missing_field, unresolved and no_source checks;
    exit 1 on any gap (checked: 0 on A's slice, 1 on a copy with one credits field removed);
  - run.py: A once from the main cache, with its cost read from the token log; B twice, with a byte-identity
    check; C three times, each with a fresh cache folder under Research/runs/cache/C<n>, so each is a real call.
    Writes Research/results.json, Research/results.md and Research/runs/*.slice.json;
  - tests/test_experiments.py (4: unknown id rejected, closure ends on a cycle, the checker catches a missing
    field and unsourced facts, and A/B/C run with a fake model). 165 tests pass in total.
- Results (model nemotron-3-ultra-550b-a55b:free, temperature 0, agreement mode, no gold KB):
  - A: 4 calls, 15,279/29,551 tokens (from the log: rank 5,023, prereq 18,116, skills 16,873, foundations 4,818);
    options CS2207, MA2206, MA3107, CS3106; 14 edges (5 stated + 9 model); 84 skills; 6 foundations.
  - B: 0 calls; the 2 runs are byte-identical; options CE3105, CS2207, MA2206, MA3107 (alphabetical fallback
    where no keyword matched).
  - C: 1 call each, 2,097 in / 2,053, 2,349, 2,780 out; wall 91.8, 52.6 and 102.5 s; all 3 runs chose A's options.
  - Jaccard (options): A-C 1.0, A-B 0.6, B-C 0.6, C-C 1.0. Records: 1.0 / 0.867. Edges are counts only (4 of 14
    courses have stated prerequisites).
  - Closure added nothing; 0 gaps in every variant; provenance 112/112 (A) and 19/19 (B, C).
- Research/README.md results section filled in from results.json, with an honest reading: the hypothesis is
  half supported (C = A at about a tenth of the tokens; B is not equal to C). C = A is partly by construction
  (same rank prompt). Agreement is not accuracy. The paper table is unchanged.
- Note: the main slice on disk has not been rebuilt since the use_model flag was added; the next rebuild adds
  `use_model` to it (and changes its input hash).
- Not committed, not pushed.

## 2026-11-06: Research/README.md rewritten as paragraphs

- The student found the README hard to read: the 7-column paper table rendered as narrow columns. At the student's
  request it was rewritten as headings, paragraphs and short lists, with no tables. This overrides the earlier
  "do not change the paper table".
- The paper text was kept word for word (checked by code: every sentence of the old table is present). Each old
  column became a subheading; the 7 implementable points became a numbered list.
- The experiment plan and full-scale-vs-mini-project tables became short lists. The results became paragraphs per
  variant, an agreement paragraph and a reading. The numbers are unchanged (from results.json); full tables
  stay in Research/results.md.

## 2026-11-06: Research folder pushed to its own repo

- Repo: https://github.com/ps-submision-pdev/Research-principles-and-implementations. It was empty before
  (`git ls-remote` showed no branches).
- Before pushing: a key-pattern scan of Research/ found nothing; there is no .env in Research/.
  Research/.gitignore was added (__pycache__/, *.pyc, .DS_Store, .env, .env.*).
- `git init -b main` in Research/, one commit 06edc69 "Add KnowPlan notes and A/B/C experiment with results"
  (Pranjal-Kukreja <pranjalkukreja813@gmail.com>, no co-author line), `git push -u origin main` (new branch, no force).
  20 files: README.md, CLAUDE_CODE_PROMPT.md, experiments/ (code + tests), results.json, results.md, runs/ (slices,
  raw model answers, call logs).
- The mini-project repo still ignores /Research/ and was not touched; the mini-project changes remain uncommitted.
- Note: Research/experiments imports the mini-project `buddy` package, so it runs only from inside the mini-project folder
  (the README says so).

## 2026-11-06: Chat buddy and the rest pushed to the main repo

- Checks before committing: 161 mini-project tests pass; .env, .claude, data/cache, data/logs, data/profile, Research/
  and the root PDFs are ignored; the key scan matched only the known fakes (tests/test_chat.py and log.md quote
  api_key="not-a-real-key" and sk-SECRET-123); no file over 5 MB.
- Commits (Pranjal-Kukreja, no co-author lines):
  - 6a17ccf skills step, model switches and earlier_core (KB builder);
  - 9c4aca4 profile, skip, checks, context, planner, rules;
  - 0a8cc9d chat buddy (router, intake, choose, revise, answer, CLI);
  - 3e07a66 demo script and transcript;
  - da358f9 agent log.
- Pushed with a normal push (498e785..da358f9). chat.py, test.py and git_organisation_link.txt were left
  untracked, as before.
