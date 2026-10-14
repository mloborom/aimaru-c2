"""
Kill Chain PDF Report Generation Service

Generates professional PDF reports documenting TTP execution flow and command details
for kill chain engagements. Reports include:
- TTP timeline (MITRE ATT&CK techniques, timestamps)
- Full PowerShell commands executed
- Execution results and outputs
- Session metadata and operator info
"""

import re
import logging
from datetime import datetime
from io import BytesIO
from typing import Optional, List, Dict, Any

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.platypus import KeepTogether
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from sqlalchemy.orm import Session

from .models import ChatMessage, ClientChatSession, User
from .mcp_service import get_result_service

log = logging.getLogger(__name__)

# AIMARU branding
AIMARU_CYAN = HexColor("#00E5CC")
AIMARU_DARK = HexColor("#1A1A2E")
AIMARU_ACCENT = HexColor("#16213E")

# MITRE ATT&CK Tactic Mapping
TACTIC_MAP = {
    "TA0007": "Discovery",
    "TA0004": "Privilege Escalation",
    "TA0005": "Defense Evasion",
    "TA0006": "Credential Access",
    "TA0003": "Persistence",
    "TA0008": "Lateral Movement",
    "TA0009": "Collection",
    "TA0010": "Exfiltration",
}


def extract_ttp_timeline(chat_messages: List[ChatMessage]) -> List[Dict[str, Any]]:
    """Extract TTP timeline from chat messages using regex pattern matching."""
    timeline = []
    technique_regex = re.compile(r'\[T(\d{4}(?:\.\d{3})?)\]')
    tactic_regex = re.compile(r'\[TA(\d{4})\]')

    for msg in chat_messages:
        if msg.role == "assistant":
            techniques = technique_regex.findall(msg.content)
            tactics = tactic_regex.findall(msg.content)

            if techniques:
                tactic_id = f"TA{tactics[0]}" if tactics else "Unknown"
                technique_id = f"T{techniques[0]}"

                # Extract technique name from message content
                technique_name = extract_technique_name(msg.content, technique_id)

                timeline.append({
                    "timestamp": msg.created_at,
                    "technique_id": technique_id,
                    "tactic_id": tactic_id,
                    "tactic_name": TACTIC_MAP.get(tactic_id, "Unknown"),
                    "technique_name": technique_name,
                    "message_content": msg.content
                })

    return sorted(timeline, key=lambda x: x["timestamp"])


def extract_technique_name(content: str, technique_id: str) -> str:
    """Extract technique name from message content."""
    # Look for pattern like "[T1082] System Information Gather" or similar
    pattern = rf'\[{technique_id}\]\s*[:-]?\s*([^\n\[]+)'
    match = re.search(pattern, content)
    if match:
        return match.group(1).strip()
    return f"Unknown ({technique_id})"


def extract_execution_details(db: Session, session_id: str) -> List[Dict[str, Any]]:
    """Extract command execution details paired with results."""
    details = []

    messages = db.query(ChatMessage).filter_by(
        session_id=session_id,
        tool_name="execute_powershell"
    ).order_by(ChatMessage.created_at).all()

    for msg in messages:
        try:
            # Get the instruction result
            result = get_result_service(db, msg.instruction_id, decrypt=True)

            command = msg.tool_args if msg.tool_args else "N/A"
            exec_result = result.get("plaintext", "") if result else "Pending/Not Found"

            # Extract technique from the assistant message before this one
            technique_info = extract_technique_from_context(db, msg)

            details.append({
                "timestamp": msg.created_at,
                "command": command,
                "result": exec_result,
                "status": msg.status if hasattr(msg, 'status') else "unknown",
                "technique": technique_info.get("technique_name", "Unknown"),
                "technique_id": technique_info.get("technique_id", "Unknown")
            })
        except Exception as e:
            log.warning(f"Failed to extract execution details for message {msg.id}: {e}")
            continue

    return details


def extract_technique_from_context(db: Session, exec_msg: ChatMessage) -> Dict[str, str]:
    """Extract technique info from preceding assistant message."""
    try:
        preceding = db.query(ChatMessage).filter(
            ChatMessage.session_id == exec_msg.session_id,
            ChatMessage.created_at < exec_msg.created_at,
            ChatMessage.role == "assistant"
        ).order_by(ChatMessage.created_at.desc()).first()

        if preceding:
            technique_regex = re.compile(r'\[T(\d{4}(?:\.\d{3})?)\]')
            tactic_regex = re.compile(r'\[TA(\d{4})\]')

            techniques = technique_regex.findall(preceding.content)
            if techniques:
                technique_name = extract_technique_name(preceding.content, f"T{techniques[0]}")
                return {
                    "technique_id": f"T{techniques[0]}",
                    "technique_name": technique_name
                }
    except Exception as e:
        log.warning(f"Failed to extract technique context: {e}")

    return {"technique_id": "Unknown", "technique_name": "Unknown"}


