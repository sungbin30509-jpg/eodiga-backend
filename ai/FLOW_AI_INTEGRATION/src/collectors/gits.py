"""GITS (Gyeonggi Intelligent Transport System) road-list client.

Scope of this module (deliberately minimal):
- One endpoint only: ``getRoadInfoList``.
- One request parameter only: the service key, passed via ``params``.
- No pagination parameters are inferred or added.

Security rules:
- The API key is obtained only from ``src.config.get_api_key`` and is never
  printed, logged, or embedded in exception messages.
- ``requests`` exceptions are never re-raised or chained, because their string
  form can contain the authenticated request URL. Every failure is converted
  to ``GitsApiError`` with a sanitized message and ``from None``.
- ``response.url`` is never accessed.
- ``contains_secret`` / ``assert_no_secret`` guard any text that is about to
  be displayed.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, quote_plus

import pandas as pd
import requests

from src.config import GITS_API_KEY_NAME, RAW_DIR, get_api_key

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://openapigits.gg.go.kr/api/rest"
ROAD_INFO_LIST_URL = f"{BASE_URL}/getRoadInfoList"
ROAD_LINK_INFO_LIST_URL = f"{BASE_URL}/getRoadLinkInfoList"
# Real-time traffic endpoints, per official manual pages
# (openapigits.gg.go.kr/api/jsp/manual_*.jsp):
#   getRoadLinkTrafficInfoList : params serviceKey, routeId (required)
#   getRoadLinkTrafficInfo     : params serviceKey, linkId  (required)
#   getRoadTrafficInfoList     : params serviceKey, routeId (optional)
ROAD_LINK_TRAFFIC_INFO_LIST_URL = f"{BASE_URL}/getRoadLinkTrafficInfoList"
ROAD_LINK_TRAFFIC_INFO_URL = f"{BASE_URL}/getRoadLinkTrafficInfo"
ROAD_TRAFFIC_INFO_LIST_URL = f"{BASE_URL}/getRoadTrafficInfoList"
DEFAULT_TIMEOUT: tuple[float, float] = (5.0, 30.0)  # (connect, read) seconds
ROAD_LIST_CSV: Path = RAW_DIR / "gits_road_list.csv"

# Tag names (lower-cased, namespace stripped) that indicate a result envelope.
_RESULT_CODE_TAGS = {
    "resultcode", "returncode", "errcode", "errorcode",
    "returnreasoncode", "code", "status", "resultstatus",
    "headercd",   # observed in the real GITS response (<msgHeader><headerCd>)
}
_RESULT_MSG_TAGS = {
    "resultmsg", "resultmessage", "returnmsg", "errmsg", "errormsg",
    "errormessage", "returnauthmsg", "message", "msg",
    "headermsg",  # observed in the real GITS response (<msgHeader><headerMsg>)
}
# Tags that are only ever used in error envelopes.
_ERROR_STYLE_TAGS = {"errmsg", "returnauthmsg", "returnreasoncode", "cmmmsgheader"}
# Generic tags are only trusted near the root to avoid matching record fields.
_GENERIC_TAGS = {"code", "status", "message", "msg", "result", "resultstatus"}
_COUNT_TAGS = {
    "totalcount", "totalcnt", "listtotalcount", "numofrows", "pageno", "count",
    "itemcount",  # observed in the real GITS response (<msgHeader><itemCount>)
}
_SUCCESS_CODES = {"0", "00", "000", "0000", "info-000", "ok", "success", "normal_service", "normal service"}


class GitsApiError(RuntimeError):
    """Raised for any GITS request/parse/envelope failure. Message is sanitized."""


# ---------------------------------------------------------------------------
# Secret guards
# ---------------------------------------------------------------------------

def _secret_variants() -> list[str]:
    key = get_api_key(GITS_API_KEY_NAME)
    if not key:
        return []
    return list({key, quote(key, safe=""), quote_plus(key)})


def contains_secret(text: str) -> bool:
    """Return True if the configured GITS key (raw or URL-encoded) occurs in text."""
    return any(v in text for v in _secret_variants())


def assert_no_secret(text: str, what: str = "content") -> None:
    """Raise if ``text`` contains the credential. Never includes the text itself."""
    if contains_secret(text):
        raise GitsApiError(f"{what} echoes the credential; refusing to display it")


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

@dataclass
class ResponseInfo:
    status_code: int
    content_type: str
    body: bytes
    encoding: str | None = None

    @property
    def byte_length(self) -> int:
        return len(self.body)

    def text(self) -> str:
        return self.body.decode(self.encoding or "utf-8", errors="replace")


def _get(url: str, extra_params: dict[str, str], timeout: tuple[float, float]) -> ResponseInfo:
    """Shared GET with the service key injected via ``params`` and sanitized errors."""
    key = get_api_key(GITS_API_KEY_NAME, required=True)
    params = {"serviceKey": key, **extra_params}
    try:
        resp = requests.get(url, params=params, timeout=timeout)
    except requests.Timeout:
        raise GitsApiError(
            f"request timed out (connect={timeout[0]}s, read={timeout[1]}s)"
        ) from None
    except requests.RequestException as exc:
        # str(exc) may contain the authenticated URL: report the type only.
        raise GitsApiError(f"request failed: {type(exc).__name__}") from None

    if resp.status_code >= 400:
        raise GitsApiError(f"HTTP error {resp.status_code}") from None

    return ResponseInfo(
        status_code=resp.status_code,
        content_type=resp.headers.get("Content-Type", ""),
        body=resp.content,
        encoding=resp.encoding,
    )


def fetch_road_info_list(timeout: tuple[float, float] = DEFAULT_TIMEOUT) -> ResponseInfo:
    """GET getRoadInfoList with the service key as the only parameter."""
    return _get(ROAD_INFO_LIST_URL, {}, timeout)


def fetch_road_link_info_list(
    route_id: str, timeout: tuple[float, float] = DEFAULT_TIMEOUT
) -> ResponseInfo:
    """GET getRoadLinkInfoList with only ``serviceKey`` and ``routeId``."""
    if not route_id or not route_id.isdigit():
        raise GitsApiError("route_id must be a non-empty numeric string")
    return _get(ROAD_LINK_INFO_LIST_URL, {"routeId": route_id}, timeout)


def fetch_road_link_traffic_info_list(
    route_id: str, timeout: tuple[float, float] = DEFAULT_TIMEOUT
) -> ResponseInfo:
    """GET getRoadLinkTrafficInfoList (real-time traffic for one route)."""
    if not route_id or not route_id.isdigit():
        raise GitsApiError("route_id must be a non-empty numeric string")
    return _get(ROAD_LINK_TRAFFIC_INFO_LIST_URL, {"routeId": route_id}, timeout)


def fetch_road_link_traffic_info(
    link_id: str, timeout: tuple[float, float] = DEFAULT_TIMEOUT
) -> ResponseInfo:
    """GET getRoadLinkTrafficInfo (real-time traffic for one link)."""
    if not link_id or not link_id.isdigit():
        raise GitsApiError("link_id must be a non-empty numeric string")
    return _get(ROAD_LINK_TRAFFIC_INFO_URL, {"linkId": link_id}, timeout)


# ---------------------------------------------------------------------------
# Raw response cache (audit trail; one fetch per route)
# ---------------------------------------------------------------------------

def raw_link_xml_path(route_id: str) -> Path:
    return RAW_DIR / f"gits_road_link_{route_id}.xml"


def save_raw_xml(response: ResponseInfo, path: Path) -> Path:
    """Persist a raw XML body, refusing if it echoes the credential."""
    assert_no_secret(response.text(), "response body")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.body)
    return path


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------

def _local(tag: str) -> str:
    """Strip an XML namespace prefix: '{ns}tag' -> 'tag'."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def parse_xml(body: bytes) -> ET.Element:
    try:
        return ET.fromstring(body)
    except ET.ParseError as exc:
        # ParseError messages contain only a position, never body content.
        raise GitsApiError(f"XML parse error: {exc}") from None


