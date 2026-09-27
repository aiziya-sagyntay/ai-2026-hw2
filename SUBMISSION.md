# HW2 submission

**Name:** Aiziya Sagyntay  
**Student ID:** S23068400  
**Group:** 9  
**Repository:** https://github.com/aiziya-sagyntay/ai-2026-hw2

## AI tool disclosure

> I used ChatGPT to help plan the Colab workflow, write and debug the three Python files, improve prompts, and draft the written explanations in this submission. The program outputs themselves were produced by my code using `gpt-5.6-luna`.

---

## Sublab Easy — one task, four roles

### Decisions per role

| Enquiry | policy_officer | front_desk | auditor | bilingual_clerk |
|---|---|---|---|---|
| E-01 | granted (OK) | granted (OK) | more_info (DIFF) | granted (OK) |
| E-02 | more_info (OK) | more_info (OK) | more_info (OK) | more_info (OK) |
| E-03 | refused (OK) | more_info (DIFF) | refused (OK) | refused (OK) |
| E-04 | refused (OK) | more_info (DIFF) | refused (OK) | refused (OK) |
| E-05 | granted (OK) | granted (OK) | more_info (DIFF) | granted (OK) |
| E-06 | granted (OK) | granted (OK) | more_info (DIFF) | granted (OK) |
| E-07 | granted (OK) | granted (OK) | more_info (DIFF) | granted (OK) |
| E-08 | not_found (OK) | not_found (OK) | not_found (OK) | not_found (OK) |
| E-09 | refused (OK) | more_info (DIFF) | refused (OK) | refused (OK) |
| E-10 | more_info (OK) | more_info (OK) | more_info (OK) | more_info (OK) |
| **agrees with `expected`** | 10/10 | 7/10 | 6/10 | 10/10 |
| **parsed** | 10/10 | 10/10 | 10/10 | 10/10 |
| **schema-valid** | 10/10 | 10/10 | 10/10 | 10/10 |

### Which field moved, on which enquiry, under which role

| Field | Enquiries that moved | Role(s) that moved it |
|---|---|---|
| `found` | none | none |
| `decision` | E-01: auditor; E-03: front_desk; E-04: front_desk; E-05: auditor; E-06: auditor; E-07: auditor; E-09: front_desk | auditor, front_desk |
| `amount` | none | none |
| `missing_documents` | none | none |

### Raw replies

Full reply for **one enquiry where a role changed the decision** away from the policy officer's:

```json
{"applicant_id":"A-201","found":true,"decision":"more_info","amount":250000,"missing_documents":[],"reason":"Under the Need-based study grant 2026 rule, the applicant meets the GPA, income-band, and required-document criteria. A second reader is needed before granting."}
```

Full reply for **E-07 (the Kazakh enquiry)** from the bilingual clerk, so the `reason` language is visible:

```json
{"applicant_id":"A-201","found":true,"decision":"granted","amount":250000,"missing_documents":[],"reason":"Ресми жазбаға сәйкес, GPA 3.4, табыс санаты 1 және қажетті құжаттардың екеуі де бар. Сізге 250 000 теңге грант беріледі."}
```

### Written answers

**1. Which fields are role-sensitive and which are not?**

> In my run, `decision` is role-sensitive. It moved on E-01, E-03, E-04, E-05, E-06, E-07 and E-09. `found`, `amount`, and `missing_documents` did not move on any enquiry. The bilingual clerk did not move the structured fields; it changed only the language of `reason`.

**2. Which enquiries are most sensitive to the role, and why those?**

> E-03 and E-04 are sensitive because the policy officer refuses them, while the front desk role avoids refusal and returns `more_info`. E-07 is sensitive because it is the Kazakh enquiry: the bilingual clerk keeps the same structured decision but changes the reason language, while the auditor changes a grant into `more_info` because it never grants on first reading. E-10 tests whether the model accepts the applicant's claim that the ID card was uploaded. The record wins, so it remains `more_info`.

**3. Where does discretion belong — the role paragraph, or code that reads `decision` afterwards?**

> Discretion belongs in code when the downstream consequence is important. The role paragraph can make the model behave differently, but the JSON record does not reliably show which role produced it. A downstream program can read `decision`, `amount`, and `missing_documents`, but it cannot safely infer the role or the reason for discretion unless that is also represented as a checked field.

**4. Is a role a boundary?**

> No. In Week 2 terms, the role paragraph is just tokens in the context. It influences continuation, but it is not a security or correctness boundary. If a wrong `decision` were expensive, I would put the grant rule, document checks, schema validation, and final decision checks in code instead of trusting the prompt alone. One issue I observed is that the auditor consistently changed `decision` from `granted` to `more_info` while leaving `amount` as 250000. This is internally inconsistent for a downstream program, and it shows why cross-field checks such as “if `decision` is not `granted`, `amount` should be 0” should be enforced in code rather than only in the role prompt.

---

## Sublab Medium — memory you choose

### Tokens per call

