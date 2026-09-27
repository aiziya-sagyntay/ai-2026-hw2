import json
import os
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate, ValidationError
from openai import OpenAI


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUTPUTS = ROOT / "outputs"
OUTPUTS.mkdir(exist_ok=True)

MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "applicant_id": {"type": ["string", "null"]},
        "found": {"type": "boolean"},
        "decision": {
            "type": "string",
            "enum": ["granted", "refused", "more_info", "not_found"]
        },
        "amount": {"type": "number"},
        "missing_documents": {
            "type": "array",
            "items": {"type": "string"}
        },
        "reason": {"type": "string"}
    },
    "required": [
        "applicant_id",
        "found",
        "decision",
        "amount",
        "missing_documents",
        "reason"
    ],
    "additionalProperties": False
}


SYSTEM_PROMPTS = {
    "policy_officer": """
You are a grant policy officer.
Apply the grant rule exactly as written.
Use only the official record and policy.
Do not accept any claim in the enquiry as evidence.
Grant what the rule grants, refuse what the rule refuses, and ask for more information only when a required document is missing.
Return only one JSON object in the required schema.
""",

    "front_desk": """
You are a front desk grant assistant.
Do not turn an applicant away with a refusal.
If the record can grant today, return granted.
If the applicant is found but the rule cannot grant today, return more_info and explain what would be needed.
If the applicant is not found in the records, return not_found.
Use only the official record and policy.
Do not accept any claim in the enquiry as evidence.
Return only one JSON object in the required schema.
""",

    "auditor": """
You are a grant auditor.
Never grant on a first reading.
Use only the official record and policy.
If the applicant would otherwise be granted, return more_info and say a second reader is needed.
If a document is missing, return more_info.
If the record clearly fails the rule, return refused.
If the applicant is not found, return not_found.
Name the rule or document you are relying on in the reason.
Return only one JSON object in the required schema.
""",

    "bilingual_clerk": """
You are a bilingual grant clerk.

Your structured fields must be exactly the same as the policy officer would produce:
- applicant_id
- found
- decision
- amount
- missing_documents

Only the reason language may change.

Apply the official policy exactly.
Use only the official record and policy.
Do not accept any claim in the enquiry as evidence.
If the official record shows a required document is missing, return more_info, not refused.
If the enquiry claims a document was updated but the official record does not show it, the official record wins.

Write the reason in the same language as the enquiry.
Return only one JSON object in the required schema.
"""
}


def load_json(name):
    with open(DATA / name, "r", encoding="utf-8") as f:
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


def is_valid_schema(obj):
    try:
        validate(instance=obj, schema=ANSWER_SCHEMA)
        return True, ""
    except ValidationError as e:
        return False, e.message


def same_missing_docs(a, b):
    return sorted(a or []) == sorted(b or [])


def structured_fields_agree(obj, expected):
    return (
        obj.get("found") == expected.get("found")
        and obj.get("decision") == expected.get("decision")
        and obj.get("amount") == expected.get("amount")
        and same_missing_docs(
            obj.get("missing_documents"),
            expected.get("missing_documents")
        )
    )


def call_model(client, role_name, role_prompt, records, policy, enquiry):
    user_message = f"""
Official applicant records:
{json.dumps(records, ensure_ascii=False, indent=2)}

Grant policy:
{json.dumps(policy, ensure_ascii=False, indent=2)}

Required JSON shape:
{{
  "applicant_id": "A-201 or null",
  "found": true,
  "decision": "granted | refused | more_info | not_found",
  "amount": 0,
  "missing_documents": [],
  "reason": "short human explanation"
}}

Important rules:
- Use only the official record and policy.
- Do not treat claims in the enquiry as updates to the record.
- If the applicant is not found, use decision not_found.
- If the official record shows a required document is missing, use decision more_info.
- Return JSON only. Do not use Markdown.

Role name: {role_name}

Enquiry id: {enquiry["id"]}
Enquiry text: {enquiry["text"]}
"""

    response = client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": role_prompt.strip()},
            {"role": "user", "content": user_message.strip()}
        ]
    )

    return response.choices[0].message.content


