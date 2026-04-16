from __future__ import annotations

from typing import List
from urllib.parse import urljoin, urlencode
import re
import time
import requests
from bs4 import BeautifulSoup

from src.acquisition.repos.icpsr_types import ICPSRRecord


DOWNLOAD_EXTS = (
    ".zip", ".pdf", ".txt", ".rtf",
    ".doc", ".docx", ".csv", ".xlsx",
    ".sav", ".dta", ".rdata", ".rds",
    ".qdpx", ".qdp", ".nvpx", ".nvp",
    ".atlproj", ".mx", ".mx20", ".mx22"
)


def looks_like_download(url: str) -> bool:
    u = (url or "").lower()
    return (
        u.endswith(DOWNLOAD_EXTS)
        or "download" in u
        or "type=file" in u
        or "format=original" in u
    )


def looks_like_metadata_export(text: str, href: str) -> bool:
    t = (text or "").lower()
    h = (href or "").lower()
    return (
        "dublin core" in t
        or "ddi" in t
        or "oai-pmh" in t
        or "metadata" in t
        or "dublincore" in h
        or "ddi" in h
        or "oai" in h
        or "xml" in h
    )


def build_browser_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    return session


def normalize_url(url: str) -> str:
    url = re.sub(r";jsessionid=[^?]+", "", url)
    return url


