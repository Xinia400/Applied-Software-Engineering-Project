from __future__ import annotations

import re
from typing import Iterable


HIGH_CONFIDENCE_QDA_EXTENSIONS = frozenset(
    {
        "qdpx",
        "qdc",
        "mqda",
        "mqbac",
        "mqtc",
        "mqex",
        "mqmtr",
        "mx24",
        "mx24bac",
        "mc24",
        "mex24",
        "mex22",
        "mx22",
        "mx20",
        "mx18",
        "mx12",
        "mx11",
        "mx5",
        "mx2",
        "m2k",
        "nvp",
        "nvpx",
        "atlasproj",
        "hpr7",
        "pprj",
        "qlt",
        "f4p",
        "qpd",
    }
)

AMBIGUOUS_QDA_EXTENSIONS = frozenset(
    {
        "mod",
        "mx3",
        "mx4",
        "mtr",
        "sea",
        "ppj",
        "loa",
    }
)

QDA_CONTEXT_TERMS = (
    "maxqda",
    "maxquda",
    "max qda",
    "nvivo",
    "atlas.ti",
    "atlas ti",
    "atlasti",
    "qda miner",
    "provalis",
    "refi-qda",
    "quirkos",
    "f4analyse",
    "f4 analyze",
    "qdacity",
    "dedoose",
    "code system",
)

PRIMARY_DATA_EXTENSIONS = frozenset(
    {
        "txt",
        "pdf",
        "rtf",
        "doc",
        "docx",
        "odt",
        "md",
        "html",
        "htm",
        "epub",
        "csv",
        "tsv",
        "tab",
        "xls",
        "xlsx",
        "ods",
        "json",
        "jsonl",
        "xml",
        "wav",
        "mp3",
        "m4a",
        "aac",
        "flac",
        "ogg",
        "mp4",
        "mov",
        "avi",
        "mkv",
        "m4v",
        "jpg",
        "jpeg",
        "png",
        "tif",
        "tiff",
        "gif",
        "bmp",
        "webp",
        "svg",
        "srt",
        "vtt",
    }
)


def extension_from_filename(file_name: object) -> str:
    """Extract a lowercase filename suffix without the leading dot."""
    if file_name is None:
        return ""

    name = str(file_name).strip().lower()

    if not name:
        return ""

    name = name.split("?", 1)[0].split("#", 1)[0]
    name = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]

    match = re.search(r"\.([a-z0-9]{1,15})$", name)
    return match.group(1) if match else ""


def normalize_context(parts: Iterable[object]) -> str:
    """Combine filename and project metadata for evidence matching."""
    return " ".join(
        str(part).lower()
        for part in parts
        if part is not None
    )


def matched_qda_terms(context: str) -> tuple[str, ...]:
    """Return all known QDA software indicators found in context."""
    return tuple(
        term
        for term in QDA_CONTEXT_TERMS
        if term in context
    )


def is_primary_data_extension(extension: str) -> bool:
    return extension in PRIMARY_DATA_EXTENSIONS
