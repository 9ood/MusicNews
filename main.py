"""MusicNews main entry."""
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from src.emailer import EmailSender
from src.hotspot_fetcher import HotspotFetcher
from src.topic_generator import TopicGenerator
from src.utils import get_date_str, setup_logger

logger = setup_logger(__name__)

RISKY_KEYWORDS = [
    "smtp",
    "starttls",
    "musicnews",
    "system test",
    "verification",
    "link check",
    "mail link check",
]


def _make_run_dir() -> Path:
    run_dir = Path("output") / get_date_str() / datetime.now().strftime("%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _write_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _flatten_topic_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_flatten_topic_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_flatten_topic_text(item) for item in value.values())
    return str(value)


def _validate_topics(topics, hotspots):
    errors = []
    seen_titles = set()

    if len(hotspots) < 10:
        errors.append(f"Too few hotspots: only {len(hotspots)} items.")

    if len(topics) < 3:
        errors.append(f"Too few topics: only {len(topics)} items.")

    for index, topic in enumerate(topics, start=1):
        title = str(topic.get("title", "")).strip()
        source = str(topic.get("hotspot_source", "")).strip()
        angle = str(topic.get("angle", "")).strip()
        category = str(topic.get("category", "")).strip()
        points = topic.get("content_points", [])

        if len(title) < 8:
            errors.append(f"Topic {index} title is too short.")

        if title in seen_titles:
            errors.append(f"Topic {index} title is duplicated.")
        seen_titles.add(title)

        if not source:
            errors.append(f"Topic {index} is missing hotspot source.")

        if not angle:
            errors.append(f"Topic {index} is missing angle.")

        if not category:
            errors.append(f"Topic {index} is missing category.")

        if not isinstance(points, list) or len(points) < 3:
            errors.append(f"Topic {index} has fewer than 3 content points.")

        full_text = _flatten_topic_text(topic)
        lowered = full_text.lower()

        if "锟" in full_text:
            errors.append(f"Topic {index} contains broken characters.")

        if full_text.count("?") >= 6:
            errors.append(f"Topic {index} has too many question marks.")

        for keyword in RISKY_KEYWORDS:
            if keyword in lowered:
                errors.append(f"Topic {index} contains risky keyword: {keyword}")
                break

    return {
        "ok": len(errors) == 0,
        "errors": errors,
    }


def _write_run_summary(run_dir: Path, hotspots, topics, preview_path: Path, sent: bool, mode: str):
    summary_path = run_dir / "run_summary.json"
    _write_json(
        summary_path,
        {
            "hotspots_count": len(hotspots),
            "topics_count": len(topics),
            "preview_path": str(preview_path),
            "sent": bool(sent),
            "mode": mode,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    return summary_path


def run_once(send_email=None):
    if send_email is None:
        send_email = os.getenv("MUSICNEWS_SEND_EMAIL", "1").strip() == "1"

    logger.info("=" * 60)
    logger.info("MusicNews run started")
    logger.info("=" * 60)

    run_dir = None
    summary_path = None

    try:
        logger.info("[1/4] Fetch hotspots")
        fetcher = HotspotFetcher()
        hotspots = fetcher.fetch_all_hotspots()

        if not hotspots:
            logger.error("No hotspots fetched. Stop.")
            return {
                "success": False,
                "mode": "send" if send_email else "preview",
                "sent": False,
                "run_dir": None,
                "summary_path": None,
                "error": "No hotspots fetched.",
            }

        logger.info("[2/4] Generate topics")
        generator = TopicGenerator()
        topics = generator.generate_topics(hotspots, num_topics=5)

        if not topics:
            logger.error("No topics generated. Stop.")
            return {
                "success": False,
                "mode": "send" if send_email else "preview",
                "sent": False,
                "run_dir": None,
                "summary_path": None,
                "error": "No topics generated.",
            }

        run_dir = _make_run_dir()
        sender = EmailSender()
        preview_path = sender.save_email_preview(topics, len(hotspots), run_dir)
        _write_json(run_dir / "hotspots.json", hotspots)
        _write_json(run_dir / "topics.json", topics)

        validation = _validate_topics(topics, hotspots)
        _write_json(run_dir / "validation.json", validation)

        if not validation["ok"]:
            logger.error("Validation failed. Stop before send.")
            for item in validation["errors"]:
                logger.error("- %s", item)
            return {
                "success": False,
                "mode": "send" if send_email else "preview",
                "sent": False,
                "run_dir": str(run_dir),
                "summary_path": None,
                "error": "Validation failed.",
                "validation": validation,
            }

        if not send_email:
            summary_path = _write_run_summary(
                run_dir,
                hotspots,
                topics,
                preview_path,
                sent=False,
                mode="preview",
            )
            logger.info("[3/4] Preview finished")
            return {
                "success": True,
                "mode": "preview",
                "sent": False,
                "run_dir": str(run_dir),
                "summary_path": str(summary_path),
                "error": None,
            }

        logger.info("[3/4] Send email")
        success = sender.send_email(topics, len(hotspots))
        summary_path = _write_run_summary(
            run_dir,
            hotspots,
            topics,
            preview_path,
            sent=success,
            mode="send",
        )

        if not success:
            logger.error("Email send failed.")
            return {
                "success": False,
                "mode": "send",
                "sent": False,
                "run_dir": str(run_dir),
                "summary_path": str(summary_path),
                "error": "Email send failed.",
            }

        logger.info("[4/4] Run finished")
        return {
            "success": True,
            "mode": "send",
            "sent": True,
            "run_dir": str(run_dir),
            "summary_path": str(summary_path),
            "error": None,
        }

    except Exception as error:
        logger.error("Run failed: %s", error)
        traceback.print_exc()
        return {
            "success": False,
            "mode": "send" if send_email else "preview",
            "sent": False,
            "run_dir": str(run_dir) if run_dir else None,
            "summary_path": str(summary_path) if summary_path else None,
            "error": str(error),
        }


def main():
    return run_once()["success"]


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
