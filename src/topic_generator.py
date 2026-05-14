"""Generate MusicNews topics from distinct hotspots."""

from typing import Dict, List
import json
import re
from difflib import SequenceMatcher

import httpx
from openai import OpenAI

from src.analyzer import XiaoyeziAnalyzer
from src.utils import get_date_str, get_env, setup_logger

logger = setup_logger(__name__)


class TopicGenerator:
    """Generate one topic per hotspot."""

    CATEGORY_WHITELIST = [
        "家长教育指导类",
        "钢琴学习技巧类",
        "考级政策资讯类",
        "明星音乐故事类",
        "练琴心理沟通类",
    ]

    def __init__(self):
        self.client = OpenAI(
            api_key=get_env("LLM_API_KEY"),
            base_url=get_env("LLM_API_BASE"),
            http_client=httpx.Client(trust_env=False),
        )
        self.model = get_env("LLM_MODEL", "gpt-4")
        self.analyzer = XiaoyeziAnalyzer()

    def _build_hotspot_label(self, spot: Dict) -> str:
        source = str(spot.get("source", "")).strip()
        title = str(spot.get("title", "")).strip()
        return f"[{source}] {title}"

    def _hotspot_source_key(self, source: str, title: str) -> tuple:
        return (
            str(source or "").strip().lower(),
            self._normalize_hotspot_title(title),
        )

    def _dedupe_hotspots(self, hotspots: List[Dict]) -> List[Dict]:
        unique = []
        seen = set()

        for spot in hotspots:
            source = str(spot.get("source", "")).strip()
            title = str(spot.get("title", "")).strip()
            if not title:
                continue

            key = self._hotspot_source_key(source, title)
            if key in seen:
                continue

            seen.add(key)
            unique.append(spot)

        return unique

    def _normalize_hotspot_title(self, title: str) -> str:
        text = str(title or "").lower().strip()
        boilerplate = [
            "如何看待",
            "怎么看待",
            "怎么看",
            "为什么",
            "有哪些",
            "意味着什么",
            "说明了什么",
        ]
        for item in boilerplate:
            text = text.replace(item, "")

        text = re.sub(r"[^\w\u4e00-\u9fff]", "", text)
        return text

    def _title_ngrams(self, title: str) -> set:
        normalized = self._normalize_hotspot_title(title)
        if len(normalized) < 2:
            return {normalized} if normalized else set()

        grams = {normalized[index:index + 2] for index in range(len(normalized) - 1)}
        grams.add(normalized)
        return grams

    def _hotspots_are_similar(self, left: Dict, right: Dict) -> bool:
        left_title = self._normalize_hotspot_title(left.get("title", ""))
        right_title = self._normalize_hotspot_title(right.get("title", ""))

        if not left_title or not right_title:
            return False

        if left_title == right_title:
            return True

        shorter = min(len(left_title), len(right_title))
        if shorter >= 6 and (left_title in right_title or right_title in left_title):
            return True

        ratio = SequenceMatcher(None, left_title, right_title).ratio()
        if ratio >= 0.72:
            return True

        left_grams = self._title_ngrams(left_title)
        right_grams = self._title_ngrams(right_title)
        if not left_grams or not right_grams:
            return False

        overlap = len(left_grams & right_grams)
        union = len(left_grams | right_grams)
        return union > 0 and (overlap / union) >= 0.5

    def _can_add_hotspot(self, spot: Dict, selected: List[Dict], seen_labels: set) -> bool:
        label = self._build_hotspot_label(spot)
        if label in seen_labels:
            return False

        for existing in selected:
            if self._hotspots_are_similar(spot, existing):
                return False

        return True

    def _label_source_key(self, label: str) -> tuple:
        text = str(label or "").strip()
        match = re.match(r"^\[([^\]]+)\]\s*(.*)$", text)
        if not match:
            return ("", self._normalize_hotspot_title(text))
        return self._hotspot_source_key(match.group(1), match.group(2))

    def filter_relevant_hotspots(self, hotspots: List[Dict]) -> List[Dict]:
        """Pick hotspots that are easier to turn into music-education topics."""
        logger.info("Start filtering hotspots")

        music_keywords = [
            "音乐",
            "钢琴",
            "乐器",
            "演奏",
            "歌手",
            "明星",
            "艺术",
            "教育",
            "孩子",
            "学习",
            "考试",
            "学校",
            "家长",
            "培养",
            "比赛",
            "表演",
        ]

        relevant = []
        for spot in hotspots:
            title = str(spot.get("title", ""))
            if any(keyword in title for keyword in music_keywords):
                relevant.append(spot)

        logger.info("Filtered hotspots count: %s", len(relevant))
        return relevant

    def _merge_hotspot_candidates(
        self,
        relevant_hotspots: List[Dict],
        all_hotspots: List[Dict],
    ) -> List[Dict]:
        ordered = []
        seen_labels = set()

        for pool in (self._dedupe_hotspots(relevant_hotspots), self._dedupe_hotspots(all_hotspots)):
            for spot in pool:
                label = self._build_hotspot_label(spot)
                if label in seen_labels:
                    continue

                seen_labels.add(label)
                ordered.append(spot)

        return ordered

    def _select_hotspots_for_topics(
        self,
        relevant_hotspots: List[Dict],
        all_hotspots: List[Dict],
        num_topics: int,
    ) -> List[Dict]:
        candidates = self._merge_hotspot_candidates(relevant_hotspots, all_hotspots)
        selected = []
        seen_labels = set()
        platform_counts = {}
        buckets = {}
        platform_order = []

        for spot in candidates:
            source = str(spot.get("source", "")).strip() or "unknown"
            if source not in buckets:
                buckets[source] = []
                platform_order.append(source)
            buckets[source].append(spot)

        progress = True
        while progress and len(selected) < num_topics:
            progress = False
            ordered_platforms = sorted(
                platform_order,
                key=lambda source: (platform_counts.get(source, 0), platform_order.index(source)),
            )

            for source in ordered_platforms:
                while buckets[source]:
                    candidate = buckets[source].pop(0)
                    if not self._can_add_hotspot(candidate, selected, seen_labels):
                        continue

                    selected.append(candidate)
                    seen_labels.add(self._build_hotspot_label(candidate))
                    platform_counts[source] = platform_counts.get(source, 0) + 1
                    progress = True
                    break

                if len(selected) >= num_topics:
                    return selected

        return selected

    def _match_hotspot_label(self, raw_source: str, selected_hotspots: List[Dict]) -> str:
        text = str(raw_source or "").strip()
        if not text:
            return ""

        for spot in selected_hotspots:
            label = self._build_hotspot_label(spot)
            if text == label:
                return label

        for spot in selected_hotspots:
            label = self._build_hotspot_label(spot)
            title = str(spot.get("title", "")).strip()
            if title and title in text:
                return label

        return ""

    def _build_fallback_topic(self, spot: Dict, index: int) -> Dict:
        title = str(spot.get("title", "")).strip()

        return {
            "title": f"{title}背后，钢琴家长最该看懂的3个提醒",
            "hotspot_source": self._build_hotspot_label(spot),
            "angle": "把这个热点转成家长能直接用上的音乐教育提醒",
            "content_points": [
                "先解释这个热点为什么会让家长有共鸣，再接到练琴家庭里最常见的真实场景",
                "拆出老师最想提醒家长注意的1到3个误区，不讲空话，只讲看得见的表现",
                "给出家长今天就能做的小动作，让热点能落回练琴陪伴和孩子状态管理",
            ],
            "potential_rating": max(3, 5 - (index % 2)),
            "category": "家长教育指导类",
            "reason": "AI 没有按要求覆盖这个热点，系统补了一条不重复热点的保底选题。",
        }

    def _clean_text(self, value, *, keep_punctuation: bool = True) -> str:
        text = str(value or "").strip()
        text = re.sub(r"\s+", " ", text)
        text = text.replace("**", "").replace("##", "").replace("`", "")
        if not keep_punctuation:
            text = re.sub(r"[“”\"'《》【】\[\]]", "", text)
        return text.strip(" \t\r\n-:：;；")

    def _shorten_text(self, value, max_length: int) -> str:
        text = self._clean_text(value)
        if len(text) <= max_length:
            return text

        shortened = text[:max_length].rstrip("，。、；：！？,.!? ")
        return f"{shortened}..."

    def _normalize_category(self, value) -> str:
        category = self._clean_text(value, keep_punctuation=False)
        for item in self.CATEGORY_WHITELIST:
            if item in category:
                return item
        return "家长教育指导类"

    def _normalize_points(self, points) -> List[str]:
        if not isinstance(points, list):
            points = [points]

        normalized = []
        for point in points:
            text = self._shorten_text(point, 46)
            if len(text) < 8:
                continue
            normalized.append(text)

        seen = set()
        unique_points = []
        for point in normalized:
            if point in seen:
                continue
            seen.add(point)
            unique_points.append(point)

        return unique_points[:4]

    def _normalize_topics(
        self,
        topics,
        selected_hotspots: List[Dict],
        num_topics: int,
    ) -> List[Dict]:
        normalized = []
        used_labels = set()
        used_source_keys = set()

        if not isinstance(topics, list):
            topics = []

        for topic in topics:
            if not isinstance(topic, dict):
                continue

            label = self._match_hotspot_label(topic.get("hotspot_source", ""), selected_hotspots)
            source_key = self._label_source_key(label)
            if not label or label in used_labels or source_key in used_source_keys:
                continue

            item = dict(topic)
            item["hotspot_source"] = label

            title = self._shorten_text(item.get("title", ""), 34)
            if not title:
                item["title"] = f"{label}：这件事对练琴家庭最重要的提醒"
            else:
                item["title"] = title

            angle = self._shorten_text(item.get("angle", ""), 70)
            if not angle:
                item["angle"] = "把热点翻成音乐教育场景下，家长和老师都能用的提醒"
            else:
                item["angle"] = angle

            item["category"] = self._normalize_category(item.get("category", ""))

            points = self._normalize_points(item.get("content_points", []))
            if len(points) < 3:
                points.extend(
                    [
                        "解释这个热点为什么会影响家长判断",
                        "拆出练琴家庭里最容易忽略的信号",
                        "给出老师和家长可以立刻执行的做法",
                    ]
                )
            item["content_points"] = points[:4]

            reason = self._shorten_text(item.get("reason", ""), 60)
            if not reason:
                item["reason"] = "这个热点和家长真实焦虑距离很近，容易转成音乐教育内容。"
            else:
                item["reason"] = reason

            try:
                rating = int(item.get("potential_rating", 3))
            except Exception:
                rating = 3
            item["potential_rating"] = max(1, min(5, rating))

            normalized.append(item)
            used_labels.add(label)
            used_source_keys.add(source_key)

            if len(normalized) >= num_topics:
                return normalized

        for index, spot in enumerate(selected_hotspots):
            if len(normalized) >= num_topics:
                break

            label = self._build_hotspot_label(spot)
            source_key = self._label_source_key(label)
            if label in used_labels or source_key in used_source_keys:
                continue

            normalized.append(self._build_fallback_topic(spot, index))
            used_labels.add(label)
            used_source_keys.add(source_key)

        return normalized[:num_topics]

    def generate_topics(self, hotspots: List[Dict], num_topics: int = 5) -> List[Dict]:
        """Generate topics with distinct hotspot sources."""
        logger.info("Start generating topics")

        analysis_summary = self.analyzer.get_analysis_summary()
        relevant_hotspots = self.filter_relevant_hotspots(hotspots)

        if not relevant_hotspots:
            logger.warning("No relevant hotspots found, fallback to general hotspots")
            relevant_hotspots = hotspots

        selected_hotspots = self._select_hotspots_for_topics(
            relevant_hotspots,
            hotspots,
            num_topics,
        )

        if not selected_hotspots:
            logger.warning("No hotspots available, fallback to built-in topics")
            return self._get_fallback_topics()[:num_topics]

        hotspots_text = "\n".join(
            f"{index + 1}. {self._build_hotspot_label(spot)}"
            for index, spot in enumerate(selected_hotspots)
        )

        prompt = f"""你是一个专业的音乐教育内容策划专家，专门为钢琴教育公众号做选题。

# 历史数据分析
{analysis_summary}

# 今日指定热点（{get_date_str()}）
{hotspots_text}

# 任务要求
请严格基于上面列出的 {len(selected_hotspots)} 个热点，生成 {num_topics} 个选题。
最重要的规则：
1. 一条选题只能对应一条热点。
2. 同一个热点绝对不能重复使用。
3. 你必须覆盖上面列出的前 {num_topics} 个热点，不能只盯着其中一个热点反复写。
4. hotspot_source 必须原样填写上面列表里的完整文字。

每个选题都要包含：
1. title
2. hotspot_source
3. angle
4. content_points
5. potential_rating
6. category
7. reason

请只返回 JSON 数组，不要写 markdown。
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个专业的音乐教育选题策划专家。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
            )

            result = response.choices[0].message.content
            if "```json" in result:
                result = result.split("```json")[1].split("```")[0].strip()
            elif "```" in result:
                result = result.split("```")[1].split("```")[0].strip()

            topics = json.loads(result)
            topics = self._normalize_topics(topics, selected_hotspots, num_topics)

            logger.info("Generated topics count: %s", len(topics))
            return topics

        except Exception as error:
            logger.error("Topic generation failed: %s", error)
            fallback_topics = self._normalize_topics([], selected_hotspots, num_topics)
            if fallback_topics:
                return fallback_topics
            return self._get_fallback_topics()[:num_topics]

    def _get_fallback_topics(self) -> List[Dict]:
        """Built-in fallback topics."""
        return [
            {
                "title": "郎朗最新演奏刷屏后，钢琴家长最容易忽略的3个基本功提醒",
                "hotspot_source": "通用备用-1",
                "angle": "从名家演奏热度，转到孩子学琴时更真实的基本功观察",
                "content_points": [
                    "为什么家长容易只看结果，不看孩子平时的动作质量",
                    "老师最常提醒的练琴基本功误区有哪些",
                    "家长回家后可以马上检查的3个小地方",
                ],
                "potential_rating": 5,
                "category": "钢琴学习技巧类",
                "reason": "名家演奏类内容长期稳定，适合作为安全备用题。",
            },
            {
                "title": "孩子一到练琴就拖延？家长最该先改掉的不是催促",
                "hotspot_source": "通用备用-2",
                "angle": "从家长最常见的陪练冲突，切到可执行的家庭方法",
                "content_points": [
                    "为什么一催就更抗拒",
                    "怎么把练琴时间拆小一点",
                    "怎么建立孩子愿意开始的开头动作",
                ],
                "potential_rating": 5,
                "category": "家长教育指导类",
                "reason": "家长陪练冲突是长期高频问题。",
            },
            {
                "title": "考级季快到了，孩子现在最该补的不是曲子数量",
                "hotspot_source": "通用备用-3",
                "angle": "从考级焦虑转到练琴安排和节奏控制",
                "content_points": [
                    "为什么临近考级更要先稳基本功",
                    "一周练琴时间怎么分配更合理",
                    "家长怎么判断孩子是在进步还是在硬扛",
                ],
                "potential_rating": 4,
                "category": "考级政策资讯类",
                "reason": "考级相关内容一直有稳定需求。",
            },
            {
                "title": "孩子弹琴总是手紧？老师通常先看这3个身体信号",
                "hotspot_source": "通用备用-4",
                "angle": "从身体状态切入，避免家长把问题都怪到态度上",
                "content_points": [
                    "常见的错误坐姿和发力问题",
                    "哪些信号说明孩子已经紧张过头了",
                    "家长怎么在家做最简单的观察",
                ],
                "potential_rating": 4,
                "category": "钢琴学习技巧类",
                "reason": "身体状态类内容实用性强，容易转发收藏。",
            },
            {
                "title": "为什么有些孩子越练越没信心？问题常常不在天赋",
                "hotspot_source": "通用备用-5",
                "angle": "从信心问题切入，连接家庭沟通和老师反馈方式",
                "content_points": [
                    "哪些话最容易伤到孩子练琴信心",
                    "老师和家长应该怎么分工",
                    "怎么让孩子重新找到可见的小进步",
                ],
                "potential_rating": 4,
                "category": "家长教育指导类",
                "reason": "情绪和信心问题一直是家长很在意的话题。",
            },
        ]


if __name__ == "__main__":
    generator = TopicGenerator()
    test_hotspots = [
        {"title": "郎朗新年音乐会", "source": "微博", "heat": 10000},
        {"title": "教育部最新政策", "source": "百度热搜", "heat": 8000},
        {"title": "孩子练琴总拖延", "source": "知乎热榜", "heat": 7000},
    ]

    topics = generator.generate_topics(test_hotspots, num_topics=3)

    print("\n生成的选题：")
    for index, topic in enumerate(topics, start=1):
        print(f"\n{index}. {topic['title']}")
        print(f"   热点：{topic['hotspot_source']}")