| Call | A — never compressed | B — compressed at the `compress` turn |
|---|---|---|
| 1 | 895 | 895 |
| 2 | 949 | 945 |
| 3 | 1039 | 1028 |
| 4 | 1134 | 1112 |
| 5 | 1185 | 1160 |
| 6 | 1280 | 1244 |
| 7 | 1379 | 1324 |
| 8 | 1463 | 1401 |
| 9 | 1535 | 1474 |
| 10 | 0 | 1121 |
| 11 | 1657 | 1350 |
| 12 | 1737 | 1386 |
| **peak** | 1737 | 1474 |
| **total for the run** | 14253 | 14440 |

### Probes after the conversation

| Probe | Tests | A retrieved? | A answer | B retrieved? | B answer |
|---|---|---|---|---|---|
| Q-1 | identity, stated once in turn 1 | yes | You are **Daniyar Qoshan**, applicant **A-202**. | yes | You are **Daniyar Qoshan**, applicant **A-202**. |
| Q-2 | the missing document, turn 5 | yes | Сіздің A-202 файлыңызда **id card** әлі де жетіспейді. Transcript құжаты тіркелген. | yes | Your **ID card** is still missing from your official file. |
| Q-3 | the band from turn 3 and the amount from turn 4 | yes | Your official income band is **2**, which corresponds to a grant amount of **150,000 KZT**. | yes | Your official income band is **2**, corresponding to a grant amount of **150,000 KZT**. |
| Q-4 | a constraint the applicant stated in turn 6 and never repeated | no | Сіз кеңсеге **бейсенбі күні** келе аласыз. | yes | You can come to the office on **Thursdays**. |
| Q-5 | an open question, turn 7, never answered | yes | You asked whether a **scanned letter from your employer** would count or whether you needed to provide the **original**. | yes | You asked whether a **scanned employer letter** would be accepted or whether you must provide the **original**. The policy does not specify this. |
| **retrieved** |  | 4/5 |  | 5/5 | |

### The state my compression produced

```json
{
  "applicant_id": "A-202",
  "topic": "Study grant eligibility, required documents, grant amount, and submission timing",
  "facts": [
    "The applicant's name is Daniyar Qoshan.",
    "The applicant sent a transcript last week.",
    "The applicant's family certificate states that the income band is 2.",
    "The applicant could not upload the ID card because the scanner at home broke.",
    "The applicant can only come to the office on Thursdays because of lab work during the rest of the week.",
    "The applicant has a question about whether a scanned employer letter is acceptable or whether the original is required.",
    "The applicant stated that their sister Aruzhan applied last year and is on file."
  ],
  "decisions": [
    "The official record lists the applicant's GPA as 2.9, income band as 2, and transcript as meeting the requirements.",
    "The ID card is missing from the official record.",
    "The applicant does not currently qualify because the ID card is missing.",
    "Once the ID card is added to the official record, the applicant would qualify for a grant of 150,000 KZT.",
    "The policy does not list an employer letter as a required document and does not specify whether it may be scanned or must be original.",
    "The policy does not specify how quickly a decision is made after the ID card is submitted.",
    "Aruzhan Nurlan (A-205) is listed in the official record, but the record does not confirm the family relationship or whether she applied last year; her application is assessed separately."
  ],
  "constraints": [
    "The ID card must be submitted and added to the official record before eligibility is met.",
    "The applicant can bring the ID card to the office on Thursday.",
    "The applicant is unavailable to come to the office on other days because of lab work."
  ],
  "open_questions": [
    "Whether a scanned employer letter is acceptable or the original is required.",
    "Whether the decision will be made on the same day the ID card is submitted on Thursday."
  ],
  "language": "Kazakh and English"
}
```

### Written answers

**1. What did compression buy?**

> The peak prompt tokens fell from 1737 without compression to 1474 with compression. In my scripted table, the uncompressed run retrieved 4/5 probes and the compressed run retrieved 5/5. The lost probe in the printed checker was Q-4, the Thursday constraint from turn 6. The answer itself used Kazakh for Thursday, so this also shows that a simple string checker can miss a semantically correct answer.

**2. Why must the state be structured rather than a paragraph?**

> A structured state has named fields such as `applicant_id`, `facts`, `decisions`, `constraints`, and `open_questions`. That means the program can validate it against a schema and decide whether it is safe to replace the full history. A paragraph summary may sound good, but it is harder for code to check, search, or use reliably.

**3. What is missing from your state that you would add?**

> I would add source turn numbers for each fact, for example `source_turn: 6` for the Thursday constraint. To pay for it, I would shorten the long prose items in `decisions`, because they repeat policy explanations that can be reconstructed from the official records and policy.

**4. When is compression the wrong choice?**

> Compression is the wrong choice when the exact wording matters, for example an appeal, complaint, legal statement, or a conversation where a user gives a precise quote that must not be paraphrased. My program would notice only malformed JSON or schema failure. It would not automatically notice a valid state object that silently dropped an important nuance.

---

