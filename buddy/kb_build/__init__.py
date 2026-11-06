"""KB builder: build one student's knowledge-base slice from the local database.

PRINCIPLE
    The model does the judgment; code verifies whatever can be verified (code exists, quote
    appears, no cycle, budget holds). Anything the model says that code cannot verify is stored
    with source="llm_inferred", low trust, and verified=false, and is shown as such. Rule
    violations, credit/contact-hour maths and plan validity are code only.

Run:  python3 -m buddy.kb_build --persona personas/<id>.json [--no-llm]
Reads only local files (data/db/, data/kb/rules.json, config/, personas/). The model is called
only through buddy/llm.py. Writes data/kb/slices/<persona_id>.auto.json (never a hand-made slice).
Nothing here may be hard-wired to one department or one goal: those come from the persona.

Slice format (decided before Step 3): courses are stored by slot, not only as a flat list:
    "core":  {semester: [codes]}                              fixed, from the persona's own semester tables
    "slots": [{"slot": "IDE-II", "semester": 5, "options": [codes]}, ...]
plus the course records themselves, rules, edges, skills, foundations and likely_known (later steps).
buddy/rules.py checks a plan against core and slots ("kb-slot-membership").

Modules
    persona.py    load and validate personas/<id>.json                                    (code)
    available.py  per slot in the planning window, what the persona may take; core fixed  (code)
    eligibility.py  remove already_done; one list of everything removed before the model  (code)
    shortlist.py  keyword overlap over the available options only                          (code)
    horizon.py    full records + ranking only for kb_horizon_semesters; later slots as codes (code)
    rank.py       order slot options; code checks ids, text_available, lab claims        (model + code)
    prereqs.py    database prerequisites; model edges among slice/already_done codes      (model + code)
    skills.py     up to 6 skills per full-record course, each quote-checked              (model + code)
    foundations.py  per weakness, up to 2 window options                                  (model + code)
    checks.py     KB checks: size 8-15 (warn), course exists, slot membership             (code)
    slice.py      run the steps and write data/kb/slices/<persona_id>.json                 (code)
    review.py     reports/kb_review_<persona_id>.md                                        (code)
Order: persona -> available -> eligibility -> horizon -> shortlist -> rank -> prerequisites -> skills
-> foundations -> rules -> checks -> slice + review
"""
