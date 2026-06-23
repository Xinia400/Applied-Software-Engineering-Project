PRAGMA foreign_keys = OFF;

DROP TABLE IF EXISTS PROJECTS;
DROP TABLE IF EXISTS FILES;
DROP TABLE IF EXISTS KEYWORDS;
DROP TABLE IF EXISTS PERSON_ROLE;
DROP TABLE IF EXISTS LICENSES;

CREATE TABLE PROJECTS (
    id INTEGER PRIMARY KEY,
    query_string TEXT,
    repository_id INTEGER NOT NULL,
    repository_url TEXT NOT NULL,
    project_url TEXT NOT NULL,
    version TEXT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    language TEXT,
    doi TEXT,
    upload_date TEXT,
    download_date TEXT NOT NULL,
    download_repository_folder TEXT NOT NULL,
    download_project_folder TEXT NOT NULL,
    download_version_folder TEXT,
    download_method TEXT NOT NULL
);

CREATE TABLE FILES (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    file_name TEXT NOT NULL,
    file_type TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE KEYWORDS (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    keyword TEXT NOT NULL
);

CREATE TABLE PERSON_ROLE (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL
);

CREATE TABLE LICENSES (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    license TEXT NOT NULL
);

INSERT INTO PROJECTS (
    repository_id,
    repository_url,
    project_url,
    version,
    title,
    description,
    language,
    doi,
    upload_date,
    download_date,
    download_repository_folder,
    download_project_folder,
    download_version_folder,
    download_method
)
SELECT DISTINCT
    CASE
        WHEN lower(repository) = 'dans' THEN 5
        WHEN lower(repository) = 'icpsr' THEN 15
        WHEN lower(repository) = 'zenodo' THEN 99
        ELSE 0
    END AS repository_id,
    CASE
        WHEN lower(repository) = 'dans' THEN 'https://dans.knaw.nl/en/'
        WHEN lower(repository) = 'icpsr' THEN 'https://icpsr.umich.edu/'
        WHEN lower(repository) = 'zenodo' THEN 'https://zenodo.org/'
        ELSE ''
    END AS repository_url,
    COALESCE(dataset_url, qda_url) AS project_url,
    NULL AS version,
    COALESCE(title, local_qda_filename, COALESCE(dataset_url, qda_url)) AS title,
    COALESCE(description, '') AS description,
    NULL AS language,
    CASE
        WHEN doi IS NULL OR trim(doi) = '' THEN NULL
        WHEN lower(doi) LIKE 'http%' THEN doi
        ELSE 'https://doi.org/' || doi
    END AS doi,
    NULL AS upload_date,
    download_timestamp AS download_date,
    lower(repository) AS download_repository_folder,
    CASE
        WHEN instr(local_directory, 'data/raw/' || lower(repository) || '/') > 0
            THEN replace(local_directory, 'data/raw/' || lower(repository) || '/', '')
        ELSE local_directory
    END AS download_project_folder,
    NULL AS download_version_folder,
    'API-CALL' AS download_method
FROM qda_files;

INSERT INTO FILES (
    project_id,
    file_name,
    file_type,
    status
)
SELECT
    p.id,
    q.local_qda_filename,
    CASE
        WHEN q.file_type IS NOT NULL AND trim(q.file_type) <> '' THEN lower(q.file_type)
        WHEN instr(q.local_qda_filename, '.') > 0 THEN lower(substr(q.local_qda_filename, instr(q.local_qda_filename, '.') + 1))
        ELSE 'unknown'
    END AS file_type,
    CASE
        WHEN upper(COALESCE(q.download_status, '')) IN ('OK', 'SUCCEEDED') THEN 'SUCCEEDED'
        WHEN lower(COALESCE(q.error_message, '')) LIKE '%login%' THEN 'FAILED_LOGIN_REQUIRED'
        WHEN lower(COALESCE(q.error_message, '')) LIKE '%too large%' THEN 'FAILED_TOO_LARGE'
        WHEN lower(COALESCE(q.error_message, '')) LIKE '%large%' THEN 'FAILED_TOO_LARGE'
        ELSE 'FAILED_SERVER_UNRESPONSIVE'
    END AS status
FROM qda_files q
JOIN PROJECTS p
  ON p.project_url = COALESCE(q.dataset_url, q.qda_url);

INSERT INTO PERSON_ROLE (
    project_id,
    name,
    role
)
SELECT DISTINCT
    p.id,
    q.uploader_name,
    'UPLOADER'
FROM qda_files q
JOIN PROJECTS p
  ON p.project_url = COALESCE(q.dataset_url, q.qda_url)
WHERE q.uploader_name IS NOT NULL
  AND trim(q.uploader_name) <> '';

INSERT INTO LICENSES (
    project_id,
    license
)
SELECT DISTINCT
    p.id,
    q.license
FROM qda_files q
JOIN PROJECTS p
  ON p.project_url = COALESCE(q.dataset_url, q.qda_url)
WHERE q.license IS NOT NULL
  AND trim(q.license) <> '';

DROP TABLE IF EXISTS qda_files;

PRAGMA foreign_keys = ON;
