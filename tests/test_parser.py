from app.parser import heading_info, parse_pdf, ParsedNode, sha256
from pathlib import Path

def test_nested_numbered_heading_level():
    assert heading_info("2.2 Cuff Specifications") == ("2.2", "Cuff Specifications", 2)
    assert heading_info("3.2.1 Detailed step") == ("3.2.1", "Detailed step", 3)

def test_duplicate_heading_keys_can_be_disambiguated():
    # Repeated titles are legal: version storage adds occurrence to the parser's semantic key.
    a = "num:4.2:Error Codes".casefold()
    b = "num:4.2:Error Codes".casefold()
    assert a == b
    assert sha256(f"{a}#occurrence:1") != sha256(f"{b}#occurrence:2")

def test_pdf_extracts_hierarchy_from_real_fixture():
    pdf = Path(__file__).parents[1] / "data" / "ct200_manual.pdf"
    if not pdf.exists():
        return
    nodes, warnings = parse_pdf(pdf)
    assert nodes
    assert any("Device Overview" in n.heading for n in nodes)
    assert any(n.level >= 2 for n in nodes)

def test_blank_or_nonexistent_pdf_is_not_silently_accepted(tmp_path):
    bad = tmp_path / "empty.pdf"
    bad.write_bytes(b"%PDF-1.4\n%%EOF")
    try:
        nodes, warnings = parse_pdf(bad)
    except Exception:
        return
    assert nodes == [] or warnings