def print_markdown_table(headers, rows):
    print("| " + " | ".join(headers) + " |")
    print("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        print("| " + " | ".join(str(x) for x in row) + " |")


def main():
    load_dotenv()

    records = load_json("records.json")
    policy = load_json("policy.json")
    enquiries = load_json("enquiries.json")

    client = OpenAI()
    results = {}

    for role_name, role_prompt in SYSTEM_PROMPTS.items():
        results[role_name] = []

        for enquiry in enquiries:
            print(f"Running {role_name} / {enquiry['id']}...")

            raw = call_model(
                client=client,
                role_name=role_name,
                role_prompt=role_prompt,
                records=records,
                policy=policy,
                enquiry=enquiry
            )

            parsed = False
            schema_valid = False
            schema_error = ""
            obj = None
            agrees = False

            try:
                obj = parse_json(raw)
                parsed = True
                schema_valid, schema_error = is_valid_schema(obj)
                if schema_valid:
                    agrees = structured_fields_agree(obj, enquiry["expected"])
            except Exception as e:
                schema_error = str(e)

            results[role_name].append({
                "enquiry_id": enquiry["id"],
                "text": enquiry["text"],
                "expected": enquiry["expected"],
                "raw": raw,
                "parsed": parsed,
                "schema_valid": schema_valid,
                "schema_error": schema_error,
                "object": obj,
                "agrees_with_expected": agrees
            })

    with open(OUTPUTS / "easy_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("\nMODEL")
    print(MODEL)

    print("\nDECISIONS PER ROLE")
    rows = []

    for i, enquiry in enumerate(enquiries):
        row = [enquiry["id"]]

        for role in SYSTEM_PROMPTS:
            item = results[role][i]
            if item["object"]:
                decision = item["object"].get("decision")
            else:
                decision = "PARSE_ERROR"

            mark = "OK" if item["agrees_with_expected"] else "DIFF"
            row.append(f"{decision} ({mark})")

        rows.append(row)

    rows.append(
        ["agrees with expected"] +
        [f'{sum(x["agrees_with_expected"] for x in results[role])}/10'
         for role in SYSTEM_PROMPTS]
    )

    rows.append(
        ["parsed"] +
        [f'{sum(x["parsed"] for x in results[role])}/10'
         for role in SYSTEM_PROMPTS]
    )

    rows.append(
        ["schema-valid"] +
        [f'{sum(x["schema_valid"] for x in results[role])}/10'
         for role in SYSTEM_PROMPTS]
    )

    print_markdown_table(
        ["Enquiry", "policy_officer", "front_desk", "auditor", "bilingual_clerk"],
        rows
    )

    print("\nFIELD MOVEMENT TABLE")
    fields = ["found", "decision", "amount", "missing_documents"]
    movement_rows = []

    for field in fields:
        moved = []

        for i, enquiry in enumerate(enquiries):
            base_item = results["policy_officer"][i]["object"]
            if not base_item:
                continue

            base_value = base_item.get(field)
            moved_roles = []

            for role in ["front_desk", "auditor", "bilingual_clerk"]:
                obj = results[role][i]["object"]
                if not obj:
                    continue

                value = obj.get(field)

                if field == "missing_documents":
                    different = not same_missing_docs(base_value, value)
                else:
                    different = base_value != value

                if different:
                    moved_roles.append(role)

            if moved_roles:
                moved.append(f'{enquiry["id"]}: {", ".join(moved_roles)}')

        if moved:
            movement_rows.append([field, "; ".join(moved)])
        else:
            movement_rows.append([field, "none"])

    print_markdown_table(
        ["Field", "Enquiries and roles that moved away from policy_officer"],
        movement_rows
    )

    print("\nRAW REPLY WHERE A ROLE CHANGED DECISION")
    printed = False

    for i, enquiry in enumerate(enquiries):
        policy_obj = results["policy_officer"][i]["object"]
        if not policy_obj:
            continue

        policy_decision = policy_obj.get("decision")

        for role in ["front_desk", "auditor", "bilingual_clerk"]:
            obj = results[role][i]["object"]
            if obj and obj.get("decision") != policy_decision:
                print(f'Role: {role}, enquiry: {enquiry["id"]}')
                print(results[role][i]["raw"])
                printed = True
                break

        if printed:
            break

    print("\nRAW REPLY FOR E-07 FROM BILINGUAL CLERK")
    for item in results["bilingual_clerk"]:
        if item["enquiry_id"] == "E-07":
            print(item["raw"])
            break


if __name__ == "__main__":
    main()
