"""Bucket estimation: group near-identical debt items, estimate one per bucket.

Many debt items are near-duplicates (missing docstrings, similar complexity
hotspots, the same bandit rule). Instead of sending every item to the LLM,
items are grouped into buckets by ``bucket_key`` and only one representative
per bucket is estimated; the remaining members reuse the representative's hours
scaled by the ratio of their size metrics.

Everything here is pure and deterministic (no I/O, no randomness).
"""

import logging
import os
import statistics
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Member/representative hours ratio is clamped to this range.
SCALE_MIN = 0.5
SCALE_MAX = 2.0

# Upper bounds (inclusive) of the size buckets: 1-2, 3-5, 6-10, 11-20, 21-50, 51+.
SIZE_UPPER_BOUNDS: tuple[float, ...] = (2, 5, 10, 20, 50)
SIZE_LABELS: tuple[str, ...] = ("1-2", "3-5", "6-10", "11-20", "21-50", "51+")
SIZE_NA = "na"

# First numeric field present wins; it is the item's "main magnitude".
MAGNITUDE_FIELDS: tuple[str, ...] = (
    "complexity",
    "max_complexity",
    "nloc",
    "line_count",
    "lines",
    "duplicated_lines",
    "statement_count",
    "duplication_count",
    "import_fanout",
    "count",
)

# Rule-like fields that refine the issue type (bandit test id, semgrep rule...).
RULE_FIELDS: tuple[str, ...] = ("bandit_test_id", "rule_id", "test_id", "check_id")
KIND_FIELDS: tuple[str, ...] = ("type", "issue_type", "kind")

EXTENSION_LANGUAGES: dict[str, str] = {
    ".py": "python", ".ipynb": "python", ".js": "javascript",
    ".jsx": "javascript", ".mjs": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".java": "java", ".go": "go", ".rb": "ruby",
    ".rs": "rust", ".c": "c", ".h": "c", ".cc": "cpp", ".cpp": "cpp",
    ".hpp": "cpp", ".cs": "csharp", ".php": "php", ".kt": "kotlin",
    ".swift": "swift", ".scala": "scala", ".sh": "shell",
    ".txt": "text", ".json": "json", ".toml": "toml", ".yml": "yaml",
    ".yaml": "yaml",
}

# Coarsening ladder: (keep_language, keep_issue, keep_severity, size_mode).
# size_mode is an int shift (0 = full resolution, n = merge 2**n adjacent size
# buckets) or None to drop the size dimension entirely. The last level
# collapses everything into one bucket so ``max_buckets >= 1`` always holds.
_LEVELS: tuple[tuple[bool, bool, bool, int | None, bool], ...] = (
    (True, True, True, 0, True),
    (False, True, True, 0, True),
    (False, True, True, 1, True),
    (False, True, True, 2, True),
    (False, True, True, 3, True),
    (False, False, True, None, True),
    (False, False, False, None, True),
    (False, False, False, None, False),
)


@dataclass
class Bucket:
    """A group of near-identical debt items.

    Attributes:
        key: Bucket key at the granularity that was finally used.
        members: Indices (into the input list) of every member, ascending.
        representative: Index of the member that is sent to the LLM.
    """

    key: str
    members: list[int] = field(default_factory=list)
    representative: int = 0


def _number(value: Any) -> float | None:
    """Return ``value`` as a finite float, or None for non-numeric input."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if number == number and abs(number) != float("inf") else None


def magnitude(item: dict[str, Any]) -> float | None:
    """Return the item's main size metric, or None when it has none.

    Looks at complexity, nloc, line count, duplicated lines/statements,
    fan-out or count (first present wins); import cycles use their length.

    Args:
        item: Debt item dict.

    Returns:
        The metric as a float, or None.
    """
    for name in MAGNITUDE_FIELDS:
        value = _number(item.get(name))
        if value is not None:
            return value
    cycle = item.get("cycle")
    if isinstance(cycle, (list, tuple)) and cycle:
        return float(len(cycle))
    return None


def size_index(value: float | None) -> int | None:
    """Map a magnitude to its log-style size bucket index (0..5), or None."""
    if value is None:
        return None
    for idx, bound in enumerate(SIZE_UPPER_BOUNDS):
        if value <= bound:
            return idx
    return len(SIZE_UPPER_BOUNDS)


def size_bucket(value: float | None) -> str:
    """Return the size bucket label (``1-2``, ``3-5`` ... ``51+``, ``na``)."""
    idx = size_index(value)
    return SIZE_NA if idx is None else SIZE_LABELS[idx]


def _merged_size_label(idx: int | None, shift: int) -> str:
    """Label for size bucket ``idx`` after merging ``2**shift`` neighbours."""
    if idx is None:
        return SIZE_NA
    if shift == 0:
        return SIZE_LABELS[idx]
    group = idx >> shift
    first = group << shift
    last = min(((group + 1) << shift) - 1, len(SIZE_LABELS) - 1)
    low = SIZE_LABELS[first].split("-")[0].rstrip("+")
    if last == len(SIZE_LABELS) - 1:
        return f"{low}+"
    return f"{low}-{SIZE_LABELS[last].split('-')[-1]}"


def item_language(item: dict[str, Any]) -> str:
    """Return the item's language (explicit field, else from file extension)."""
    explicit = str(item.get("language") or "").strip().lower()
    if explicit:
        return explicit
    ext = os.path.splitext(str(item.get("file") or ""))[1].lower()
    return EXTENSION_LANGUAGES.get(ext, "other")


