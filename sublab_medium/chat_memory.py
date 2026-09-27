import argparse
import copy
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


def prompt_tokens(response):
    if response.usage and response.usage.prompt_tokens is not None:
        return response.usage.prompt_tokens
    return 0


def build_system_prompt(records, policy):
    return f"""
You are a grant office assistant.

Use the official applicant records and policy when the user asks about eligibility,
missing documents, amounts, or decisions. Use the conversation history for facts
the applicant personally stated, such as availability, side questions, and constraints.

Official records:
{json.dumps(records, ensure_ascii=False, indent=2)}

Official policy:
{json.dumps(policy, ensure_ascii=False, indent=2)}

Important rules:
- A model call is stateless; answer only from the messages or memory state sent to you.
- Do not treat a user's claim as an update to the official record.
- If the official record shows a required document is missing, say it is still missing.
- Keep answers short and clear.
""".strip()


def build_messages(system_prompt, history, state=None):
    messages = [{"role": "system", "content": system_prompt}]

    if state is not None:
        messages.append({
            "role": "system",
            "content": "Compressed memory state:\n" + json.dumps(state, ensure_ascii=False, indent=2)
        })

    messages.extend(history)
    return messages


def call_chat(client, system_prompt, history, user_text, state=None):
    messages = build_messages(system_prompt, history, state)
    messages.append({"role": "user", "content": user_text})

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages
    )

    answer = response.choices[0].message.content
    tokens = prompt_tokens(response)

    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": answer})

    return answer, tokens


def compress_history(client, schema, history):
    transcript = "\n".join(
        f'{m["role"].upper()}: {m["content"]}'
        for m in history
    )

    system_prompt = f"""
You compress a grant-office conversation into one structured memory state.

Return only valid JSON that matches this schema:
{json.dumps(schema, ensure_ascii=False, indent=2)}

Rules:
- Nothing may be invented.
- A fact the applicant did not say must not appear.
- applicant_id is null if not established.
- facts are things the applicant stated.
- decisions are assistant conclusions or policy/record conclusions already discussed.
- constraints are limits such as dates, days, deadlines, or availability.
- open_questions are questions asked by the applicant that have not yet been answered.
- Use arrays. Empty arrays are allowed.
- Keep enough detail to answer later probes about identity, missing documents, income band,
  amount, availability constraints, and unanswered employer-letter question.
""".strip()

    response = client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": transcript}
        ]
    )

    raw = response.choices[0].message.content
    tokens = prompt_tokens(response)

    obj = parse_json(raw)
    validate(instance=obj, schema=schema)

    return obj, raw, tokens


def retrieved(probe, answer):
    answer_low = answer.lower()

    if probe["id"] in ["Q-2", "Q-3"]:
        return any(x.lower() in answer_low for x in probe["expect_contains"])

    return all(x.lower() in answer_low for x in probe["expect_contains"])


def run_script(compressed):
    load_dotenv()

    records = load_json("records.json")
    policy = load_json("policy.json")
    script = load_json("chat_script.json")
    schema = load_json("memory_state.schema.json")

    client = OpenAI()
    system_prompt = build_system_prompt(records, policy)

    history = []
    state = None
    token_rows = []
    state_raw = None

    call_no = 0

    for turn in script["conversation"]:
        call_no += 1

        if turn == "<compress>":
            if compressed:
                try:
                    state, state_raw, tokens = compress_history(client, schema, history)
                    history = []
                    token_rows.append(tokens)
                except Exception as e:
                    print("Compression failed:", e)
                    token_rows.append(0)
            else:
                token_rows.append(0)
            continue

        answer, tokens = call_chat(
            client=client,
            system_prompt=system_prompt,
            history=history,
            user_text=turn,
            state=state
        )

        token_rows.append(tokens)

    base_history = copy.deepcopy(history)
    base_state = copy.deepcopy(state)

    probe_results = []

    for probe in script["probes"]:
        probe_history = copy.deepcopy(base_history)

        answer, tokens = call_chat(
            client=client,
            system_prompt=system_prompt,
            history=probe_history,
            user_text=probe["question"],
            state=base_state
        )

        probe_results.append({
            "id": probe["id"],
            "question": probe["question"],
            "tests": probe["tests"],
            "answer": answer,
            "retrieved": retrieved(probe, answer),
            "prompt_tokens": tokens
        })

    return {
        "mode": "compressed" if compressed else "uncompressed",
        "tokens_per_call": token_rows,
        "peak": max(token_rows) if token_rows else 0,
        "total": sum(token_rows),
        "state": state,
        "state_raw": state_raw,
        "probes": probe_results,
        "retrieved_count": sum(p["retrieved"] for p in probe_results)
    }


