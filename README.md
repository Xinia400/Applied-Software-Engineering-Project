# Applied Software Engineering Project — QDArchive

![Status](https://img.shields.io/badge/status-completed-success)
![Part%201](https://img.shields.io/badge/Part%201-data%20acquisition-blue)
![Part%202](https://img.shields.io/badge/Part%202-classification%20%26%20deduplication-purple)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![SQLite](https://img.shields.io/badge/database-SQLite-lightgrey)

## Overview

QDArchive is a repository-aware software engineering project for qualitative research data.

The implementation covers the following workflow:

1. qualitative-data acquisition from assigned repositories;
2. SQLite metadata storage;
3. multi-source staging for development and evaluation;
4. project-type classification;
5. ISIC Rev. 5 classification;
6. QDPX primary-file analysis;
7. provenance-preserving duplicate resolution;
8. drift monitoring and quality assurance;
9. generation of SQLite, XLSX, and PDF submission outputs.

| Part | Objective |
|---|---|
| Part 1 | Acquire qualitative research data and metadata from assigned repositories |
| Part 2 | Classify, deduplicate, validate, and report the acquired data |

---

# Part 1 — Data Acquisition Pipeline

## Assigned repositories

| Repository ID | Repository | Acquisition approach |
|---:|---|---|
| 5 | DANS | API search and direct file download where available |
| 15 | ICPSR | Metadata acquisition using DDI XML exports |

Zenodo was used during early pipeline development and testing. The final assigned-repository scope is DANS and ICPSR.

## DANS acquisition

The DANS pipeline supports:

- API-based search;
- qualitative-data extension filtering;
- direct file download where access is available;
- local storage of QDPX archives for later primary-file analysis.

Relevant QDA-oriented extensions include:

~~~~text
.qdpx
.nvpx
.atlproj
.mx
~~~~

## ICPSR acquisition

Direct automated dataset download from ICPSR is not consistently available because of repository restrictions, dynamic pages, and authentication requirements.

The pipeline therefore uses structured DDI XML metadata where appropriate. This preserves reproducibility and captures available study-level metadata, including title, description, methodology context, and dataset information.

## Part 1 delivery database

~~~~text
23071063-seeding.db
~~~~

The Part 1 submission database contains the required SQ26 tables:

~~~~text
PROJECTS
FILES
KEYWORDS
PERSON_ROLE
LICENSES
~~~~

---

# Part 2 — Classification, Deduplication, and Reporting

> **Scope note:** `data/staging/qdarchive_x_staging.db` is an internal multi-source development and evaluation workspace. The official submitted Part 2 delivery database is `23071063-sq26-classification.db`, which contains only MY_CORE repositories 5 (DANS) and 15 (ICPSR).

## Internal multi-source staging corpus

Peer-shared databases and MY_CORE data are normalized into:

~~~~text
data/staging/qdarchive_x_staging.db
~~~~

The staging database preserves:

- source database IDs;
- source project IDs;
- repository IDs;
- source scope;
- available metadata;
- raw source payloads;
- import and provenance information.

| Scope | Registered databases | Raw staged projects |
|---|---:|---:|
| PEER_SHARED | 43 | 174,875 |
| MY_CORE | 1 | 16 |
| **Total** | **44** | **174,891** |

Raw staging records remain preserved for provenance and reproducibility.

## Project-type classification

Each project is classified into one of the required categories:

~~~~text
QDA_PROJECT
QD_PROJECT
OTHER_PROJECT
NOT_A_PROJECT
~~~~

### Full staging corpus

| Project type | Count |
|---|---:|
| QD_PROJECT | 131,532 |
| OTHER_PROJECT | 33,413 |
| NOT_A_PROJECT | 9,296 |
| QDA_PROJECT | 650 |

### Official delivery scope

| Repository | QDA_PROJECT | QD_PROJECT | OTHER_PROJECT | NOT_A_PROJECT |
|---|---:|---:|---:|---:|
| DANS (5) | 4 | 0 | 0 | 0 |
| ICPSR (15) | 0 | 0 | 5 | 0 |
| **Total** | **4** | **0** | **5** | **0** |

---

# Extra Engineering Task 1 — Provenance-Preserving Deduplication

## Objective

The internal staging corpus may contain repeated records from different source databases. This project therefore implements a provenance-preserving deduplication system.

The system does not delete, overwrite, or merge raw staging records. Instead, it creates a separate derived analysis layer in which high-confidence duplicate records are excluded while raw records remain preserved and traceable.

## Architecture

Duplicate handling uses two layers.

### Layer 1 — Candidate duplicate registry

Candidate duplicate clusters are created using deterministic evidence such as:

- canonical DOI extraction;
- normalized non-generic titles;
- source-granularity profiles;
- cross-source links;
- cross-student links;
- canonical-record references.

### Layer 2 — Derived deduplicated analysis layer

High-confidence duplicate records are excluded only from the derived analysis layer.

Each duplicate decision retains:

- canonical-record reference;
- evidence and confidence information;
- source-scope provenance;
- audit metadata;
- decision tags.

A record is excluded only when it satisfies:

~~~~text
same valid DOI
same punctuation-insensitive normalized title
DATASET_LIKE source profile
high-confidence duplicate cluster
~~~~

## Deduplication results

| Metric | Result |
|---|---:|
| Raw staged projects | 174,891 |
| High-confidence duplicate clusters | 56,164 |
| Candidate cluster members | 119,917 |
| High-confidence duplicate records excluded from derived analysis | 63,753 |
| Projects retained in derived analysis layer | 111,138 |
| MY_CORE records excluded | 0 |
| MY_CORE records retained | 16 |
| PEER_SHARED records retained | 111,122 |

## Deduplication policy

- Raw source records are never deleted.
- Duplicate exclusion is non-destructive.
- Exclusion affects only the derived analysis layer.
- Every excluded record has one canonical replacement.
- Ambiguous cases remain retained for review.
- The official MY_CORE delivery database is not modified by duplicate exclusion.

## Deduplication tags

~~~~text
CONFIRMED_DUPLICATE
EXACT_IDENTIFIER_DUPLICATE
CANONICAL_RECORD
EXCLUDED_FROM_DEDUPLICATED_ANALYSIS
AMBIGUOUS_DUPLICATE_REVIEW
UNIQUE_RECORD
RETAINED_IN_ANALYSIS
~~~~

## Deduplication tables

~~~~text
source_granularity_profiles
duplicate_clusters
duplicate_cluster_members
deduplication_runs
deduplication_decisions
deduplication_audit
deduplicated_projects
deduplication_project_tags
~~~~

---

# ISIC Rev. 5 Classification

The project uses transparent deterministic rule-based classification at ISIC Rev. 5 division level. No machine-learning model was trained.

## Tier 1 — Available metadata classification

Tier 1 uses available metadata:

- title;
- description;
- repository metadata;
- project context;
- QDPX project metadata;
- keywords where available.

For the final MY_CORE delivery scope, no keyword records were available in the acquisition data. Therefore, keyword evidence was not used for the four final ISIC-classified projects.

## Tier 2 — Primary-file content classification

For eligible QDPX projects, the pipeline extracts bounded evidence from embedded:

~~~~text
TXT files
PDF files
~~~~

The pipeline uses direct primary-file evidence where available and documented project-context fallback when direct evidence is insufficient.

Raw extracted text is not stored in the official delivery database.

## QD-project clarification

No eligible `QD_PROJECT` existed in the final MY_CORE ISIC classification scope.

Therefore, a QD-specific ISIC run was not applicable for the official final delivery. The same classification pipeline can process eligible QD projects when such data is available.

---

# Official Part 2 Delivery Results

## Official delivery database

~~~~text
23071063-sq26-classification.db
~~~~

The official delivery database contains exactly 9 projects from MY_CORE repositories 5 and 15.

## Required database tables

~~~~text
PROJECTS
FILES
KEYWORDS
PERSON_ROLE
LICENSES
PROJECT_TYPE_CLASSIFICATIONS
ISIC_PROJECT_CLASSIFICATIONS
ISIC_FILE_CLASSIFICATIONS
delivery_metadata
~~~~

`KEYWORDS`, `PERSON_ROLE`, and `LICENSES` correctly contain zero rows for the official MY_CORE delivery because those metadata records were unavailable in both acquisition and staging sources. The pipeline does not invent unavailable metadata.

## Repository-level results

| Repository | Total projects | Eligible QDA projects | Primary files |
|---|---:|---:|---:|
| DANS (5) | 4 | 4 | 507 |
| ICPSR (15) | 5 | 0 | 0 |
| **Total** | **9** | **4** | **507** |

## Project-level ISIC results

| ISIC division | Class | Projects |
|---|---|---:|
| N69 | Legal and accounting activities | 3 |
| N72 | Scientific research and development | 1 |

## Primary-file ISIC results

| ISIC division | Class | Primary files |
|---|---|---:|
| N69 | Legal and accounting activities | 499 |
| N72 | Scientific research and development | 8 |

The final classified activities belong to ISIC section `M` — Professional, scientific and technical activities.

## Repository 15 — ICPSR zero-result interpretation

Repository 15 contains five `OTHER_PROJECT` metadata records.

~~~~text
Eligible QDA projects: 0
Primary files: 0
Primary-class histogram: not applicable
Top-20 class ranking: no classes available
ISIC classification: not applicable
~~~~

No ICPSR record is falsely assigned an ISIC class.

---

# Extra Engineering Task 2 — Automation and Quality Assurance

> The following monitoring and quality-assurance mechanisms are engineering extensions beyond the mandatory Part 2 deliverables. They support reproducibility, auditability, and controlled release generation.

## Deduplication drift monitor

The deduplication drift monitor detects changes in:

- staging input fingerprint;
- duplicate-resolution version;
- canonical project decisions;
- excluded duplicate counts;
- derived analysis corpus size;
- MY_CORE and PEER_SHARED scope results.

Run:

~~~~bash
python -m scripts.run_deduplication_drift_monitor \
  --staging-db data/staging/qdarchive_x_staging.db \
  --snapshot-dir .automation/deduplication_drift \
  --report-output reports/deduplication_drift_report.json
~~~~

## Deduplication quality gate

The deduplication quality gate validates:

- SQLite integrity and foreign keys;
- required deduplication tables;
- decision coverage for every raw project;
- analysis-layer coverage for every raw project;
- count conservation;
- canonical replacement for every excluded duplicate;
- audit coverage;
- tag coverage;
- MY_CORE duplicate impact;
- consistency with the deduplication drift report.

Run:

~~~~bash
python -m scripts.run_deduplication_quality_gate \
  --staging-db data/staging/qdarchive_x_staging.db \
  --drift-report reports/deduplication_drift_report.json \
  --require-drift-report \
  --report-output reports/deduplication_quality_gate.json
~~~~

## Official delivery automation

The project also includes official delivery automation for:

- delivery drift monitoring;
- QDPX archive and manifest monitoring;
- project and primary-file classification validation;
- ISIC distribution validation;
- official release quality validation.

---

# Submission Artifacts

## Part 1 database

~~~~text
23071063-seeding.db
~~~~

## Part 2 official database

~~~~text
23071063-sq26-classification.db
~~~~

## Required XLSX output

~~~~text
reports/23071063-sq26-classification.xlsx
~~~~

Required columns:

~~~~text
repository_id
project_type
project_title
primary_class
secondary_class
no_project_files
~~~~

## PDF report

~~~~text
reports/23071063-sq26-classification-report.pdf
~~~~

The PDF report documents:

- repository-level project-type classification;
- project-level ISIC classification;
- primary-file ISIC classification;
- primary-class histograms;
- ranked class tables;
- methodology;
- technical data challenges;
- limitations;
- reproducibility;
- deduplication and automation extensions.

Regenerate and verify the XLSX and PDF against the official delivery database before creating the final release tag.

---

# Important Scripts

~~~~text
scripts/build_deduplication_registry.py
scripts/run_deduplication_resolution.py
scripts/run_deduplication_drift_monitor.py
scripts/run_deduplication_quality_gate.py
scripts/classify_project_types.py
scripts/classify_official_isic.py
scripts/materialize_sq26_classification_delivery.py
scripts/generate_part2_deliverables.py
~~~~

---

# Validation

Run all tests:

~~~~bash
python -m pytest -q
~~~~

Verify the official delivery database:

~~~~bash
sqlite3 23071063-sq26-classification.db "PRAGMA integrity_check;"
sqlite3 23071063-sq26-classification.db "PRAGMA foreign_key_check;"
~~~~

Run deduplication validation:

~~~~bash
python -m scripts.run_deduplication_quality_gate \
  --staging-db data/staging/qdarchive_x_staging.db \
  --drift-report reports/deduplication_drift_report.json \
  --require-drift-report \
  --report-output reports/deduplication_quality_gate.json
~~~~

---

# Project Structure

~~~~text
Applied-Software-Engineering-Project/
├── 23071063-seeding.db
├── 23071063-sq26-classification.db
├── README.md
├── requirements.txt
├── requirements-part2.txt
├── data/
│   ├── raw/
│   ├── staging/
│   │   └── qdarchive_x_staging.db
│   └── private/
│       └── backups/
├── reports/
│   ├── 23071063-sq26-classification.xlsx
│   ├── 23071063-sq26-classification-report.pdf
│   ├── deduplication_resolution_summary.json
│   ├── deduplication_drift_report.json
│   └── deduplication_quality_gate.json
├── scripts/
├── src/
│   ├── acquisition/
│   ├── automation/
│   ├── classification/
│   └── metadata/
└── tests/
~~~~

---

# Engineering Principles

- repository-aware acquisition;
- provenance-preserving staging;
- deterministic rule-based classification;
- evidence-based duplicate resolution;
- non-destructive duplicate exclusion from the derived analysis layer only;
- auditable SQLite decisions and tags;
- automated drift monitoring;
- quality gates before release;
- reproducible outputs.

---

# Author

Xinia Apchora  
FAU Erlangen-Nürnberg  
Applied Software Engineering Project
