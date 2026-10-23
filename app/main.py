from __future__ import annotations
import hashlib, json, os, re
from pathlib import Path
from difflib import SequenceMatcher
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from .db import Base, engine, get_db
from .models import Document, DocumentVersion, DocumentNode, Selection, SelectionItem, Generation, GenerationSource
from .schemas import IngestRequest, SelectionCreate, GenerationRequest
from .parser import parse_pdf, sha256, norm
from .generation import generate_cases, PROMPT_VERSION

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Tri9T CT-200 Requirement Traceability API", version="1.0.0",
              description="PDF ingestion, versioned hierarchy, selection-pinned QA generation, and staleness detection.")

def node_dict(n: DocumentNode):
    return {"id": n.id, "version_id": n.version_id, "logical_key": n.logical_key,
            "node_key": n.node_key, "parent_id": n.parent_id, "heading": n.heading,
            "level": n.level, "node_type": n.node_type, "body_text": n.body_text,
            "content_hash": n.content_hash, "page_start": n.page_start, "page_end": n.page_end,
            "metadata_json": n.metadata_json or {}}

def get_latest_version(db: Session, doc: Document):
    return db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == doc.id)
                     .order_by(DocumentVersion.version_number.desc()))

def find_document(db: Session, name: str):
    doc = db.scalar(select(Document).where(Document.name == name))
    if not doc:
        raise HTTPException(404, f"Document '{name}' not found")
    return doc

def summarize_diff(old: str, new: str):
    a, b = norm(old), norm(new)
    ratio = SequenceMatcher(a=a, b=b).ratio()
    matcher = SequenceMatcher(a=a.split(), b=b.split())
    changed = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            changed.append({"operation": tag, "old": " ".join(a.split()[i1:i2])[:250],
                            "new": " ".join(b.split()[j1:j2])[:250]})
    return {"similarity": round(ratio, 3), "old_chars": len(old), "new_chars": len(new),
            "changes": changed[:10]}

def ingest_bytes(db: Session, content: bytes, source_filename: str, document_name: str, requested_version: int | None = None):
    file_hash = hashlib.sha256(content).hexdigest()
    doc = db.scalar(select(Document).where(Document.name == document_name))
    if doc is None:
        doc = Document(name=document_name); db.add(doc); db.flush()
    existing = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == doc.id,
                                                         DocumentVersion.source_sha256 == file_hash))
    if existing:
        return {"document_id": doc.id, "version_id": existing.id, "version_number": existing.version_number,
                "node_count": db.scalar(select(func.count(DocumentNode.id)).where(DocumentNode.version_id == existing.id)),
                "already_ingested": True, "warnings": []}
    latest = get_latest_version(db, doc)
    version_number = requested_version or ((latest.version_number + 1) if latest else 1)
    if db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == doc.id,
                                                DocumentVersion.version_number == version_number)):
        raise HTTPException(409, f"Version {version_number} already exists; choose another version number.")
    temp_path = Path("/tmp") / f"ct200_{file_hash[:12]}.pdf"
    temp_path.write_bytes(content)
    parsed, warnings = parse_pdf(temp_path)
    temp_path.unlink(missing_ok=True)
    if not parsed:
        raise HTTPException(422, "No parseable text found in PDF; scanned pages need OCR.")
    version = DocumentVersion(document_id=doc.id, version_number=version_number,
                              source_filename=source_filename, source_sha256=file_hash)
    db.add(version); db.flush()
    # Map semantic-ish logical keys to previous version nodes. Duplicate headings are disambiguated by occurrence.
    previous_nodes = []
    if latest:
        previous_nodes = list(db.scalars(select(DocumentNode).where(DocumentNode.version_id == latest.id)).all())
    previous_by_key = {}
    for p in previous_nodes:
        previous_by_key.setdefault(p.logical_key, []).append(p)
    occurrence = {}
    parsed_to_id = {}
    for i, p in enumerate(parsed):
        base_key = p.logical_key or "heading:" + norm(p.heading).casefold()
        occurrence[base_key] = occurrence.get(base_key, 0) + 1
        # Occurrence index prevents duplicate-heading collisions while retaining cross-version matching.
        logical_key = sha256(f"{base_key}#occurrence:{occurrence[base_key]}")
        parent_db_id = parsed_to_id.get(p.parent_index) if p.parent_index is not None else None
        node = DocumentNode(version_id=version.id, logical_key=logical_key,
            node_key=sha256(f"{version.id}:{logical_key}"), parent_id=parent_db_id,
            heading=p.heading, level=p.level, node_type=p.node_type, body_text=p.body_text,
            content_hash=p.content_hash, page_start=p.page_start, page_end=p.page_end,
            metadata_json=p.metadata_json or {})
        db.add(node); db.flush()
        parsed_to_id[i] = node.id
    db.commit()
    return {"document_id": doc.id, "version_id": version.id, "version_number": version_number,
            "node_count": len(parsed), "already_ingested": False, "warnings": warnings}