def issue_type(item: dict[str, Any]) -> str:
    """Return the issue kind, refined by a rule id (e.g. ``type:B101``)."""
    kind = ""
    for name in KIND_FIELDS:
        if item.get(name):
            kind = str(item[name]).strip().lower()
            break
    rule = ""
    for name in RULE_FIELDS:
        if item.get(name):
            rule = str(item[name]).strip().upper()
            break
    if kind and rule:
        return f"{kind}:{rule}"
    return kind or rule or "unknown"


def _facets(item: dict[str, Any]) -> tuple[str, str, str, str, int | None]:
    """Return (category, severity, language, issue, size_index) for an item."""
    category = str(item.get("category") or "code_quality").strip().lower()
    severity = str(item.get("severity") or "medium").strip().lower()
    return (
        category,
        severity,
        item_language(item),
        issue_type(item),
        size_index(magnitude(item)),
    )


def _key_at_level(
    facets: tuple[str, str, str, str, int | None],
    level: tuple[bool, bool, bool, int | None, bool],
) -> str:
    """Build the bucket key for ``facets`` at one coarsening level."""
    category, severity, language, issue, idx = facets
    keep_lang, keep_issue, keep_sev, size_mode, keep_cat = level
    parts = [
        category if keep_cat else "*",
        severity if keep_sev else "*",
        language if keep_lang else "*",
        issue if keep_issue else "*",
        "*" if size_mode is None else _merged_size_label(idx, size_mode),
    ]
    return "|".join(parts)


def bucket_key(item: dict[str, Any]) -> str:
    """Return the full-resolution bucket key of a debt item.

    The key is ``category|severity|language|issue|size`` where ``issue`` is the
    item type refined by its rule id (bandit test id etc.) and ``size`` is the
    log-style bucket of the item's main magnitude metric (``na`` if missing).

    Args:
        item: Debt item dict.

    Returns:
        Deterministic key string.
    """
    return _key_at_level(_facets(item), _LEVELS[0])


def _pick_representative(
    members: list[int], magnitudes: list[float | None]
) -> int:
    """Pick the member closest to the median magnitude (ties: lowest index)."""
    known = [magnitudes[i] for i in members if magnitudes[i] is not None]
    if not known:
        return members[0]
    median = statistics.median(known)  # type: ignore[type-var]
    best = members[0]
    best_dist = float("inf")
    for i in members:
        value = magnitudes[i]
        if value is None:
            continue
        dist = abs(value - median)
        if dist < best_dist:
            best, best_dist = i, dist
    return best


def build_buckets(items: list[dict[str, Any]], max_buckets: int) -> list[Bucket]:
    """Group items into at most ``max_buckets`` buckets.

    Starts from the full-resolution key and coarsens (drop language, merge
    adjacent size buckets, then drop issue type / severity / category) until the
    bucket count fits. Buckets are ordered by their first member; the result is
    fully deterministic for a given input order.

    Args:
        items: Debt item dicts.
        max_buckets: Upper bound on the number of buckets (min 1).

    Returns:
        Buckets covering every input index exactly once.
    """
    if not items:
        return []
    max_buckets = max(1, int(max_buckets))
    facets = [_facets(item) for item in items]
    magnitudes = [magnitude(item) for item in items]

    chosen: dict[str, list[int]] = {}
    for level in _LEVELS:
        groups: dict[str, list[int]] = {}
        for idx, f in enumerate(facets):
            groups.setdefault(_key_at_level(f, level), []).append(idx)
        chosen = groups
        if len(groups) <= max_buckets:
            break
    if len(chosen) < len(items):
        logger.info(
            "[BUCKETS] %d items -> %d buckets (max %d)",
            len(items), len(chosen), max_buckets,
        )
    return [
        Bucket(key=key, members=members,
               representative=_pick_representative(members, magnitudes))
        for key, members in chosen.items()
    ]


def scale_factor(member: dict[str, Any], representative: dict[str, Any]) -> float:
    """Hours multiplier for ``member`` relative to its representative.

    The member/representative magnitude ratio clamped to [0.5, 2.0]; 1.0 when
    either magnitude is missing or the representative's is not positive.
    """
    member_mag = magnitude(member)
    rep_mag = magnitude(representative)
    if member_mag is None or rep_mag is None or rep_mag <= 0:
        return 1.0
    return max(SCALE_MIN, min(SCALE_MAX, member_mag / rep_mag))
