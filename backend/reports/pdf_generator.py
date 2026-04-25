"""Professional PDF report generation for Tech Debt Quantifier."""

from __future__ import annotations

import os
import re
from datetime import datetime
from io import BytesIO
from typing import Any

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

C_BG = HexColor("#0f0e0d")
C_SURFACE = HexColor("#1c1b19")
C_BORDER = HexColor("#2d2c2a")
C_TEXT = HexColor("#cdccca")
C_MUTED = HexColor("#797876")
C_PRIMARY = HexColor("#4f98a3")
C_SUCCESS = HexColor("#6daa45")
C_WARNING = HexColor("#e8af34")
C_DANGER = HexColor("#dd6974")
C_WHITE = HexColor("#f5f5f4")

SEV_COLORS = {
    "critical": C_DANGER,
    "high": HexColor("#fdab43"),
    "medium": C_WARNING,
    "low": C_SUCCESS,
}

CAT_COLORS = [
    HexColor("#4f98a3"),
    HexColor("#5591c7"),
    HexColor("#e8af34"),
    HexColor("#a86fdf"),
    HexColor("#dd6974"),
    HexColor("#6daa45"),
    HexColor("#fdab43"),
    HexColor("#797876"),
]

CATEGORY_ACTION_TEMPLATES = {
    "code_quality": "Refactor {file} — reduce cyclomatic complexity and improve maintainability",
    "architecture": "Restructure {file} — address architectural coupling and improve modularity",
    "security": "Remediate {file} — fix {severity}-severity security vulnerability",
    "documentation": "Document {file} — add missing docstrings and API documentation",
    "test_debt": "Improve test coverage in {file} — add unit and integration tests",
    "reliability": "Harden {file} — add error handling and improve fault tolerance",
    "performance": "Optimize {file} — address performance bottleneck",
    "dependency": "Update dependencies in {file} — resolve outdated or vulnerable packages",
}


def clean_file_path(raw_path: str) -> str:
    """Strip temp/OS paths and return a clean relative path."""
    if not raw_path:
        return "unknown"
    path = re.sub(r"^[A-Za-z]:\\.*?\\tech-debt-repos\\[^\\]+\\", "", raw_path)
    path = re.sub(r"^/tmp/repos/[^/]+/", "", path)
    path = re.sub(r":\??$|:\d+$", "", path)
    path = path.replace("\\", "/")
    if len(path) > 60:
        parts = path.split("/")
        while len("/".join(parts)) > 57 and len(parts) > 1:
            parts = parts[1:]
        path = "…/" + "/".join(parts)
    return path or "unknown"


def item_hours(item: dict[str, Any]) -> float:
    """Return rounded debt item hours using adjusted minutes first."""
    minutes = item.get("adjusted_minutes") or item.get("base_minutes") or 0
    hours = item.get("hours") or item.get("remediation_hours") or 0
    if minutes:
        try:
            return round(float(minutes) / 60, 1)
        except (TypeError, ValueError):
            return 0.0
    try:
        return round(float(hours), 1)
    except (TypeError, ValueError):
        return 0.0


def build_action_description(action: dict[str, Any]) -> str:
    """Create a specific action description from category and file context."""
    category = str(action.get("category") or "code_quality").lower()
    file_path = clean_file_path(
        str(action.get("file") or action.get("file_or_module") or "")
    )
    severity = str(action.get("severity") or "medium").lower()
    template = CATEGORY_ACTION_TEMPLATES.get(category, "Address tech debt in {file}")
    return template.format(file=file_path, severity=severity)


