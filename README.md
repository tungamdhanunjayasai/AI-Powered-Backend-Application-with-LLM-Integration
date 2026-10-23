AI-Powered Backend Application with LLM Integration

A FastAPI-based backend for extracting structured hierarchy data from
PDF documents, managing immutable document versions, detecting changes
between versions, and generating question-and-answer content with an LLM
integration and an offline fallback.

Overview

This project demonstrates backend API development and
document-processing workflows for the CT-200 assignment. It processes
PDF manuals into a searchable hierarchy, preserves document versions,
compares versions to identify changes, and supports version-pinned
selections and question generation.

Key Features

PDF hierarchy extraction: Extracts structured content from PDF
manuals.

Document versioning: Stores versions as immutable snapshots
rather than overwriting earlier versions.

Change detection: Compares document versions and identifies
unchanged, changed, added, and removed hierarchy items.

Browse and search APIs: Supports navigating and searching
extracted document content.

Version-pinned selections: Allows selections to remain
associated with the document version from which they were made.

LLM-assisted Q&A generation: Generates question-and-answer
content using the configured model integration when available.

Offline fallback: Provides a fallback path so the workflow can
still be exercised when an LLM service is not configured or
unavailable.

Staleness detection: Helps identify selections or generated
content that may need review after a document update.

Automated tests: Includes tests for core application behavior.

Technology Stack

Language: Python

Backend framework: FastAPI

Data validation: Pydantic

ORM / persistence: SQLAlchemy

Database: SQLite

PDF processing: PyMuPDF

API documentation: OpenAPI / Swagger UI

Testing: pytest

The actual LLM provider and model depend on the configuration used in
your environment. Do not add a provider name unless it is configured
in the project.

Project Structure

tri9t_ct200_assignment/
├── app/                 # FastAPI application and backend logic
├── data/                # Local data and document-related files
├── docs/                # Supporting documentation
├── tests/               # Automated tests
├── .env.example         # Example environment configuration
├── requirements.txt     # Python dependencies
└── README.md            # Project documentation

The exact files inside each directory may vary by project revision.

Getting Started

1. Prerequisites

Python 3.10 or later recommended

pip

A terminal or command prompt

2. Open the project directory

Change into the project folder that contains requirements.txt:

cd tri9t_ct200_assignment

If the folder is inside a downloaded ZIP, extract the ZIP first and
navigate into the inner project directory.

3. Create and activate a virtual environment

Windows (PowerShell):

python -m venv .venv
.\.venv\Scripts\Activate.ps1

Windows (Command Prompt):

python -m venv .venv
.venv\Scripts\activate

macOS / Linux:

python3 -m venv .venv
source .venv/bin/activate

4. Install dependencies

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

5. Configure environment variables

If the project uses an external LLM provider, copy .env.example to
.env and fill in only the variables required by the provider
configured in the code.

Windows:

Copy-Item .env.example .env

macOS / Linux:

cp .env.example .env

Keep API keys private. Do not commit .env or secrets to GitHub. If no
LLM credentials are configured, use the supported offline fallback if
available.

6. Run the API

From the directory containing the app folder, run:

python -m uvicorn app.main:app --reload

The development server should be available at:

API base: http://127.0.0.1:8000

Swagger UI: http://127.0.0.1:8000/docs

ReDoc: http://127.0.0.1:8000/redoc

Health endpoint: http://127.0.0.1:8000/health

The endpoints above assume the application uses the default Uvicorn port
and the health route documented in this project.

Testing

Run the automated tests from the project root:

python -m pytest -v

The latest run recorded during development passed 7 tests. Run the
test suite locally to verify the current checkout.

Typical Workflow

Load or process a source PDF.

Extract its structured hierarchy.

Store the extracted content as a document version.

Browse or search the hierarchy through the API.

Create a later version when the source document changes.

Compare versions to review added, removed, changed, and unchanged
items.

Generate Q&A content and review whether it is associated with the
correct document version.

Check for stale selections or content after a version update.

The exact request bodies and endpoint paths are defined by the running
API and can be explored through Swagger UI at /docs.

Engineering Considerations

Earlier document versions should remain available for reliable
comparison and traceability.

LLM-generated content should be reviewed for correctness before
being used in production.

External model calls can fail or be rate-limited; error handling and
the offline fallback improve development resilience.

For production deployment, configure authentication, request
validation, logging, database backups, rate limits, and secret
management.

SQLite is suitable for local development and demonstrations; a
multi-user production deployment may require a managed database.

Current Limitations and Next Improvements

The next improvements would be to strengthen integration tests around
external LLM failures, expand API error handling, and add more robust
observability. Further enhancements could include richer retrieval
strategies for RAG, configurable model providers, and
authentication/authorization for protected endpoints.


GitHub:
tungamdhanunjayasai-27138

This project is intended as an academic and portfolio demonstration of
Python backend engineering, document processing, version management, and
LLM-assisted workflows.
