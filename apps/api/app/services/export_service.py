import io
import csv
import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import Submission, Answer, Extraction, Cohort

SURVEY_CONFIG_PATH = Path(__file__).resolve().parents[4] / "docs" / "survey-config" / "survey-en.json"


def _load_questions() -> list[tuple[str, str]]:
    """Return (question_id, question_text) pairs in survey order."""
    with open(SURVEY_CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    return [(q["id"], q["text"]) for q in config["questions"]]


def _format_answer(answer_raw: str | None, question_type: str | None = None) -> str:
    if not answer_raw:
        return ""
    if question_type == "multi":
        try:
            items = json.loads(answer_raw)
            if isinstance(items, list):
                return " | ".join(str(item) for item in items)
        except (json.JSONDecodeError, TypeError):
            pass
    return answer_raw


async def _get_submissions(
    db: AsyncSession,
    cohort_id: Optional[uuid.UUID],
    start: Optional[datetime],
    end: Optional[datetime],
) -> list[Submission]:
    query = select(Submission).where(Submission.status == "completed")
    if cohort_id:
        query = query.where(Submission.cohort_id == cohort_id)
    if start:
        query = query.where(Submission.created_at >= start)
    if end:
        query = query.where(Submission.created_at <= end)
    query = query.order_by(Submission.created_at)
    result = await db.execute(query)
    return list(result.scalars().all())


async def generate_raw_csv(
    db: AsyncSession,
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> str:
    questions = _load_questions()
    submissions = await _get_submissions(db, cohort_id, start, end)

    all_rows: list[tuple[Submission, dict[str, Answer]]] = []
    max_followups: dict[str, int] = {qid: 0 for qid, _ in questions}

    for sub in submissions:
        result = await db.execute(
            select(Answer).where(Answer.submission_id == sub.id)
        )
        answers = {a.question_id: a for a in result.scalars().all()}
        all_rows.append((sub, answers))

        for qid, _ in questions:
            a = answers.get(qid)
            if a:
                count = 0
                if a.followup_1:
                    count = 1
                if a.followup_2:
                    count = 2
                max_followups[qid] = max(max_followups[qid], count)

    output = io.StringIO()
    writer = csv.writer(output)

    headers: list[str] = ["RespondentID"]
    for i, (qid, _) in enumerate(questions, 1):
        headers.extend([f"Q{i}", f"A{i}"])
        for j in range(1, max_followups[qid] + 1):
            headers.extend([f"Q{i}_FQ{j}", f"Q{i}_FA{j}"])
    writer.writerow(headers)

    for respondent_id, (sub, answers) in enumerate(all_rows, 1):
        row: list[str] = [str(respondent_id)]
        for qid, qtext in questions:
            a = answers.get(qid)
            row.append(qtext)
            row.append(_format_answer(a.answer_raw if a else None, a.question_type if a else None))
            for j in range(1, max_followups[qid] + 1):
                if a and j == 1:
                    row.extend([a.followup_1 or "", a.followup_1_answer or ""])
                elif a and j == 2:
                    row.extend([a.followup_2 or "", a.followup_2_answer or ""])
                else:
                    row.extend(["", ""])
        writer.writerow(row)

    return output.getvalue()


async def generate_structured_csv(
    db: AsyncSession,
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> str:
    questions = _load_questions()
    start_question_id = questions[0][0] if questions else None
    submissions = await _get_submissions(db, cohort_id, start, end)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["RespondentID", "MainQuestion", "FollowUpQuestions", "Answers"])

    respondent_id = 0

    for sub in submissions:
        result = await db.execute(
            select(Answer).where(Answer.submission_id == sub.id)
        )
        answers = {a.question_id: a for a in result.scalars().all()}

        for qid, qtext in questions:
            a = answers.get(qid)
            if not a:
                continue

            if qid == start_question_id:
                respondent_id += 1

            main_answer = _format_answer(a.answer_raw, a.question_type)

            followup_qs: list[str] = []
            answer_parts: list[str] = [main_answer] if main_answer else []

            if a.followup_1:
                followup_qs.append(a.followup_1)
                if a.followup_1_answer:
                    answer_parts.append(a.followup_1_answer)
            if a.followup_2:
                followup_qs.append(a.followup_2)
                if a.followup_2_answer:
                    answer_parts.append(a.followup_2_answer)

            writer.writerow([
                respondent_id,
                qtext,
                " | ".join(followup_qs),
                " | ".join(answer_parts),
            ])

    return output.getvalue()


async def _gather_report_data(
    db: AsyncSession,
    cohort_id: Optional[uuid.UUID],
    start: Optional[datetime],
    end: Optional[datetime],
) -> dict:
    submissions = await _get_submissions(db, cohort_id, start, end)

    cohort_name = ""
    if cohort_id:
        cohort = await db.get(Cohort, cohort_id)
        cohort_name = cohort.name if cohort else ""

    total = len(submissions)
    scores = []
    all_themes: list[str] = []
    all_barriers: list[str] = []
    all_workflows: list[str] = []
    stories: list[str] = []

    for sub in submissions:
        result = await db.execute(
            select(Answer).where(
                Answer.submission_id == sub.id, Answer.question_id == "q1_recommend"
            )
        )
        rec = result.scalar_one_or_none()
        if rec and rec.answer_raw:
            try:
                scores.append(int(rec.answer_raw))
            except ValueError:
                pass

        extraction = await db.get(Extraction, sub.id)
        if extraction:
            if extraction.top_themes:
                all_themes.extend(extraction.top_themes)
            if extraction.barriers:
                all_barriers.extend(extraction.barriers)
            if extraction.planned_task_or_workflow:
                all_workflows.append(extraction.planned_task_or_workflow)
            if extraction.success_story_candidate:
                stories.append(extraction.success_story_candidate)

    theme_counts: dict[str, int] = {}
    for t in all_themes:
        theme_counts[t] = theme_counts.get(t, 0) + 1
    top_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)[:6]

    barrier_counts: dict[str, int] = {}
    for b in all_barriers:
        barrier_counts[b] = barrier_counts.get(b, 0) + 1
    top_barriers = sorted(barrier_counts.items(), key=lambda x: x[1], reverse=True)[:6]

    return {
        "cohort_name": cohort_name,
        "total_responses": total,
        "avg_recommend": round(sum(scores) / len(scores), 1) if scores else None,
        "top_themes": top_themes,
        "top_barriers": top_barriers,
        "workflows": all_workflows[:10],
        "stories": stories[:6],
        "start_date": start.strftime("%Y-%m-%d") if start else "All time",
        "end_date": end.strftime("%Y-%m-%d") if end else "Present",
    }


async def generate_summary_pdf(
    db: AsyncSession,
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.units import inch

    data = await _gather_report_data(db, cohort_id, start, end)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.75 * inch, bottomMargin=0.75 * inch)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle", parent=styles["Title"],
        textColor=HexColor("#124D8F"), fontSize=20,
    )
    heading_style = ParagraphStyle(
        "CustomHeading", parent=styles["Heading2"],
        textColor=HexColor("#124D8F"), fontSize=14,
    )

    elements = []

    elements.append(Paragraph("InnovateUS Feedback Summary", title_style))
    elements.append(Spacer(1, 12))

    meta = f"Cohort: {data['cohort_name'] or 'All'} | Period: {data['start_date']} — {data['end_date']}"
    elements.append(Paragraph(meta, styles["Normal"]))
    elements.append(Spacer(1, 20))

    elements.append(Paragraph("Key Metrics", heading_style))
    elements.append(Spacer(1, 8))
    metrics_text = f"Total Responses: {data['total_responses']}"
    if data["avg_recommend"]:
        metrics_text += f" | Avg. Recommendation Score: {data['avg_recommend']}/10"
    elements.append(Paragraph(metrics_text, styles["Normal"]))
    elements.append(Spacer(1, 16))

    if data["top_themes"]:
        elements.append(Paragraph("Top Themes", heading_style))
        elements.append(Spacer(1, 8))
        for theme, count in data["top_themes"]:
            elements.append(Paragraph(f"• {theme} ({count})", styles["Normal"]))
        elements.append(Spacer(1, 16))

    if data["top_barriers"]:
        elements.append(Paragraph("Top Barriers", heading_style))
        elements.append(Spacer(1, 8))
        for barrier, count in data["top_barriers"]:
            elements.append(Paragraph(f"• {barrier} ({count})", styles["Normal"]))
        elements.append(Spacer(1, 16))

    if data["stories"]:
        elements.append(Paragraph("Success Stories", heading_style))
        elements.append(Spacer(1, 8))
        for i, story in enumerate(data["stories"], 1):
            elements.append(Paragraph(f'{i}. "{story}"', styles["Normal"]))
            elements.append(Spacer(1, 4))
        elements.append(Spacer(1, 16))

    if data["workflows"]:
        elements.append(Paragraph("Planned Workflows", heading_style))
        elements.append(Spacer(1, 8))
        for wf in data["workflows"][:8]:
            elements.append(Paragraph(f"• {wf}", styles["Normal"]))

    doc.build(elements)
    return buffer.getvalue()


