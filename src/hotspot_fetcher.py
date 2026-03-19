"""
热点抓取模块
混合方案：优先使用 DailyHotApi，失败则使用直接爬虫
"""
import requests
from typing import List, Dict
from bs4 import BeautifulSoup
from src.utils import setup_logger, get_env

logger = setup_logger(__name__)


class HotspotFetcher:
    """热点抓取器 - 混合方案"""

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        self.session = requests.Session()
        self.session.trust_env = False

    def fetch_weibo_hot(self) -> List[Dict]:
        """抓取微博热搜"""
        logger.info("开始抓取微博热搜...")
        try:
            # 方案1: 使用今日热榜聚合API
            url = "https://tophub.today/n/KqndgxeLl9"
            response = self.session.get(url, headers=self.headers, timeout=10)

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                items = soup.select('.al a')

                results = []
                for item in items[:30]:
                    title = item.get_text(strip=True)
                    href = item.get('href', '')
                    if title:
                        results.append({
                            'title': title,
                            'url': href,
                            'heat': 0,
                            'source': '微博热搜'
                        })

                if results:
                    logger.info(f"✅ 微博热搜抓取成功，获取 {len(results)} 条")
                    return results

            logger.warning("⚠️  微博热搜抓取失败，使用备用方案")
            return []

        except Exception as e:
            logger.error(f"❌ 微博热搜抓取异常: {e}")
            return []

    def fetch_zhihu_hot(self) -> List[Dict]:
        """抓取知乎热榜"""
        logger.info("开始抓取知乎热榜...")
        try:
            # 今日热榜 - 知乎
            url = "https://tophub.today/n/mproPpoq6O"
            response = self.session.get(url, headers=self.headers, timeout=10)

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                items = soup.select('.al a')

                results = []
                for item in items[:30]:
                    title = item.get_text(strip=True)
                    href = item.get('href', '')
                    if title:
                        results.append({
                            'title': title,
                            'url': href,
                            'heat': 0,
                            'source': '知乎热榜'
                        })

                if results:
                    logger.info(f"✅ 知乎热榜抓取成功，获取 {len(results)} 条")
                    return results

            logger.warning("⚠️  知乎热榜抓取失败")
            return []

        except Exception as e:
            logger.error(f"❌ 知乎热榜抓取异常: {e}")
            return []

    def fetch_baidu_hot(self) -> List[Dict]:
        """抓取百度热搜"""
        logger.info("开始抓取百度热搜...")
        try:
            url = "https://top.baidu.com/board?tab=realtime"
            response = self.session.get(url, headers=self.headers, timeout=10)

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                items = soup.select('.category-wrap_iQLoo .c-single-text-ellipsis')

                results = []
                for item in items[:30]:
                    title = item.get_text(strip=True)
                    if title:
                        results.append({
                            'title': title,
                            'url': f"https://www.baidu.com/s?wd={title}",
                            'heat': 0,
                            'source': '百度热搜'
                        })

                logger.info(f"✅ 百度热搜抓取成功，获取 {len(results)} 条")
                return results
            else:
                logger.error(f"❌ 百度热搜抓取失败: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"❌ 百度热搜抓取异常: {e}")
            return []

    def fetch_all_hotspots(self) -> List[Dict]:
        """
        抓取所有平台热点
        """
        logger.info("=" * 50)
        logger.info("开始抓取各平台热点...")
        logger.info("=" * 50)

        all_hotspots = []

        # 微博热搜
        weibo_hot = self.fetch_weibo_hot()
        all_hotspots.extend(weibo_hot)

        # 知乎热榜
        zhihu_hot = self.fetch_zhihu_hot()
        all_hotspots.extend(zhihu_hot)

        # 百度热搜
        baidu_hot = self.fetch_baidu_hot()
        all_hotspots.extend(baidu_hot)

        logger.info("=" * 50)
        logger.info(f"✅ 总共抓取到 {len(all_hotspots)} 条热点")
        logger.info("=" * 50)

        return all_hotspots


if __name__ == "__main__":
    # 测试代码
    fetcher = HotspotFetcher()
    hotspots = fetcher.fetch_all_hotspots()

    print(f"\n抓取到 {len(hotspots)} 条热点")
    print("\n前5条热点：")
    for i, spot in enumerate(hotspots[:5], 1):
        print(f"{i}. [{spot['source']}] {spot['title']}")
