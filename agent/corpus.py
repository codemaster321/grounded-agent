"""Load the policy corpus into citable chunks.

Chunking is by markdown '## ' section. Files without sections become one chunk:
they are all under ~1 KB, so splitting further would separate a rule from its context.
Chunk ids are what the agent cites: 'POL-CRD-001#3' (numbered section),
'POL-PRD-010#classic-card' (named section) or 'POL-FEE-007' (whole document).
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "data" / "policy_corpus"
MANIFEST = json.loads((Path(__file__).parent / "corpus_manifest.json").read_text(encoding="utf-8"))

_HEADER = re.compile(r"Document ID: (?P<doc_id>[\w-]+) \| Version (?P<version>[^|]+?)(?: \| Effective (?P<effective>[^|]+?))? \| Owner")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    title: str
    section: str
    version: str
    effective: str | None
    text: str

    def for_search(self) -> str:
        # Title + section heading are prepended so a chunk like "## 3. Mandatory declines"
        # still matches a query about "credit limit".
        return f"{self.title}. {self.section}\n{self.text}"


def _section_key(heading: str) -> str:
    m = re.match(r"(\d+)\.", heading)
    return m.group(1) if m else re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")


def parse_document(raw: str) -> list[Chunk]:
    lines = raw.strip().splitlines()
    title = lines[0].lstrip("# ").strip()
    header = _HEADER.search(lines[1])
    if not header:
        raise ValueError(f"unrecognised document header: {lines[1]!r}")
    doc_id = header["doc_id"]
    body = "\n".join(lines[2:]).strip()

    parts = re.split(r"^## (.+)$", body, flags=re.MULTILINE)
    # re.split with a capture group gives [preamble, heading1, text1, heading2, text2, ...]
    sections = [("", parts[0].strip())] if parts[0].strip() else []
    sections += [(parts[i].strip(), parts[i + 1].strip()) for i in range(1, len(parts), 2)]

    return [
        Chunk(
            chunk_id=f"{doc_id}#{_section_key(heading)}" if heading else doc_id,
            doc_id=doc_id,
            title=title,
            section=heading,
            version=header["version"].strip(),
            effective=header["effective"],
            text=text,
        )
        for heading, text in sections
    ]


def load_corpus(include_excluded: bool = False) -> list[Chunk]:
    """include_excluded=True is only for the Break demos: indexing POL-OPS-012 on purpose."""
    chunks = []
    for path in sorted(CORPUS_DIR.glob("*.md")):
        for chunk in parse_document(path.read_text(encoding="utf-8")):
            if include_excluded or chunk.doc_id not in MANIFEST["excluded"]:
                chunks.append(chunk)
    return chunks