async def generate_summary_pptx(
    db: AsyncSession,
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> bytes:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor

    data = await _gather_report_data(db, cohort_id, start, end)

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    brand_blue = RGBColor(0x12, 0x4D, 0x8F)

    def add_title_slide(title: str, subtitle: str = ""):
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        slide.shapes.title.text = title
        slide.shapes.title.text_frame.paragraphs[0].font.color.rgb = brand_blue
        if subtitle and slide.placeholders[1]:
            slide.placeholders[1].text = subtitle

    def add_content_slide(title: str, bullets: list[str]):
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = title
        slide.shapes.title.text_frame.paragraphs[0].font.color.rgb = brand_blue
        body = slide.placeholders[1]
        tf = body.text_frame
        tf.clear()
        for i, bullet in enumerate(bullets):
            if i == 0:
                tf.paragraphs[0].text = bullet
                tf.paragraphs[0].font.size = Pt(18)
            else:
                p = tf.add_paragraph()
                p.text = bullet
                p.font.size = Pt(18)

    # Slide 1: Title
    cohort_label = data["cohort_name"] or "All Cohorts"
    add_title_slide(
        "InnovateUS Feedback Summary",
        f"{cohort_label} | {data['start_date']} — {data['end_date']}",
    )

    # Slide 2: Participation Metrics
    metrics_bullets = [f"Total Responses: {data['total_responses']}"]
    if data["avg_recommend"]:
        metrics_bullets.append(f"Average Recommendation Score: {data['avg_recommend']}/10")
    add_content_slide("Participation Metrics", metrics_bullets)

    # Slide 3: What Learners Will Try
    workflows = data["workflows"][:6] or ["No data yet"]
    add_content_slide("What Learners Plan to Try", workflows)

    # Slide 4: Barriers
    barrier_bullets = [f"{b} ({c})" for b, c in data["top_barriers"]] or ["No barriers reported"]
    add_content_slide("Barriers Identified", barrier_bullets)

    # Slide 5: Success Stories
    story_bullets = [f'"{s}"' for s in data["stories"][:4]] or ["No success stories yet"]
    add_content_slide("Success Stories", story_bullets)

    # Slide 6: Top Themes
    theme_bullets = [f"{t} ({c})" for t, c in data["top_themes"]] or ["No themes extracted"]
    add_content_slide("Top Themes", theme_bullets)

    # Slide 7: Recommendations
    add_content_slide("Recommendations", [
        "Continue iterating on course content based on feedback",
        "Address identified barriers in future cohorts",
        "Highlight success stories to promote engagement",
    ])

    buffer = io.BytesIO()
    prs.save(buffer)
    return buffer.getvalue()
