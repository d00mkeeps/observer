import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

PDF_PATH = "/Users/miles/Code/projects/observer/Volcano_Project_Brief_2026-09-18.pdf"

# Horizon Color Palette
COLOR_BG = colors.HexColor("#08080A")
COLOR_CARD = colors.HexColor("#121215")
COLOR_CARD_BORDER = colors.HexColor("#24242A")
COLOR_TEXT_PRIMARY = colors.HexColor("#FFFFFF")
COLOR_TEXT_SECONDARY = colors.HexColor("#A1A1AA")
COLOR_TEXT_MUTED = colors.HexColor("#71717A")
COLOR_ACCENT_GREEN = colors.HexColor("#30D158")
COLOR_BADGE_BG = colors.HexColor("#1C2A20")
COLOR_BADGE_BORDER = colors.HexColor("#2A4430")


def draw_background_and_footer(canvas_obj, doc):
    canvas_obj.saveState()
    # 1. Fill entire background
    canvas_obj.setFillColor(COLOR_BG)
    canvas_obj.rect(0, 0, doc.pagesize[0], doc.pagesize[1], fill=True, stroke=False)

    # 2. Subtle top border line
    canvas_obj.setFillColor(COLOR_CARD_BORDER)
    canvas_obj.rect(48, doc.pagesize[1] - 36, doc.pagesize[0] - 96, 1, fill=True, stroke=False)

    # 3. Footer
    canvas_obj.setFont("Helvetica-Bold", 8)
    canvas_obj.setFillColor(COLOR_TEXT_MUTED)
    canvas_obj.drawString(48, 30, "VOLCANO INFRASTRUCTURE & APPLICATION SUITE")
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.drawRightString(doc.pagesize[0] - 48, 30, f"PAGE {canvas_obj._pageNumber} OF 5")
    canvas_obj.restoreState()


