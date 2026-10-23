# Technical Approach — Tri9T AI CT-200 Assignment

## 1. Architecture

- **Ingestion/parser:** PyMuPDF extracts text spans and page numbers from the supplied PDF. A CT-200-specific recognizer identifies numbered headings and reconstructs the parent/child tree using a level stack.
- **Persistence:** SQLAlchemy 2 + SQLite stores documents, immutable versions, nodes, selections, source snapshots, generations, and generation-source links.
- **Generation:** an optional OpenAI-compatible LLM endpoint returns structured JSON. Pydantic validates fields and constraints; reference keys and case count are validated separately. A deterministic offline fallback is used on provider, JSON, schema, count, or traceability failures.
- **Retrieval/staleness:** generation retrieval compares the selection's stored content hash to the logical node in the latest version and returns an explicit stale flag per requirement.

## 2. Hierarchy reconstruction

The parser recognizes numbered headings such as `2.2 Cuff Specifications` and maps numeric depth to hierarchy level. A stack closes peers and descendants when a new heading appears. Paragraph text is attached to the current heading. Bullet-like lines are retained verbatim in body text and copied into list metadata. Page ranges are tracked. The document title is a level-zero node when detectable.

## 3. Irregularities and edge cases

1. **Repeated headings:** nodes are stored with distinct database IDs and logical keys include an occurrence counter. Identical titles are not merged.
2. **Heading numbering and hierarchy:** numbering depth is used as a heuristic; an unexpected skipped level may attach to the nearest prior lower-level node. This should be reviewed against the PDF.
3. **Tables:** PDF text may flatten columns. The parser flags likely table headers/rows in metadata but does not claim to reconstruct all cell boundaries perfectly.
4. **Figures/images:** images with no text are not OCR'd; pages without a text layer are surfaced in warnings. Figure captions that exist as text are retained in the relevant body.
5. **Version wording changes:** content hashes change on textual changes. Parent hashes exclude child text so local change impact is easier to identify.
6. **PDF extraction order:** original block order is retained. Complex multi-column layouts can still produce ambiguous reading order.
7. **PDF parser errors:** invalid or unreadable PDFs return an error rather than being silently accepted.

## 4. Version matching

Matching uses a normalized numbered heading/title and its occurrence index within each version. This is deliberately transparent and deterministic. The body hash independently determines whether matched node content changed. The method is vulnerable to heading renames, reordered duplicate headings, and semantically equivalent paraphrases. A production approach could combine stable section numbering, parent-path identity, fuzzy title matching, and reviewer-confirmed mappings.

## 5. Stale traceability

A selection item snapshots the source version, node ID, logical key, content hash, heading, and body text. Generated records link to selection items, not just current node IDs. Retrieval checks the matching logical key in the latest version and compares the hash. Missing current nodes count as stale. This is conservative and visible to the caller.

The system detects wording and numeric changes as text changes but does not claim to understand clinical significance. A change from one threshold to another is detected; semantic risk classification and selective invalidation require a more domain-aware layer. The API does not auto-regenerate stale cases, as this is out of scope.

## 6. LLM prompt and validation

The prompt demands 3–5 cases with title, objective, preconditions, steps, expected result, requirement references, and risk. It explicitly forbids invented thresholds and requires references to supplied logical keys. Pydantic validates shape and field constraints. The application then validates count and reference integrity. Provider errors, malformed JSON, invalid schema, and unknown references trigger deterministic fallback, with a stored validation error. This keeps the endpoint usable while making failure observable.

## 7. Duplicate generation policy

Submitting the same selection again returns the most recent generation by default, avoiding accidental duplicate records and repeated LLM cost. `force_new=true` explicitly requests another generation. The generation keeps a snapshot relationship to the selection items, so later document ingestion does not rewrite its evidence.

## 8. Validation plan

- Unit tests for nested heading levels, duplicate heading identity, and empty/unreadable PDF behavior.
- Integration test ingests both supplied manual versions and asserts a comparison reports at least one changed node.
- Integration test creates a selection and verifies the exact version number is retained.
- Manual review should compare the extracted tree and table candidates with the visual PDF pages, especially the specification tables and error-code table.

## 9. Decision log

1. **Most likely silent failure:** a paragraph/table row can be attached to the wrong heading because PDF layout and text extraction order are not semantic structure. Catch it with a fixture-based extraction review, page-level text comparison, and explicit assertions for known table/heading anchors.
2. **Simplicity chosen over correctness:** table reconstruction and OCR are not fully implemented; text extraction plus heuristics was chosen to deliver the end-to-end versioning/traceability workflow. A production deployment would first fail on scanned PDFs and complex tables.
3. **Unhandled input:** a scanned page with no text layer is not OCR'd. The parser reports the page in warnings; a fully textless PDF is rejected rather than producing an empty, misleading hierarchy.

## 10. Further work

Add OCR fallback (e.g. Tesseract or a managed OCR service), geometry-aware table extraction, semantic section matching with reviewer confirmation, stronger hierarchy constraints, clinically aware change severity, and regression fixtures for every detected PDF irregularity.
