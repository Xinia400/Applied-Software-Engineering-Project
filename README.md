# Applied Software Engineering Project  
## Part 1 — Data Acquisition Pipeline for QDArchive

---

## Overview

This project implements a repository-aware data acquisition pipeline for qualitative research data.

The goal is to:
- search assigned repositories  
- download available qualitative data files  
- store metadata in SQLite  
- organize data into a clean folder structure  
- handle repository-specific limitations intelligently  

---

## Final Submission File

The final validated database is included in this repository:

```bash
23071063-seeding.db
```

This file:
- follows the required naming convention  
- matches the required submission schema  
- passed the official SQ26 validator  

---

## Assigned Repositories

### Repo 5 — DANS
- API-based search and direct file download  
- Dataverse-style backend  

### Repo 15 — ICPSR
- Metadata-based acquisition using DDI XML export  
- No direct dataset download available  

---

## Methods

### DANS
- Uses `/api/search`
- Filters QDA file types:
  ```
  .qdpx, .nvpx, .atlproj, .mx
  ```
- Downloads via:
  ```
  /api/access/datafile/{id}
  ```

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
- fallback study IDs ensure reproducibility  

---

## Why ICPSR Uses XML

ICPSR does not always provide downloadable dataset files.

Instead, it provides structured metadata via DDI XML, which includes:
- study title  
- description  
- methodology  
- structured dataset information  

This is a repository-aware design decision, not a limitation.

---

## System Design

- repository-specific logic  
- fault-tolerant pipeline  
- duplicate prevention  
- structured storage  
- SQLite-based metadata management  

---

## Project Structure

```
Applied-Software-Engineering-Project/
│
├── 23071063-seeding.db  (final submission file)
├── README.md
├── config/
├── data/
├── database/
├── src/
└── ...
```

---

## How to Run

```bash
source .venv/bin/activate
python -m src.main --config config/queries.yaml --limit 50
```

---

## Validation

The database was validated using the official SQ26 validator.

Result:
- 9 checks passed  
- 0 errors  
- 1 minor warning (license naming)  

---

## Findings

- DANS → direct file downloads  
- Zenodo → direct file downloads  
- ICPSR → XML metadata downloads  

All repositories were successfully processed.

---

## Limitations

- DANS may occasionally fail due to network issues  
- ICPSR does not provide direct dataset downloads  
- ICPSR relies on metadata instead of raw files  

---

## Final Remarks

This project demonstrates that different repositories require different acquisition strategies.

Instead of forcing a single method, the system adapts:
- direct download when possible  
- metadata extraction when necessary  

---

## Author

Xinia Apchora  
FAU Erlangen-Nürnberg  
Applied Software Engineering Project