@app.get("/health")
def health():
    return {"status": "ok", "service": "tri9t-ct200"}

@app.post("/documents/ingest")
async def ingest(request: IngestRequest, file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(415, "Upload a PDF file.")
    content = await file.read()
    if not content.startswith(b"%PDF"):
        raise HTTPException(415, "Uploaded file does not have a PDF signature.")
    return ingest_bytes(db, content, request.source_filename or file.filename, request.document_name, request.version_number)

@app.post("/documents/ingest-path")
def ingest_path(path: str = Query(..., description="Path to a PDF accessible to the API process"),
                document_name: str = Query("CardioTrack CT-200 Home Blood Pressure Monitor"),
                version_number: int | None = Query(None, ge=1), db: Session = Depends(get_db)):
    p = Path(path)
    if not p.exists() or not p.is_file() or p.suffix.lower() != ".pdf":
        raise HTTPException(404, "PDF path not found.")
    return ingest_bytes(db, p.read_bytes(), p.name, document_name, version_number)

@app.get("/documents")
def list_documents(db: Session = Depends(get_db)):
    docs = db.scalars(select(Document).order_by(Document.id)).all()
    out = []
    for doc in docs:
        latest = get_latest_version(db, doc)
        out.append({"id": doc.id, "name": doc.name, "latest_version": latest.version_number if latest else None})
    return out

@app.get("/documents/{document_id}/versions")
def list_versions(document_id: int, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc: raise HTTPException(404, "Document not found")
    versions = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == document_id)
                          .order_by(DocumentVersion.version_number)).all()
    return [{"id": v.id, "version_number": v.version_number, "source_filename": v.source_filename,
             "source_sha256": v.source_sha256, "created_at": v.created_at} for v in versions]

@app.get("/documents/{document_id}/sections")
def top_sections(document_id: int, version: int | None = None, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc: raise HTTPException(404, "Document not found")
    ver = (db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == document_id,
              DocumentVersion.version_number == version)) if version else get_latest_version(db, doc))
    if not ver: raise HTTPException(404, "Version not found")
    nodes = db.scalars(select(DocumentNode).where(DocumentNode.version_id == ver.id).order_by(DocumentNode.id)).all()
    return [node_dict(n) for n in nodes if n.parent_id is None or n.level <= 1]

@app.get("/nodes/{node_id}")
def get_node(node_id: int, db: Session = Depends(get_db)):
    node = db.get(DocumentNode, node_id)
    if not node: raise HTTPException(404, "Node not found")
    children = db.scalars(select(DocumentNode).where(DocumentNode.parent_id == node.id).order_by(DocumentNode.id)).all()
    return {**node_dict(node), "children": [node_dict(c) for c in children],
            "full_text": "\n".join(x for x in [node.heading, node.body_text] if x)}