def score_color(score: float) -> HexColor:
    """Return a severity color for the debt score."""
    if score <= 3:
        return C_SUCCESS
    if score <= 6:
        return C_WARNING
    return C_DANGER


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _merged_payload(result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return merged result and analysis payloads for report generation."""
    analysis = result.get("raw_analysis") or result
    if not isinstance(analysis, dict):
        analysis = {}

    merged_analysis = {
        **analysis,
        "executive_summary": analysis.get("executive_summary")
        or result.get("executive_summary")
        or "",
        "priority_actions": analysis.get("priority_actions")
        or result.get("priority_actions")
        or [],
        "roi_analysis": analysis.get("roi_analysis") or result.get("roi_analysis") or {},
        "repo_profile": analysis.get("repo_profile") or result.get("repo_profile") or {},
    }
    merged_result = {**result, "raw_analysis": merged_analysis}
    return merged_result, merged_analysis


def _profile_value(
    profile: dict[str, Any],
    analysis: dict[str, Any],
    *keys: str,
    default: Any = None,
) -> Any:
    """Resolve a value from profile, nested profile sections, then analysis."""
    for key in keys:
        if key in profile and profile.get(key) is not None:
            return profile.get(key)
    for section in ("tech_stack", "team", "multipliers", "ai_detection"):
        section_data = profile.get(section)
        if isinstance(section_data, dict):
            for key in keys:
                if section_data.get(key) is not None:
                    return section_data.get(key)
    for key in keys:
        if analysis.get(key) is not None:
            return analysis.get(key)
    return default


def _fallback_priority_actions(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    """Build concrete priority actions when the report payload lacks them."""
    findings = analysis.get("findings")
    debt_items = analysis.get("debt_items")
    source_items = findings if isinstance(findings, list) and findings else debt_items
    if not isinstance(source_items, list):
        return []

    actions: list[dict[str, Any]] = []
    for index, item in enumerate(source_items[:5], start=1):
        if not isinstance(item, dict):
            continue
        actions.append(
            {
                "title": item.get("title")
                or f"Address {str(item.get('category') or 'tech debt').replace('_', ' ')}",
                "file": item.get("file_path") or item.get("file"),
                "file_or_module": item.get("module") or item.get("file_path") or item.get("file"),
                "severity": item.get("severity") or "medium",
                "category": item.get("category") or "code_quality",
                "estimated_cost": _safe_float(item.get("cost_usd")),
                "estimated_hours": _safe_float(item.get("effort_hours"), item_hours(item)),
                "monthly_savings": round(_safe_float(item.get("cost_usd")) * 0.015, 2),
                "sprint_number": index,
            }
        )
    return actions


class ColorRect(Flowable):
    """Full-width colored rectangle used behind the cover header."""

    def __init__(self, height: float, color: HexColor, width: float | None = None):
        super().__init__()
        self.rect_height = height
        self.color = color
        self._width = width

    def draw(self) -> None:
        width = self._width or self.canv._pagesize[0]
        self.canv.setFillColor(self.color)
        self.canv.rect(0, 0, width, self.rect_height, fill=1, stroke=0)

    def wrap(self, available_width: float, available_height: float) -> tuple[float, float]:
        self._width = available_width
        return available_width, self.rect_height


def generate_pdf_report(result: dict[str, Any]) -> bytes:
    """Generate a professional dark-theme PDF report and return raw bytes."""
    result, analysis = _merged_payload(result)
    buffer = BytesIO()

    repo_url = (
        result.get("github_url")
        or analysis.get("github_url")
        or analysis.get("repo_path")
        or "Unknown Repository"
    )
    repo_name = repo_url.split("/")[-1] if "/" in str(repo_url) else str(repo_url)
    generated = datetime.now().strftime("%B %d, %Y at %H:%M")

    score = _safe_float(analysis.get("debt_score"))
    cost = _safe_float(analysis.get("total_cost_usd"))
    hours = _safe_float(analysis.get("total_remediation_hours"))
    sprints = _safe_float(analysis.get("total_remediation_sprints"))
    score_fill = score_color(score)

    page_width, page_height = A4
    margin = 18 * mm

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Tech Debt Report - {repo_name}",
        author="Tech Debt Quantifier",
    )

    styles = getSampleStyleSheet()

    def S(name: str, parent: str = "Normal", **kwargs: Any) -> ParagraphStyle:
        return ParagraphStyle(name, parent=styles[parent], **kwargs)

    s_h1 = S(
        "H1",
        fontSize=22,
        textColor=C_WHITE,
        fontName="Helvetica-Bold",
        spaceAfter=4,
        leading=26,
    )
    s_h2 = S(
        "H2",
        fontSize=13,
        textColor=C_WHITE,
        fontName="Helvetica-Bold",
        spaceBefore=16,
        spaceAfter=6,
        leading=17,
    )
    s_body = S("Body", fontSize=9, textColor=C_TEXT, leading=14, spaceAfter=4)
    s_muted = S("Muted", fontSize=8, textColor=C_MUTED, leading=12)
    s_label = S(
        "Label",
        fontSize=7,
        textColor=C_MUTED,
        fontName="Helvetica-Bold",
        leading=10,
        spaceAfter=1,
    )
    s_center = S("Center", fontSize=9, textColor=C_TEXT, alignment=TA_CENTER, leading=13)
    s_mono = S("Mono", fontSize=8, textColor=C_TEXT, fontName="Courier", leading=12)
    s_mono_muted = S(
        "MonoMuted", fontSize=7, textColor=C_MUTED, fontName="Courier", leading=11
    )

    story: list[Any] = []

    story.append(ColorRect(52 * mm, C_BG))
    story.append(Spacer(1, -52 * mm))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("Tech Debt Quantifier", s_h1))
    story.append(
        Paragraph(
            "<font color='#797876'>Technical Debt Analysis Report</font>",
            S("Sub", fontSize=11, textColor=C_MUTED, leading=15),
        )
    )
    story.append(Spacer(1, 3 * mm))
    story.append(
        Paragraph(
            f"<font color='#4f98a3'>●</font>  <font color='#797876'>{repo_url}</font>",
            S("Repo", fontSize=8, textColor=C_MUTED, leading=12),
        )
    )
    story.append(
        Paragraph(
            f"<font color='#797876'>Generated: {generated}</font>",
            S("Gen", fontSize=8, textColor=C_MUTED, leading=12),
        )
    )
    story.append(Spacer(1, 6 * mm))

    score_hex = score_fill.hexval()[2:]
    kpi_col_width = (page_width - 2 * margin) / 4
    kpi_table = Table(
        [
            [
                Paragraph("DEBT SCORE", s_label),
                Paragraph("TOTAL COST", s_label),
                Paragraph("HOURS", s_label),
                Paragraph("SPRINTS", s_label),
            ],
            [
                Paragraph(
                    f"<font color='#{score_hex}'>{score:.1f}<font size='12'>/10</font></font>",
                    S(
                        "ScoreValue",
                        fontSize=28,
                        fontName="Helvetica-Bold",
                        textColor=score_fill,
                        leading=32,
                    ),
                ),
                Paragraph(
                    f"${cost:,.0f}",
                    S(
                        "KpiValue",
                        fontSize=22,
                        fontName="Helvetica-Bold",
                        textColor=C_WHITE,
                        leading=26,
                    ),
                ),
                Paragraph(
                    f"{hours:,.0f}",
                    S(
                        "KpiValueHours",
                        fontSize=22,
                        fontName="Helvetica-Bold",
                        textColor=C_WHITE,
                        leading=26,
                    ),
                ),
                Paragraph(
                    f"{sprints:.1f}",
                    S(
                        "KpiValueSprints",
                        fontSize=22,
                        fontName="Helvetica-Bold",
                        textColor=C_WHITE,
                        leading=26,
                    ),
                ),
            ],
        ],
        colWidths=[kpi_col_width] * 4,
        rowHeights=[10 * mm, 14 * mm],
    )
    kpi_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), C_SURFACE),
                ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
                ("LINEAFTER", (0, 0), (2, -1), 0.5, C_BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(kpi_table)
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("Executive Summary", s_h2))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=4))
    summary = str(
        analysis.get("executive_summary")
        or result.get("executive_summary")
        or (
            f"This repository carries an estimated ${cost:,.0f} in technical debt with "
            f"a score of {score:.1f}/10 and approximately {hours:,.0f} remediation hours."
        )
    )
    story.append(Paragraph(summary, s_body))
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("Key Metrics", s_h2))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=4))

    profile = analysis.get("repo_profile") if isinstance(analysis.get("repo_profile"), dict) else {}
    roi = result.get("roi_analysis") if isinstance(result.get("roi_analysis"), dict) else {}
    if not roi:
        roi = analysis.get("roi_analysis") if isinstance(analysis.get("roi_analysis"), dict) else {}

    hourly_rate = (
        _safe_float(analysis.get("hourly_rate"))
        or _safe_float((analysis.get("hourly_rates") or {}).get("blended_rate"))
    )
    combined_multiplier = _safe_float(analysis.get("combined_multiplier"))
    if not combined_multiplier:
        combined_multiplier = _safe_float(_profile_value(profile, analysis, "combined_multiplier", default=1.0), 1.0)

    total_issues = _safe_int(analysis.get("total_issues"))
    if not total_issues:
        findings = analysis.get("findings")
        debt_items = analysis.get("debt_items")
        if isinstance(findings, list) and findings:
            total_issues = len(findings)
        elif isinstance(debt_items, list):
            total_issues = len(debt_items)
        else:
            categories = analysis.get("cost_by_category") or {}
            if isinstance(categories, dict):
                total_issues = sum(
                    _safe_int(v.get("count") or v.get("item_count"))
                    for v in categories.values()
                    if isinstance(v, dict)
                )

    metrics_rows = [
        ["Metric", "Value", "Note"],
        ["Hourly Rate", f"${hourly_rate:,.2f}/hr", "Blended engineer rate"],
        [
            "Combined Multiplier",
            f"{combined_multiplier:.2f}x",
            "Bus factor x repo age x team risk",
        ],
        [
            "Team Size",
            str(_safe_int(_profile_value(profile, analysis, "team_size", "estimated_team_size", default=1))),
            "From git history",
        ],
        [
            "Bus Factor",
            str(_safe_int(_profile_value(profile, analysis, "bus_factor", default=1))),
            "1 = single point of failure",
        ],
        [
            "Files Analyzed",
            str(
                _safe_int(
                    (analysis.get("summary") or {}).get("files_scanned")
                    or analysis.get("files_analyzed")
                )
            ),
            "Source files scanned",
        ],
        ["Total Issues", str(total_issues), "Across all categories"],
    ]

    content_width = page_width - 2 * margin
    metrics_table = Table(
        metrics_rows,
        colWidths=[content_width * 0.38, content_width * 0.22, content_width * 0.40],
    )
    metrics_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), C_PRIMARY),
                ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_SURFACE, HexColor("#201f1d")]),
                ("TEXTCOLOR", (0, 1), (-1, -1), C_TEXT),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("FONTNAME", (1, 1), (1, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (1, 1), (1, -1), C_WHITE),
                ("GRID", (0, 0), (-1, -1), 0.3, C_BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(metrics_table)

    story.append(PageBreak())
    story.append(Paragraph("Cost by Category", s_h2))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=6))

    categories = analysis.get("cost_by_category") or {}
    category_items: list[tuple[str, dict[str, Any]]] = []
    if isinstance(categories, dict):
        for key, value in categories.items():
            if isinstance(value, dict):
                category_items.append((key, value))
            elif isinstance(value, (int, float)):
                category_items.append((key, {"cost_usd": value, "count": 0, "hours": 0}))
    category_items.sort(key=lambda item: _safe_float(item[1].get("cost_usd")), reverse=True)

    total_category_cost = sum(_safe_float(value.get("cost_usd")) for _, value in category_items) or 1.0
    category_rows: list[list[Any]] = [["", "Category", "Cost", "Hours", "Issues", "% of Total"]]
    for index, (key, value) in enumerate(category_items):
        category_cost = _safe_float(value.get("cost_usd"))
        category_hours = _safe_float(value.get("hours") or value.get("total_hours"))
        category_count = _safe_int(value.get("count") or value.get("item_count") or value.get("issues"))
        pct = category_cost / total_category_cost * 100
        color = CAT_COLORS[index % len(CAT_COLORS)]
        category_rows.append(
            [
                Paragraph(f"<font color='#{color.hexval()[2:]}'>■</font>", s_center),
                Paragraph(key.replace("_", " ").title(), s_body),
                Paragraph(
                    f"${category_cost:,.0f}",
                    S("CatCost", fontSize=9, fontName="Helvetica-Bold", textColor=C_WHITE, leading=12),
                ),
                Paragraph(f"{category_hours:.1f}h", s_mono_muted),
                Paragraph(str(category_count), s_mono_muted),
                Paragraph(f"{pct:.1f}%", s_muted),
            ]
        )

    category_table = Table(
        category_rows,
        colWidths=[
            content_width * 0.05,
            content_width * 0.30,
            content_width * 0.18,
            content_width * 0.15,
            content_width * 0.12,
            content_width * 0.20,
        ],
    )
    category_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), C_PRIMARY),
                ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_SURFACE, HexColor("#201f1d")]),
                ("GRID", (0, 0), (-1, -1), 0.3, C_BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(category_table)
    story.append(Spacer(1, 8 * mm))

    story.append(Paragraph("Top Priority Actions", s_h2))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=6))

    actions = result.get("priority_actions")
    if not isinstance(actions, list) or not actions:
        actions = analysis.get("priority_actions")
    if not isinstance(actions, list) or not actions:
        actions = _fallback_priority_actions(analysis)

    sprint_labels = ["Fix First", "Fix Second", "Fix Third", "Sprint 4", "Sprint 5"]
    for index, action in enumerate(actions[:5]):
        if not isinstance(action, dict):
            continue
        severity = str(action.get("severity") or "medium").lower()
        severity_fill = SEV_COLORS.get(severity, C_MUTED)
        label = sprint_labels[index] if index < len(sprint_labels) else f"Sprint {index + 1}"
        sprint = action.get("sprint_number") or action.get("sprint") or index + 1
        action_cost = _safe_float(action.get("estimated_cost") or action.get("fix_cost"))
        action_hours = _safe_float(action.get("estimated_hours"), item_hours(action))
        action_savings = _safe_float(action.get("monthly_savings") or action.get("saves_per_month"))
        description = build_action_description(action)
        file_label = clean_file_path(
            str(action.get("file") or action.get("file_or_module") or "")
        )

        metric_table = Table(
            [
                [Paragraph("Fix Cost", s_label), Paragraph("Hours", s_label), Paragraph("Monthly Savings", s_label)],
                [
                    Paragraph(
                        f"${action_cost:,.0f}",
                        S("ActionMetricValue", fontSize=10, fontName="Helvetica-Bold", textColor=C_WHITE, leading=13),
                    ),
                    Paragraph(
                        f"{action_hours:.1f}h",
                        S("ActionMetricHours", fontSize=10, fontName="Helvetica-Bold", textColor=C_WHITE, leading=13),
                    ),
                    Paragraph(
                        f"${action_savings:,.0f}/mo" if action_savings > 0 else "—",
                        S(
                            "ActionMetricSavings",
                            fontSize=10,
                            fontName="Helvetica-Bold",
                            textColor=C_SUCCESS if action_savings > 0 else C_MUTED,
                            leading=13,
                        ),
                    ),
                ],
            ],
            colWidths=[(content_width - 20) * 0.33] * 3,
        )
        metric_table.setStyle(
            TableStyle(
                [
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )

        action_table = Table(
            [
                [
                    Paragraph(
                        f"<font color='#{severity_fill.hexval()[2:]}'>● {label.upper()}</font>  "
                        f"<font color='#797876'>Sprint {sprint}</font>",
                        S("ActionLabel", fontSize=8, fontName="Helvetica-Bold", textColor=C_WHITE, leading=11),
                    ),
                    Paragraph(
                        f"${action_cost:,.0f}",
                        S(
                            "ActionCost",
                            fontSize=11,
                            fontName="Helvetica-Bold",
                            textColor=C_WHITE,
                            alignment=TA_RIGHT,
                            leading=14,
                        ),
                    ),
                ],
                [Paragraph(description, s_body), ""],
                [
                    Paragraph(
                        f"<font color='#4f98a3'>⬡</font> <font color='#797876' size='7'>{file_label}</font>",
                        S("ActionFile", fontSize=7, fontName="Courier", textColor=C_MUTED, leading=10),
                    ),
                    "",
                ],
                [metric_table, ""],
            ],
            colWidths=[content_width - 12 * mm - 2, 12 * mm + 2],
        )
        action_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), C_SURFACE),
                    ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
                    ("LINEABOVE", (0, 0), (-1, 0), 2.5, severity_fill),
                    ("SPAN", (0, 1), (1, 1)),
                    ("SPAN", (0, 2), (1, 2)),
                    ("SPAN", (0, 3), (1, 3)),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(KeepTogether([action_table, Spacer(1, 4 * mm)]))

    story.append(PageBreak())
    story.append(Paragraph("ROI Analysis", s_h2))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=6))

    annual_savings = _safe_float(roi.get("annual_maintenance_savings"))
    payback = _safe_int(roi.get("payback_months"))
    roi_3yr = _safe_float(
        roi.get("three_year_roi_pct", roi.get("3_year_roi_pct", roi.get("roi_percentage")))
    )
    quarterly_budget = _safe_float(
        roi.get("quarterly_budget", roi.get("recommended_quarterly_spend", roi.get("recommended_budget")))
    )

    roi_table = Table(
        [
            ["Annual Savings", "Payback Period", "3-Year ROI", "Quarterly Budget"],
            [
                f"${annual_savings:,.0f}",
                f"{payback} mo" if payback else "N/A",
                f"{roi_3yr:.0f}%" if roi_3yr else "N/A",
                f"${quarterly_budget:,.0f}" if quarterly_budget else "N/A",
            ],
        ],
        colWidths=[content_width / 4] * 4,
        rowHeights=[8 * mm, 14 * mm],
    )
    roi_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), C_SURFACE),
                ("BACKGROUND", (0, 1), (-1, 1), HexColor("#201f1d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), C_MUTED),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 7),
                ("TEXTCOLOR", (0, 1), (-1, 1), C_SUCCESS),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 1), (-1, 1), 16),
                ("GRID", (0, 0), (-1, -1), 0.3, C_BORDER),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(roi_table)
    story.append(Spacer(1, 6 * mm))

    roi_recommendation = (
        roi.get("recommendation")
        or result.get("roi_recommendation")
        or "Prioritize the top hotspots this sprint for the strongest maintenance ROI."
    )
    story.append(
        Paragraph(
            f"<font color='#4f98a3'>\"</font>{roi_recommendation}<font color='#4f98a3'>\"</font>",
            S(
                "Quote",
                fontSize=9,
                textColor=C_TEXT,
                leftIndent=12,
                leading=15,
                spaceBefore=4,
                spaceAfter=8,
            ),
        )
    )

    story.append(Paragraph("Repository Profile", s_h2))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=6))

    frameworks = _profile_value(profile, analysis, "frameworks", default=[])
    databases = _profile_value(profile, analysis, "databases", default=[])
    ai_libraries = _profile_value(
        profile, analysis, "ai_libraries", "ai_ml_libraries", default=[]
    )
    has_tests = bool(_profile_value(profile, analysis, "has_tests", default=False))
    has_ci_cd = bool(_profile_value(profile, analysis, "has_ci_cd", "has_cicd", default=False))
    repo_age_days = _safe_int(_profile_value(profile, analysis, "repo_age_days", default=0))
    repo_age_str = (
        str(_profile_value(profile, analysis, "repo_age_str"))
        if _profile_value(profile, analysis, "repo_age_str") is not None
        else (f"{repo_age_days // 365} years" if repo_age_days else "Unknown")
    )

    profile_rows = [
        ["Primary Language", str(_profile_value(profile, analysis, "primary_language", default="Unknown")), "Has Tests", "Yes" if has_tests else "No"],
        ["Frameworks", ", ".join(frameworks) if isinstance(frameworks, list) and frameworks else "None", "Has CI/CD", "Yes" if has_ci_cd else "No"],
        ["Databases", ", ".join(databases) if isinstance(databases, list) and databases else "None", "AI Libraries", ", ".join(ai_libraries) if isinstance(ai_libraries, list) and ai_libraries else "None"],
        ["Team Size", f"~{_safe_int(_profile_value(profile, analysis, 'team_size', 'estimated_team_size', default=1))} engineer(s)", "Bus Factor", str(_safe_int(_profile_value(profile, analysis, 'bus_factor', default=1)))],
        ["Repo Age", repo_age_str, "Combined Multiplier", f"{combined_multiplier:.2f}x"],
    ]

    profile_table = Table(
        [
            [
                Paragraph(str(cell), s_label if idx % 2 == 0 else s_body)
                for idx, cell in enumerate(row)
            ]
            for row in profile_rows
        ],
        colWidths=[content_width / 4] * 4,
    )
    profile_table.setStyle(
        TableStyle(
            [
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [C_SURFACE, HexColor("#201f1d")]),
                ("GRID", (0, 0), (-1, -1), 0.3, C_BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(profile_table)

    story.append(PageBreak())
    story.append(Paragraph("Top 20 Debt Items", s_h2))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=6))

    debt_items = analysis.get("debt_items") if isinstance(analysis.get("debt_items"), list) else []
    debt_items = sorted(debt_items, key=lambda item: _safe_float(item.get("cost_usd")), reverse=True)[:20]
    debt_rows: list[list[Any]] = [
        [
            Paragraph("<b>#</b>", s_muted),
            Paragraph("<b>File</b>", s_muted),
            Paragraph("<b>Category</b>", s_muted),
            Paragraph("<b>Sev</b>", s_muted),
            Paragraph("<b>Cost</b>", s_muted),
            Paragraph("<b>Hours</b>", s_muted),
        ]
    ]
    for index, item in enumerate(debt_items, start=1):
        severity = str(item.get("severity") or "medium").lower()
        severity_fill = SEV_COLORS.get(severity, C_MUTED)
        debt_rows.append(
            [
                Paragraph(str(index), s_muted),
                Paragraph(clean_file_path(str(item.get("file") or "")), s_mono),
                Paragraph(str(item.get("category") or "").replace("_", " ").title(), s_body),
                Paragraph(
                    f"<font color='#{severity_fill.hexval()[2:]}'>{severity[:3].upper()}</font>",
                    S("DebtSeverity", fontSize=8, fontName="Helvetica-Bold", textColor=severity_fill, leading=11),
                ),
                Paragraph(
                    f"${_safe_float(item.get('cost_usd')):,.0f}",
                    S("DebtCost", fontSize=9, fontName="Helvetica-Bold", textColor=C_WHITE, leading=12),
                ),
                Paragraph(f"{item_hours(item):.1f}h", s_mono_muted),
            ]
        )

    debt_table = Table(
        debt_rows,
        colWidths=[
            content_width * 0.05,
            content_width * 0.40,
            content_width * 0.20,
            content_width * 0.08,
            content_width * 0.14,
            content_width * 0.13,
        ],
    )
    debt_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), C_PRIMARY),
                ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_SURFACE, HexColor("#201f1d")]),
                ("GRID", (0, 0), (-1, -1), 0.3, C_BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(debt_table)
    story.append(Spacer(1, 6 * mm))

    story.append(HRFlowable(width="100%", thickness=0.3, color=C_BORDER, spaceBefore=6))
    data_sources = analysis.get("data_sources") or {}
    source_parts = [str(repo_url), generated]
    if isinstance(data_sources, dict) and data_sources:
        source_parts.insert(0, "Data sources: " + " · ".join(f"{k}:{v}" for k, v in data_sources.items()))
    else:
        source_parts.insert(
            0,
            "Data sources: " + " · ".join(analysis.get("data_sources_used") or ["benchmarks:live", "hourly_rates:live"]),
        )
    story.append(
        Paragraph(
            "  ·  ".join(source_parts),
            S("Footer", fontSize=7, textColor=C_MUTED, alignment=TA_CENTER, leading=10),
        )
    )

    def _page_bg(canvas: Any, doc_obj: Any) -> None:
        canvas.saveState()
        canvas.setFillColor(C_BG)
        canvas.rect(0, 0, page_width, page_height, fill=1, stroke=0)
        canvas.restoreState()

    doc.build(story, onFirstPage=_page_bg, onLaterPages=_page_bg)
    return buffer.getvalue()


class TechDebtPDFGenerator:
    """Compatibility wrapper for existing report generation callers."""

    def generate(self, analysis: dict[str, Any], agent_state: dict[str, Any]) -> bytes:
        result = {
            **agent_state,
            "raw_analysis": analysis,
        }
        if not result.get("github_url"):
            result["github_url"] = analysis.get("github_url") or analysis.get("repo_path")
        return generate_pdf_report(result)
