"""Export service — generates CSV, PDF, and PPTX from submission data.

All functions receive pre-fetched submission dicts instead of a database session.
"""
import io
import csv
import json
import uuid
from pathlib import Path
from typing import Optional

SURVEY_CONFIG_PATH = Path(__file__).resolve().parents[4] / "docs" / "survey-config" / "survey-en.json"


def _load_default_survey() -> dict:
    with open(SURVEY_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_questions() -> list[tuple[str, str]]:
    """Return (question_id, question_text) pairs in survey order."""
    config = _load_default_survey()
    return [(q["id"], q["text"]) for q in config["questions"]]


def _get_cohort_info(cohort_id: Optional[uuid.UUID]) -> tuple[str, str]:
    """Return (course_name, survey_version) — caller should pass cohort data directly if available."""
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
    headers.extend([
        "TimeToCompleteSec", "VoiceQuestionsUsed", "TextQuestionsUsed",
        "FollowupsReceived", "FollowupsAnswered",
        "ExperienceRating", "ExperienceFeedback",
    ])
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
        # New analytics columns
        all_answers = list(answers.values())
        voice_used = sum(1 for a in all_answers if a.get("input_mode") == "voice")
        text_used = sum(1 for a in all_answers if a.get("input_mode") not in ("voice", "none") or (a.get("question_type") == "open" and a.get("input_mode") != "voice"))
        followups_received = sum(1 for a in all_answers if a.get("followups_asked", 0) > 0 or a.get("followup_1"))
        followups_answered = sum(1 for a in all_answers if a.get("followup_1_answer"))
        row.extend([
            str(sub.get("time_to_complete_sec") or ""),
            str(voice_used),
            str(text_used),
            str(followups_received),
            str(followups_answered),
            str(sub.get("experience_rating") or ""),
            sub.get("experience_feedback") or "",
        ])
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
    writer.writerow(["RespondentID", "CourseName", "SurveyVersion", "MainQuestion", "FollowUpQuestions", "Answers", "VoiceUsed", "IsVague", "FollowupsAsked", "FollowupAnswered", "ExperienceRating"])

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

            is_vague = "Yes" if a.get("is_vague") else "No" if a.get("is_vague") is not None else ""
            followups_asked = str(a.get("followups_asked", 0))
            followup_answered = "Yes" if a.get("followup_1_answer") else "No" if a.get("followup_1") else ""

            writer.writerow([
                respondent_id,
                course_name,
                sv,
                qtext,
                " | ".join(followup_qs),
                " | ".join(answer_parts),
                voice_used,
                is_vague,
                followups_asked,
                followup_answered,
                str(sub.get("experience_rating") or ""),
            ])

    return output.getvalue()


def _gather_report_data(
    submissions: list[dict],
    cohort_id: Optional[uuid.UUID],
) -> dict:
    cohort_name = ""
    course_name = ""
    survey_version = "1.0"

    if submissions:
        # Pick cohort info from the first submission's data if available
        first = submissions[0]
        cohort_name = first.get("cohort_name", "")
        course_name = first.get("course_name", "")
        survey_version = first.get("survey_version") or "1.0"

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


def generate_user_testing_csv(
    submissions: list[dict],
    events: list[dict],
    cohort_id: Optional[uuid.UUID] = None,
) -> str:
    """Generate a CSV focused on user testing metrics with one row per submission."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "SubmissionId", "CohortId", "Status", "StartedAt", "CompletedAt",
        "TimeToCompleteSec", "SurveyVersion",
        "TotalQuestionsAnswered", "VoiceQuestionsCount", "TextQuestionsCount",
        "FollowupsTriggered", "FollowupsAnswered", "FollowupsSkipped",
        "VagueAnswersVoice", "VagueAnswersText",
        "ExperienceRating", "ExperienceFeedback",
        "ReviewEdits",
    ])

    # Build event lookup: submission_id -> list of events
    events_by_sub: dict[str, list[dict]] = {}
    for evt in events:
        sid = evt.get("submission_id", "")
        if sid:
            events_by_sub.setdefault(sid, []).append(evt)

    # Also count review edits by session
    review_edits_by_session: dict[str, int] = {}
    for evt in events:
        if evt.get("event_type") == "review_edit":
            session = evt.get("session_token", "")
            review_edits_by_session[session] = review_edits_by_session.get(session, 0) + 1

    for sub in submissions:
        sub_id = sub.get("submission_id", "")
        answers = sub.get("answers", [])
        open_answers = [a for a in answers if a.get("question_type") == "open"]

        voice_count = sum(1 for a in open_answers if a.get("input_mode") == "voice")
        text_count = sum(1 for a in open_answers if a.get("input_mode") != "voice")
        followups_triggered = sum(1 for a in answers if a.get("followup_1"))
        followups_answered = sum(1 for a in answers if a.get("followup_1_answer"))
        followups_skipped = followups_triggered - followups_answered
        vague_voice = sum(1 for a in open_answers if a.get("is_vague") and a.get("input_mode") == "voice")
        vague_text = sum(1 for a in open_answers if a.get("is_vague") and a.get("input_mode") != "voice")

        # Count review edits from events for this submission
        sub_events = events_by_sub.get(sub_id, [])
        review_edit_count = sum(1 for e in sub_events if e.get("event_type") == "review_edit")

        writer.writerow([
            sub_id,
            sub.get("cohort_id", ""),
            sub.get("status", ""),
            sub.get("created_at", ""),
            sub.get("completed_at", ""),
            str(sub.get("time_to_complete_sec") or ""),
            sub.get("survey_version", ""),
            str(len(answers)),
            str(voice_count),
            str(text_count),
            str(followups_triggered),
            str(followups_answered),
            str(followups_skipped),
            str(vague_voice),
            str(vague_text),
            str(sub.get("experience_rating") or ""),
            sub.get("experience_feedback") or "",
            str(review_edit_count),
        ])

    return output.getvalue()