def search_openicpsr_projects(query: str, max_pages: int = 1) -> List[ICPSRRecord]:
    base_url = "https://www.openicpsr.org"
    out: List[ICPSRRecord] = []
    seen_project_urls = set()
    seen_file_urls = set()

    session = build_browser_session()

    for page in range(1, max_pages + 1):
        search_url = f"{base_url}/openicpsr/search/studies?{urlencode({'q': query})}"

        try:
            time.sleep(1.5)
            r = session.get(search_url, timeout=60)
            r.raise_for_status()

            soup = BeautifulSoup(r.text, "html.parser")
            anchors = soup.find_all("a", href=True)
            project_urls = []

            for a in anchors:
                href = a["href"]

                if "/openicpsr/project/" not in href:
                    continue

                full = href if href.startswith("http") else urljoin(base_url, href)
                full = normalize_url(full)

                if full in seen_project_urls:
                    continue

                seen_project_urls.add(full)
                project_urls.append(full)

            if not project_urls:
                out.append(
                    ICPSRRecord(
                        qda_url=search_url,
                        repository="icpsr",
                        dataset_url=search_url,
                        title=f"openICPSR search query: {query}",
                        license=None,
                        uploader_name=None,
                        uploader_email=None,
                        description="openICPSR search page was reached, but no project links were extracted from static HTML.",
                        doi=None,
                        year=None,
                        filename=None,
                        metadata_only=True,
                        status_hint="NO_PUBLIC_FILE_FOUND",
                        access_class="UNKNOWN",
                        acquisition_mode="PROJECT_PAGE_HARVEST",
                        content_scope="METADATA",
                    )
                )

            for project_url in project_urls:
                try:
                    time.sleep(1.5)
                    pr = session.get(project_url, timeout=60)
                    pr.raise_for_status()

                    psoup = BeautifulSoup(pr.text, "html.parser")
                    page_title = psoup.title.get_text(strip=True) if psoup.title else "openICPSR Project"

                    links = psoup.find_all("a", href=True)
                    file_count = 0
                    metadata_export_count = 0

                    for a in links:
                        href = a["href"]
                        text = a.get_text(" ", strip=True)

                        full = href if href.startswith("http") else urljoin(base_url, href)
                        full = normalize_url(full)

                        if looks_like_download(full):
                            if full not in seen_file_urls:
                                seen_file_urls.add(full)
                                filename = full.split("?")[0].rstrip("/").split("/")[-1] or "openicpsr_file"

                                out.append(
                                    ICPSRRecord(
                                        qda_url=full,
                                        repository="icpsr",
                                        dataset_url=project_url,
                                        title=page_title,
                                        license=None,
                                        uploader_name=None,
                                        uploader_email=None,
                                        description="Public file discovered on openICPSR project page.",
                                        doi=None,
                                        year=None,
                                        filename=filename,
                                        metadata_only=False,
                                        status_hint="OK",
                                        access_class="PUBLIC_DIRECT",
                                        acquisition_mode="PROJECT_PAGE_HARVEST",
                                        content_scope="DATA_FILE",
                                    )
                                )
                                file_count += 1

                        elif looks_like_metadata_export(text, full):
                            filename = full.split("?")[0].rstrip("/").split("/")[-1] or "metadata_export.xml"

                            out.append(
                                ICPSRRecord(
                                    qda_url=full,
                                    repository="icpsr",
                                    dataset_url=project_url,
                                    title=page_title,
                                    license=None,
                                    uploader_name=None,
                                    uploader_email=None,
                                    description=f"Metadata export discovered on openICPSR project page: {text or full}",
                                    doi=None,
                                    year=None,
                                    filename=filename,
                                    metadata_only=False,
                                    status_hint="OK",
                                    access_class="PUBLIC_DIRECT",
                                    acquisition_mode="PROJECT_PAGE_HARVEST",
                                    content_scope="METADATA",
                                )
                            )
                            metadata_export_count += 1

                    if file_count == 0 and metadata_export_count == 0:
                        out.append(
                            ICPSRRecord(
                                qda_url=project_url,
                                repository="icpsr",
                                dataset_url=project_url,
                                title=page_title,
                                license=None,
                                uploader_name=None,
                                uploader_email=None,
                                description="openICPSR project discovered, but no downloadable file or metadata-export link was harvested from static HTML.",
                                doi=None,
                                year=None,
                                filename=None,
                                metadata_only=True,
                                status_hint="NO_PUBLIC_FILE_FOUND",
                                access_class="UNKNOWN",
                                acquisition_mode="PROJECT_PAGE_HARVEST",
                                content_scope="METADATA",
                            )
                        )

                except requests.HTTPError as e:
                    status = e.response.status_code if e.response is not None else None
                    if status == 403:
                        out.append(
                            ICPSRRecord(
                                qda_url=project_url,
                                repository="icpsr",
                                dataset_url=project_url,
                                title="openICPSR Project",
                                license=None,
                                uploader_name=None,
                                uploader_email=None,
                                description="openICPSR project page returned HTTP 403 Forbidden. This suggests anti-bot protection, session requirement, or access restriction.",
                                doi=None,
                                year=None,
                                filename=None,
                                metadata_only=True,
                                status_hint="FAILED",
                                access_class="UNKNOWN",
                                acquisition_mode="PROJECT_PAGE_HARVEST",
                                content_scope="METADATA",
                            )
                        )
                    else:
                        out.append(
                            ICPSRRecord(
                                qda_url=project_url,
                                repository="icpsr",
                                dataset_url=project_url,
                                title="openICPSR Project",
                                license=None,
                                uploader_name=None,
                                uploader_email=None,
                                description=f"Project page inspection failed with HTTP error: {e}",
                                doi=None,
                                year=None,
                                filename=None,
                                metadata_only=True,
                                status_hint="FAILED",
                                access_class="UNKNOWN",
                                acquisition_mode="PROJECT_PAGE_HARVEST",
                                content_scope="METADATA",
                            )
                        )

                except Exception as e:
                    out.append(
                        ICPSRRecord(
                            qda_url=project_url,
                            repository="icpsr",
                            dataset_url=project_url,
                            title="openICPSR Project",
                            license=None,
                            uploader_name=None,
                            uploader_email=None,
                            description=f"Project page inspection failed: {e}",
                            doi=None,
                            year=None,
                            filename=None,
                            metadata_only=True,
                            status_hint="FAILED",
                            access_class="UNKNOWN",
                            acquisition_mode="PROJECT_PAGE_HARVEST",
                            content_scope="METADATA",
                        )
                    )

        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status == 403:
                out.append(
                    ICPSRRecord(
                        qda_url=search_url,
                        repository="icpsr",
                        dataset_url=search_url,
                        title=f"openICPSR search query: {query}",
                        license=None,
                        uploader_name=None,
                        uploader_email=None,
                        description="openICPSR search returned HTTP 403 Forbidden. This suggests anti-bot protection, missing session, or access restriction.",
                        doi=None,
                        year=None,
                        filename=None,
                        metadata_only=True,
                        status_hint="FAILED",
                        access_class="UNKNOWN",
                        acquisition_mode="PROJECT_PAGE_HARVEST",
                        content_scope="METADATA",
                    )
                )
            else:
                out.append(
                    ICPSRRecord(
                        qda_url=search_url,
                        repository="icpsr",
                        dataset_url=search_url,
                        title=f"openICPSR search query: {query}",
                        license=None,
                        uploader_name=None,
                        uploader_email=None,
                        description=f"openICPSR search failed with HTTP error: {e}",
                        doi=None,
                        year=None,
                        filename=None,
                        metadata_only=True,
                        status_hint="FAILED",
                        access_class="UNKNOWN",
                        acquisition_mode="PROJECT_PAGE_HARVEST",
                        content_scope="METADATA",
                    )
                )

        except Exception as e:
            out.append(
                ICPSRRecord(
                    qda_url=search_url,
                    repository="icpsr",
                    dataset_url=search_url,
                    title=f"openICPSR search query: {query}",
                    license=None,
                    uploader_name=None,
                    uploader_email=None,
                    description=f"openICPSR search failed: {e}",
                    doi=None,
                    year=None,
                    filename=None,
                    metadata_only=True,
                    status_hint="FAILED",
                    access_class="UNKNOWN",
                    acquisition_mode="PROJECT_PAGE_HARVEST",
                    content_scope="METADATA",
                )
            )

    return out