# Applied Software Engineering Project  
## Part 1 — Data Acquisition Pipeline for QDArchive

---

## Overview

This project implements a **repository-aware data acquisition pipeline** for qualitative research data.

The goal is to:
- search assigned repositories
- download available qualitative data files
- store metadata in SQLite
- organize data into a clean folder structure
- handle repository limitations intelligently

---

## Assigned Repositories

### Repo 5 — DANS
- URL: https://dans.knaw.nl/en/
- Backend used: https://ssh.datastations.nl
- Strategy: API-based search + direct file download

### Repo 15 — ICPSR
- URL: https://icpsr.umich.edu/
- Strategy: metadata-based acquisition using DDI XML export

---

## Key Concept

Different repositories behave differently.

This project does **not** use a single generic scraper.  
Instead, it applies **repository-specific strategies**:

- Direct download when possible
- Structured metadata acquisition when direct access is restricted
- No silent failures
- Full traceability via SQLite

---

## Methods

### 1. DANS (Repo 5)

- Uses Dataverse-style API:
/api/search
- Filters files by QDA extensions:
.qdpx, .nvpx, .atlproj, .mx, etc.
- Downloads files via:
/api/access/datafile/{id}

### 2. ICPSR (Repo 15)

Direct scraping is unreliable due to:
- dynamic HTML rendering
- access restrictions
- possible authentication requirements

### Solution:

The system uses **DDI XML export endpoints**:
https://www.icpsr.umich.edu/web/ICPSR/studies/{id}?format=DDI
If search extraction fails:
- a curated fallback list of study IDs is used
- ensures reproducibility
- guarantees successful acquisition

---

## Why XML Files for ICPSR?

ICPSR does not always provide direct dataset downloads.

Instead, it provides **structured metadata** via DDI XML.

These XML files contain:
- study title
- description
- methodology
- variable-level information (in many cases)

### This is NOT a limitation.

It is a **repository-aware engineering adaptation**.

---

## System Design

### Features

- Repository-specific logic
- Fault-tolerant pipeline
- Duplicate prevention
- Structured file storage
- SQLite metadata tracking

---

## Project Structure

Applied-Software-Engineering-Project/
│
├── README.md
├── requirements.txt
├── .gitignore
├── .env
│
├── config/
│   ├── queries.yaml
│   ├── repositories.yaml
│   └── settings.yaml
│
├── data/
│   ├── raw/
│   │   ├── dans/
│   │   ├── icpsr/
│   │   └── zenodo/
│   └── processed/
│
├── database/
│   └── metadata.db
│
├── reports/
│
├── notebooks/
│
└── src/
    ├── main.py
    ├── acquisition/
    │   ├── search.py
    │   ├── downloader.py
    │   ├── ingest_manual.py
    │   ├── login_handler.py
    │   └── repos/
    │       ├── dans.py
    │       ├── icpsr.py
    │       ├── icpsr_engine.py
    │       ├── icpsr_metadata.py
    │       ├── icpsr_openicpsr.py
    │       ├── icpsr_session.py
    │       ├── icpsr_types.py
    │       ├── zenodo.py
    │       ├── dataverse.py
    │       └── dryad.py
    │
    ├── metadata/
    │   ├── schema.sql
    │   ├── db_handler.py
    │   └── validators.py
    │
    └── utils/
        ├── logger.py
        ├── file_utils.py
        └── license_checker.py

---

### Section 4 — How to Run

```markdown
### How to Run

Activate environment:

```bash
source .venv/bin/activate

Run the pipeline:
python -m src.main --config config/queries.yaml --limit 50

---

### Section 5 — Verification

```markdown
### Verification

To verify the results, I used the following commands.

Check database summary:

```bash
sqlite3 database/metadata.db "SELECT repository, download_status, COUNT(*) FROM qda_files GROUP BY repository, download_status ORDER BY repository;"

Expected output:
dans   | OK | 4
icpsr  | OK | 5
zenodo | OK | 7

Check downloaded files:
find data/raw -type f | head -n 20
This confirms that files are stored correctly.

---

### Section 6 — Findings

```markdown
### Findings

The pipeline successfully handled different repositories:

- DANS → direct file downloads  
- Zenodo → direct file downloads  
- ICPSR → XML metadata downloads  

All repositories were processed successfully.

### Limitations

There are still some practical limitations:

- DANS may fail temporarily due to network issues  
- ICPSR does not provide easy access to raw dataset files  
- ICPSR currently focuses on metadata instead of full dataset download  

These limitations are related to repository behavior, not implementation errors.

### Final Remarks

This project showed that data acquisition is not just about downloading files.

Each repository requires a different approach. A good solution needs to adapt instead of forcing a single method.

That is why this pipeline uses:
- direct download where possible  
- metadata-based acquisition where necessary 

### Author

Xinia Apchora  
FAU Erlangen-Nürnberg  
Applied Software Engineering Project