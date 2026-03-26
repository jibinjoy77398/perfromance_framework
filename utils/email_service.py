"""
email_service.py — Asynchronous SMTP utility for performance alerts.
"""
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

class EmailService:
    @staticmethod
    def send_report_alert(recipient_email: str, site_name: str, grade: str, report_url: str):
        """
        Sends an HTML email alert with the test results.
        Requires environment variables: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS.
        """
        # Load credentials from ENV
        host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        port = int(os.getenv("SMTP_PORT", "587"))
        user = os.getenv("SMTP_USER")
        pwd = os.getenv("SMTP_PASS")
        sender = os.getenv("SMTP_SENDER", user)

        if not user or not pwd:
            print("  [WARN] SMTP credentials not found. Email alert skipped.")
            return

        # Build Message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🚀 Perf Report: {site_name} graded [{grade}]"
        msg["From"] = sender
        msg["To"] = recipient_email

        html = f"""
        <html>
        <body style="font-family: sans-serif; color: #333; line-height: 1.6;">
            <div style="max-width:600px; margin: 20px auto; border: 1px solid #ddd; border-radius: 8px; padding: 20px;">
                <h2 style="color: #4F46E5;">Performance Test Complete</h2>
                <p>The synthetic transaction engine has finished evaluating <b>{site_name}</b>.</p>
                
                <div style="background: #F3F4F6; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <span style="font-size: 1.1rem;">Verdict Grade:</span>
                    <b style="font-size: 2rem; color: {'#10B981' if grade in 'AB' else '#EF4444'}; margin-left: 10px;">{grade}</b>
                </div>

                <p>You can view the full interactive dashboard here:</p>
                <a href="{report_url}" style="display:inline-block; background: #6366F1; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;">
                    Open Executive Report
                </a>
                
                <p style="margin-top: 30px; font-size: 0.85rem; color: #999;">
                    This is an automated message from your Antigravity Performance Framework.
                </p>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html, "html"))

        try:
            with smtplib.SMTP(host, port) as server:
                server.starttls()
                server.login(user, pwd)
                server.send_message(msg)
            print(f"  [INFO] Email alert sent to {recipient_email}")
        except Exception as e:
            print(f"  [ERROR] Failed to send email alert: {e}")
