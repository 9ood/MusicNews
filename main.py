"""MusicNews main entry."""
import json
import os
import re
import sys
import traceback
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from src.emailer import EmailSender
from src.hotspot_fetcher import HotspotFetcher
from src.topic_generator import TopicGenerator
from src.utils import get_date_str, setup_logger

logger = setup_logger(__name__)

RUNTIME_DIR = Path(".runtime")
SEND_LOCK_MAX_AGE_SECONDS = max(
    int(os.getenv("MUSICNEWS_SEND_LOCK_MAX_AGE_SECONDS", str(6 * 60 * 60))),
    300,
)

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


def _get_successful_send_summary_for_date(day_str: str):
    day_dir = Path("output") / day_str
    if not day_dir.exists():
        return None

    run_dirs = sorted(
        [item for item in day_dir.iterdir() if item.is_dir()],
        key=lambda item: item.name,
        reverse=True,
    )

    for run_dir in run_dirs:
        summary_path = run_dir / "run_summary.json"
        if not summary_path.exists():
            continue
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if summary.get("mode") == "send" and summary.get("sent") is True:
            return summary_path

    return None


class DailySendLock:
    def __init__(self, day_str: str):
        self.path = RUNTIME_DIR / f"send-{day_str}.lock"
        self.acquired = False

    def _cleanup_stale_lock(self):
        if not self.path.exists():
            return
        try:
            age_seconds = datetime.now().timestamp() - self.path.stat().st_mtime
        except OSError:
            return
        if age_seconds < SEND_LOCK_MAX_AGE_SECONDS:
            return
        try:
            self.path.unlink()
            logger.warning("Removed stale send lock: %s", self.path)
        except OSError:
            return

    def acquire(self) -> bool:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        self._cleanup_stale_lock()

        try:
            descriptor = os.open(
                str(self.path),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
        except FileExistsError:
            return False

        with os.fdopen(descriptor, "w", encoding="utf-8") as lock_file:
            lock_file.write(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "startedAt": datetime.now().isoformat(timespec="seconds"),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )

        self.acquired = True
        return True

    def release(self):
        if not self.acquired:
            return
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        self.acquired = False


def _flatten_topic_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_flatten_topic_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_flatten_topic_text(item) for item in value.values())
    return str(value)


def _normalize_source_title(source: str) -> str:
    text = re.sub(r"^\[[^\]]+\]\s*", "", str(source or "").strip()).lower()
    text = re.sub(r"[^\w\u4e00-\u9fff]", "", text)
    return text


def _extract_source_platform(source: str) -> str:
    text = str(source or "").strip()
    match = re.match(r"^\[([^\]]+)\]", text)
    if match:
        return match.group(1).strip()
    return text


def _source_key(source: str) -> tuple:
    return (
        _extract_source_platform(source).lower(),
        _normalize_source_title(source),
    )


def _sources_are_similar(left: str, right: str) -> bool:
    left_text = _normalize_source_title(left)
    right_text = _normalize_source_title(right)

    if not left_text or not right_text:
        return False

    if left_text == right_text:
        return True

    shorter = min(len(left_text), len(right_text))
    if shorter >= 6 and (left_text in right_text or right_text in left_text):
        return True

    return SequenceMatcher(None, left_text, right_text).ratio() >= 0.72


def _validate_topics(topics, hotspots):
    errors = []
    seen_titles = set()
    seen_sources = set()
    unique_sources = []
    platform_counts = {}
    available_platforms = {
        str(spot.get("source", "")).strip()
        for spot in hotspots
        if str(spot.get("source", "")).strip()
    }

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
        else:
            canonical_source = _source_key(source)
            if canonical_source in seen_sources:
                errors.append(f"Topic {index} hotspot source is duplicated.")
            else:
                seen_sources.add(canonical_source)
                platform = _extract_source_platform(source)
                if platform:
                    platform_counts[platform] = platform_counts.get(platform, 0) + 1
                for previous_source in unique_sources:
                    if _sources_are_similar(source, previous_source):
                        errors.append(f"Topic {index} hotspot source is too similar to another topic.")
                        break
                unique_sources.append(source)

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

    if len(available_platforms) > 1 and platform_counts:
        required_platforms = min(len(topics), len(available_platforms))
        if len(platform_counts) < required_platforms:
            errors.append("Topics are not using enough different platforms.")

        max_per_platform = (len(topics) + len(available_platforms) - 1) // len(available_platforms)
        if any(count > max_per_platform for count in platform_counts.values()):
            errors.append("Topics are too concentrated on one platform.")

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
    send_lock = None
    run_day = get_date_str()

    if send_email:
        existing_summary = _get_successful_send_summary_for_date(run_day)
        if existing_summary:
            logger.warning(
                "Skip duplicate send because today already succeeded: %s",
                existing_summary,
            )
            return {
                "success": True,
                "mode": "send",
                "sent": False,
                "run_dir": str(existing_summary.parent),
                "summary_path": str(existing_summary),
                "error": None,
                "duplicateSkipped": True,
            }

        send_lock = DailySendLock(run_day)
        if not send_lock.acquire():
            logger.warning("Skip duplicate send because another send is already running.")
            return {
                "success": True,
                "mode": "send",
                "sent": False,
                "run_dir": None,
                "summary_path": None,
                "error": None,
                "duplicateSkipped": True,
            }

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
    finally:
        if send_lock:
            send_lock.release()


def main():
    return run_once()["success"]


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
