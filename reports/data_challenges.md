# Data Challenges Report

## Overview

This report documents data-related challenges in the QDArchive acquisition and classification workflow. It focuses on repository metadata, licences, QDPX file structures, access conditions, duplicates, and classification evidence.

## Heterogeneous Metadata

DANS and ICPSR provide different levels of metadata. DANS provided downloadable QDPX files, while important parent-dataset information such as DOI and licence was not always available in the initially acquired file-level metadata. ICPSR provided study-level metadata, but no eligible QDA/QD project archives or primary files were available in the final scope.

Missing metadata was kept unavailable rather than guessed or invented.

## Licence Verification

Public download access is not itself evidence of an open licence. The four final DANS QDPX projects were therefore resolved to their official DANS dataset records and manually verified.

| QDPX project | Dataset DOI | Verified licence | Access |
|---|---|---|---|
| Sensing Risk (bertisum 2020-04-02).qdpx | doi:10.17026/DANS-ZRE-T3HD | CC0-1.0 | Open |
| Prosecution_Appeals_Briefs_V1.qdpx | doi:10.17026/DANS-XWQ-KA6Y | CC-BY-SA-4.0 | Open |
| International_Criminal_Law_Charging_Document_Database_v6.qdpx | doi:10.17026/DANS-ZCC-ZDHP | CC-BY-SA-4.0 | Open |
| International Criminal Law Charging Document Database v7.qdpx | doi:10.17026/DANS-ZCC-ZDHP | CC-BY-SA-4.0 | Open |

All matched QDPX files were marked `restricted: false`. Supporting evidence is available in `reports/dans_license_review.md` and `reports/license_audit.csv`.

## File-Level URLs and Dataset Context

Initial DANS records used direct file-download URLs such as `/api/access/datafile/<file_id>`. These endpoints allow retrieval but do not reliably expose the parent dataset DOI, licence, or terms of access. The final review used DANS search and dataset-level metadata to connect QDPX files with their parent datasets.

## QDPX File Structure

Each final QDPX archive contains primary PDF/TXT content files and one `.qde` project-definition file. The `.qde` file is part of the project archive and must be included in the total file count, but it is not a primary data file and is not suitable for ISIC classification.

| Measure | Count |
|---|---:|
| Total internal QDPX project files | 511 |
| Classified primary files | 507 |
| QDE project-definition files | 4 |

The XLSX field `no_project_files` reports all internal QDPX files. The four QDE files are excluded only from primary-file ISIC classification. Reproducible evidence is available in `reports/qdpx_total_file_manifest.json`.

## ICPSR Scope Limitation

The five final ICPSR studies were classified as `OTHER_PROJECT`. No eligible QDA/QD archive or primary-file set was available. Therefore, their `no_project_files` value is `0` and no unsupported ISIC project or file classification was assigned.

## Duplicate Records

The internal multi-source staging workspace contained duplicate-like records from independently collected metadata. Deduplication used deterministic high-confidence evidence, including canonical DOI and normalized-title matching. Raw source records were preserved; decisions affected derived analysis only.

## Classification Evidence

Classification used available repository metadata, QDPX project metadata, and bounded PDF/TXT primary-file evidence. DANS projects had usable primary-file evidence. ICPSR studies without eligible files were not forcibly classified.

## Third-Party Data Boundary

Raw downloaded third-party data are not distributed through GitHub. Third-party materials remain subject to their original licences, access restrictions, and data-protection conditions. The MIT licence applies only to this project's original source code and documentation.

## Conclusion

The main data challenges were incomplete metadata, distinguishing open access from open licensing, resolving file-level records to dataset-level evidence, separating QDE project-definition files from primary data files, duplicate handling, and avoiding unsupported classifications. The final delivery addresses these issues through verified evidence, reproducible manifests, conservative classification decisions, and clear documentation.