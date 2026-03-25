from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table,
    TableStyle, HRFlowable, PageBreak
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER
import io
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

PURPLE       = HexColor('#8b5cf6')
DARK_BG      = HexColor('#1f2937')
CARD_BG      = HexColor('#111827')
LIGHT_GRAY   = HexColor('#9ca3af')
WHITE        = HexColor('#ffffff')
GREEN        = HexColor('#10b981')
RED          = HexColor('#ef4444')
YELLOW       = HexColor('#f59e0b')
DARK_PURPLE  = HexColor('#6d28d9')


class TechDebtPDFGenerator:
    """Generates a professional executive PDF report from a Tech Debt analysis."""

    def __init__(self) -> None:
        self.styles = getSampleStyleSheet()
        self._build_custom_styles()

    def _build_custom_styles(self) -> None:
        self.title_style = ParagraphStyle(
            'TDTitle', parent=self.styles['Title'],
            fontSize=28, textColor=WHITE, spaceAfter=6,
            fontName='Helvetica-Bold', alignment=TA_LEFT,
        )
        self.subtitle_style = ParagraphStyle(
            'TDSubtitle', parent=self.styles['Normal'],
            fontSize=12, textColor=LIGHT_GRAY, spaceAfter=4,
            fontName='Helvetica',
        )
        self.section_header_style = ParagraphStyle(
            'TDSectionHeader', parent=self.styles['Heading1'],
            fontSize=14, textColor=PURPLE, spaceBefore=16,
            spaceAfter=8, fontName='Helvetica-Bold',
        )
        self.body_style = ParagraphStyle(
            'TDBody', parent=self.styles['Normal'],
            fontSize=10, textColor=HexColor('#d1d5db'),
            spaceAfter=6, fontName='Helvetica', leading=16,
        )
        self.metric_label_style = ParagraphStyle(
            'TDMetricLabel', parent=self.styles['Normal'],
            fontSize=9, textColor=LIGHT_GRAY,
            fontName='Helvetica', alignment=TA_CENTER,
        )
        self.metric_value_style = ParagraphStyle(
            'TDMetricValue', parent=self.styles['Normal'],
            fontSize=20, textColor=WHITE,
            fontName='Helvetica-Bold', alignment=TA_CENTER,
        )
        self.small_style = ParagraphStyle(
            'TDSmall', parent=self.styles['Normal'],
            fontSize=8, textColor=LIGHT_GRAY,
            fontName='Helvetica',
        )

    def generate(self, analysis: dict, agent_state: dict) -> bytes:
        """Generate PDF and return as bytes."""
        buffer = io.BytesIO()

        doc = SimpleDocTemplate(
            buffer, pagesize=letter,
            rightMargin=0.6 * inch, leftMargin=0.6 * inch,
            topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        )

        story = []
        story += self._build_cover(analysis, agent_state)
        story += self._build_executive_summary(agent_state)
        story += self._build_metrics_section(analysis)
        story += self._build_cost_breakdown(analysis)
        story += self._build_priority_actions(agent_state)
        story += self._build_roi_section(agent_state)
        story += self._build_repo_profile(analysis)
        story += self._build_top_debt_items(analysis)
        story += self._build_footer_section(analysis)

        doc.build(
            story,
            onFirstPage=self._draw_page_background,
            onLaterPages=self._draw_page_background,
        )

        buffer.seek(0)
        return buffer.read()

    def _draw_page_background(self, canvas: object, doc: object) -> None:
        """Draw dark background on every page."""
        canvas.saveState()
        canvas.setFillColor(CARD_BG)
        canvas.rect(0, 0, letter[0], letter[1], fill=1, stroke=0)
        canvas.setFillColor(PURPLE)
        canvas.rect(0, letter[1] - 6, letter[0], 6, fill=1, stroke=0)
        canvas.setFillColor(LIGHT_GRAY)
        canvas.setFont('Helvetica', 8)
        canvas.drawRightString(letter[0] - 0.6 * inch, 0.3 * inch, f"Page {doc.page}")
        canvas.restoreState()

    def _build_cover(self, analysis: dict, agent_state: dict) -> list:
        story = []
        story.append(Spacer(1, 0.3 * inch))
        story.append(Paragraph("Tech Debt Quantifier", self.title_style))
        story.append(Paragraph("Technical Debt Analysis Report", self.subtitle_style))

        repo_url = analysis.get('repo_path') or agent_state.get('github_url', 'Unknown')
        story.append(Paragraph(f"Repository: <b>{repo_url}</b>", self.body_style))
        story.append(Paragraph(
            f"Generated: {datetime.now().strftime('%B %d, %Y at %H:%M')}",
            self.small_style
        ))
        story.append(Spacer(1, 0.2 * inch))
        story.append(HRFlowable(width="100%", thickness=1, color=PURPLE, spaceAfter=12))

        score = analysis.get('debt_score', 0)
        total = analysis.get('total_cost_usd', 0)
        hours = analysis.get('total_remediation_hours', 0)
        sprints = analysis.get('total_remediation_sprints', 0)

        score_color = '#10b981' if score <= 3 else '#f59e0b' if score <= 6 else '#ef4444'

        hero_data = [
            [
                Paragraph("DEBT SCORE", self.metric_label_style),
                Paragraph("TOTAL COST", self.metric_label_style),
                Paragraph("REMEDIATION", self.metric_label_style),
                Paragraph("SPRINTS", self.metric_label_style),
            ],
            [
                Paragraph(f'<font color="{score_color}">{score:.1f}/10</font>', self.metric_value_style),
                Paragraph(f'${total:,.0f}', self.metric_value_style),
                Paragraph(f'{hours:.0f} hrs', self.metric_value_style),
                Paragraph(f'{sprints:.1f}', self.metric_value_style),
            ],
        ]

        hero_table = Table(hero_data, colWidths=[1.8 * inch] * 4)
        hero_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), DARK_BG),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 14),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
            ('LINEAFTER', (0, 0), (2, -1), 0.5, HexColor('#374151')),
        ]))
        story.append(hero_table)
        story.append(Spacer(1, 0.15 * inch))
        return story

    def _build_executive_summary(self, agent_state: dict) -> list:
        summary = agent_state.get('executive_summary')
        if not summary:
            return []

        story = []
        story.append(Paragraph("Executive Summary", self.section_header_style))

        summary_data = [[Paragraph(summary, self.body_style)]]
        summary_table = Table(summary_data, colWidths=[7.3 * inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), DARK_BG),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('LEFTPADDING', (0, 0), (-1, -1), 14),
            ('RIGHTPADDING', (0, 0), (-1, -1), 14),
            ('LINEBEFORE', (0, 0), (0, -1), 3, PURPLE),
        ]))
        story.append(summary_table)
        return story

    def _build_cost_breakdown(self, analysis: dict) -> list:
        categories = analysis.get('cost_by_category', {})
        if not categories:
            return []

        story = []
        story.append(Paragraph("Cost by Category", self.section_header_style))

        total = analysis.get('total_cost_usd', 1)

        rows = [[
            Paragraph('<b>Category</b>', self.body_style),
            Paragraph('<b>Cost</b>', self.body_style),
            Paragraph('<b>Hours</b>', self.body_style),
            Paragraph('<b>Issues</b>', self.body_style),
            Paragraph('<b>% of Total</b>', self.body_style),
        ]]

        cat_colors = {
            'code_quality': '#8b5cf6', 'security': '#ef4444',
            'documentation': '#3b82f6', 'dependency': '#f59e0b',
            'test_debt': '#10b981',
        }

        for cat, data in sorted(
            categories.items(),
            key=lambda x: x[1].get('cost_usd', 0) if isinstance(x[1], dict) else 0,
            reverse=True
        ):
            if not isinstance(data, dict):
                continue
            cost = data.get('cost_usd', 0)
            hours = data.get('hours', 0)
            items = data.get('item_count', 0)
            pct = (cost / total * 100) if total else 0
            color = cat_colors.get(cat, '#6b7280')
            label = cat.replace('_', ' ').title()

            rows.append([
                Paragraph(f'<font color="{color}">■</font> {label}', self.body_style),
                Paragraph(f'${cost:,.0f}', self.body_style),
                Paragraph(f'{hours:.1f}h', self.body_style),
                Paragraph(str(items), self.body_style),
                Paragraph(f'{pct:.1f}%', self.body_style),
            ])

        cat_table = Table(rows, colWidths=[2.4*inch, 1.3*inch, 1.0*inch, 0.9*inch, 1.4*inch])
        cat_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), DARK_PURPLE),
            ('BACKGROUND', (0, 1), (-1, -1), DARK_BG),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [DARK_BG, HexColor('#1a2435')]),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('LINEBELOW', (0, 0), (-1, 0), 0.5, PURPLE),
        ]))
        story.append(cat_table)
        return story

    def _build_metrics_section(self, analysis: dict) -> list:
        story = []
        story.append(Paragraph("Key Metrics", self.section_header_style))

        sanity = analysis.get('sanity_check', {})
        rates = analysis.get('hourly_rates', {})
        profile = analysis.get('repo_profile', {})
        team = profile.get('team', {}) if profile else {}
        mults = profile.get('multipliers', {}) if profile else {}

        raw_rows = [
            ['Metric', 'Value', 'Source'],
            ['Hourly Rate Used',
             f"${rates.get('blended_rate', 84.55):.2f}/hr",
             f"Confidence: {rates.get('confidence', 'N/A')}"],
            ['Cost per Function',
             f"${sanity.get('your_cost_per_function', 0):,.0f}",
             'Industry avg: $1,083/fn'],
            ['Variance vs Industry',
             f"{sanity.get('variance_pct', 0):+.1f}%",
             sanity.get('assessment', '')],
            ['Combined Multiplier',
             f"{mults.get('combined_multiplier', 1.0):.2f}x",
             'Bus factor x age x team'],
            ['Team Size',
             str(team.get('estimated_team_size', '?')),
             'From git history'],
            ['Bus Factor',
             str(team.get('bus_factor', '?')),
             '1 = high risk'],
            ['Repo Age',
             f"{team.get('repo_age_days', 0) // 365} years",
             f"{team.get('repo_age_days', 0)} days"],
        ]

        styled_rows = []
        for i, row in enumerate(raw_rows):
            if i == 0:
                styled_rows.append([
                    Paragraph(f'<b>{row[0]}</b>', self.body_style),
                    Paragraph(f'<b>{row[1]}</b>', self.body_style),
                    Paragraph(f'<b>{row[2]}</b>', self.small_style),
                ])
            else:
                styled_rows.append([
                    Paragraph(row[0], self.body_style),
                    Paragraph(row[1], self.body_style),
                    Paragraph(row[2], self.small_style),
                ])

        metrics_table = Table(styled_rows, colWidths=[2.4*inch, 1.8*inch, 3.1*inch])
        metrics_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), DARK_PURPLE),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [DARK_BG, HexColor('#1a2435')]),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('LINEBELOW', (0, 0), (-1, 0), 0.5, PURPLE),
        ]))
        story.append(metrics_table)
        return story

    def _build_priority_actions(self, agent_state: dict) -> list:
        actions = agent_state.get('priority_actions', [])
        if not actions:
            return []

        story = []
        story.append(Paragraph("Top Priority Actions", self.section_header_style))

        rank_colors = ['#ef4444', '#f59e0b', '#3b82f6']
        rank_labels = ['Fix First', 'Fix Second', 'Fix Third']

        for i, action in enumerate(actions[:3]):
            if 'error' in action:
                continue
            color = rank_colors[i] if i < 3 else '#6b7280'
            label = rank_labels[i] if i < 3 else f'#{i+1}'

            action_data = [
                [
                    Paragraph(
                        f'<font color="{color}">●</font> '
                        f'<b>{label}</b> — {action.get("title", "")}',
                        self.body_style
                    ),
                    Paragraph(action.get('sprint', ''), self.small_style),
                ],
                [
                    Paragraph(f'File: {action.get("file_or_module", "")}', self.small_style),
                    Paragraph('', self.small_style),
                ],
                [
                    Paragraph(action.get('why', ''), self.body_style),
                    Paragraph('', self.small_style),
                ],
                [
                    Paragraph(
                        f'Fix Cost: <b>${action.get("estimated_cost", 0):,.0f}</b>'
                        f' ({action.get("estimated_hours", 0)}h)   '
                        f'Saves: <b>${action.get("saves_per_month", 0):,.0f}/mo</b>',
                        self.body_style
                    ),
                    Paragraph('', self.small_style),
                ],
            ]

            action_table = Table(action_data, colWidths=[5.8*inch, 1.5*inch])
            action_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), DARK_BG),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('LEFTPADDING', (0, 0), (-1, -1), 12),
                ('LINEBEFORE', (0, 0), (0, -1), 3, HexColor(color)),
            ]))
            story.append(action_table)
            story.append(Spacer(1, 0.08 * inch))

        return story

    def _build_roi_section(self, agent_state: dict) -> list:
        roi = agent_state.get('roi_analysis', {})
        if not roi or roi.get('annual_maintenance_savings', 0) == 0:
            return []

        story = []
        story.append(Paragraph("ROI Analysis", self.section_header_style))

        roi_data = [
            [
                Paragraph("Annual Savings", self.metric_label_style),
                Paragraph("Payback Period", self.metric_label_style),
                Paragraph("3-Year ROI", self.metric_label_style),
                Paragraph("Quarterly Budget", self.metric_label_style),
            ],
            [
                Paragraph(
                    f'<font color="#10b981">${roi.get("annual_maintenance_savings", 0):,.0f}</font>',
                    self.metric_value_style
                ),
                Paragraph(f'{roi.get("payback_months", 0)} mo', self.metric_value_style),
                Paragraph(f'{roi.get("3_year_roi_pct", 0)}%', self.metric_value_style),
                Paragraph(f'${roi.get("recommended_budget", 0):,.0f}', self.metric_value_style),
            ],
        ]

        roi_table = Table(roi_data, colWidths=[1.8*inch] * 4)
        roi_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), DARK_BG),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 14),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
            ('LINEAFTER', (0, 0), (2, -1), 0.5, HexColor('#374151')),
        ]))
        story.append(roi_table)

        rec = roi.get('recommendation', '')
        if rec:
            story.append(Spacer(1, 0.1*inch))
            story.append(Paragraph(f'<i>"{rec}"</i>', self.body_style))

        return story

    def _build_repo_profile(self, analysis: dict) -> list:
        profile = analysis.get('repo_profile', {})
        if not profile:
            return []

        story = []
        story.append(Paragraph("Repository Profile", self.section_header_style))

        tech = profile.get('tech_stack', {})
        team = profile.get('team', {})
        mults = profile.get('multipliers', {})

        frameworks = ', '.join(tech.get('frameworks', [])) or 'N/A'
        ai_libs = ', '.join(tech.get('ai_ml_libraries', [])) or 'None'
        dbs = ', '.join(tech.get('databases', [])) or 'None'

        profile_data = [
            ['Primary Language', tech.get('primary_language', 'Unknown'),
             'Has Tests', 'Yes' if tech.get('has_tests') else 'No'],
            ['Frameworks', frameworks,
             'Has CI/CD', 'Yes' if tech.get('has_ci_cd') else 'No'],
            ['Databases', dbs,
             'AI Libraries', ai_libs],
            ['Team Size', f"~{team.get('estimated_team_size', '?')} engineers",
             'Bus Factor', str(team.get('bus_factor', '?'))],
            ['Repo Age', f"{(team.get('repo_age_days', 0) or 0) // 365} years",
             'Combined Multiplier', f"{mults.get('combined_multiplier', 1.0):.2f}x"],
        ]

        styled = []
        for row in profile_data:
            styled.append([
                Paragraph(row[0], self.small_style),
                Paragraph(str(row[1]), self.body_style),
                Paragraph(row[2], self.small_style),
                Paragraph(str(row[3]), self.body_style),
            ])

        prof_table = Table(styled, colWidths=[1.5*inch, 2.1*inch, 1.5*inch, 2.2*inch])
        prof_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), DARK_BG),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [DARK_BG, HexColor('#1a2435')]),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('LINEAFTER', (1, 0), (1, -1), 0.5, HexColor('#374151')),
        ]))
        story.append(prof_table)
        return story

    def _build_top_debt_items(self, analysis: dict) -> list:
        items = analysis.get('debt_items', [])
        if not items:
            return []

        story = []
        story.append(PageBreak())
        story.append(Paragraph("Top 20 Debt Items", self.section_header_style))

        top = sorted(items, key=lambda x: x.get('cost_usd', 0), reverse=True)[:20]

        def clean_path(p: str) -> str:
            if not p:
                return 'unknown'
            p = re.sub(r'^/tmp/repos/[^/]+/', '', str(p))
            p = re.sub(r':\?$|:\d+$', '', p)
            return p[:45] + '...' if len(p) > 45 else p

        rows = [[
            Paragraph('<b>#</b>', self.small_style),
            Paragraph('<b>File</b>', self.small_style),
            Paragraph('<b>Category</b>', self.small_style),
            Paragraph('<b>Sev</b>', self.small_style),
            Paragraph('<b>Cost</b>', self.small_style),
            Paragraph('<b>Hours</b>', self.small_style),
        ]]

        sev_colors = {
            'critical': '#ef4444', 'high': '#f59e0b',
            'medium': '#3b82f6', 'low': '#6b7280',
        }

        for i, item in enumerate(top, 1):
            sev = (item.get('severity') or 'low').lower()
            color = sev_colors.get(sev, '#6b7280')
            cost = item.get('cost_usd', 0)
            hours = (item.get('adjusted_minutes', 0) or 0) / 60

            rows.append([
                Paragraph(str(i), self.small_style),
                Paragraph(clean_path(item.get('file', '')), self.small_style),
                Paragraph((item.get('category') or '').replace('_', ' ').title(), self.small_style),
                Paragraph(f'<font color="{color}">{sev[:3].upper()}</font>', self.small_style),
                Paragraph(f'${cost:,.0f}', self.small_style),
                Paragraph(f'{hours:.1f}h', self.small_style),
            ])

        items_table = Table(rows, colWidths=[0.3*inch, 2.8*inch, 1.3*inch, 0.5*inch, 0.9*inch, 0.7*inch])
        items_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), DARK_PURPLE),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [DARK_BG, HexColor('#1a2435')]),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('LINEBELOW', (0, 0), (-1, 0), 0.5, PURPLE),
        ]))
        story.append(items_table)
        return story

    def _build_footer_section(self, analysis: dict) -> list:
        story = []
        story.append(Spacer(1, 0.2 * inch))
        story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor('#374151'), spaceAfter=10))

        sources = analysis.get('data_sources_used', [])
        sources_text = ' · '.join(sources) if sources else 'N/A'

        story.append(Paragraph(
            f'<font color="#6b7280">Data sources: {sources_text}'
            f' · Generated by Tech Debt Quantifier</font>',
            self.small_style
        ))
        return story
