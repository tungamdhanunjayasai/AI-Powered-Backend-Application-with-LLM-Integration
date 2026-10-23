"""CT-200-focused PDF extraction and hierarchy reconstruction.

Uses PyMuPDF text blocks with geometry where possible, then deterministic heading
recognition and parent-stack reconstruction. This is not a universal PDF parser.
OCR is not silently assumed: scanned pages with no extractable text are flagged.
"""
from __future__ import annotations
import hashlib, re
from dataclasses import dataclass, field
from pathlib import Path
import fitz

HEADING_RE = re.compile(r"^\s*((?:\d+(?:\.\d+)*\.?\.?\s+)|(?:Appendix\s+[A-Z]\s*[:.-]?\s*))(.+?)\s*$", re.I)
NUMBER_ONLY_RE = re.compile(r"^\s*(\d+(?:\.\d+)*\.?)\s*$")
BULLET_RE = re.compile(r"^\s*(?:[•●▪◦\-*]|\d+[.)])\s+")
TABLE_HINTS = ("parameter", "value", "code", "meaning", "device behavior")

@dataclass
class ParsedNode:
    heading: str
    level: int
    node_type: str = "section"
    body_text: str = ""
    parent_index: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    metadata_json: dict = field(default_factory=dict)
    children: list[int] = field(default_factory=list)
    logical_key: str = ""
    content_hash: str = ""

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def heading_info(line: str):
    line = norm(line)
    m = HEADING_RE.match(line)
    if not m:
        return None
    prefix, title = m.groups()
    num_match = re.match(r"(\d+(?:\.\d+)*)", prefix.strip())
    if num_match:
        number = num_match.group(1)
        level = number.count(".") + 1
        return number, title.strip(), level
    return prefix.strip(), title.strip(), 1

def extract_lines(pdf_path: str | Path):
    lines = []
    warnings = []
    with fitz.open(pdf_path) as doc:
        for pno, page in enumerate(doc, 1):
            page_lines = []
            blocks = page.get_text("dict").get("blocks", [])
            for block in blocks:
                if "lines" not in block:
                    continue
                for line in block["lines"]:
                    spans = line.get("spans", [])
                    text = norm("".join(s.get("text", "") for s in spans))
                    if not text:
                        continue
                    size = max((float(s.get("size", 0)) for s in spans), default=0)
                    page_lines.append((text, size, pno))
            if not page_lines:
                warnings.append(f"Page {pno} contains no extractable text; OCR required but not configured.")
            # Retain PDF order; do not sort geometry because multi-column/table reading order can be ambiguous.
            lines.extend(page_lines)
    return lines, warnings

def parse_pdf(pdf_path: str | Path) -> tuple[list[ParsedNode], list[str]]:
    lines, warnings = extract_lines(pdf_path)
    nodes: list[ParsedNode] = []
    stack: list[int] = []
    pending_number = None
    for text, font_size, page in lines:
        if NUMBER_ONLY_RE.match(text):
            pending_number = norm(text).rstrip(".")
            continue
        info = heading_info(text)
        # Large-font unnumbered title / headings are recognized conservatively.
        if info:
            number, title, level = info
            # Some source PDFs have repeated section numbering / subheadings.
            heading = f"{number} {title}".strip()
            logical_key = f"num:{number}:{norm(title).casefold()}"
            node = ParsedNode(heading, level, "section", "", None, page, page, {}, [], logical_key)
            # Stack is keyed to structural level; same-level duplicate headings remain distinct nodes.
            while stack and nodes[stack[-1]].level >= level:
                stack.pop()
            if stack:
                node.parent_index = stack[-1]
            idx = len(nodes); nodes.append(node)
            if node.parent_index is not None:
                nodes[node.parent_index].children.append(idx)
            stack.append(idx)
            pending_number = None
            continue
        # Standalone document title / unnumbered heading detected by font size and position.
        if not nodes and (font_size >= 16 or text.lower().startswith("cardiot")):
            node = ParsedNode(text, 0, "document_title", "", None, page, page, {}, [], "title:" + norm(text).casefold())
            nodes.append(node); stack = [0]
            continue
        # Figure/table-like content: preserve text and indicate classification instead of silently discarding.
        if not nodes:
            node = ParsedNode("Extracted content", 0, "document", "", None, page, page, {}, [], "document:root")
            nodes.append(node); stack = [0]
        current = nodes[stack[-1]] if stack else nodes[0]
        current.body_text = (current.body_text + "\n" + text).strip()
        current.page_end = page
        if any(h in text.casefold() for h in TABLE_HINTS):
            current.metadata_json.setdefault("table_candidates", []).append(text)
        if BULLET_RE.match(text):
            current.metadata_json.setdefault("list_items", []).append(text)
        # Tables may be flattened by PDF text extraction; flag for validation/inspection.
        if "|" in text or "\t" in text:
            current.metadata_json.setdefault("table_rows", []).append(text)
    if not nodes:
        warnings.append("No text was parsed from the PDF.")
        return [], warnings
    # Hash normalized heading + body, excluding child content so child edits do not taint parent hash.
    for n in nodes:
        n.content_hash = sha256(norm(n.heading) + "\n" + norm(n.body_text))
    return nodes, warnings

def to_nested(nodes: list[ParsedNode]) -> list[dict]:
    result = []
    for i, node in enumerate(nodes):
        result.append({
            "heading": node.heading, "level": node.level, "node_type": node.node_type,
            "body_text": node.body_text, "parent_index": node.parent_index,
            "page_start": node.page_start, "page_end": node.page_end,
            "metadata_json": node.metadata_json, "logical_key": node.logical_key,
            "content_hash": node.content_hash
        })
    return result