# ---------------------------------------------------------------------------
# Envelope / application-level error detection
# ---------------------------------------------------------------------------

@dataclass
class ApiEnvelope:
    is_error: bool
    status: str                     # "success" | "error" | "unknown"
    code: str | None = None
    message: str | None = None
    header_fields: list[tuple[str, str]] = field(default_factory=list)
    count_fields: dict[str, str] = field(default_factory=dict)


def _iter_with_depth(root: ET.Element):
    stack = [(root, 0, _local(root.tag))]
    while stack:
        el, depth, path = stack.pop()
        yield el, depth, path
        for child in reversed(list(el)):
            stack.append((child, depth + 1, f"{path}/{_local(child.tag)}"))


def detect_api_error(root: ET.Element) -> ApiEnvelope:
    """Inspect header/result elements BEFORE any record detection.

    HTTP 200 alone is not treated as success. Only leaf elements are
    considered; generic tag names (code/message/...) are trusted only within
    two levels of the root so that record fields are not mistaken for headers.
    """
    header: list[tuple[str, str]] = []
    counts: dict[str, str] = {}
    code: str | None = None
    message: str | None = None
    error_style = False

    for el, depth, path in _iter_with_depth(root):
        tag = _local(el.tag).lower()
        if tag in _ERROR_STYLE_TAGS:
            error_style = True
        if len(el) > 0:
            continue  # not a leaf
        value = (el.text or "").strip()
        if tag in _GENERIC_TAGS and depth > 2:
            continue
        if tag in _RESULT_CODE_TAGS:
            header.append((path, value))
            if code is None:
                code = value
        elif tag in _RESULT_MSG_TAGS:
            header.append((path, value))
            if message is None:
                message = value
        elif tag in _COUNT_TAGS and depth <= 3:
            header.append((path, value))
            counts[_local(el.tag)] = value

    if error_style:
        return ApiEnvelope(True, "error", code, message, header, counts)
    if code is not None:
        ok = code.lower() in _SUCCESS_CODES
        return ApiEnvelope(not ok, "success" if ok else "error", code, message, header, counts)
    return ApiEnvelope(False, "unknown", None, message, header, counts)


