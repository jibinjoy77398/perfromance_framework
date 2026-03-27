import smtplib
import os as _os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

class EmailService:
    @staticmethod
    def send_report_alert(recipient_email: str, site_name: str, grade: str, report_url: str, spike: dict = None, stress: list = None):
        """
        Sends an HTML email alert with the test results, including Spike and Stress highlights.
        """
        # Load credentials from ENV
        host = _os.getenv("SMTP_HOST", "smtp.gmail.com")
        port = int(_os.getenv("SMTP_PORT", "587"))
        user = _os.getenv("SMTP_USER", "jibinjoy.810@gmail.com")
        pwd = _os.getenv("SMTP_PASS", "acnghekumrfodwei")
        sender = _os.getenv("SMTP_SENDER", user)

        if not user or not pwd:
            print("  [WARN] SMTP credentials not found. Email alert skipped.")
            return

        # Build Message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🚀 Perf Report: {site_name} graded [{grade}]"
        msg["From"] = sender
        msg["To"] = recipient_email

        # Build Summary Sections
        spike_html = ""
        if spike:
            spike_html = f"""
            <div style="margin-top: 20px; border-top: 1px solid #eee; padding-top: 20px;">
                <h3 style="color: #4F46E5;">🌪️ Spike Test Results</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr style="background: #f9fafb;"><td style="padding: 8px; border: 1px solid #eee;">Requests</td><td style="padding: 8px; border: 1px solid #eee;">{spike.get('success', 0) + spike.get('failed', 0)}</td></tr>
                    <tr><td style="padding: 8px; border: 1px solid #eee;">Success Rate</td><td style="padding: 8px; border: 1px solid #eee;">{round((spike.get('success', 0)/(spike.get('success',0)+spike.get('failed',1 or 1)))*100)}%</td></tr>
                    <tr style="background: #f9fafb;"><td style="padding: 8px; border: 1px solid #eee;">Avg Latency</td><td style="padding: 8px; border: 1px solid #eee;">{spike.get('avg_time', 0)}ms</td></tr>
                </table>
            </div>
            """

        stress_html = ""
        if stress and len(stress) > 0:
            last_level = stress[-1]
            stress_html = f"""
            <div style="margin-top: 20px; border-top: 1px solid #eee; padding-top: 20px;">
                <h3 style="color: #4F46E5;">👥 Stress (Breakpoint) Analysis</h3>
                <p>System handled up to <b>{last_level.get('users', 0)}</b> concurrent users.</p>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr style="background: #f9fafb;"><td style="padding: 8px; border: 1px solid #eee;">Max Users</td><td style="padding: 8px; border: 1px solid #eee;">{last_level.get('users', 0)}</td></tr>
                    <tr><td style="padding: 8px; border: 1px solid #eee;">Error Rate</td><td style="padding: 8px; border: 1px solid #eee;">{last_level.get('error_rate_pct', 0)}%</td></tr>
                    <tr style="background: #f9fafb;"><td style="padding: 8px; border: 1px solid #eee;">P95 Load Time</td><td style="padding: 8px; border: 1px solid #eee;">{last_level.get('p95_load_time', 0)}ms</td></tr>
                </table>
            </div>
            """

        html = f"""
        <html>
        <body style="font-family: sans-serif; color: #333; line-height: 1.6;">
            <div style="max-width:600px; margin: 20px auto; border: 1px solid #ddd; border-radius: 8px; padding: 20px;">
                <h2 style="color: #4F46E5;">Performance Test Complete</h2>
                <p>The synthetic transaction engine has finished evaluating <b>{site_name}</b>.</p>
                
                <div style="background: #F3F4F6; padding: 15px; border-radius: 8px; margin: 20px 0; text-align: center;">
                    <span style="font-size: 1.1rem;">Overall Score:</span>
                    <b style="font-size: 2.5rem; color: {'#10B981' if grade in 'AB' else '#EF4444'}; margin-left: 10px;">{grade}</b>
                </div>

                {spike_html}
                {stress_html}

                <div style="margin-top: 30px; text-align: center;">
                    <p>View the full interactive dashboard here:</p>
                    <a href="{report_url}" style="display:inline-block; background: #6366F1; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;">
                        Open Executive Report
                    </a>
                </div>
                
                <p style="margin-top: 30px; font-size: 0.85rem; color: #999; text-align: center;">
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
