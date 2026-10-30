"""Tag a company with a coarse type: yaml table -> sqlite cache -> Gemini -> "other"."""
import logging
import os
import re
import sqlite3

import requests
import yaml

log = logging.getLogger(__name__)

TYPES = ("defense", "aerospace", "big-tech", "semiconductor", "startup",
         "health", "automotive", "industrial", "consumer-hw", "other")
_SUFFIXES = {"inc", "incorporated", "llc", "corp", "corporation", "co", "company",
             "ltd", "limited", "plc", "lp", "llp", "gmbh", "ag", "sa"}
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"


def normalize(name: str) -> str:
    words = re.sub(r"[.,()]", " ", name.lower()).split()
    if words and words[0] == "the":
        words = words[1:]
    while len(words) > 1 and words[-1] in _SUFFIXES:
        words.pop()
    return " ".join(words)


class CompanyTyper:
    def __init__(self, config: dict, db_path: str, yaml_path: str = "company_types.yaml"):
        self.config = config
        self.db_path = db_path
        try:
            with open(yaml_path) as f:
                raw = yaml.safe_load(f) or {}
        except OSError:
            log.warning("company types file %s not found", yaml_path)
            raw = {}
        self.table = {normalize(k): v for k, v in raw.items() if v in TYPES}
        with sqlite3.connect(db_path) as c:
            c.execute("CREATE TABLE IF NOT EXISTS company_types (name TEXT PRIMARY KEY, type TEXT)")

    def label(self, company: str) -> str:
        key = normalize(company or "")
        if not key:
            return "other"
        if key in self.table:
            return self.table[key]
        try:
            with sqlite3.connect(self.db_path) as c:
                row = c.execute("SELECT type FROM company_types WHERE name = ?", (key,)).fetchone()
            if row:
                return row[0]
            t = self._ask_gemini(company)
            if t:
                with sqlite3.connect(self.db_path) as c:
                    c.execute("INSERT OR REPLACE INTO company_types VALUES (?, ?)", (key, t))
                return t
        except Exception as e:  # never raise from tagging
            log.warning("company type lookup failed for %r: %s", company, e)
        return "other"

    def _ask_gemini(self, company: str) -> str | None:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            return None
        model = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
        prompt = (f'Classify the employer "{company}" for an electrical engineering intern. '
                  f"Answer with exactly one of: {', '.join(TYPES)}. Reply with only that word.")
        try:
            r = requests.post(GEMINI_URL.format(model), headers={"x-goog-api-key": key},
                              json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=10)
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:  # key not in message: it's sent as a header, not in the URL
            log.warning("Gemini company type request failed for %r: %s", company, e)
            return None
        answer = text.strip().strip(".`'\"").lower()
        return answer if answer in TYPES else None