def sanitized_envelope_summary(env: ApiEnvelope) -> str:
    """Human-readable code/message that is guaranteed not to contain the key."""
    code = env.code if env.code is not None and not contains_secret(env.code) else "<withheld>"
    msg = env.message if env.message is not None and not contains_secret(env.message) else "<withheld>"
    return f"code={code!r} message={msg!r}"


# ---------------------------------------------------------------------------
# Structure inspection (only after the envelope is not an error)
# ---------------------------------------------------------------------------

@dataclass
class StructureInfo:
    root_tag: str
    record_tag: str
    record_parent_tag: str | None
    record_count: int
    field_names: list[str]


def inspect_structure(root: ET.Element) -> StructureInfo:
    """Find the repeating record element and the union of its child field names.

    Heuristic: among non-root elements that have element children, the most
    frequent tag is the record tag.
    """
    # Envelope containers observed in the real GITS response are never records.
    envelope_containers = {"msgheader", "commsgheader", "cmmmsgheader", "header", "msgbody", "body"}
    counter: Counter[str] = Counter(
        _local(el.tag)
        for el in root.iter()
        if el is not root and len(el) > 0 and _local(el.tag).lower() not in envelope_containers
    )
    if not counter:
        raise GitsApiError("unexpected response structure: no repeating record element found")
    record_tag, record_count = counter.most_common(1)[0]

    fields: dict[str, None] = {}
    parent_tag: str | None = None
    parent_map = {c: p for p in root.iter() for c in p}
    for el in root.iter():
        if _local(el.tag) != record_tag:
            continue
        if parent_tag is None and el in parent_map:
            parent_tag = _local(parent_map[el].tag)
        for child in el:
            fields.setdefault(_local(child.tag), None)

    return StructureInfo(
        root_tag=_local(root.tag),
        record_tag=record_tag,
        record_parent_tag=parent_tag,
        record_count=record_count,
        field_names=list(fields),
    )


def structure_outline(root: ET.Element, max_depth: int = 4, max_children: int = 12) -> list[str]:
    """Tag-name-only outline of the document (no text values)."""
    lines = [f"<{_local(root.tag)}>"]

    def walk(el: ET.Element, depth: int) -> None:
        if depth > max_depth:
            return
        counts = Counter(_local(c.tag) for c in el)
        seen: set[str] = set()
        for child in el:
            tag = _local(child.tag)
            if tag in seen:
                continue
            seen.add(tag)
            if len(seen) > max_children:
                lines.append("  " * depth + "...")
                break
            suffix = f"  (x{counts[tag]})" if counts[tag] > 1 else ""
            lines.append("  " * depth + f"<{tag}>{suffix}")
            walk(child, depth + 1)

    walk(root, 1)
    return lines


