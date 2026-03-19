"""
Email sending for MusicNews.
"""
import smtplib
import ssl
from pathlib import Path
from typing import Dict, List

from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from src.utils import get_date_str, get_datetime_str, get_env, setup_logger

logger = setup_logger(__name__)


class EmailSender:
    """Send topic emails."""

    def __init__(self):
        self.smtp_server = get_env("SMTP_SERVER")
        self.smtp_port = int(get_env("SMTP_PORT"))
        self.username = get_env("SMTP_USERNAME")
        self.password = get_env("SMTP_PASSWORD")
        self.from_name = get_env("SMTP_FROM", "音乐新闻选题助手")
        self.to_recipients = [
            recipient.strip()
            for recipient in get_env("TO_RECIPIENTS").split(",")
            if recipient.strip()
        ]
        self.timeout = 30

    def create_email_content(self, topics: List[Dict], hotspots_count: int) -> str:
        """Build HTML email body."""
        today = get_date_str()
        time_now = get_datetime_str()

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px; text-align: center; margin-bottom: 30px; }}
        .header h1 {{ margin: 0; font-size: 28px; }}
        .header p {{ margin: 10px 0 0 0; opacity: 0.9; }}
        .topic {{ background: #f8f9fa; border-left: 4px solid #667eea; padding: 20px; margin-bottom: 20px; border-radius: 5px; }}
        .topic-title {{ font-size: 20px; font-weight: bold; color: #2c3e50; margin-bottom: 10px; }}
        .topic-meta {{ display: flex; flex-wrap: wrap; gap: 15px; margin-bottom: 15px; font-size: 14px; }}
        .meta-item {{ display: flex; align-items: center; }}
        .meta-label {{ color: #7f8c8d; margin-right: 5px; }}
        .meta-value {{ color: #2c3e50; font-weight: 500; }}
        .content-points {{ margin-top: 15px; }}
        .content-points li {{ margin-bottom: 8px; color: #555; }}
        .reason {{ background: #fff3cd; padding: 10px; border-radius: 5px; margin-top: 10px; font-size: 14px; }}
        .footer {{ text-align: center; padding: 20px; color: #7f8c8d; font-size: 14px; border-top: 1px solid #e0e0e0; margin-top: 30px; }}
        .stars {{ color: #ffc107; }}
        .badge {{ display: inline-block; padding: 4px 8px; border-radius: 3px; font-size: 12px; font-weight: 500; }}
        .badge-cat {{ background: #4ecdc4; color: white; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>MusicNews 选题推荐</h1>
            <p>{today} | 基于 {hotspots_count} 条热点分析</p>
        </div>
"""

        for index, topic in enumerate(topics, start=1):
            stars = "★" * int(topic.get("potential_rating", 3))
            points_html = "\n".join(
                f"<li>{point}</li>" for point in topic.get("content_points", [])
            )

            html += f"""
        <div class="topic">
            <div class="topic-title">[选题{index}] {topic.get('title', '')}</div>
            <div class="topic-meta">
                <div class="meta-item">
                    <span class="meta-label">热点来源：</span>
                    <span class="meta-value">{topic.get('hotspot_source', '未知')}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">切入角度：</span>
                    <span class="meta-value">{topic.get('angle', '未知')}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">爆款指数：</span>
                    <span class="meta-value stars">{stars}</span>
                </div>
            </div>
            <div>
                <span class="badge badge-cat">{topic.get('category', '未分类')}</span>
            </div>
            <div class="content-points">
                <strong>内容方向：</strong>
                <ul>
                    {points_html}
                </ul>
            </div>
            <div class="reason">
                <strong>推荐理由：</strong> {topic.get('reason', '基于历史数据分析')}
            </div>
        </div>
"""

        html += f"""
        <div class="footer">
            <p>本期选题由 <strong>MusicNews</strong> 自动生成</p>
            <p>生成时间：{time_now}</p>
        </div>
    </div>
</body>
</html>
"""
        return html

    def save_email_preview(self, topics: List[Dict], hotspots_count: int, output_dir) -> Path:
        """Save HTML preview before sending."""
        output_path = Path(output_dir) / "email_preview.html"
        output_path.write_text(
            self.create_email_content(topics, hotspots_count),
            encoding="utf-8",
        )
        return output_path

    def _connect_and_login(self):
        """Try SSL first, then fall back to STARTTLS."""
        errors = []

        if self.smtp_port == 465:
            try:
                logger.info("尝试使用 SMTP_SSL 连接...")
                server = smtplib.SMTP_SSL(
                    self.smtp_server,
                    self.smtp_port,
                    timeout=self.timeout,
                    context=ssl.create_default_context(),
                )
                server.login(self.username, self.password)
                logger.info("SMTP_SSL 登录成功")
                return server
            except Exception as error:
                errors.append(f"SMTP_SSL 失败: {error}")
                logger.warning(f"SMTP_SSL 失败，准备回退到 STARTTLS: {error}")

        try:
            fallback_port = 587
            logger.info(f"尝试使用 STARTTLS 连接 {self.smtp_server}:{fallback_port} ...")
            server = smtplib.SMTP(self.smtp_server, fallback_port, timeout=self.timeout)
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            server.login(self.username, self.password)
            logger.info("STARTTLS 登录成功")
            return server
        except Exception as error:
            errors.append(f"STARTTLS 失败: {error}")
            raise RuntimeError(" | ".join(errors)) from error

    def send_email(self, topics: List[Dict], hotspots_count: int) -> bool:
        """Send the email."""
        try:
            logger.info("开始发送邮件...")

            msg = MIMEMultipart("alternative")
            msg["Subject"] = str(Header(f"MusicNews 选题推荐 {get_date_str()}", "utf-8"))
            msg["From"] = formataddr((str(Header(self.from_name, "utf-8")), self.username))
            msg["To"] = ", ".join(self.to_recipients)

            html_content = self.create_email_content(topics, hotspots_count)
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            logger.info(f"准备发送到: {', '.join(self.to_recipients)}")
            server = self._connect_and_login()
            server.sendmail(self.username, self.to_recipients, msg.as_string())
            server.quit()

            logger.info("邮件发送成功")
            return True

        except Exception as error:
            logger.error(f"邮件发送失败: {error}")
            return False


if __name__ == "__main__":
    print("请运行 main.py，不要直接运行 emailer.py。")