def generate_kill_chain_report(
    db: Session,
    session_id: str,
    user: Optional[User] = None
) -> BytesIO:
    """Generate PDF report for kill chain session."""

    # Fetch session data
    session = db.query(ClientChatSession).filter_by(id=session_id).first()
    if not session:
        raise ValueError(f"Session {session_id} not found")

    # Extract data
    chat_messages = db.query(ChatMessage).filter_by(session_id=session_id).all()
    ttp_timeline = extract_ttp_timeline(chat_messages)
    exec_details = extract_execution_details(db, session_id)

    # Create PDF
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch
    )

    styles = getSampleStyleSheet()
    story = []

    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=AIMARU_CYAN,
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    story.append(Paragraph("KILL CHAIN ENGAGEMENT REPORT", title_style))
    story.append(Paragraph("Powered by AIMARU / PSMCP Platform", styles['Normal']))
    story.append(Spacer(1, 0.2 * inch))

    # Session metadata
    metadata = [
        ["Session ID", session_id],
        ["Client ID", session.client_id or "N/A"],
        ["Operator", user.email if user else "Unknown"],
        ["Start Time", session.created_at.strftime("%Y-%m-%d %H:%M:%S") if session.created_at else "N/A"],
        ["Report Generated", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")]
    ]

    metadata_table = Table(metadata, colWidths=[2 * inch, 4 * inch])
    metadata_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), HexColor("#F0F0F0")),
        ('TEXTCOLOR', (0, 0), (-1, -1), AIMARU_DARK),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, HexColor("#CCCCCC"))
    ]))
    story.append(metadata_table)
    story.append(Spacer(1, 0.3 * inch))

    # TTP Timeline Section
    story.append(Paragraph("MITRE ATT&CK TTP TIMELINE", title_style))
    story.append(Spacer(1, 0.1 * inch))

    if ttp_timeline:
        timeline_data = [["Timestamp", "Tactic", "Technique", "Description"]]
        for ttp in ttp_timeline:
            timestamp = ttp["timestamp"].strftime("%H:%M:%S") if ttp["timestamp"] else "N/A"
            timeline_data.append([
                timestamp,
                f"{ttp['tactic_id']}",
                f"{ttp['technique_id']}",
                ttp['tactic_name']
            ])

        timeline_table = Table(timeline_data, colWidths=[1.2 * inch, 1.2 * inch, 1.2 * inch, 2.4 * inch])
        timeline_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), AIMARU_CYAN),
            ('TEXTCOLOR', (0, 0), (-1, 0), AIMARU_DARK),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, AIMARU_CYAN),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor("#F9F9F9"), HexColor("#FFFFFF")])
        ]))
        story.append(timeline_table)
    else:
        story.append(Paragraph("No TTP executions recorded", styles['Normal']))

    story.append(Spacer(1, 0.3 * inch))

    # Execution Details Section
    story.append(Paragraph("EXECUTION DETAILS", title_style))
    story.append(Spacer(1, 0.1 * inch))

    if exec_details:
        for detail in exec_details:
            # Detail header
            timestamp = detail["timestamp"].strftime("%H:%M:%S") if detail["timestamp"] else "N/A"
            header_text = f"[{timestamp}] {detail['technique_id']} - {detail['technique']}"
            header_style = ParagraphStyle(
                'DetailHeader',
                parent=styles['Normal'],
                fontSize=11,
                textColor=AIMARU_CYAN,
                fontName='Helvetica-Bold',
                spaceAfter=6,
                spaceBefore=12
            )
            story.append(Paragraph(header_text, header_style))

            # Command
            story.append(Paragraph("<b>Command:</b>", styles['Normal']))
            cmd_style = ParagraphStyle(
                'CodeStyle',
                parent=styles['Normal'],
                fontName='Courier',
                fontSize=8,
                textColor=AIMARU_DARK,
                leftIndent=0.25 * inch,
                wordWrap='break',
                spaceBefore=3,
                spaceAfter=6
            )
            cmd_text = detail["command"][:500] + "..." if len(detail["command"]) > 500 else detail["command"]
            story.append(Paragraph(cmd_text, cmd_style))

            # Result
            story.append(Paragraph("<b>Result:</b>", styles['Normal']))
            result_text = detail["result"][:300] + "..." if len(detail["result"]) > 300 else detail["result"]
            story.append(Paragraph(result_text, cmd_style))
    else:
        story.append(Paragraph("No command executions recorded", styles['Normal']))

    story.append(Spacer(1, 0.2 * inch))

    # Footer
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=HexColor("#666666"),
        alignment=TA_CENTER
    )
    story.append(Paragraph("Report generated by PSMCP | Classified Material", footer_style))

    # Build PDF
    doc.build(story)
    pdf_buffer.seek(0)
    return pdf_buffer