def pagination_hint(env: ApiEnvelope, record_count: int) -> str | None:
    """Report (never act on) a possible pagination indicator."""
    for name, value in env.count_fields.items():
        try:
            total = int(value)
        except ValueError:
            continue
        if name.lower() in {"totalcount", "totalcnt", "listtotalcount", "count", "itemcount"} and total > record_count:
            return (
                f"pagination may exist: header field {name}={total} but "
                f"{record_count} records were returned. No paging parameters "
                "were added; review the official GITS documentation first."
            )
    return None


# ---------------------------------------------------------------------------
# DataFrame + CSV
# ---------------------------------------------------------------------------

def records_to_dataframe(root: ET.Element, info: StructureInfo) -> pd.DataFrame:
    rows: list[dict[str, str | None]] = []
    for el in root.iter():
        if _local(el.tag) != info.record_tag:
            continue
        row: dict[str, str | None] = {}
        for child in el:
            text = (child.text or "").strip()
            row[_local(child.tag)] = text if text else None
        rows.append(row)
    return pd.DataFrame(rows, columns=info.field_names)


def save_road_list_csv(df: pd.DataFrame, path: Path = ROAD_LIST_CSV) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def load_road_list_csv(path: Path = ROAD_LIST_CSV) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)


def verify_roundtrip(original: pd.DataFrame, reloaded: pd.DataFrame) -> list[str]:
    """Return a list of mismatches (empty list == round-trip verified).

    Makes no assumption about column names. Missing values are normalized to
    empty strings on both sides before comparison.
    """
    problems: list[str] = []
    if len(original) != len(reloaded):
        problems.append(f"row count differs: {len(original)} vs {len(reloaded)}")
    if original.shape[1] != reloaded.shape[1]:
        problems.append(f"column count differs: {original.shape[1]} vs {reloaded.shape[1]}")
    if list(original.columns) != list(reloaded.columns):
        problems.append("column names/order differ")
    if problems:
        return problems

    left = original.fillna("").astype(str).reset_index(drop=True)
    right = reloaded.fillna("").astype(str).reset_index(drop=True)
    mismatch = (left.to_numpy() != right.to_numpy())
    if mismatch.any():
        problems.append(f"{int(mismatch.sum())} cell value(s) differ after normalization")
    return problems


# ---------------------------------------------------------------------------
# Orchestrator (reusable in later steps)
# ---------------------------------------------------------------------------

@dataclass
class RoadListResult:
    response: ResponseInfo
    root: ET.Element
    envelope: ApiEnvelope
    structure: StructureInfo
    dataframe: pd.DataFrame


def collect_road_list(timeout: tuple[float, float] = DEFAULT_TIMEOUT) -> RoadListResult:
    """Fetch -> parse -> envelope check -> structure -> DataFrame (one request)."""
    response = fetch_road_info_list(timeout=timeout)
    root = parse_xml(response.body)
    envelope = detect_api_error(root)
    if envelope.is_error:
        raise GitsApiError(f"API returned an error envelope: {sanitized_envelope_summary(envelope)}")
    structure = inspect_structure(root)
    df = records_to_dataframe(root, structure)
    return RoadListResult(response, root, envelope, structure, df)


@dataclass
class RoadLinkResult:
    route_id: str
    response: ResponseInfo
    root: ET.Element
    envelope: ApiEnvelope
    structure: StructureInfo
    dataframe: pd.DataFrame


def collect_road_links(
    route_id: str,
    body: bytes | None = None,
    timeout: tuple[float, float] = DEFAULT_TIMEOUT,
) -> RoadLinkResult:
    """Links for one route. If ``body`` (cached raw XML) is given, no request is made."""
    if body is None:
        response = fetch_road_link_info_list(route_id, timeout=timeout)
    else:
        response = ResponseInfo(status_code=0, content_type="cached", body=body)
    root = parse_xml(response.body)
    envelope = detect_api_error(root)
    if envelope.is_error:
        raise GitsApiError(f"API returned an error envelope: {sanitized_envelope_summary(envelope)}")
    structure = inspect_structure(root)
    df = records_to_dataframe(root, structure)
    return RoadLinkResult(route_id, response, root, envelope, structure, df)


__all__ = [
    "ROAD_INFO_LIST_URL",
    "ROAD_LINK_INFO_LIST_URL",
    "RoadLinkResult",
    "fetch_road_link_info_list",
    "raw_link_xml_path",
    "save_raw_xml",
    "collect_road_links",
    "ROAD_LIST_CSV",
    "DEFAULT_TIMEOUT",
    "GitsApiError",
    "ResponseInfo",
    "ApiEnvelope",
    "StructureInfo",
    "RoadListResult",
    "contains_secret",
    "assert_no_secret",
    "fetch_road_info_list",
    "parse_xml",
    "detect_api_error",
    "sanitized_envelope_summary",
    "inspect_structure",
    "structure_outline",
    "pagination_hint",
    "records_to_dataframe",
    "save_road_list_csv",
    "load_road_list_csv",
    "verify_roundtrip",
    "collect_road_list",
]


