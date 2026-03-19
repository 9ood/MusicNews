"""
MusicNews main entry.
"""
import json
import os
import sys
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
    "系统测试",
    "验证",
    "链路",
    "邮件链路",
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
        errors.append(f"热点太少：只抓到 {len(hotspots)} 条。")

    if len(topics) < 3:
        errors.append(f"选题太少：只生成了 {len(topics)} 条。")

    for index, topic in enumerate(topics, start=1):
        title = str(topic.get("title", "")).strip()
        source = str(topic.get("hotspot_source", "")).strip()
        angle = str(topic.get("angle", "")).strip()
        category = str(topic.get("category", "")).strip()
        points = topic.get("content_points", [])

        if len(title) < 8:
            errors.append(f"第 {index} 条标题太短。")

        if title in seen_titles:
            errors.append(f"第 {index} 条标题和前面重复。")
        seen_titles.add(title)

        if not source:
            errors.append(f"第 {index} 条没有热点来源。")

        if not angle:
            errors.append(f"第 {index} 条没有切入角度。")

        if not category:
            errors.append(f"第 {index} 条没有分类。")

        if not isinstance(points, list) or len(points) < 3:
            errors.append(f"第 {index} 条内容方向少于 3 条。")

        full_text = _flatten_topic_text(topic)
        lowered = full_text.lower()

        if "�" in full_text:
            errors.append(f"第 {index} 条包含乱码字符。")

        if full_text.count("?") >= 6:
            errors.append(f"第 {index} 条问号太多，像坏内容。")

        for keyword in RISKY_KEYWORDS:
            if keyword in lowered:
                errors.append(f"第 {index} 条包含危险词：{keyword}")
                break

    return {
        "ok": len(errors) == 0,
        "errors": errors,
    }


def main():
    logger.info("=" * 60)
    logger.info(f"MusicNews 选题推荐系统 - {get_date_str()}")
    logger.info("=" * 60)

    try:
        logger.info("\n[1/4] 抓取各平台热点...")
        fetcher = HotspotFetcher()
        hotspots = fetcher.fetch_all_hotspots()

        if not hotspots:
            logger.error("没有抓到任何热点，任务停止。")
            return False

        logger.info(f"成功抓到 {len(hotspots)} 条热点")

        logger.info("\n[2/4] 生成选题...")
        generator = TopicGenerator()
        topics = generator.generate_topics(hotspots, num_topics=5)

        if not topics:
            logger.error("没有生成出选题，任务停止。")
            return False

        logger.info(f"成功生成 {len(topics)} 条选题")

        run_dir = _make_run_dir()
        sender = EmailSender()
        preview_path = sender.save_email_preview(topics, len(hotspots), run_dir)
        _write_json(run_dir / "hotspots.json", hotspots)
        _write_json(run_dir / "topics.json", topics)

        logger.info(f"预览文件已保存：{preview_path}")
        logger.info("\n选题预览：")
        for index, topic in enumerate(topics, start=1):
            logger.info(f"{index}. {topic['title']}")
            logger.info(
                f"   分类：{topic['category']} | 爆款指数：{'★' * topic['potential_rating']}"
            )

        validation = _validate_topics(topics, hotspots)
        _write_json(run_dir / "validation.json", validation)

        if not validation["ok"]:
            logger.error("\n[3/4] 内容检查未通过，已停止发送。")
            for item in validation["errors"]:
                logger.error(f"- {item}")
            logger.error(f"请先查看预览文件：{preview_path}")
            return False

        send_email = os.getenv("MUSICNEWS_SEND_EMAIL", "1").strip() == "1"

        if not send_email:
            logger.info("\n[3/4] 当前是预览模式，已停止在发送前。")
            logger.info(f"请先查看预览文件：{preview_path}")
            _write_json(
                run_dir / "run_summary.json",
                {
                    "hotspots_count": len(hotspots),
                    "topics_count": len(topics),
                    "preview_path": str(preview_path),
                    "sent": False,
                    "mode": "preview",
                    "finished_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
            return True

        logger.info("\n[3/4] 发送选题邮件...")
        success = sender.send_email(topics, len(hotspots))
        _write_json(
            run_dir / "run_summary.json",
            {
                "hotspots_count": len(hotspots),
                "topics_count": len(topics),
                "preview_path": str(preview_path),
                "sent": bool(success),
                "mode": "send",
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            },
        )

        if not success:
            logger.error("邮件发送失败。")
            return False

        logger.info("\n[4/4] 任务完成")
        logger.info("=" * 60)
        logger.info("今日选题已经检查通过，并成功发送。")
        logger.info("=" * 60)
        return True

    except Exception as error:
        logger.error(f"程序执行出错: {error}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
