from html import escape
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import Project

FONT_DIR = Path(__file__).resolve().parent.parent / "assets"


def specification(project: Project) -> bytes:
    for name, file in [("PW", "DejaVuSans.ttf"), ("PW-Bold", "DejaVuSans-Bold.ttf")]:
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))
    pdfmetrics.registerFontFamily("PW", normal="PW", bold="PW-Bold")
    output = BytesIO()
    doc = SimpleDocTemplate(output, title=f"PackWise - {project.name}", leftMargin=42, rightMargin=42, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("PWBody", fontName="PW", fontSize=9, leading=13, spaceAfter=7))
    styles.add(ParagraphStyle("PWTitle", fontName="PW-Bold", fontSize=23, leading=28, textColor=colors.HexColor("#163C32"), spaceAfter=14))
    styles.add(ParagraphStyle("PWHeading", fontName="PW-Bold", fontSize=12, leading=17, spaceBefore=12, spaceAfter=6))
    p = lambda s: Paragraph(escape(str(s)), styles["PWBody"])
    h = lambda s: Paragraph(escape(str(s)), styles["PWHeading"])
    story = [Paragraph("PackWise / Packaging specification", styles["PWTitle"]), h(project.name), p(f"Record {project.id} · revision {project.revision} · {project.created_at.isoformat()}"), p(project.result["notice"]), p(project.result["message"]), h("Food and operating conditions")]
    for key, value in project.inputs.items():
        if value is not None and key != "stages":
            story.append(p(f"{key.replace('_', ' ')}: {value}"))
    story.append(h("Storage journey"))
    for stage in project.result["stages"]:
        story.append(p(f"{stage['name']}: {stage['days']} days, {stage['temperature_c']} °C, {stage['relative_humidity']}% RH"))
    story.append(h("Calculated screening requirements"))
    for key, value in project.result["requirements"].items():
        story.append(p(f"{key.replace('_', ' ')}: {value if value is not None else 'Not applicable / insufficient evidence'}"))
    candidates = project.result["candidates"]
    if project.selected_material_id:
        candidates = sorted(candidates, key=lambda x: x["material_id"] != project.selected_material_id)
    for i, candidate in enumerate(candidates[:8], 1):
        m = candidate["material_snapshot"]
        story.extend([h(f"{i}. {candidate['name']}"), p("SELECTED FOR TRIAL" if candidate["material_id"] == project.selected_material_id else "Trial candidate"), p(m["source"])])
        rows = [[p("Property"), p("Specification / assumption")]]
        for label, value in [
            ("Grade / structure", f"{m['grade']} / {m['structure']}"), ("Thickness", f"{m['thickness_um']} µm"),
            ("OTR", f"{m['otr']} {m['otr_unit']} / {m['otr_test']}"), ("WVTR", f"{m['wvtr']} {m['wvtr_unit']} / {m['wvtr_test']}"),
            ("Sealing", m["seal_range_c"]), ("Mechanical", m["mechanical"]), ("Estimated quality days", f"{candidate['quality_range_days']} / {candidate['interval_type']}"),
            ("Packaging / total cost", f"INR {candidate['cost_inr']} / INR {candidate['total_cost_inr']} per pack"),
            ("Loss assumption", f"{candidate['loss_assumption_percent']}% (user supplied)"), ("Material / recovery", f"{candidate['material_mass_g']} g / {m['recovery']}"),
        ]:
            rows.append([p(label), p(value)])
        table = Table(rows, colWidths=[130, 370], repeatRows=1)
        table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E7F3EC")), ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#CBDDD4")), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 6)]))
        story.append(table)
        if candidate["gas"]:
            gas = candidate["gas"]
            story.extend([p(f"Gas screening: equilibrium O2 {gas['equilibrium_o2_pct']}%, CO2 {gas['equilibrium_co2_pct']}%. Initial atmosphere: air."), p(gas["method"]), p(gas["microperforation"])])
        for reason in candidate["reasons"] + candidate["documents_needed"]:
            story.append(p(f"• {reason}"))
    story.append(h("Rejected alternatives"))
    for candidate in project.result["rejected"]:
        story.append(p(f"{candidate['name']}: {'; '.join(candidate['failures'])}"))
    for heading, lines in [("Assumptions", project.result["assumptions"]), ("Next measurements", project.result["next_measurements"]), ("Target changes", project.result["suggested_changes"])]:
        story.append(h(heading))
        story.extend(p(line) for line in lines)
    story.extend([h("Handling and validation"), p(project.result["secondary_packaging"]), p(project.result["active_packaging"]), p(f"Engine: {project.result['engine_version']}. Food source: {project.result['food_snapshot']['source']}")])
    doc.build(story)
    return output.getvalue()
