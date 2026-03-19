"""
选题生成模块
基于热点和历史数据，使用AI生成选题
"""
from typing import List, Dict
import httpx
from openai import OpenAI
from src.utils import setup_logger, get_env, get_date_str
from src.analyzer import XiaoyeziAnalyzer

logger = setup_logger(__name__)


class TopicGenerator:
    """选题生成器"""

    def __init__(self):
        self.client = OpenAI(
            api_key=get_env('LLM_API_KEY'),
            base_url=get_env('LLM_API_BASE'),
            http_client=httpx.Client(trust_env=False)
        )
        self.model = get_env('LLM_MODEL', 'gpt-4')
        self.analyzer = XiaoyeziAnalyzer()

    def filter_relevant_hotspots(self, hotspots: List[Dict]) -> List[Dict]:
        """
        过滤出与音乐教育相关的热点
        """
        logger.info("开始过滤热点...")

        # 相关关键词
        music_keywords = [
            '音乐', '钢琴', '乐器', '演奏', '唱歌', '歌手', '明星', '电影',
            '艺术', '教育', '孩子', '学习', '考试', '学校', '家长', '培养',
            '郎朗', '李云迪', '周杰伦', '才艺', '比赛', '表演'
        ]

        relevant = []
        for spot in hotspots:
            title = spot['title']
            # 检查是否包含相关关键词
            if any(keyword in title for keyword in music_keywords):
                relevant.append(spot)

        logger.info(f"✅ 过滤完成，找到 {len(relevant)} 条相关热点")
        return relevant

    def generate_topics(self, hotspots: List[Dict], num_topics: int = 5) -> List[Dict]:
        """
        生成选题建议
        """
        logger.info("开始生成选题...")

        # 获取历史数据分析
        analysis_summary = self.analyzer.get_analysis_summary()

        # 过滤相关热点
        relevant_hotspots = self.filter_relevant_hotspots(hotspots)

        if not relevant_hotspots:
            logger.warning("⚠️  没有找到相关热点，使用所有热点")
            relevant_hotspots = hotspots[:20]

        # 构建提示词
        hotspots_text = "\n".join([
            f"{i+1}. [{spot['source']}] {spot['title']}"
            for i, spot in enumerate(relevant_hotspots[:30])
        ])

        prompt = f"""你是一个专业的音乐教育内容策划专家，专门为"小叶子钢琴智能陪练"公众号策划选题。

# 历史数据分析
{analysis_summary}

# 今日热点话题 ({get_date_str()})
{hotspots_text}

# 任务要求
请基于以上热点话题，结合小叶子公众号的内容风格，生成 {num_topics} 个优质选题建议。

每个选题需要包含：
1. 选题标题（吸引眼球，借鉴爆款文章风格）
2. 热点来源（**必须是上面列表中的原始热点标题**，格式：平台名 - 热点标题，例如："知乎热榜 - 故宫下雪刷屏"）
3. 切入角度（如何与音乐教育结合）
4. 内容方向（3-5个要点）
5. 爆款指数（1-5星，基于历史数据预测）
6. 目标分类（5大类中的哪一类）

# 选题策略
- 优先结合热点话题，找到音乐教育切入点
- 参考爆款文章的标题风格（用数字、名人、悬念等）
- 考虑家长痛点：孩子不爱练琴、如何坚持、如何提升兴趣
- 结合时令：寒假、暑假、考级季、新年等
- 明星/名人效应：郎朗、明星学琴故事

**重要：hotspot_source 必须从上面的热点列表中选择，保留原始标题，格式为"[平台] 原始热点标题"**

请返回纯JSON格式，不要有任何markdown标记，格式如下：
[{{"title": "选题标题", "hotspot_source": "[知乎热榜] 故宫下雪刷屏", "angle": "切入角度", "content_points": ["要点1", "要点2", "要点3"], "potential_rating": 5, "category": "钢琴学习技巧类", "reason": "推荐理由"}}]
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个专业的音乐教育内容策划专家。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )

            result = response.choices[0].message.content

            # 解析JSON
            import json
            # 提取JSON部分（可能被markdown包裹）
            if "```json" in result:
                result = result.split("```json")[1].split("```")[0].strip()
            elif "```" in result:
                result = result.split("```")[1].split("```")[0].strip()

            topics = json.loads(result)

            logger.info(f"✅ 成功生成 {len(topics)} 个选题")
            return topics

        except Exception as e:
            logger.error(f"❌ 选题生成失败: {e}")
            # 返回默认选题
            return self._get_fallback_topics()

    def _get_fallback_topics(self) -> List[Dict]:
        """备用选题（AI生成失败时使用）"""
        return [
            {
                "title": "郎朗最新演奏视频刷屏，藏着孩子学琴的3个秘密",
                "hotspot_source": "通用备用",
                "angle": "名家演奏赏析 → 学琴启发",
                "content_points": [
                    "郎朗演奏技巧解析",
                    "如何培养孩子的音乐感",
                    "坚持练琴的方法"
                ],
                "potential_rating": 5,
                "category": "名家演奏赏析类",
                "reason": "郎朗相关内容历来受欢迎，平均阅读量高"
            },
            {
                "title": "寒假练琴计划来了！这样安排，开学让老师刮目相看",
                "hotspot_source": "时令热点",
                "angle": "假期练琴规划 → 进步方法",
                "content_points": [
                    "科学的练琴时间安排",
                    "假期练琴目标设定",
                    "如何保持兴趣不枯燥"
                ],
                "potential_rating": 4,
                "category": "钢琴学习技巧类",
                "reason": "寒假是家长关注重点，练琴规划需求大"
            },
            {
                "title": "孩子不想练琴？聪明家长都在用这5个方法",
                "hotspot_source": "家长痛点",
                "angle": "教育方法 → 兴趣培养",
                "content_points": [
                    "了解孩子抗拒练琴的真实原因",
                    "游戏化练琴的5个小技巧",
                    "建立正向反馈机制"
                ],
                "potential_rating": 5,
                "category": "家长教育指导类",
                "reason": "家长教育类文章占比高，'孩子'提及233次"
            },
            {
                "title": "钢琴考级新政策发布，这些变化家长必须知道！",
                "hotspot_source": "考级政策",
                "angle": "政策变化 → 备考建议",
                "content_points": [
                    "考级政策最新变化解读",
                    "对琴童的影响分析",
                    "如何调整学习计划"
                ],
                "potential_rating": 5,
                "category": "考级政策资讯类",
                "reason": "考级政策类最易爆款，历史最高阅读79,484"
            },
            {
                "title": "10岁开始学琴晚不晚？看完这位钢琴家的故事就明白了",
                "hotspot_source": "励志故事",
                "angle": "年龄焦虑 → 学琴信心",
                "content_points": [
                    "大器晚成的钢琴家案例",
                    "不同年龄学琴的优势",
                    "如何科学规划学琴之路"
                ],
                "potential_rating": 4,
                "category": "明星音乐故事类",
                "reason": "打破年龄焦虑，给家长信心和希望"
            }
        ]


if __name__ == "__main__":
    # 测试代码
    generator = TopicGenerator()

    # 模拟热点数据
    test_hotspots = [
        {"title": "郎朗新年音乐会", "source": "微博", "heat": 10000},
        {"title": "教育部最新政策", "source": "百度", "heat": 8000},
    ]

    topics = generator.generate_topics(test_hotspots, num_topics=3)

    print("\n生成的选题：")
    for i, topic in enumerate(topics, 1):
        print(f"\n{i}. {topic['title']}")
        print(f"   分类：{topic['category']}")
        print(f"   爆款指数：{'⭐' * topic['potential_rating']}")
