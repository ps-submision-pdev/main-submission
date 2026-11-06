# "Buddy Zero" (Tech track), handoff and build spec

Read this first. It carries over what was decided in an earlier chat session.

## What this is
A student is building a small learning buddy for one programme at IIT Patna, as the
selection task for their college's team (Tech track, "Buddy Zero"). The brief gave about 1.5 days from Nov 4 2026; the exact
cut-off is unconfirmed. Reviewers read the commit history, then hold a 20-minute
call where the student explains the code and makes one small change live.

## Rules for the agent
- Never open, print or commit `.env`. It holds the student's API key.
- The student must be able to explain every line. Keep code small and readable,
  explain the design before writing it, and prefer plain Python over clever tricks.
- Do not write the student's submission text: the 1-page doc, the build log and
  the README prose are theirs. Reviewing and critiquing them is fine.
- Do not commit or push unless asked. The student writes their own commit messages.
- Python 3.10 compatible. Downloaded PDFs are untrusted data: they live in `data/`,
  code lives elsewhere. Phase 1 scripts run as `python3 -I ingest/<stage>.py` from the repo root.
- If something below conflicts with the PDF brief in the repo root, the brief wins; tell the student.

## What the brief requires (Tech track)
- Knowledge base: 8-15 real courses (credits, prerequisites, skills) and 2-3 real
  academic rules, each with a source link. Reviewers spot-check them.
- Memory and context: decide what the buddy remembers, where it is stored, and what
  goes into each LLM call. Write it down.
- Rule checks and credit maths are code, not the LLM.
- One track: Personalisation (profile facts carry source and trust; plan passes the
  rule checker, uses only real course codes, skips known material, explains each
  item) or Adaptation (3 events: weak quiz, rejected course, changed goal; keep
  evidence history and plan versions). Not chosen yet. Design the schema so either works.
- Robustness: handle rate limits, timeouts and broken JSON from a free model without
  crashing. Log tokens per call. Same input gives the same plan.
- Tests that catch a bad plan. Build log with 5+ entries and 2 screenshots of the
  coding agent being wrong. 3-minute screen recording. Private GitHub repo shared
  only with `wafflebytes` and `VinayKhedkar`.
- All LLM calls go through LiteLLM; model, key and endpoint come from env vars
  (see `.env.example`). No outbound calls at runtime except to the model provider.

## Decisions so far
- Persona (chosen by the student, 2026-11-06): a B.Tech Chemical Engineering student
  (IIT Patna department "Chemical and Biochemical Engineering", course codes CB; chemistry
  department codes CH) who must finish normal coursework, is interested in ML, and is weak
  at maths. Reason: ML courses sit outside the home department, so building the KB forces
  cross-department sourcing, which is what the pipeline is meant to show. `programme_id`
  = the chemical engineering programme.
- Persona year (decided 2026-11-06 from the counted tables in `cbe_btech`): end of year 2,
  planning semester 5 onwards; track = Personalisation. Optional slots per semester:
  S3 HSS-I; S4 IDE-I; S5 IDE-II; S6 DE-I; S7 DE-II, DE-III, IDE-III, HSS-II; S8 DE-IV..VI.
  The programme has 12 optional slots (3 HSS, 3 IDE, 6 DE); planning from S5 covers 9 of them
  (IDE-II, DE-I, DE-II, DE-III, HSS-II, IDE-III, DE-IV, DE-V, DE-VI), leaves four semesters for the maths-to-ML
  chain, and puts ordinance 8.4(a) (pass all first-year courses before third-year courses)
  right at the S5 registration, e.g. a failed MA1201.
