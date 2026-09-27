import json
import os
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate
from openai import OpenAI


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CANDIDATES = DATA / "candidates"
OUTPUTS = ROOT / "outputs"
OUTPUTS.mkdir(exist_ok=True)

MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")


CV_SCHEMA = {
    "type": "object",
    "properties": {
        "candidate_id": {"type": "string"},
        "full_name": {"type": ["string", "null"]},
        "degree": {"type": ["string", "null"]},
        "graduation_year": {"type": ["integer", "null"]},
        "gpa_4_scale": {"type": ["number", "null"]},
        "gpa_original_value": {"type": ["number", "null"]},
        "gpa_original_scale": {"type": ["string", "null"]},
        "languages": {
            "type": "array",
            "items": {"type": "string"}
        },
        "published_peer_reviewed_outputs": {"type": "integer", "minimum": 0},
        "unpublished_outputs": {
            "type": "array",
            "items": {"type": "string"}
        },
        "relevant_experience_months": {"type": ["integer", "null"], "minimum": 0},
        "uncountable_experience": {
            "type": "array",
            "items": {"type": "string"}
        },
        "evidence": {
            "type": "object",
            "properties": {
                "candidate_id": {"type": ["string", "null"]},
                "full_name": {"type": ["string", "null"]},
                "degree": {"type": ["string", "null"]},
                "graduation_year": {"type": ["string", "null"]},
                "gpa": {"type": ["string", "null"]},
                "languages": {"type": ["string", "null"]},
                "publications": {"type": ["string", "null"]},
                "experience": {"type": ["string", "null"]}
            },
            "required": [
                "candidate_id",
                "full_name",
                "degree",
                "graduation_year",
                "gpa",
                "languages",
                "publications",
                "experience"
            ],
            "additionalProperties": False
        },
        "ambiguities": {
            "type": "array",
            "items": {"type": "string"}
        },
        "traps_hit": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "no_gpa_stated",
                    "gpa_on_another_scale",
                    "unpublished_paper",
                    "contradiction"
                ]
            }
        }
    },
    "required": [
        "candidate_id",
        "full_name",
        "degree",
        "graduation_year",
        "gpa_4_scale",
        "gpa_original_value",
        "gpa_original_scale",
        "languages",
        "published_peer_reviewed_outputs",
        "unpublished_outputs",
        "relevant_experience_months",
        "uncountable_experience",
        "evidence",
        "ambiguities",
        "traps_hit"
    ],
    "additionalProperties": False
}


SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "candidate_id": {"type": "string"},
        "academic": {"type": "number", "minimum": 0, "maximum": 5},
        "research": {"type": "number", "minimum": 0, "maximum": 5},
        "experience": {"type": "number", "minimum": 0, "maximum": 5},
        "score_notes": {
            "type": "object",
            "properties": {
                "academic": {"type": "string"},
                "research": {"type": "string"},
                "experience": {"type": "string"}
            },
            "required": ["academic", "research", "experience"],
            "additionalProperties": False
        }
    },
    "required": ["candidate_id", "academic", "research", "experience", "score_notes"],
    "additionalProperties": False
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_json(text):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


def print_markdown_table(headers, rows):
    print("| " + " | ".join(headers) + " |")
    print("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        clean = [str(x).replace("\n", " ") for x in row]
        print("| " + " | ".join(clean) + " |")


def null_fields(cv):
    fields = []
    for key in [
        "full_name",
        "degree",
        "graduation_year",
        "gpa_4_scale",
        "gpa_original_value",
        "gpa_original_scale",
        "relevant_experience_months"
    ]:
        if cv.get(key) is None:
            fields.append(key)
    return fields


def extract_cv(client, candidate_id, story_text):
    prompt = f"""
You extract a structured CV record from an unstructured scholarship application story.

Candidate id to use exactly: {candidate_id}

Return only valid JSON matching this schema:
{json.dumps(CV_SCHEMA, ensure_ascii=False, indent=2)}

Extraction rules that must be followed:
- A fact the story does not state is null. Never estimate. No GPA means no GPA.
- A GPA on another scale is converted to a 4.0 scale, and the original scale is recorded beside it.
- Use simple linear conversion for GPA: converted = original_value / original_scale * 4.0.
- A paper is published only when the story says published or accepted.
- Submitted, under review, in preparation, planned and in press are not published: record them separately and do not count them.
- Contradictions are not resolved and not averaged: the contradicted field is null, and the contradiction is recorded in ambiguities.
- Count experience months, not jobs. Overlapping periods count once.
- A period with no dates or no stated duration is not countable; record it in uncountable_experience.
- Provide a short evidence quote for every field you fill. If the field is null, evidence can be null.
- traps_hit must list any of these traps present in the story: no_gpa_stated, gpa_on_another_scale, unpublished_paper, contradiction.

Story:
{story_text}
""".strip()

    response = client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "You are a careful information extraction system. Return JSON only."},
            {"role": "user", "content": prompt}
        ]
    )

    raw = response.choices[0].message.content
    obj = parse_json(raw)
    validate(instance=obj, schema=CV_SCHEMA)
    return obj, raw