@app.get("/nodes")
def search_nodes(q: str = "", version_id: int | None = None, level: int | None = None,
                 db: Session = Depends(get_db)):
    stmt = select(DocumentNode)
    if version_id: stmt = stmt.where(DocumentNode.version_id == version_id)
    if level is not None: stmt = stmt.where(DocumentNode.level == level)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where((DocumentNode.heading.ilike(pattern)) | (DocumentNode.body_text.ilike(pattern)))
    nodes = db.scalars(stmt.order_by(DocumentNode.version_id, DocumentNode.id).limit(200)).all()
    return [node_dict(n) for n in nodes]

@app.get("/nodes/{node_id}/changes")
def node_changes(node_id: int, db: Session = Depends(get_db)):
    node = db.get(DocumentNode, node_id)
    if not node: raise HTTPException(404, "Node not found")
    ver = db.get(DocumentVersion, node.version_id)
    doc = db.get(Document, ver.document_id)
    versions = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == doc.id)
                          .order_by(DocumentVersion.version_number)).all()
    result = []
    for other_ver in versions:
        other = db.scalar(select(DocumentNode).where(DocumentNode.version_id == other_ver.id,
                                                      DocumentNode.logical_key == node.logical_key))
        if not other:
            result.append({"version": other_ver.version_number, "status": "missing", "changed": True})
        else:
            result.append({"version": other_ver.version_number,
                           "status": "unchanged" if other.content_hash == node.content_hash else "changed",
                           "changed": other.content_hash != node.content_hash,
                           "node_id": other.id,
                           "diff": None if other.content_hash == node.content_hash else summarize_diff(other.body_text, node.body_text)})
    return {"node_id": node.id, "logical_key": node.logical_key, "versions": result}

@app.post("/selections")
def create_selection(request: SelectionCreate, db: Session = Depends(get_db)):
    nodes = []
    for nid in request.node_ids:
        node = db.get(DocumentNode, nid)
        if not node: raise HTTPException(404, f"Node {nid} not found")
        nodes.append(node)
    selection = Selection(name=request.name); db.add(selection); db.flush()
    for node in nodes:
        selection.items.append(SelectionItem(node_id=node.id, version_id=node.version_id,
            logical_key=node.logical_key, content_hash=node.content_hash,
            heading_snapshot=node.heading, body_snapshot=node.body_text, level_snapshot=node.level))
    db.commit(); db.refresh(selection)
    return {"selection_id": selection.id, "name": selection.name, "items": [
        {"node_id": i.node_id, "version_id": i.version_id, "version_number": i.version.version_number,
         "logical_key": i.logical_key, "content_hash": i.content_hash, "heading": i.heading_snapshot}
        for i in selection.items]}

@app.get("/selections/{selection_id}")
def get_selection(selection_id: int, db: Session = Depends(get_db)):
    s = db.get(Selection, selection_id)
    if not s: raise HTTPException(404, "Selection not found")
    return {"selection_id": s.id, "name": s.name, "items": [
        {"node_id": i.node_id, "version_id": i.version_id, "version_number": i.version.version_number,
         "logical_key": i.logical_key, "content_hash": i.content_hash, "heading": i.heading_snapshot,
         "body_text": i.body_snapshot} for i in s.items]}

@app.post("/generations")
def create_generation(request: GenerationRequest, db: Session = Depends(get_db)):
    selection = db.get(Selection, request.selection_id)
    if not selection: raise HTTPException(404, "Selection not found")
    if not selection.items: raise HTTPException(422, "Selection has no nodes")
    if not request.force_new:
        existing = db.scalar(select(Generation).where(Generation.selection_id == selection.id)
                              .order_by(Generation.id.desc()))
        if existing:
            return generation_payload(existing, db, reused=True)
    requirements = [{"logical_key": i.logical_key, "heading": i.heading_snapshot,
                     "body_text": i.body_snapshot, "content_hash": i.content_hash,
                     "version_number": i.version.version_number} for i in selection.items]
    cases, provider, model, errors = generate_cases(requirements)
    gen = Generation(selection_id=selection.id, provider=provider, model=model,
                     prompt_version=PROMPT_VERSION, status="ok" if not errors else "fallback_after_error",
                     output_json={"test_cases": cases}, validation_errors=errors)
    db.add(gen); db.flush()
    for item in selection.items:
        db.add(GenerationSource(generation_id=gen.id, selection_item_id=item.id))
    db.commit(); db.refresh(gen)
    return generation_payload(gen, db, reused=False)

