"""Export service — generates CSV, PDF, and PPTX from DynamoDB submission data.

All functions now receive pre-fetched submission dicts (from DynamoDB)
instead of taking a database session.
"""
import io
import csv
import json
import uuid
from pathlib import Path
from typing import Optional
from app.dynamo import get_surveys_table

SURVEY_CONFIG_PATH = Path(__file__).resolve().parents[4] / "docs" / "survey-config" / "survey-en.json"


def _load_default_survey() -> dict:
    with open(SURVEY_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_questions() -> list[tuple[str, str]]:
    """Return (question_id, question_text) pairs in survey order."""
    config = _load_default_survey()
    return [(q["id"], q["text"]) for q in config["questions"]]


def _get_cohort_info(cohort_id: Optional[uuid.UUID]) -> tuple[str, str]:
    """Return (course_name, survey_version) for a cohort."""
    if not cohort_id:
        return ("", "1.0")
    table = get_surveys_table()
    result = table.get_item(Key={"pk": f"COHORT#{cohort_id}", "sk": "METADATA"})
    item = result.get("Item")
    if item:
        config = item.get("survey_config") or {}
        version = config.get("version", "1.0")
        return (item.get("course_name", ""), version)
    return ("", "1.0")


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


def generate_raw_csv(
    submissions: list[dict],
    cohort_id: Optional[uuid.UUID] = None,
) -> str:
    questions = _load_questions()
    course_name, default_version = _get_cohort_info(cohort_id)

    # Determine max followups per question
    max_followups: dict[str, int] = {qid: 0 for qid, _ in questions}
    for sub in submissions:
        answers = {a["question_id"]: a for a in sub.get("answers", [])}
        for qid, _ in questions:
            a = answers.get(qid)
            if a:
                count = 0
                if a.get("followup_1"):
                    count = 1
                if a.get("followup_2"):
                    count = 2
                max_followups[qid] = max(max_followups[qid], count)

    output = io.StringIO()
    writer = csv.writer(output)

    # Headers
    headers: list[str] = ["RespondentID", "CourseName", "SurveyVersion"]
    for i, (qid, _) in enumerate(questions, 1):
        headers.extend([f"Q{i}", f"A{i}", f"A{i}_Voice"])
        for j in range(1, max_followups[qid] + 1):
            headers.extend([f"Q{i}_FQ{j}", f"Q{i}_FA{j}"])
    writer.writerow(headers)

    # Data rows
    for respondent_id, sub in enumerate(submissions, 1):
        answers = {a["question_id"]: a for a in sub.get("answers", [])}
        sv = sub.get("survey_version") or default_version
        row: list[str] = [str(respondent_id), course_name, sv]
        for qid, qtext in questions:
            a = answers.get(qid)
            row.append(qtext)
            row.append(_format_answer(a.get("answer_raw") if a else None, a.get("question_type") if a else None))
            row.append("Yes" if a and a.get("input_mode") == "voice" else "No")
            for j in range(1, max_followups[qid] + 1):
                if a and j == 1:
                    row.extend([a.get("followup_1") or "", a.get("followup_1_answer") or ""])
                elif a and j == 2:
                    row.extend([a.get("followup_2") or "", a.get("followup_2_answer") or ""])
                else:
                    row.extend(["", ""])
        writer.writerow(row)

    return output.getvalue()


def generate_structured_csv(
    submissions: list[dict],
    cohort_id: Optional[uuid.UUID] = None,
) -> str:
    questions = _load_questions()
    start_question_id = questions[0][0] if questions else None
    course_name, default_version = _get_cohort_info(cohort_id)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["RespondentID", "CourseName", "SurveyVersion", "MainQuestion", "FollowUpQuestions", "Answers", "VoiceUsed"])

    respondent_id = 0

    for sub in submissions:
        answers = {a["question_id"]: a for a in sub.get("answers", [])}
        sv = sub.get("survey_version") or default_version

        for qid, qtext in questions:
            a = answers.get(qid)
            if not a:
                continue

            if qid == start_question_id:
                respondent_id += 1

            main_answer = _format_answer(a.get("answer_raw"), a.get("question_type"))

            followup_qs: list[str] = []
            answer_parts: list[str] = [main_answer] if main_answer else []

            if a.get("followup_1"):
                followup_qs.append(a["followup_1"])
                if a.get("followup_1_answer"):
                    answer_parts.append(a["followup_1_answer"])
            if a.get("followup_2"):
                followup_qs.append(a["followup_2"])
                if a.get("followup_2_answer"):
                    answer_parts.append(a["followup_2_answer"])

            voice_used = "Yes" if a.get("input_mode") == "voice" else "No"

            writer.writerow([
                respondent_id,
                course_name,
                sv,
                qtext,
                " | ".join(followup_qs),
                " | ".join(answer_parts),
                voice_used,
            ])

    return output.getvalue()