def score_candidate(client, rubric, cv):
    prompt = f"""
You score one scholarship candidate using the rubric.

Rubric and counting rules:
{json.dumps(rubric, ensure_ascii=False, indent=2)}

Candidate structured CV:
{json.dumps(cv, ensure_ascii=False, indent=2)}

Return only valid JSON matching this schema:
{json.dumps(SCORE_SCHEMA, ensure_ascii=False, indent=2)}

Rules:
- Return a 0-5 score for each criterion: academic, research, experience.
- Do not compute the weighted total and do not name a winner.
- Use only the structured CV fields.
- If gpa_4_scale is null because the GPA is missing or contradicted, academic must be 0 because there is no reliable grade number.
- For research, count only published_peer_reviewed_outputs.
- For experience, score only relevant_experience_months. Do not count uncountable experience.
""".strip()

    response = client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "You are a strict rubric scoring system. Return JSON only."},
            {"role": "user", "content": prompt}
        ]
    )

    raw = response.choices[0].message.content
    obj = parse_json(raw)
    validate(instance=obj, schema=SCORE_SCHEMA)
    return obj, raw


def weighted_total(score, rubric):
    weights = {c["id"]: c["weight"] for c in rubric["criteria"]}
    total = (
        weights["academic"] * score["academic"]
        + weights["research"] * score["research"]
        + weights["experience"] * score["experience"]
    )
    return round(total, 2)


def ask_prose_winner(client, rubric, cvs):
    prompt = f"""
The scholarship committee has one funded place.

Rubric:
{json.dumps(rubric, ensure_ascii=False, indent=2)}

Structured CV records:
{json.dumps(cvs, ensure_ascii=False, indent=2)}

In prose, say which candidate should win and briefly explain why.
This is a separate prose answer. Do not compute the official code ranking.
""".strip()

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are advising a scholarship committee in prose."},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content


def main():
    load_dotenv()
    client = OpenAI()
    rubric = load_json(DATA / "candidate_rubric.json")

    stories = sorted(CANDIDATES.glob("story-*.md"))

    cvs = []
    cv_raw = {}
    extraction_rows = []

    for path in stories:
        candidate_id = path.stem
        story_text = path.read_text(encoding="utf-8")
        print(f"Extracting {candidate_id}...")

        parsed = False
        valid = False
        cv = None
        traps = []
        nulls = []

        try:
            cv, raw = extract_cv(client, candidate_id, story_text)
            parsed = True
            valid = True
            cvs.append(cv)
            cv_raw[candidate_id] = raw
            traps = cv.get("traps_hit", [])
            nulls = null_fields(cv)
        except Exception as e:
            raw = str(e)
            cv_raw[candidate_id] = raw

        extraction_rows.append([
            candidate_id,
            "yes" if parsed else "no",
            "yes" if valid else "no",
            ", ".join(nulls) if nulls else "none",
            ", ".join(traps) if traps else "none"
        ])

    scores = []
    score_raw = {}
    score_rows = []

    for cv in cvs:
        candidate_id = cv["candidate_id"]
        print(f"Scoring {candidate_id}...")

        score, raw = score_candidate(client, rubric, cv)
        score_raw[candidate_id] = raw
        total = weighted_total(score, rubric)
        score["weighted_total"] = total
        scores.append(score)

        score_rows.append([
            candidate_id,
            score["academic"],
            score["research"],
            score["experience"],
            total
        ])

    ranked = sorted(scores, key=lambda x: x["weighted_total"], reverse=True)
    winner = ranked[0]["candidate_id"] if ranked else None

    top_gap = None
    if len(ranked) >= 2:
        top_gap = round(ranked[0]["weighted_total"] - ranked[1]["weighted_total"], 2)

    print("Asking prose winner...")
    prose_answer = ask_prose_winner(client, rubric, cvs)

    output = {
        "model": MODEL,
        "extractions": cvs,
        "extraction_raw": cv_raw,
        "scores": scores,
        "score_raw": score_raw,
        "winner_by_code": winner,
        "ranked_by_code": ranked,
        "top_gap": top_gap,
        "prose_answer": prose_answer
    }

    with open(OUTPUTS / "hard_results.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("\nMODEL")
    print(MODEL)

    print("\nPART 1 — EXTRACTION")
    print_markdown_table(
        ["Story", "Parsed?", "Valid?", "Fields that came back null", "Traps hit"],
        extraction_rows
    )

    print("\nEXTRACTION FOR STORY-06")
    for cv in cvs:
        if cv["candidate_id"] == "story-06":
            print(json.dumps(cv, ensure_ascii=False, indent=2))
            break

    print("\nPART 2 — SCORES AND WINNER")
    print_markdown_table(
        ["Candidate", "academic (0-5)", "research (0-5)", "experience (0-5)", "weighted total (code)"],
        score_rows
    )

    print("\nWINNER, COMPUTED BY CODE")
    print(winner)

    print("\nRANKED BY CODE")
    for i, item in enumerate(ranked, start=1):
        print(f'{i}. {item["candidate_id"]}: {item["weighted_total"]}')

    print("\nTOP TWO GAP")
    print(top_gap)

    print("\nMODEL PROSE ANSWER")
    print(prose_answer)


if __name__ == "__main__":
    main()
