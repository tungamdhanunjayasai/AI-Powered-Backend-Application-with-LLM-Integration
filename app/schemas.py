from pydantic import BaseModel, Field, ConfigDict
from typing import Literal

class IngestRequest(BaseModel):
    document_name: str = "CardioTrack CT-200 Home Blood Pressure Monitor"
    source_filename: str | None = None
    version_number: int | None = Field(default=None, ge=1)

class NodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    version_id: int
    logical_key: str
    node_key: str
    parent_id: int | None
    heading: str
    level: int
    node_type: str
    body_text: str
    content_hash: str
    page_start: int | None
    page_end: int | None
    metadata_json: dict

class SelectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    node_ids: list[int] = Field(min_length=1)

class TestCase(BaseModel):
    title: str = Field(min_length=5, max_length=200)
    objective: str = Field(min_length=10)
    preconditions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(min_length=1)
    expected_result: str = Field(min_length=5)
    requirement_refs: list[str] = Field(min_length=1)
    risk: Literal["low", "medium", "high"] = "medium"

class GenerationRequest(BaseModel):
    selection_id: int
    force_new: bool = False

class GenerationOut(BaseModel):
    generation_id: int
    selection_id: int
    provider: str
    model: str
    status: str
    test_cases: list[TestCase]
    validation_errors: list[str]
