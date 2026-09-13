import os
from collections import defaultdict
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import Dataset
from app.models.finding import Finding
from app.models.pii_classification import PiiClassification
from app.models.pii_detection import PiiDetection
from app.models.risk_score import RiskScore
from app.pipeline.rules_engine import load_rules

DISCLAIMER_TEXT = (
    "This report reflects automated assessment findings against a configurable rule set based on the "
    "DPDP Act 2023 and DPDP Rules 2025. It is not legal advice and does not constitute a definitive "
    "compliance determination."
)


async def _load_report_data(scan_id: str, db: AsyncSession) -> dict:
    dataset = (await db.execute(select(Dataset).where(Dataset.id == scan_id))).scalar_one()

    classification_rows = (
        await db.execute(
            select(PiiClassification, PiiDetection)
            .join(PiiDetection, PiiClassification.detection_id == PiiDetection.id)
            .where(PiiDetection.scan_id == scan_id)
        )
    ).all()
    category_counts: dict[str, int] = defaultdict(int)
    for classification, _detection in classification_rows:
        category_counts[classification.category] += 1

    findings = (await db.execute(select(Finding).where(Finding.scan_id == scan_id))).scalars().all()
    rules_by_id = {rule["rule_id"]: rule for rule in load_rules()}

    risk_score = (await db.execute(select(RiskScore).where(RiskScore.scan_id == scan_id))).scalar_one_or_none()

    return {
        "dataset": dataset,
        "category_counts": dict(category_counts),
        "findings": findings,
        "rules_by_id": rules_by_id,
        "risk_score": risk_score,
    }


def _build_pdf(file_path: str, scan_id: str, data: dict) -> None:
    styles = getSampleStyleSheet()
    heading_style = styles["Heading2"]
    body_style = styles["BodyText"]
    disclaimer_style = ParagraphStyle(
        "Disclaimer", parent=styles["BodyText"], fontSize=8, textColor=colors.grey
    )

    dataset: Dataset = data["dataset"]
    elements = []

    elements.append(Paragraph("DPDP Compliance Assessment Report", styles["Title"]))
    elements.append(Spacer(1, 0.3 * cm))
    elements.append(Paragraph(f"Dataset: {dataset.filename}", body_style))
    elements.append(Paragraph(f"Scan ID: {scan_id}", body_style))
    elements.append(
        Paragraph(f"Report generated: {datetime.now(timezone.utc).isoformat()}", body_style)
    )
    elements.append(Spacer(1, 0.5 * cm))

    elements.append(Paragraph("PII Summary", heading_style))
    category_counts = data["category_counts"]
    if category_counts:
        table_data = [["Category", "Field Count"]] + [
            [category, str(count)] for category, count in sorted(category_counts.items())
        ]
        table = Table(table_data, colWidths=[10 * cm, 4 * cm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2454ff")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                ]
            )
        )
        elements.append(table)
    else:
        elements.append(Paragraph("No PII detected for this scan.", body_style))
    elements.append(Spacer(1, 0.5 * cm))

    elements.append(Paragraph("Findings", heading_style))
    findings = data["findings"]
    rules_by_id = data["rules_by_id"]
    if findings:
        table_data = [["Rule ID", "Evidence", "Severity", "Remediation"]]
        for finding in findings:
            remediation = rules_by_id.get(finding.rule_id, {}).get("remediation", "—")
            table_data.append([finding.rule_id, finding.evidence, finding.severity, Paragraph(remediation, body_style)])
        table = Table(table_data, colWidths=[2.5 * cm, 3 * cm, 2.5 * cm, 6 * cm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2454ff")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        elements.append(table)
    else:
        elements.append(Paragraph("No findings for this scan.", body_style))
    elements.append(Spacer(1, 0.5 * cm))

    elements.append(Paragraph("Risk Score", heading_style))
    risk_score: RiskScore | None = data["risk_score"]
    if risk_score is not None:
        elements.append(Paragraph(f"Score: {risk_score.score}/100 — Band: {risk_score.band}", body_style))
        breakdown_table_data = [["Factor", "Points", "Reason"]] + [
            [item["factor"], str(item["points_added"]), Paragraph(item["reason"], body_style)]
            for item in risk_score.breakdown
        ]
        breakdown_table = Table(breakdown_table_data, colWidths=[4 * cm, 2 * cm, 8 * cm])
        breakdown_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2454ff")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        elements.append(breakdown_table)
    else:
        elements.append(Paragraph("Risk score not yet computed for this scan.", body_style))
    elements.append(Spacer(1, 1 * cm))

    elements.append(Paragraph(DISCLAIMER_TEXT, disclaimer_style))

    doc = SimpleDocTemplate(file_path, pagesize=A4)
    doc.build(elements)


async def generate_report_pdf(scan_id: str, db: AsyncSession, reports_dir: str = "./reports") -> str:
    data = await _load_report_data(scan_id, db)
    os.makedirs(reports_dir, exist_ok=True)
    file_path = os.path.join(reports_dir, f"{scan_id}.pdf")
    _build_pdf(file_path, scan_id, data)
    return file_path