def build_pdf():
    doc = BaseDocTemplate(
        PDF_PATH,
        pagesize=A4,
        leftMargin=48,
        rightMargin=48,
        topMargin=48,
        bottomMargin=48,
    )

    frame = Frame(
        doc.leftMargin,
        doc.bottomMargin,
        doc.width,
        doc.height,
        id="normal",
        topPadding=0,
        bottomPadding=0,
        leftPadding=0,
        rightPadding=0,
    )

    template = PageTemplate(id="horizon_page", frames=frame, onPage=draw_background_and_footer)
    doc.addPageTemplates([template])

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "HorizonTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=COLOR_TEXT_PRIMARY,
    )

    subtitle_style = ParagraphStyle(
        "HorizonSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=COLOR_TEXT_SECONDARY,
    )

    section_header_style = ParagraphStyle(
        "HorizonSectionHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=14,
        textColor=COLOR_ACCENT_GREEN,
    )

    body_style = ParagraphStyle(
        "HorizonBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13.5,
        textColor=COLOR_TEXT_PRIMARY,
    )

    body_muted = ParagraphStyle(
        "HorizonBodyMuted",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=COLOR_TEXT_MUTED,
        alignment=2,
    )

    badge_style = ParagraphStyle(
        "HorizonBadge",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=COLOR_ACCENT_GREEN,
        alignment=1,
    )

    metric_val_style = ParagraphStyle(
        "HorizonMetricVal",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=19,
        textColor=COLOR_TEXT_PRIMARY,
        alignment=1,
    )

    metric_lbl_style = ParagraphStyle(
        "HorizonMetricLbl",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=COLOR_TEXT_SECONDARY,
        alignment=1,
    )

    story = []

    pages_data = [
        # PAGE 1: OBSERVER
        {
            "project_name": "OBSERVER",
            "tagline": "Autonomous Host & Container SRE Monitoring Operator",
            "status_badge": "DEPLOYED & ACTIVE",
            "overview": "Observer is Volcano's centralized monitoring and incident response engine. Deployed to monitor 29+ production containers, ingest Loki log streams in real-time, and route human-readable digests to Telegram.",
            "metrics": [
                ("< 60s", "Incident Alert Latency"),
                ("0 False Alarms", "Grafana Alert Noise Elimination"),
                ("24/7", "Autonomous Health Polling"),
            ],
            "changes": [
                ("<b>Real-Time Loki Error Stream Poller</b>", "Implemented background async monitor scanning container logs for exceptions and panics with a 5-minute per-service debounce."),
                ("<b>Automated Daily Performance Reports</b>", "Automated 09:00 AM server reports aggregating NVMe disk capacity, RAM consumption, CPU load, and 24h error frequency."),
                ("<b>Telegram Channel Routing & Sanitized HTML</b>", "Replaced raw markdown with sanitized Telegram HTML and category routing (<code>#alerts</code>, <code>#deploys</code>, <code>#reports</code>)."),
                ("<b>Live System Status API (<code>GET /status</code>)</b>", "Added endpoint exposing real-time container health and deploy history for portfolio integration."),
            ],
            "impact_title": "BUSINESS & OPERATIONAL IMPACT",
            "impact_points": [
                ("Zero-Downtime Awareness", "Immediate push visibility into PostgreSQL connection exhaustion, container crashes, and API exceptions across all apps before users report them."),
                ("High Signal-to-Noise Ratio", "Eliminated alert fatigue by replacing raw label dumps with structured diagnostics and debounced summaries."),
                ("Automated DevOps Auditing", "Every code deployment to Volcano now automatically posts confirmation and audit trails directly to mobile."),
            ],
        },
        # PAGE 2: PORTFOLIO & ADMIN CONTROL CENTER
        {
            "project_name": "PORTFOLIO & CONTROL CENTER",
            "tagline": "Unified Multi-Dashboard Portal at mileshillary.com/admin",
            "status_badge": "PRODUCTION LIVE",
            "overview": "mileshillary.com was transformed into both a dynamic showcase of active projects and a unified single-pane-of-glass administrative control center hosting all backend engineering dashboards.",
            "metrics": [
                ("1 URL", "Unified Admin Access Point"),
                ("5 Dashboards", "Consolidated in Multi-Tab UI"),
                ("100% Real-Time", "Dynamic Project Health Sync"),
            ],
            "changes": [
                ("<b>Unified Admin Portal (<code>/admin</code>)</b>", "Built a tabbed command center consolidating Grafana Metrics, Clearbox Supabase Studio, Horizon Studio, Crucible QA, and Observer Ops into a single URL."),
                ("<b>Dynamic Status Engine</b>", "Connected homepage status indicator dots to Observer's live status API, dynamically reflecting <code>live</code>, <code>updating</code>, and <code>archived</code> states."),
                ("<b>Nginx Internal Reverse Proxy</b>", "Configured Nginx dynamic DNS resolution to securely proxy API status and report triggers to internal Docker containers on the observability network."),
                ("<b>Deploy Notification Hook</b>", "Added automated CI/CD webhooks into the deployment workflow to notify Observer upon every successful site build."),
            ],
            "impact_title": "BUSINESS & OPERATIONAL IMPACT",
            "impact_points": [
                ("Operational Consolidation", "Eliminated fragmented port-hopping across local IPs and remote endpoints; manage databases, metrics, and QA in one browser tab."),
                ("Accurate Public Representation", "Visitors to mileshillary.com see verified, real-time live statuses for active production products (Volc, Clearbox, Horizon)."),
                ("Instant Actionability", "One-click 'Telegram Report' trigger right from the web UI to inspect server diagnostics on demand."),
            ],
        },
        # PAGE 3: VOLC AI GYM COACH
        {
            "project_name": "VOLC AI GYM COACH",
            "tagline": "iOS Computer Vision Coaching & Backend Analytics Engine",
            "status_badge": "APP STORE LIVE",
            "overview": "Volc is an AI-powered workout tracking and computer vision coaching platform consisting of a live iOS application, high-throughput backend API, and landing page with integrated telemetry analytics.",
            "metrics": [
                ("Live iOS App", "App Store ID: 6751469055"),
                ("v2.0 Backend", "FastAPI + Dockerized Stack"),
                ("1-Click CTA", "Platform-Aware App Store Routing"),
            ],
            "changes": [
                ("<b>Unified Multi-Container Stack</b>", "Integrated landing page website (<code>volc-website:3004</code>) and backend API (<code>supreme-octo-doodle-api:8002</code>) under unified Docker Compose with healthchecks."),
                ("<b>Admin Analytics Dashboard</b>", "Engineered Highcharts visual analytics dashboard with hourly backend aggregation for workout sessions and active users."),
                ("<b>Platform-Aware Landing Page</b>", "Updated web client with native App Store badges for iOS users and inline email capture for Android/web visitors."),
                ("<b>Observer Health & Error Monitoring</b>", "Integrated Volc backend and frontend into Observer's automated 24h error log parser and live status engine."),
            ],
            "impact_title": "BUSINESS & OPERATIONAL IMPACT",
            "impact_points": [
                ("Conversion Rate Optimization", "Dynamic platform detection routes iOS visitors directly to the App Store while capturing Android/desktop leads for future rollouts."),
                ("Session Reliability", "Continuous monitoring of workout telemetry endpoints ensures uninterrupted video analysis and exercise logging for gym users."),
                ("User Retention Visibility", "Real-time Highcharts analytics provide daily and hourly insights into workout completion and repeat usage patterns."),
            ],
        },
        # PAGE 4: CLEARBOX MEDICINE API
        {
            "project_name": "CLEARBOX MEDICINE API",
            "tagline": "Self-Hosted Supabase, Pgvector & Biomedical Telemetry",
            "status_badge": "PRODUCTION LIVE",
            "overview": "Clearbox is a biomedical knowledge retrieval and clinical adherence platform running a complete self-hosted Supabase infrastructure (PostgreSQL 16, pgvector, PostgREST, Studio, and Kong Gateway).",
            "metrics": [
                ("Pgvector PG16", "Biomedical Embeddings DB"),
                ("Port 8009", "Supabase Studio Console"),
                ("4 Services", "Complete Self-Hosted DB Stack"),
            ],
            "changes": [
                ("<b>Self-Hosted Supabase Stack</b>", "Deployed PostgreSQL with pgvector, PostgREST (<code>:3006</code>), GoTrue auth, and Supabase Studio (<code>:8009</code>) on the internal Volcano network."),
                ("<b>Embedded Studio in Unified Admin</b>", "Integrated Clearbox Supabase Studio directly into <code>mileshillary.com/admin</code> for instant database table and embedding management."),
                ("<b>Clinical Telemetry & Analytics Aggregator</b>", "Wired analytical join aggregators (<code>dmd_ampp</code>) for tracking patient adherence, retention metrics, and dosage schedules."),
                ("<b>LogQL Diagnostic Filtering</b>", "Hardened Observer error queries to distinguish actual database exceptions from telemetry log payloads containing error substrings."),
            ],
            "impact_title": "BUSINESS & OPERATIONAL IMPACT",
            "impact_points": [
                ("Zero Third-Party Cloud DB Cost", "Running a complete enterprise Supabase + pgvector stack locally on Volcano eliminates recurring cloud database expenses."),
                ("Direct Data Governance", "Full control over biomedical embedding tables and patient telemetry data with zero data leaving the private server infrastructure."),
                ("Rapid Incident Resolution", "Real-time Loki error alerts instantly catch schema mismatches and PostgREST JWT authentication failures before users notice."),
            ],
        },
        # PAGE 5: HORIZON PAPER TRACKER & VOLCANO CI/CD
        {
            "project_name": "HORIZON & VOLCANO CI/CD",
            "tagline": "Algorithmic Token Fund & Cloudflare Zero Trust CI/CD",
            "status_badge": "ACTIVE DEPLOYMENT",
            "overview": "Horizon runs simulation token trading on Solana paired with automated server deployment pipelines across all repositories via Cloudflare Zero Trust Tunnels.",
            "metrics": [
                ("29 Containers", "Active Monitored Fleet"),
                ("< 45s", "Git Push to Live Deployment"),
                ("Zero Trust", "Cloudflare HTTP/2 Tunnels"),
            ],
            "changes": [
                ("<b>Capital Rotation Engine</b>", "Refactored Horizon's wallet manager to automatically deduct reinvested capital from the cash pool upon strategy rotations."),
                ("<b>Portfolio Net % Valuation</b>", "Corrected portfolio ROI calculations to measure returns against actual invested capital rather than theoretical limits."),
                ("<b>Standardized GitHub Actions CI/CD</b>", "Equipped all project workflows with Cloudflare SSH proxy commands and automated Telegram deploy webhooks."),
                ("<b>Zero Trust Tunnel Optimization</b>", "Updated cloudflared tunnel sidecar parameters to resolve websocket/HTTP2 handshake drops for remote tunnels."),
            ],
            "impact_title": "BUSINESS & OPERATIONAL IMPACT",
            "impact_points": [
                ("Algorithmic Capital Accuracy", "Precise cash pool and ROI accounting prevents simulation capital drift during high-frequency trading."),
                ("Sub-45s Developer Velocity", "Any commit pushed to main across any project tests, builds, and deploys to production with zero manual SSH steps."),
                ("Foundation for Autonomous AI SRE", "Established the network topology and API layer required for Antigravity AI agents to diagnose and repair codebases."),
            ],
        },
    ]

    total_width = 499

    for i, p in enumerate(pages_data):
        # Header block
        header_table = Table([
            [
                Paragraph(f"<b>{p['project_name']}</b>", title_style),
                Paragraph(f"<font color='#30D158'>●</font> {p['status_badge']}", badge_style),
            ],
            [
                Paragraph(p["tagline"], subtitle_style),
                Paragraph("<b>DATE:</b> 18 SEP 2026", body_muted),
            ],
        ], colWidths=[370, 129])
        header_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("ALIGN", (1, 1), (1, 1), "RIGHT"),
            ("BACKGROUND", (1, 0), (1, 0), COLOR_BADGE_BG),
            ("BOX", (1, 0), (1, 0), 1, COLOR_BADGE_BORDER),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 10))

        # Overview Paragraph Card
        overview_card = Table([[Paragraph(p["overview"], body_style)]], colWidths=[total_width])
        overview_card.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_CARD),
            ("BOX", (0, 0), (-1, -1), 1, COLOR_CARD_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ]))
        story.append(overview_card)
        story.append(Spacer(1, 10))

        # 3 Key Metrics Row
        col_w = total_width / 3.0
        m1 = Table([[Paragraph(p["metrics"][0][0], metric_val_style)], [Paragraph(p["metrics"][0][1], metric_lbl_style)]], colWidths=[col_w - 4])
        m2 = Table([[Paragraph(p["metrics"][1][0], metric_val_style)], [Paragraph(p["metrics"][1][1], metric_lbl_style)]], colWidths=[col_w - 4])
        m3 = Table([[Paragraph(p["metrics"][2][0], metric_val_style)], [Paragraph(p["metrics"][2][1], metric_lbl_style)]], colWidths=[col_w - 4])

        metrics_table = Table([[m1, m2, m3]], colWidths=[col_w, col_w, col_w])
        metrics_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_CARD),
            ("BOX", (0, 0), (-1, -1), 1, COLOR_CARD_BORDER),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("LINEBEFORE", (1, 0), (1, 0), 1, COLOR_CARD_BORDER),
            ("LINEBEFORE", (2, 0), (2, 0), 1, COLOR_CARD_BORDER),
        ]))
        story.append(metrics_table)
        story.append(Spacer(1, 12))

        # Technical Changes Made Section
        story.append(Paragraph("TECHNICAL CHANGES & HIGHLIGHTS", section_header_style))
        story.append(Spacer(1, 5))

        changes_rows = []
        for heading, desc in p["changes"]:
            changes_rows.append([
                Paragraph(f"<font color='#30D158'>▸</font> {heading}<br/><font color='#A1A1AA'>{desc}</font>", body_style)
            ])

        changes_table = Table(changes_rows, colWidths=[total_width])
        changes_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_CARD),
            ("BOX", (0, 0), (-1, -1), 1, COLOR_CARD_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_CARD_BORDER),
        ]))
        story.append(changes_table)
        story.append(Spacer(1, 12))

        # Business Impact Section
        story.append(Paragraph(p["impact_title"], section_header_style))
        story.append(Spacer(1, 5))

        impact_rows = []
        for headline, detail in p["impact_points"]:
            impact_rows.append([
                Paragraph(f"<b>{headline}:</b> <font color='#A1A1AA'>{detail}</font>", body_style)
            ])

        impact_table = Table(impact_rows, colWidths=[total_width])
        impact_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_CARD),
            ("BOX", (0, 0), (-1, -1), 1, COLOR_CARD_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_CARD_BORDER),
        ]))
        story.append(impact_table)

        # Page break if not last page
        if i < len(pages_data) - 1:
            story.append(PageBreak())

    doc.build(story)
    print(f"Generated 5-page PDF successfully at: {PDF_PATH}")


if __name__ == "__main__":
    build_pdf()
