# python/gateway/utils/schema_enforcer.py
"""
Robust JSON Schema Enforcement with Auto-Repair and Observability
Single source of truth for schema extraction, repair, validation, and re-ask prompt building.

Implements redisTicket.md recommendations:
- Balanced brace extraction (not regex scraping)
- Deterministic sanitization 
- One re-ask with strict JSON mode
- Telemetry for observability
"""

from __future__ import annotations
import json
import re
import time
import logging
from typing import Optional, Tuple, Type, Dict, Any
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

class JSONEnforceError(Exception):
    """Exception raised during JSON enforcement stages"""
    def __init__(self, stage: str, detail: str):
        super().__init__(f"{stage}: {detail}")
        self.stage = stage
        self.detail = detail

def _extract_fenced_json(text: str) -> Optional[str]:
    """Extract JSON from code fences like ```json ... ``` or ``` ... ```"""
    fences = [
        r"```json\s*(\{.*?\})\s*```",
        r"```\s*(\{.*?\})\s*```",
    ]
    for pat in fences:
        m = re.search(pat, text, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None

def _extract_json_anywhere(text: str) -> Optional[str]:
    """Find the first balanced top-level JSON object in text using brace balancing"""
    start = text.find("{")
    if start < 0:
        return None
    
    depth = 0
    in_str = False
    esc = False
    
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return None

def _simple_repairs(raw: str) -> str:
    """Apply common LLM output repairs without being overly aggressive"""
    s = raw.strip()
    
    # Common LLM mistakes
    s = s.replace("\u201c", '"').replace("\u201d", '"')  # Smart quotes
    s = s.replace("\u2018", "'").replace("\u2019", "'")  # Smart apostrophes
    
    # Remove leading/trailing backticks
    s = re.sub(r"^`+|`+$", "", s.strip())
    
    # Fix trailing commas in objects/arrays
    s = re.sub(r",\s*([}\]])", r"\1", s)
    
    # Convert single to double quotes if it looks like JSON-with-single-quotes
    if s.count('"') == 0 and s.count("'") > 0:
        # Heuristic only - try not to break apostrophes inside text
        s = re.sub(r"'", '"', s)
    
    return s

def extract_and_validate(model_cls: Type[BaseModel], text: str) -> BaseModel:
    """
    One-pass: extract → repair → parse → validate.
    Raises JSONEnforceError with stage info on failure.
    """
    # Try fenced extraction first, then balanced extraction, finally raw text
    j = _extract_fenced_json(text) or _extract_json_anywhere(text) or text
    j = _simple_repairs(j)
    
    try:
        data = json.loads(j)
    except json.JSONDecodeError as e:
        raise JSONEnforceError("json_decode", str(e))
    
    try:
        return model_cls.model_validate(data)
    except ValidationError as e:
        raise JSONEnforceError("schema_validate", e.json())

def build_repair_prompt(model_cls: Type[BaseModel], original_user_prompt: str) -> str:
    """Build strict re-ask prompt with inlined schema"""
    schema = model_cls.model_json_schema()
    return (
        original_user_prompt
        + "\n\n"
        "Now output ONLY a JSON object that conforms to this schema. No prose, no code fences.\n"
        f"SCHEMA:\n{json.dumps(schema, ensure_ascii=False)}\n"
        "Rules:\n"
        "- If unsure, use conservative defaults.\n"
        "- 3–5 recommendations; unique course_code; ascending priority.\n"
        "- Include 'schema_version': 'v1' at top-level if the schema supports it.\n"
    )

def sanitize_validated(model: BaseModel) -> BaseModel:
    """
    Extra hygiene: dedupe, normalize, clamp lengths.
    Never throws - returns original model on any error.
    """
    try:
        # Handle ChatAdvisorResponse specifically
        if hasattr(model, 'recommendations'):
            recs = getattr(model, 'recommendations', [])
            
            # Canonicalize course codes: "CS 3110" form and dedupe
            norm = {}
            for r in recs:
                if hasattr(r, 'course_code'):
                    code = re.sub(r"\s+", " ", str(getattr(r, "course_code", ""))).strip().upper()
                    code = re.sub(r"^([A-Z]{2,4})\s*([0-9]{4}[A-Z]?)$", r"\1 \2", code)
                    if code and code not in norm:
                        setattr(r, "course_code", code)
                        norm[code] = r
            
            # Keep up to 5 recs with contiguous priorities
            recs = list(norm.values())[:5]
            for idx, r in enumerate(recs, 1):
                if hasattr(r, 'priority'):
                    setattr(r, 'priority', idx)
            
            setattr(model, 'recommendations', recs)
        
        # Cap notes length if present
        if hasattr(model, 'notes') and getattr(model, 'notes'):
            notes = str(getattr(model, 'notes'))[:1000]
            setattr(model, 'notes', notes)
        
        return model
    except Exception as e:
        logger.warning(f"Sanitization failed: {e}")
        return model  # Never throw here

def enforce_with_retry(
    model_cls: Type[BaseModel],
    first_attempt_text: str,
    original_user_prompt: str,
) -> Tuple[Optional[BaseModel], Dict[str, Any]]:
    """
    Returns (model or None, telemetry dict).
    This is the sync version - orchestrator will handle async re-ask if needed.
    """
    t0 = time.perf_counter()
    
    try:
        model = extract_and_validate(model_cls, first_attempt_text)
        model = sanitize_validated(model)
        return model, {
            "stage": "first_pass", 
            "ms": int((time.perf_counter() - t0) * 1000)
        }
    except JSONEnforceError as e1:
        # Needs re-ask - return repair prompt
        repair_prompt = build_repair_prompt(model_cls, original_user_prompt)
        return None, {
            "stage": "needs_reask",
            "ms": int((time.perf_counter() - t0) * 1000),
            "error": f"{e1.stage}",
            "repair_prompt": repair_prompt,
        }

def validate_reask_result(model_cls: Type[BaseModel], raw_json: str) -> Optional[BaseModel]:
    """
    Validate the result from re-ask attempt.
    Returns validated model or None on failure.
    """
    try:
        model = model_cls.model_validate_json(raw_json)
        return sanitize_validated(model)
    except Exception as e:
        logger.error(f"Re-ask validation failed: {e}")
        return None