# ---------------------------------------------------------------------------
# Link master table (Phase B)
# ---------------------------------------------------------------------------

from src.config import MASTER_DIR  # noqa: E402

LINK_MASTER_CSV: Path = MASTER_DIR / "gits_road_link_master.csv"
LINK_MASTER_PARQUET: Path = MASTER_DIR / "gits_road_link_master.parquet"

# GITS link fields preserved in the master, in this order (all observed).
LINK_FIELDS: tuple[str, ...] = (
    "linkId", "startNodeId", "startNodeNm", "endNodeId", "endNodeNm",
    "linkLength", "routeWay", "routeSeq",
)


def load_cached_or_fetch_links(route_id: str) -> tuple[ResponseInfo, bool]:
    """Return (response, from_cache). Fetches at most once per route; caches raw XML.

    Error envelopes are cached too, so a no-data route is never re-called.
    """
    path = raw_link_xml_path(route_id)
    if path.exists():
        return ResponseInfo(status_code=0, content_type="cached", body=path.read_bytes()), True
    response = fetch_road_link_info_list(route_id)
    save_raw_xml(response, path)
    return response, False


def save_table(df: pd.DataFrame, csv_path: Path, parquet_path: Path | None = None) -> None:
    """Write utf-8-sig CSV and (optionally) a Parquet twin with all-string columns."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    if parquet_path is not None:
        df.astype("string").to_parquet(parquet_path, index=False, engine="pyarrow")


def load_table_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)


def load_table_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path, engine="pyarrow").fillna("").astype(str)


# ---------------------------------------------------------------------------
# Real-time traffic normalization (fields verified on getRoadLinkTrafficInfoList)
# ---------------------------------------------------------------------------

# API field -> normalized name. Applied only when the API field is present.
TRAFFIC_NORMALIZED: dict[str, str] = {
    "collDate": "timestamp", "routeId": "route_id", "linkId": "link_id",
    "routeNm": "road_name", "routeWay": "direction_raw", "routeSeq": "route_seq",
    "startNodeId": "start_node_id", "startNodeNm": "start_node_name",
    "endNodeId": "end_node_id", "endNodeNm": "end_node_name",
    "spd": "speed", "vol": "volume", "trvlTime": "travel_time",
    "linkDelayTime": "delay_time", "congGrade": "congestion_grade",
}
TRAFFIC_TIMEZONE_NOTE = "timestamp = GITS collDate, Korean local time (KST, UTC+9), no tz suffix"


def normalize_traffic_records(
    df: pd.DataFrame, route_id: str, route_nm: str, fetched_at_utc: str,
    master: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Map observed GITS traffic fields to normalized names; omit absent fields."""
    norm = pd.DataFrame({"requested_route_id": route_id, "requested_route_name": route_nm,
                         "fetched_at_utc": fetched_at_utc}, index=df.index)
    for api_field, name in TRAFFIC_NORMALIZED.items():
        if api_field in df.columns:
            norm[name] = df[api_field]
    if master is not None and "link_id" in norm and "linkLength" in master.columns:
        ll = master.drop_duplicates("linkId").set_index("linkId")["linkLength"]
        norm["link_length"] = norm["link_id"].map(ll)
    return norm


def collect_route_traffic(route_id: str, route_nm: str, master: pd.DataFrame | None = None,
                          timeout: tuple[float, float] = DEFAULT_TIMEOUT) -> tuple[pd.DataFrame | None, ResponseInfo, ApiEnvelope | None]:
    """One getRoadLinkTrafficInfoList request -> (normalized df or None, response, envelope)."""
    from datetime import datetime, timezone
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    response = fetch_road_link_traffic_info_list(route_id, timeout=timeout)
    root = parse_xml(response.body)
    envelope = detect_api_error(root)
    if envelope.is_error:
        return None, response, envelope
    info = inspect_structure(root)
    df = records_to_dataframe(root, info)
    return normalize_traffic_records(df, route_id, route_nm, fetched_at, master), response, envelope
