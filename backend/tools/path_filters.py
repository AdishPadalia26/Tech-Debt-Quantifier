"""Classify repository paths that are not principal (production) source code.

Used to keep tests, docs, examples and generated files from inflating
debt estimates.
"""

from fnmatch import fnmatch

from constants import SKIP_FILE_PATTERNS, TEST_DIR_NAMES, TEST_FILE_PATTERNS

DOCS_DIR_NAMES: frozenset[str] = frozenset({"docs", "doc", "docs_src", "documentation"})
EXAMPLE_DIR_NAMES: frozenset[str] = frozenset(
    {"examples", "example", "samples", "sample", "demo", "demos"}
)
GENERATED_DIR_NAMES: frozenset[str] = frozenset({"__generated__"})
GENERATED_SUFFIXES: tuple[str, ...] = ("_pb2.py", ".min.js")


def _is_test_file(file_name: str) -> bool:
    """Return True when a file name matches a test file pattern."""
    for pattern in TEST_FILE_PATTERNS:
        if pattern.endswith("_") and not pattern.startswith((".", "_")):
            # Prefix pattern such as "test_"
            if file_name.startswith(pattern):
                return True
        elif pattern in file_name:
            return True
    return False


def _is_generated_file(file_name: str) -> bool:
    """Return True when a file name matches a generated/vendored pattern."""
    if file_name.endswith(GENERATED_SUFFIXES):
        return True
    return any(fnmatch(file_name, pattern) for pattern in SKIP_FILE_PATTERNS)


def is_non_principal_path(path: str) -> str | None:
    """Classify a repo-relative path as non-principal code.

    Args:
        path: File path (any separator style, relative or absolute)

    Returns:
        "test", "docs", "example" or "generated" when the path is not
        principal source code, otherwise None.
    """
    if not path:
        return None
    normalized = path.replace("\\", "/").strip("/")
    segments = [seg for seg in normalized.split("/") if seg and seg != "."]
    if not segments:
        return None
    dir_segments = [seg.lower() for seg in segments[:-1]]
    file_name = segments[-1].lower()

    if any(seg in TEST_DIR_NAMES for seg in dir_segments) or _is_test_file(file_name):
        return "test"
    if any(seg in DOCS_DIR_NAMES for seg in dir_segments):
        return "docs"
    if any(seg in EXAMPLE_DIR_NAMES for seg in dir_segments):
        return "example"
    if any(seg in GENERATED_DIR_NAMES for seg in dir_segments) or _is_generated_file(
        file_name
    ):
        return "generated"
    return None
