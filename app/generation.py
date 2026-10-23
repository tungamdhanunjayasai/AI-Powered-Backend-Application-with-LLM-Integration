"""LLM generation with strict schema validation and a safe offline fallback."""
import json, os
from pydantic import ValidationError
from .schemas import TestCase

PROMPT_VERSION = "1.0"

def _fallback_cases(requirements: list[dict]) -> list[dict]:
    cases = []
    for req in requirements[:5]:
        heading = req["heading"]
        body = req["body_text"] or req["heading"]
        lower = (heading + " " + body).lower()
        steps = ["Open the device/manual workflow relevant to this requirement.",
                 "Execute the stated condition using a controlled test setup.",
                 "Record the displayed result and compare it with the requirement."]
        expected = "Observed behavior matches the stated requirement; deviations are recorded."
        risk = "medium"
        if any(x in lower for x in ["overpressure", "crisis", "immediate medical", "sensor fault"]):
            risk = "high"
        if "180 mmhg" in lower or "299 mmhg" in lower or "300 mmhg" in lower:
            steps = ["Use a calibrated test fixture to simulate the stated cuff-pressure condition.",
                     "Start a measurement and monitor the pressure-control behavior.",
                     "Capture the error code, inflation stop, and deflation timing."]
            expected = "The stated pressure threshold and protective behavior are observed and documented."
        cases.append({
            "title": f"Verify: {heading[:150]}",
            "objective": f"Verify that implementation behavior conforms to the requirement in {heading}.",
            "preconditions": ["Use a controlled test environment and calibrated equipment where applicable.",
                              "Record the manual version and requirement hash."],
            "steps": steps,
            "expected_result": expected,
            "requirement_refs": [req["logical_key"]],
            "risk": risk
        })
    while len(cases) < 3 and requirements:
        req = requirements[len(cases) % len(requirements)]
        cases.append({
            "title": f"Boundary and repeatability: {req['heading'][:130]}",
            "objective": f"Check repeatability and boundary behavior for {req['heading']}.",
            "preconditions": ["Test environment is controlled.", "Source version and content hash are recorded."],
            "steps": ["Run the test at the stated nominal condition.", "Repeat near the stated boundary if one is specified.",
                      "Compare outputs with the exact source text."],
            "expected_result": "Behavior is consistent with the requirement; unsupported assumptions are reported.",
            "requirement_refs": [req["logical_key"]],
            "risk": "medium"
        })
    return cases[:5]

def _call_llm(requirements: list[dict]) -> tuple[list[dict], str, str]:
    base_url = os.getenv("LLM_BASE_URL", "").strip()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "").strip()
    if not (base_url and api_key and model):
        return _fallback_cases(requirements), "local-fallback", "deterministic-fallback"
    import httpx
    prompt = {
        "task": "Generate 3 to 5 concrete QA test cases from supplied medical-device manual excerpts.",
        "constraints": [
            "Return only a JSON object with key test_cases containing an array of 3-5 objects.",
            "Each case fields: title, objective, preconditions (array), steps (array), expected_result, requirement_refs (array), risk (low|medium|high).",
            "Do not invent requirements or thresholds. Use only supplied excerpts.",
            "Every case must cite one or more supplied logical_key values in requirement_refs.",
            "If text is ambiguous, say so in the test rather than guessing."
        ],
        "requirements": requirements
    }
    response = httpx.post(
        base_url.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "temperature": 0.1, "messages": [
            {"role": "system", "content": "You are a careful medical-device QA test designer. Output valid JSON only."},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}
        ]},
        timeout=45
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    data = json.loads(content)
    cases = data["test_cases"] if isinstance(data, dict) else data
    return cases, "openai-compatible", model

def generate_cases(requirements: list[dict]) -> tuple[list[dict], str, str, list[str]]:
    errors = []
    try:
        cases, provider, model = _call_llm(requirements)
        validated = [TestCase.model_validate(c).model_dump() for c in cases]
        if not 3 <= len(validated) <= 5:
            raise ValueError(f"Expected 3-5 cases, got {len(validated)}")
        valid_keys = {r["logical_key"] for r in requirements}
        for i, case in enumerate(validated):
            unknown = set(case["requirement_refs"]) - valid_keys
            if unknown:
                raise ValueError(f"Case {i} references unknown requirement keys: {sorted(unknown)}")
        return validated, provider, model, errors
    except Exception as exc:
        errors.append(f"LLM/validation failure; deterministic fallback used: {type(exc).__name__}: {exc}")
        cases = [TestCase.model_validate(c).model_dump() for c in _fallback_cases(requirements)]
        # If the input is empty or too small, caller should reject before this function.
        return cases, "local-fallback", "deterministic-fallback", errors