def _gather_report_data(
    submissions: list[dict],
    cohort_id: Optional[uuid.UUID],
) -> dict:
    cohort_name = ""
    course_name = ""
    survey_version = "1.0"

    if cohort_id:
        table = get_surveys_table()
        result = table.get_item(Key={"pk": f"COHORT#{cohort_id}", "sk": "METADATA"})
        item = result.get("Item")
        if item:
            cohort_name = item.get("name", "")
            course_name = item.get("course_name", "")
            config = item.get("survey_config") or {}
            survey_version = config.get("version", "1.0")

    total = len(submissions)
    scores = []
    all_themes: list[str] = []
    all_barriers: list[str] = []
    all_workflows: list[str] = []
    stories: list[str] = []

    for sub in submissions:
        # Recommendation score
        for a in sub.get("answers", []):
            if a.get("question_id") == "q1_recommend" and a.get("answer_raw"):
                try:
                    scores.append(int(a["answer_raw"]))
                except ValueError:
                    pass

        # Extraction data
        extraction = sub.get("extraction")
        if extraction:
            if extraction.get("top_themes"):
                all_themes.extend(extraction["top_themes"])
            if extraction.get("barriers"):
                all_barriers.extend(extraction["barriers"])
            if extraction.get("planned_task_or_workflow"):
                all_workflows.append(extraction["planned_task_or_workflow"])
            if extraction.get("success_story_candidate"):
                stories.append(extraction["success_story_candidate"])

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
        "course_name": course_name,
        "survey_version": survey_version,
        "total_responses": total,
        "avg_recommend": round(sum(scores) / len(scores), 1) if scores else None,
        "top_themes": top_themes,
        "top_barriers": top_barriers,
        "workflows": all_workflows[:10],
        "stories": stories[:6],
    }


def generate_summary_pdf(
    submissions: list[dict],
    cohort_id: Optional[uuid.UUID] = None,
) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.units import inch

    data = _gather_report_data(submissions, cohort_id)

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

    meta = f"Cohort: {data['cohort_name'] or 'All'}"
    elements.append(Paragraph(meta, styles["Normal"]))
    if data["course_name"]:
        course_meta = f"Course: {data['course_name']} | Survey Version: {data['survey_version']}"
        elements.append(Paragraph(course_meta, styles["Normal"]))
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


def generate_summary_pptx(
    submissions: list[dict],
    cohort_id: Optional[uuid.UUID] = None,
) -> bytes:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor

    data = _gather_report_data(submissions, cohort_id)

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

    cohort_label = data["cohort_name"] or "All Cohorts"
    subtitle = cohort_label
    if data["course_name"]:
        subtitle += f"\nCourse: {data['course_name']} | Survey v{data['survey_version']}"
    add_title_slide("InnovateUS Feedback Summary", subtitle)

    metrics_bullets = [f"Total Responses: {data['total_responses']}"]
    if data["avg_recommend"]:
        metrics_bullets.append(f"Average Recommendation Score: {data['avg_recommend']}/10")
    add_content_slide("Participation Metrics", metrics_bullets)

    workflows = data["workflows"][:6] or ["No data yet"]
    add_content_slide("What Learners Plan to Try", workflows)

    barrier_bullets = [f"{b} ({c})" for b, c in data["top_barriers"]] or ["No barriers reported"]
    add_content_slide("Barriers Identified", barrier_bullets)

    story_bullets = [f'"{s}"' for s in data["stories"][:4]] or ["No success stories yet"]
    add_content_slide("Success Stories", story_bullets)

    theme_bullets = [f"{t} ({c})" for t, c in data["top_themes"]] or ["No themes extracted"]
    add_content_slide("Top Themes", theme_bullets)

    add_content_slide("Recommendations", [
        "Continue iterating on course content based on feedback",
        "Address identified barriers in future cohorts",
        "Highlight success stories to promote engagement",
    ])

    buffer = io.BytesIO()
    prs.save(buffer)
    return buffer.getvalue()