- ML-related options for a chemical student (checked in the extracted docs 2026-11-06):
  core CB3204 AI/ML for Chemical Engineers (S6, 1-0-4-3), CB3105 Chemical Process Modeling
  and Simulation (S5), CB3203 Numerical Methods in Chemical Engineering (S6); DE-II CB4102
  Introduction to Computational Biology and CB4103 Molecular Modeling and Simulation.
  Other departments' courses are reachable only two ways: (1) IDE slots, filled from each
  department's list "available to students other than Dept. of X", e.g. IDE-I CS2207
  Introduction to Data Science or MA2206 Introduction to Numerical Methods, IDE-II MA3107
  PDEs, IDE-III CS4113 Data Analysis and Visualization or ME4103 Nonlinear Dynamics and
  Chaos (CB's own IDEs CB2206/CB3106/CB4108 are "not applicable" to CB students);
  (2) a Minor, e.g. Minor in AI&DS = CS2103, CS2202, CS3103 Machine Learning, CS3202 Deep
  Learning (16 credits). EC3203 and MA4104 are on no IDE list, so they are not open to CB
  students. No document found states who may take a Minor or when (the 2015 ordinance
  predates Minors; the curriculum and `btech_program_nep2020` are silent), so any Minor
  eligibility rule would be unsourced: say so in the doc.
- Alternative considered and rejected: Electrical/ECE (EC3203 AI/ML is already core there,
  and the core is maths-heavy, so there is less cross-department choice to show).
  Complication candidate (unverified): the ordinance reportedly requires passing all
  first-year courses before registering third-year courses; a weak-maths student may be
  blocked from some third-year courses.
- Rule we follow, carried over from the full brief (p.10): the buddy at
  runtime makes no network calls except to the configured model provider. The mini-project
  brief itself does not say this, but we adopt it. So all source PDFs are downloaded
  ahead of time and committed; nothing is fetched while the buddy runs, and the persona
  never decides what to download.
- Universe: the set of PDFs we download is a bounded list chosen once by the developer =
  the persona's home programme + the departments its interests point to + the ordinance
  + the common first-year curriculum, plus the programmes of the brief's sample personas if
  cheap. If a persona falls outside the universe, the buddy says plainly that it does not
  cover that department yet; the 1-page doc states this limit. `sources.yaml` is the
  catalogue of this universe (it lists what may be downloaded; `data/extracted/` is the
  database). Today it has CSE, CSE AI&DS, Maths (M&C), the ordinance, the NEP-2020
  curriculum (195 pages; search snippets show it contains Chemical and Biochemical
  Engineering semester tables, plus Electrical, ECE, Maths and others) and
  `btech_program_nep2020` (Senate document "Course / Curriculum / Syllabus revision in
  compliance of NEP-2020 (B. Tech. / B. S.) with minors", 42 pages, semester tables for
  all branches) and `cbe_btech`, the Chemical and Biochemical Engineering syllabus with full
  course entries. `cbe_btech` is published only as a Word file (`format: docx`); it was
  found via the department page -> academics.iitp.ac.in/revised_syllabus/B.TECH-CSE/sem-1/
  chemicalengineering.html, whose download link lacks the /revised_syllabus prefix. Every
  B.Tech programme has the same kind of page and docx (index: academics.iitp.ac.in/
  revised_syllabus/btech.html); add others the same way if a persona needs them.
- Priority: the graded core is the buddy (profile, planner, rule checker, memory,
  robustness, tests). The data pipeline is not scored on its own. Keep it small: fetch and
  extract exist; write the parser only if the extracted tables are clean; otherwise the
  student picks the 8-15 courses and 2-3 rules by hand from the extracted text, checks
  them against the PDF, and says so in their doc. Build Phase 2 only after the buddy works.
- LLM vs code: the LLM never writes the plan and never decides whether a rule holds.
  It turns free text into structured fields, picks from lists that code built, and
  words explanations. Planner, validator and mastery updates are plain code.
  Evidence: TravelPlanner, Hao et al. 2024 (LLM + solver), LLM-Modulo (Kambhampati
  et al. 2024), TRACE-CS, the DegreeMap part of KNOWPLAN, Huang et al. (no
  self-correction without external feedback).
- The LLM may only choose ids that exist in a catalogue or candidate list built by
  code. It never produces URLs or course codes of its own.
- Data layers: database (all courses, no student, `data/db/`) vs KB (one student's
  verified slice, `data/kb/slices/`). The buddy reads only the KB. RAG is not used in
  the mini-project; the shortlist is keyword scoring, kept behind one function.

## Architecture: build the KB from the student's persona, in two phases
Idea: when a student first uses the buddy they state who they are and what they want
(their persona), and the system builds the knowledge base slice they need. The PDFs
are fetched ahead of time, because fetching is cheap. The slicing happens at
onboarding, from local files only. The pipeline must stay persona-agnostic: nothing
in it may be hard-wired to the maths/ML demo persona.

Two data layers, never mixed up:
- Database (`data/db/`): every course and the ordinance text, parsed from all the
  downloaded PDFs, for every programme, with no student in mind. Built once by code.
  Not hand-verified record by record. The pipeline reads it; the buddy never does.
- KB (`data/kb/slices/<persona_id>.json`): one student's slice of the database, 8-15
  courses plus 2-3 rules, each with a source link, page and a `verified` flag. This is
  the only course data the buddy may use. If a course is not in the KB, the buddy must
  not recommend it. Reviewers spot-check the KB.
The student's profile (facts with source and trust) is a third thing: buddy memory,
stored separately from both.

### Phase 1: build the database (offline, run by the developer; only fetch needs network)
`discover -> fetch -> extract -> parse`, standalone scripts in `ingest/`.
- discover (not written yet): crawl the department pages under
  https://www.iitp.ac.in/departments and write `ingest/sources.yaml`, one entry per
  syllabus PDF (department, programme, level, url). The links are labelled "Click here
  for detailed Syllabus and Curriculum" and the programme name sits in the neighbouring
  list item. Checked on the CSE and Mathematics pages only. Until it exists,
  `sources.yaml` is hand-written.
- fetch (done): PDFs to `data/raw/` with `manifest.json` (url, date, sha256).
- extract (done): `data/extracted/<id>.jsonl`, one line per page with text and tables.
- parse (not written yet; only if the real extracted tables are clean enough; otherwise
  skip it and hand-pick, see Decisions; deterministic, no LLM): turn the extracted pages into course
  records (code, title, L-T-P, credits, semester, category label, learning mode,
  objectives, outcomes) in `data/db/courses.json`, keyed by course code. The ordinance
  pages go to `data/db/rules_text.jsonl` (clause text with page numbers) for the rules
  step. Write `reports/parse_quality.md` (counts per source, records with missing
  fields, credit mismatches). Do not write it until the student has seen real
  extracted pages.
- Commit `sources.yaml`, `data/raw/`, `data/extracted/`, `data/db/`. If `data/raw/`
  grows past about 100 MB, stop and ask the student before committing.

### Phase 2: persona KB builder (stretch goal: build only after the buddy works; no network except the LLM provider)
If time is short, the demo persona's KB is the hand-picked, student-verified seed slice,
and this builder is shown through the CLI with cached outputs. A normal importable package, `buddy/kb_build/`, because the buddy calls it during
onboarding. Also exposed as a CLI: `python3 -m buddy.kb_build --persona personas/<id>.json`.
It reads only `data/db/`, never the PDFs or the web.
1. shortlist (code): keyword scoring of the persona's `goal_keywords` against course
   titles, objectives and outcomes in the database (simple term overlap or BM25, no
   embeddings). Optional narrowing before this: an LLM scope step picks which
   programmes/departments to search, returning `scope_plan.json` (ids from the
   catalogue only, each with a reason, budget at most about 4); fallback = the
   student's own programme + common first year + departments whose names match the
   goal keywords. Keep the shortlist behind one function so a better retriever
   (embeddings, hybrid search) can replace it later without touching the other steps.
2. rank (LLM): ranks shortlist codes by relevance to the goal. It may only return
   codes from the shortlist, with a one-line reason each. Code keeps the top N within
   the course budget and adds the prerequisite closure. Prerequisite edges: use an
   explicit prerequisite field if the PDF has one, otherwise the LLM proposes edges,
   tagged `inferred`.
3. rules (LLM extracts, code verifies): for each rule kind needed (credit limit,
   prerequisite, eligibility), the LLM is given the ordinance clauses from
   `rules_text.jsonl` and must return the clause id plus a verbatim quote. Code checks
   the quote appears in that clause. Fail means no rule record.
4. check (code): see "KB checks". Failing records go to `reports/`, not the KB.
5. write: `data/kb/slices/<persona_id>.json` containing the chosen course records
   (copied from the database, with the rank reasons), the rule records, and the scope
   plan if one was used.

Trust: facts parsed from tables are high trust. LLM-inferred prerequisites and skills
are lower trust and `verified: false`. The buddy must say when it relies on unverified
records. Slices built at onboarding are unverified. The seed slice for the demo persona
is built once with this same code, then the student checks every record against the PDF,
sets `verified: true` and commits it. That committed slice is what reviewers spot-check.

### Contracts (keep these small and stable)
- `personas/<id>.json`: persona_id, programme_id, year, goal_text, goal_keywords,
  constraints (credit cap, courses not to be taken together, hours per week), and an
  evidence list. Each evidence item has field, value, source (graded | tested |
  self_declared), trust. Produced by an LLM intake call at onboarding; hand-written
  for the demo.
- `scope_plan.json` (optional narrowing step): persona_id, created_by (llm | human |
  fallback), model, prompt_version, input_hash, sources [{source_id, reason}],
  goal_keywords, budget.
- Course record (same shape in the database and the KB): code, title, credits, l, t, p, semester, category, learning_mode,
  skills [{name, source, trust}], prerequisites [{code, source: explicit | inferred,
  trust}], provenance {source_id, page, quote}, verified.
- Rule record: id, kind (credit_limit | prerequisite | eligibility | other), text (a
  paraphrase), parameters, provenance {source_id, clause, page, quote}, verified.
  Rules are extracted by an LLM from the ordinance with the quoted text required.
- Trust numbers live in one config file, nowhere else.

### KB checks (code)
Run on the database after parse (flag only) and again on every slice (failing records
are kept out of the KB). Credits equal L + T + P/2 (flag mismatches, never auto-fix);
course codes unique; every prerequisite code exists; no prerequisite cycles; every
provenance quote really appears in the extracted page text; required fields present.
Write `reports/kb_quality.md` with counts and the flagged items.

## Shared pieces
- `buddy/llm.py`: the only place LiteLLM is called. Reads `LLM_MODEL`, `LLM_API_KEY`,
  `LLM_API_BASE` from env. Timeout; retry with backoff on rate limits and server
  errors, capped; JSON parsed against a schema with one repair retry; temperature 0;
  every call logs tokens to a jsonl file; responses cached under `data/cache/llm/`
  keyed by a hash of the full input (model, prompt version, messages).
- Same input must give the same plan: sorted inputs, deterministic planner, cached LLM outputs.

## IIT Patna sources (checked against the downloaded files 2026-11-05/06 unless marked)
- Full list with URLs: `ingest/sources.yaml`. All five original URLs matched the live
  department and academics pages on 2026-11-05. The CSE page now links a newer CSE docx
  ("CSE_B. Tech. Program_Done updated 22-01-2025.docx") than the CSE PDF we hold; only
  matters if a CSE persona is used.
- Prerequisite fields: CSE / AI&DS entries almost never have one (4 mentions in 97 pages),
  so their edges would be inferred. `cbe_btech` has explicit "Pre-requisite" fields on
  about 10 courses (e.g. CB2205, CB2202, CB2102, CB2103): use those as `explicit`.
- Data errors found: CS3202 Deep Learning (CSE and AI&DS PDFs, page 43): Pre-requisite reads
  "offline" and the Learning Outcome is pasted from a pressure-vessel course. `cbe_btech`
  semester III table has Heat Transfer with no code (CB2103 per the Minor table and
  `btech_program_nep2020`). IKS is IK1201 in the syllabi but IK1101 in `btech_program_nep2020`.
- Ordinance page 1 says "Applicable for 2015 Batch onwards" although the file name says
  2019. Verified on page 4: 8.4(a) and 8.4(c) as below; 8.4(b) says 30-50 credits per
  semester, which does not fit today's ~19-23 credit semesters (stale scale).
- Rules freshness (checked 2026-11-06 on the Academic Regulations menu of
  https://academics.iitp.ac.in/): the newest B.Tech rules document listed there is
  "B. Tech. Ordinances and Regulations" whose file name says 2019 onwards. The same menu lists
  "Revised NEP-2020 Compliant Curriculum" and "Syllabus" with no date. No newer B.Tech
  ordinance or amendment was visible, but the notice board was not searched for amendments,
  so "latest" is unconfirmed. The student should open the menu and notice board once and
  tell us if a newer B.Tech rules document exists; if so, add it to `sources.yaml` and use it.
- Rule sources: take credit/structure rules from the NEP-2020 curriculum (newer) and
  eligibility/prerequisite/registration rules from the ordinance. Where the two disagree,
  prefer the curriculum and flag it. Every rule record must carry the document name, the
  `fetched_at` and `sha256` from `data/raw/manifest.json`, the clause, page and a verbatim
  quote, and the KB must show "as of <fetched date>" to the student.
- B.Tech ordinance (2019 onwards, may predate NEP-2020). Clauses to verify: 8.4(a)
  first-year before third-year; 8.4(c) CPI >= 8.0 may take one extra course;
  8.4(b) credit limit looks like an older scale (Chemical degree total is 166 credits: `cbe_btech` p3
  "Total Credits (including B. Tech. first year): 166", and its 8 semester TOTAL rows sum to 166;
  same in `curriculum_nep2020` p4 and `btech_program_nep2020` p3. Other programmes differ, e.g. 168).
- Not rules for this task: the Disciplinary Ordinance, the refund policy notice and the
  academic calendar (skip unless a rule you need lives there).
- The sandbox the earlier chat ran in cannot reach iitp.ac.in; page-fetch tools drop link URLs.

## Status
Done: repo scaffold, `ingest/sources.yaml` (hand-written, 7 sources), `ingest/fetch.py`,
`ingest/extract.py`. Fetch and extract have run on the real site (2026-11-05/06): all 7
sources are in `data/raw/` and `data/extracted/`. Both scripts now handle `.docx` as well
as PDF (`format` field in `sources.yaml` and the manifest; for a docx, "page" = part between
the author's explicit page breaks). Build order step 0 is done except the parse-or-hand-pick
decision. Everything else below is not done. No git repo yet; the student does `git init`
and the GitHub push from their own machine.

## Build order (stop and show the student after each numbered item)
0. The student runs fetch and extract on the real site (after adding the persona's
   branch PDF to `sources.yaml` if it is not there). Inspect `data/extracted/*.jsonl`
   together, then decide: are the tables clean enough to parse (step 2) or do we hand-pick
   (step 3)?
1. `buddy/llm.py` with tests that simulate a rate limit, a timeout and broken JSON.
2. `ingest/parse.py` (ONLY if step 0 says the tables are clean): deterministic parser that
   builds `data/db/` (courses and ordinance text), plus tests on a few real pages kept as
   fixtures, plus `reports/parse_quality.md`. Otherwise skip.
3. Seed KB: the student picks 8-15 courses and 2-3 rules for the demo persona (from the
   database if step 2 ran, otherwise by hand from the extracted text, copying code, title,
   credits, prerequisites, source link, page and a short quote), then verifies each record
   against the PDF and sets `verified: true`. This is the KB reviewers spot-check.
4. Student profile store: evidence log with source and trust, plan versions. Schema
   first, discussed with the student.
5. Validator and planner (backtracking over sorted candidates), bad-plan tests written
   before the planner, explanations generated from the planner's trace.
6. Onboarding intake (LLM turns free text into `personas/<id>.json`), memory and
   context assembly, token logging per call.
7. The chosen track's extras (Personalisation or Adaptation).
8. Phase 2 as a package: shortlist (keywords), LLM rank, rule extraction with verbatim
   quote check, checks, write slice; optional LLM scope with the fallback. Test with the
   four personas from the brief and check with plain code that the budget holds, all
   codes exist in the database and every choice has a reason.
9. discover, last.

If time runs short, ship 0-7 and demonstrate 8 through the CLI with cached outputs. The
graded core is the buddy: profile, planner, validator, memory, robustness, tests.

## Scaling note (for the live call; do NOT build)
Not needed for the mini-project: RAG, a vector database, Postgres, OpenSearch, Airflow.
If asked how this grows: the keyword shortlist is swapped for hybrid retrieval (BM25 plus
embeddings, then a reranker) behind the same function, chunks being whole course records
and ordinance clauses; the database moves from JSON files to Postgres (`pgvector`); crawls
run on a schedule (Airflow or Prefect); OR-Tools CP-SAT can replace the backtracking
planner. Retrieval only proposes candidates; code still decides eligibility, credits and
prerequisites.

## Open questions for the student
Parse or hand-pick (the `cbe_btech` docx tables are clean `cell | cell` rows, which makes
a parser cheaper than for the PDFs); the exact deadline, which may be close (brief gave about a
day and a half from Nov 4). If time is short: steps 0-3, then the buddy; cut 8 and 9 first.
- May a Chemical student take a Minor, and which ones? No document read so far says (see Decisions).
- `btech_program_nep2020` (Senate document) numbers many electives differently from every other
  source: CB DE-I is CB3211-CB3214 there but CB3206-CB3209 in `cbe_btech` and `curriculum_nep2020`;
  Introduction to Data Science CS2209 vs CS2207; Introduction to Numerical Methods MA2251 vs MA2206.
  Which numbering is current? For now it is last in `ingest/source_priority.yaml`.
