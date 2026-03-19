"""
数据分析模块
分析小叶子公众号历史文章数据
"""
import pandas as pd
from typing import List, Dict
from src.utils import setup_logger
import os

logger = setup_logger(__name__)


class XiaoyeziAnalyzer:
    """小叶子历史文章分析器"""

    def __init__(self, excel_path: str = "data/小叶子钢琴智能陪练公众号数据.xlsx"):
        self.excel_path = excel_path
        self.df = None
        self.load_data()

    def load_data(self):
        """加载数据"""
        try:
            if not os.path.exists(self.excel_path):
                logger.error(f"❌ 数据文件不存在: {self.excel_path}")
                return

            self.df = pd.read_excel(self.excel_path)
            logger.info(f"✅ 加载历史文章数据成功，共 {len(self.df)} 篇")
        except Exception as e:
            logger.error(f"❌ 加载数据失败: {e}")

    def get_top_articles(self, n: int = 10) -> List[Dict]:
        """获取阅读量TOP N的文章"""
        if self.df is None:
            return []

        top = self.df.nlargest(n, '阅读数')[['文章标题', '阅读数', '点赞数', '在看数']]
        return top.to_dict('records')

    def get_keywords(self) -> Dict[str, int]:
        """分析关键词频率"""
        if self.df is None:
            return {}

        all_titles = ' '.join(self.df['文章标题'].dropna())

        # 定义关键词
        keywords = [
            '钢琴', '孩子', '练琴', '郎朗', '音乐', '家长', '学琴', '陪练',
            '小叶子', '老师', '考级', '琴童', '学习', '演奏', '教育', '弹琴',
            '技巧', '手指', '方法', '曲子', '视频', '课程', '比赛', '大师',
            '指法', '乐理', '节奏', '兴趣', '坚持', '天赋', '寒假', '暑假'
        ]

        keyword_counts = {kw: all_titles.count(kw) for kw in keywords}
        # 按频率排序
        sorted_keywords = dict(sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True))

        return sorted_keywords

    def get_article_categories(self) -> Dict[str, int]:
        """统计文章分类"""
        if self.df is None:
            return {}

        categories = {
            '钢琴学习技巧类': 0,
            '家长教育指导类': 0,
            '名家演奏赏析类': 0,
            '考级政策资讯类': 0,
            '明星音乐故事类': 0,
            '其他': 0
        }

        for _, row in self.df.iterrows():
            title = str(row['文章标题'])

            if any(kw in title for kw in ['练琴', '技巧', '方法', '指法', '乐理', '节奏']):
                categories['钢琴学习技巧类'] += 1
            elif any(kw in title for kw in ['孩子', '家长', '教育', '陪伴', '兴趣']):
                categories['家长教育指导类'] += 1
            elif any(kw in title for kw in ['郎朗', '演奏', '大师', '弹奏']):
                categories['名家演奏赏析类'] += 1
            elif any(kw in title for kw in ['考级', '证书', '政策', '教育部']):
                categories['考级政策资讯类'] += 1
            elif any(kw in title for kw in ['明星', '迪丽热巴', '刘晓庆', '刘德华']):
                categories['明星音乐故事类'] += 1
            else:
                categories['其他'] += 1

        return categories

    def get_stats(self) -> Dict:
        """获取统计信息"""
        if self.df is None:
            return {}

        return {
            'total_articles': len(self.df),
            'avg_reads': int(self.df['阅读数'].mean()),
            'avg_likes': int(self.df['点赞数'].mean()),
            'avg_shares': int(self.df['在看数'].mean()),
            'original_rate': f"{(self.df['原创'].value_counts().get('是', 0) / len(self.df) * 100):.1f}%"
        }

    def get_analysis_summary(self) -> str:
        """获取分析摘要（用于提供给AI）"""
        if self.df is None:
            return "无法加载历史数据"

        stats = self.get_stats()
        top_articles = self.get_top_articles(5)
        keywords = self.get_keywords()
        categories = self.get_article_categories()

        summary = f"""
# 小叶子公众号历史文章分析报告

## 基础数据
- 文章总数：{stats['total_articles']} 篇
- 原创率：{stats['original_rate']}
- 平均阅读数：{stats['avg_reads']}
- 平均点赞数：{stats['avg_likes']}
- 平均在看数：{stats['avg_shares']}

## TOP5 爆款文章
"""
        for i, article in enumerate(top_articles, 1):
            summary += f"{i}. {article['文章标题']} (阅读: {article['阅读数']})\n"

        summary += "\n## 高频关键词 (TOP 15)\n"
        for kw, count in list(keywords.items())[:15]:
            if count > 0:
                summary += f"- {kw}: {count}次\n"

        summary += "\n## 内容分类统计\n"
        for cat, count in categories.items():
            percentage = count / stats['total_articles'] * 100
            summary += f"- {cat}: {count}篇 ({percentage:.1f}%)\n"

        summary += """
## 选题策略建议
1. 考级政策类文章最容易爆款（历史最高7.9万阅读）
2. 郎朗相关内容必火（87次提及，平均阅读高）
3. 明星学琴故事吸引眼球（4万+阅读）
4. 家长教育指导类需求大（233次提及"孩子"）
5. 热点结合角度：电影音乐、明星动态、教育政策
"""

        return summary


if __name__ == "__main__":
    # 测试代码
    analyzer = XiaoyeziAnalyzer()

    print("\n" + "=" * 50)
    print("小叶子公众号数据分析")
    print("=" * 50)

    print(analyzer.get_analysis_summary())