## Sublab Hard — stories in, CVs out, the best candidate by code

### Part 1 — extraction

| Story | Parsed? | Valid? | Fields that came back `null` | Traps hit |
|---|---|---|---|---|
| story-01 | yes | yes | none | none |
| story-02 | yes | yes | gpa_4_scale, gpa_original_value, gpa_original_scale | no_gpa_stated |
| story-03 | yes | yes | none | gpa_on_another_scale, unpublished_paper |
| story-04 | yes | yes | none | unpublished_paper |
| story-05 | yes | yes | none | unpublished_paper |
| story-06 | yes | yes | graduation_year, gpa_4_scale, gpa_original_value, gpa_original_scale | contradiction |

The four traps, for reference: no GPA stated · a GPA on another scale · a paper that is not published · a story that contradicts itself.

Extraction for **story-06**, the one that contradicts itself:

```json
{
  "candidate_id": "story-06",
  "full_name": "Nurzhan Abilov",
  "degree": "BSc in Statistics",
  "graduation_year": null,
  "gpa_4_scale": null,
  "gpa_original_value": null,
  "gpa_original_scale": null,
  "languages": [
    "Kazakh",
    "Russian",
    "English"
  ],
  "published_peer_reviewed_outputs": 1,
  "unpublished_outputs": [
    "One poster at a local event"
  ],
  "relevant_experience_months": 40,
  "uncountable_experience": [],
  "evidence": {
    "candidate_id": "story-06",
    "full_name": "Nurzhan Abilov",
    "degree": "I graduated in 2024 with a BSc in Statistics.",
    "graduation_year": "I graduated in 2024... I am currently a final-year student graduating in 2026.",
    "gpa": "My GPA was 3.2. Actually... I think it was 3.5.",
    "languages": "Languages: Kazakh, Russian, English.",
    "publications": "One paper published, in a peer-reviewed proceedings, on survey weighting.",
    "experience": "I have been at an insurance analytics team since February 2023, which is about forty months."
  },
  "ambiguities": [
    "Graduation status and year are contradictory: the candidate says they graduated in 2024 and also are a final-year student graduating in 2026.",
    "GPA is contradictory: both 3.2 and 3.5 are stated."
  ],
  "traps_hit": [
    "contradiction"
  ]
}
```

### Part 2 — scores and the winner

| Candidate | academic (0–5) | research (0–5) | experience (0–5) | weighted total (code) |
|---|---|---|---|---|
| story-01 | 5 | 5 | 2 | 4.4 |
| story-02 | 0 | 2.5 | 5 | 1.75 |
| story-03 | 4 | 2.5 | 3 | 3.35 |
| story-04 | 4 | 2.5 | 5 | 3.75 |
| story-05 | 5 | 2.5 | 1.25 | 3.5 |
| story-06 | 0 | 2.5 | 5 | 1.75 |

**Winner, computed by my code:**

story-01

**The model's prose answer, asked separately ("who should win?"):**

> Aziza Bekova should receive the funded place. Her story provides clear evidence of a strong academic record—a 3.8 GPA on a 4.0 scale—and two published peer-reviewed outputs. She also has documented relevant experience, although shorter than that of some other candidates. This combination is stronger and more complete than the alternatives: some candidates have more experience but no stated GPA, while others have higher or comparable academic records but only one published output. Aziza’s record is also free of the publication and contradiction issues present in several applications.

### Part 3 — written answers

**1. Which rule did you have to add, and what broke without it?**

> I had to add a strict contradiction rule: if a story gives conflicting values, the field becomes `null` and the contradiction is recorded. Story-06 forced this rule because it says both that the candidate graduated in 2024 and that he is a final-year student graduating in 2026, and it also gives two GPA values, 3.2 and 3.5. Without the rule, the model could choose one value or average them.

**2. Where did the model guess, and where did your code have to decide?**

> The model had to make judgement calls when turning CV facts into 0–5 scores, for example assigning research scores for candidates with one countable publication. My code had to decide the weighted totals and ranking using the formula from the rubric. The winner was not taken from a sentence; it was computed from the numeric fields.

**3. Did your prose ranking and your computed ranking agree?**

> Yes. The computed ranking chose story-01, and the separate prose answer also chose Aziza Bekova, who is story-01. I trust the computed ranking more because it comes from structured scores and a visible formula. Before trusting the prose answer alone, I would need the same candidate fields, scores, weights, and rule applications shown explicitly.

**4. The rubric has no anchor for a contradicted field.**

> I treated the contradicted GPA in story-06 as unreliable, so `gpa_4_scale` is `null` and the academic score is 0. I think the rule should explicitly say that a contradicted GPA is handled like a missing GPA unless the committee resolves it manually from official documents.

**5. How close were your top two candidates?**

> The top two candidates were not within 0.05. Story-01 scored 4.4 and story-04 scored 3.75, so the gap was 0.65. I would tell the committee that the computed ranking has a clear first place in this run, but I would still check the evidence quotes for the top candidates before making a final human decision.
