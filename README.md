# Applied Software Engineering Project  
## Part 1 — Data Acquisition Pipeline for QDArchive

---

## Overview

This project implements a repository-aware data acquisition pipeline for qualitative research data.

The goal of this part was to:
- search assigned repositories  
- download qualitative data files  
- store metadata in SQLite  
- organize downloaded content  
- handle repository-specific limitations  

Different repositories behave differently, so I implemented repository-specific strategies instead of using a single generic scraper.

---

## Final Submission File

The final validated database is:

```bash
23071063-seeding.db
```

This file:
- follows the required naming convention  
- matches the official SQ26 schema  
- passed the validator successfully  

---

## Assigned Repositories

### Repo 5 — DANS
- API-based search  
- direct file download  

### Repo 15 — ICPSR
- metadata-based acquisition  
- DDI XML export used  

### Additional Repository (Used in Pipeline)
- Zenodo  
- direct download supported  

---

## Methods

### DANS

- Uses:
  ```
  /api/search
  ```
- Filters QDA file types:
  ```
  .qdpx, .nvpx, .atlproj, .mx
  ```
- Downloads via:
  ```
  /api/access/datafile/{id}
  ```

---

### ICPSR

Direct scraping is unreliable due to:
- dynamic pages  
- access restrictions  
- authentication requirements  

Solution:
- use DDI XML export:
  ```
  https://www.icpsr.umich.edu/web/ICPSR/studies/{id}?format=DDI
  ```
- fallback study IDs added  
- ensures reproducibility  

---

### Zenodo

- direct file download  
- metadata stored in SQLite  

---

## Why ICPSR Uses XML

ICPSR does not always allow direct dataset download.

Instead, it provides structured metadata in DDI XML format.

These XML files contain:
- study title  
- description  
- methodology  
- structured dataset information  

This is a repository-aware adaptation, not a limitation.

---

## What I Corrected

### Repository Logic
- replaced generic scraper with repository-specific logic  
- improved ICPSR handling  
- added fallback IDs  

### Robustness
- handled API failures  
- prevented crashes  
- improved duplicate handling  

### Database Fix
- initial DB used custom schema  
- created final submission DB:

```bash
23071063-seeding.db
```

- converted into required tables:
  - PROJECTS  
  - FILES  
  - KEYWORDS  
  - PERSON_ROLE  
  - LICENSES  

---

## Final Results

```
dans   | OK | 4
icpsr  | OK | 5
zenodo | OK | 7
```

All repositories were processed successfully.

---

## Validation

Validator used:

```bash
python sq26-grading/check_submission.py 23071063-seeding.db
```

Result:
- 9 passed  
- 0 errors  
- 1 warning (license naming)  

---

## System Design

- repository-specific logic  
- fault-tolerant pipeline  
- duplicate prevention  
- structured storage  
- SQLite metadata tracking  

---

## Project Structure

```
Applied-Software-Engineering-Project/
│
├── 23071063-seeding.db
├── README.md
├── requirements.txt
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
│   ├── metadata.db
│   └── 23071063-seeding.db
│
├── notebooks/
│
├── reports/
│
├── src/
│   ├── main.py
│   │
│   ├── acquisition/
│   │   ├── search.py
│   │   ├── downloader.py
│   │   ├── ingest_manual.py
│   │   ├── login_handler.py
│   │   │
│   │   └── repos/
│   │       ├── dans.py
│   │       ├── icpsr.py
│   │       ├── icpsr_engine.py
│   │       ├── icpsr_metadata.py
│   │       ├── icpsr_openicpsr.py
│   │       ├── icpsr_session.py
│   │       ├── icpsr_types.py
│   │       ├── zenodo.py
│   │       ├── dataverse.py
│   │       └── dryad.py
│   │
│   ├── metadata/
│   │   ├── schema.sql
│   │   ├── db_handler.py
│   │   └── validators.py
│   │
│   └── utils/
│       ├── logger.py
│       ├── file_utils.py
│       └── license_checker.py
│
└── sq26-grading/
    ├── check_submission.py
    ├── schema-definition/
    ├── tests/
    └── validator/
```

---

## How to Run

```bash
source .venv/bin/activate
python -m src.main --config config/queries.yaml --limit 50
```

---

## How to Verify

```bash
sqlite3 database/23071063-seeding.db "SELECT COUNT(*) FROM PROJECTS;"
```

```bash
find data/raw -type f | head -n 20
```

---

## Limitations

- DANS may fail due to network issues  
- ICPSR does not provide direct dataset download  
- ICPSR relies on metadata extraction  

---

## Final Remarks

This project demonstrates that data acquisition requires different strategies for different repositories.

The pipeline adapts using:
- direct downloads  
- API usage  
- metadata extraction  

---

## Author

Xinia Apchora  
FAU Erlangen-Nürnberg  
Applied Software Engineering Project