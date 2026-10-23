from pathlib import Path

def test_health(client):
    assert client.get("/health").json()["status"] == "ok"

def test_ingest_v1_v2_and_compare(client):
    root = Path(__file__).parents[1] / "data"
    v1, v2 = root / "ct200_manual.pdf", root / "ct200_manual_v2.pdf"
    if not (v1.exists() and v2.exists()):
        return
    r1 = client.post("/documents/ingest-path", params={"path": str(v1), "version_number": 1})
    assert r1.status_code == 200, r1.text
    r2 = client.post("/documents/ingest-path", params={"path": str(v2), "version_number": 2})
    assert r2.status_code == 200, r2.text
    did = r1.json()["document_id"]
    assert client.get(f"/documents/{did}/versions").status_code == 200
    comparison = client.get(f"/documents/{did}/compare", params={"from_version": 1, "to_version": 2})
    assert comparison.status_code == 200
    assert comparison.json()["summary"]["changed"] >= 1

def test_selection_is_version_pinned(client):
    root = Path(__file__).parents[1] / "data" / "ct200_manual.pdf"
    if not root.exists(): return
    ing = client.post("/documents/ingest-path", params={"path": str(root), "version_number": 1}).json()
    nodes = client.get("/nodes", params={"version_id": ing["version_id"]}).json()
    assert nodes
    selected = client.post("/selections", json={"name":"test-selection", "node_ids":[nodes[0]["id"]]})
    assert selected.status_code == 200
    snapshot = client.get(f"/selections/{selected.json()['selection_id']}").json()
    assert snapshot["items"][0]["version_number"] == 1