def generation_payload(gen: Generation, db: Session, reused=False):
    selection = db.get(Selection, gen.selection_id)
    stale = []
    for item in selection.items:
        version = db.get(DocumentVersion, item.version_id)
        doc = db.get(Document, version.document_id)
        latest = get_latest_version(db, doc)
        current = db.scalar(select(DocumentNode).where(DocumentNode.version_id == latest.id,
                                                        DocumentNode.logical_key == item.logical_key)) if latest else None
        stale.append({"logical_key": item.logical_key, "source_version": version.version_number,
                      "current_version": latest.version_number if latest else None,
                      "stale": current is None or current.content_hash != item.content_hash,
                      "current_node_id": current.id if current else None})
    return {"generation_id": gen.id, "selection_id": gen.selection_id, "provider": gen.provider,
            "model": gen.model, "status": gen.status, "reused_existing_generation": reused,
            "test_cases": gen.output_json.get("test_cases", []), "validation_errors": gen.validation_errors,
            "traceability": stale, "is_stale": any(x["stale"] for x in stale)}

@app.get("/generations/{generation_id}")
def get_generation(generation_id: int, db: Session = Depends(get_db)):
    gen = db.get(Generation, generation_id)
    if not gen: raise HTTPException(404, "Generation not found")
    return generation_payload(gen, db)

@app.get("/generations")
def retrieve_generations(selection_id: int | None = None, node_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(Generation)
    if selection_id is not None: stmt = stmt.where(Generation.selection_id == selection_id)
    gens = db.scalars(stmt.order_by(Generation.id.desc()).limit(100)).all()
    if node_id is not None:
        gens = [g for g in gens if any(src.selection_item.node_id == node_id
                  for src in db.scalars(select(GenerationSource).where(GenerationSource.generation_id == g.id)).all())]
    return [generation_payload(g, db) for g in gens]

@app.get("/documents/{document_id}/compare")
def compare_versions(document_id: int, from_version: int = 1, to_version: int = 2, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc: raise HTTPException(404, "Document not found")
    oldv = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == document_id,
                                                    DocumentVersion.version_number == from_version))
    newv = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == document_id,
                                                    DocumentVersion.version_number == to_version))
    if not oldv or not newv: raise HTTPException(404, "Requested versions not found")
    oldnodes = db.scalars(select(DocumentNode).where(DocumentNode.version_id == oldv.id)).all()
    newnodes = db.scalars(select(DocumentNode).where(DocumentNode.version_id == newv.id)).all()
    oldmap = {n.logical_key:n for n in oldnodes}; newmap = {n.logical_key:n for n in newnodes}
    out = []
    for key in sorted(set(oldmap)|set(newmap)):
        a, b = oldmap.get(key), newmap.get(key)
        if a is None: out.append({"logical_key":key,"status":"added","v1_node_id":None,"v2_node_id":b.id,"heading":b.heading})
        elif b is None: out.append({"logical_key":key,"status":"removed","v1_node_id":a.id,"v2_node_id":None,"heading":a.heading})
        elif a.content_hash != b.content_hash:
            out.append({"logical_key":key,"status":"changed","v1_node_id":a.id,"v2_node_id":b.id,
                        "heading":b.heading,"diff":summarize_diff(a.body_text,b.body_text)})
        else: out.append({"logical_key":key,"status":"unchanged","v1_node_id":a.id,"v2_node_id":b.id,"heading":b.heading})
    return {"document":doc.name,"from_version":from_version,"to_version":to_version,
            "summary":{"added":sum(x["status"]=="added" for x in out),
                       "removed":sum(x["status"]=="removed" for x in out),
                       "changed":sum(x["status"]=="changed" for x in out),
                       "unchanged":sum(x["status"]=="unchanged" for x in out)},
            "nodes":out}