def print_markdown_table(headers, rows):
    print("| " + " | ".join(headers) + " |")
    print("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        print("| " + " | ".join(str(x).replace("\n", " ") for x in row) + " |")


def scripted_main():
    a = run_script(compressed=False)
    b = run_script(compressed=True)

    results = {"uncompressed": a, "compressed": b}

    with open(OUTPUTS / "medium_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("\nMODEL")
    print(MODEL)

    print("\nTOKENS PER CALL")
    rows = []
    n = max(len(a["tokens_per_call"]), len(b["tokens_per_call"]))

    for i in range(n):
        a_tok = a["tokens_per_call"][i] if i < len(a["tokens_per_call"]) else ""
        b_tok = b["tokens_per_call"][i] if i < len(b["tokens_per_call"]) else ""
        rows.append([i + 1, a_tok, b_tok])

    rows.append(["peak", a["peak"], b["peak"]])
    rows.append(["total for the run", a["total"], b["total"]])

    print_markdown_table(
        ["Call", "A — never compressed", "B — compressed at the compress turn"],
        rows
    )

    print("\nPROBES AFTER THE CONVERSATION")
    probe_rows = []

    for pa, pb in zip(a["probes"], b["probes"]):
        probe_rows.append([
            pa["id"],
            pa["tests"],
            "yes" if pa["retrieved"] else "no",
            pa["answer"],
            "yes" if pb["retrieved"] else "no",
            pb["answer"]
        ])

    probe_rows.append([
        "retrieved",
        "",
        f'{a["retrieved_count"]}/5',
        "",
        f'{b["retrieved_count"]}/5',
        ""
    ])

    print_markdown_table(
        ["Probe", "Tests", "A retrieved?", "A answer", "B retrieved?", "B answer"],
        probe_rows
    )

    print("\nTHE STATE MY COMPRESSION PRODUCED")
    print(json.dumps(b["state"], ensure_ascii=False, indent=2))


def interactive_main():
    load_dotenv()

    records = load_json("records.json")
    policy = load_json("policy.json")
    schema = load_json("memory_state.schema.json")

    client = OpenAI()
    system_prompt = build_system_prompt(records, policy)

    history = []
    state = None
    last_tokens = 0

    print("Interactive chat. Type 'compress', 'tokens', or 'exit'.")

    while True:
        user_text = input("you> ").strip()

        if user_text.lower() in ["exit", "quit"]:
            break

        if user_text.lower() == "tokens":
            print("last prompt tokens:", last_tokens)
            continue

        if user_text.lower() == "compress":
            try:
                state, raw, last_tokens = compress_history(client, schema, history)
                history = []
                print("compressed state:")
                print(json.dumps(state, ensure_ascii=False, indent=2))
            except Exception as e:
                print("compression failed; history kept")
                print(e)
            continue

        answer, last_tokens = call_chat(
            client=client,
            system_prompt=system_prompt,
            history=history,
            user_text=user_text,
            state=state
        )

        print("assistant>", answer)
        print("prompt tokens:", last_tokens)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args()

    if args.interactive:
        interactive_main()
    else:
        scripted_main()


if __name__ == "__main__":
    main()
