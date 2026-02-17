#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RSS源测试脚本
用于测试RSS源的可用性并生成报告
"""

import requests
import feedparser
import time
import json
from datetime import datetime
from typing import Dict, List, Tuple
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class RSSTester:
    def __init__(self):
        self.results = []
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
    def test_rss_feed(self, name: str, url: str, category: str) -> Dict:
        """测试单个RSS源"""
        result = {
            'name': name,
            'url': url,
            'category': category,
            'status': 'unknown',
            'response_time': 0,
            'entries_count': 0,
            'last_updated': None,
            'error': None,
            'sample_entries': []
        }
        
        start_time = time.time()
        
        try:
            # 尝试获取RSS内容
            response = requests.get(url, headers=self.headers, timeout=10, verify=False)
            response_time = time.time() - start_time
            result['response_time'] = round(response_time, 2)
            
            if response.status_code == 200:
                # 解析RSS内容
                feed = feedparser.parse(response.content)
                
                if feed.bozo:
                    result['status'] = 'parse_error'
                    result['error'] = str(feed.bozo_exception)
                else:
                    result['status'] = 'success'
                    result['entries_count'] = len(feed.entries)
                    
                    # 获取最后更新时间
                    if hasattr(feed.feed, 'updated_parsed') and feed.feed.updated_parsed:
                        result['last_updated'] = datetime(*feed.feed.updated_parsed[:6]).strftime('%Y-%m-%d %H:%M:%S')
                    
                    # 获取示例条目
                    for i, entry in enumerate(feed.entries[:3]):
                        if i < 3:  # 只取前3条作为示例
                            sample = {
                                'title': entry.get('title', '无标题'),
                                'link': entry.get('link', '无链接'),
                                'published': entry.get('published', '未知时间')[:50] if entry.get('published') else '未知时间'
                            }
                            result['sample_entries'].append(sample)
                    
            else:
                result['status'] = 'http_error'
                result['error'] = f"HTTP {response.status_code}"
                
        except requests.exceptions.Timeout:
            result['status'] = 'timeout'
            result['error'] = '请求超时'
        except requests.exceptions.ConnectionError:
            result['status'] = 'connection_error'
            result['error'] = '连接错误'
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
        
        return result
    
    def test_all_feeds(self, feeds_list: List[Dict]) -> List[Dict]:
        """测试所有RSS源"""
        print(f"开始测试 {len(feeds_list)} 个RSS源...")
        
        for i, feed_info in enumerate(feeds_list, 1):
            print(f"正在测试 [{i}/{len(feeds_list)}]: {feed_info['name']}")
            result = self.test_rss_feed(
                feed_info['name'],
                feed_info['url'],
                feed_info.get('category', '未分类')
            )
            self.results.append(result)
            
            # 避免请求过于频繁
            time.sleep(0.5)
        
        print("所有RSS源测试完成！")
        return self.results
    
    def generate_summary(self) -> Dict:
        """生成测试摘要"""
        total = len(self.results)
        success = len([r for r in self.results if r['status'] == 'success'])
        failed = total - success
        
        categories = {}
        for result in self.results:
            cat = result['category']
            if cat not in categories:
                categories[cat] = {'total': 0, 'success': 0}
            categories[cat]['total'] += 1
            if result['status'] == 'success':
                categories[cat]['success'] += 1
        
        # 计算平均响应时间
        successful_times = [r['response_time'] for r in self.results if r['status'] == 'success']
        avg_time = sum(successful_times) / len(successful_times) if successful_times else 0
        
        return {
            'total_feeds': total,
            'successful_feeds': success,
            'failed_feeds': failed,
            'success_rate': round(success / total * 100, 2) if total > 0 else 0,
            'average_response_time': round(avg_time, 2),
            'categories': categories,
            'test_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def save_results(self, filename: str = 'rss_test_results.json'):
        """保存测试结果到JSON文件"""
        data = {
            'summary': self.generate_summary(),
            'results': self.results,
            'test_timestamp': datetime.now().isoformat()
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"测试结果已保存到: {filename}")
        return filename

def get_rss_feeds_to_test():
    """获取要测试的RSS源列表"""
    feeds = [
        # 综合平台
        {'name': '全文RSS导航', 'url': 'https://quanwenrss.com/', 'category': '综合平台'},
        {'name': 'FeedSpot RSS目录', 'url': 'https://rss.feedspot.com/rss_directory/', 'category': '综合平台'},
        
        # 新闻类
        {'name': 'Solidot', 'url': 'https://www.solidot.org/index.rss', 'category': '新闻'},
        {'name': '煎蛋', 'url': 'http://jandan.net/feed', 'category': '新闻'},
        
        # 科技与编程
        {'name': '阮一峰的网络日志', 'url': 'https://www.ruanyifeng.com/blog/atom.xml', 'category': '科技编程'},
        {'name': '少数派', 'url': 'https://sspai.com/feed', 'category': '科技生活'},
        
        # 热门中文源
        {'name': '知乎日报', 'url': 'https://www.zhihu.com/rss', 'category': '社区问答'},
        {'name': 'V2EX', 'url': 'https://www.v2ex.com/index.xml', 'category': '技术社区'},
        
        # 测试其他类型
        {'name': 'GitHub博客', 'url': 'https://github.blog/feed/', 'category': '技术博客'},
        {'name': 'BBC新闻', 'url': 'http://feeds.bbci.co.uk/news/rss.xml', 'category': '国际新闻'},
        {'name': '纽约时报科技', 'url': 'https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml', 'category': '科技新闻'},
        {'name': 'Hacker News', 'url': 'https://news.ycombinator.com/rss', 'category': '技术新闻'},
        
        # 中文独立博客
        {'name': '酷壳', 'url': 'https://coolshell.cn/feed', 'category': '技术博客'},
        {'name': '云风博客', 'url': 'https://blog.codingnow.com/atom.xml', 'category': '游戏开发'},
        
        # 新媒体
        {'name': '爱范儿', 'url': 'https://www.ifanr.com/feed', 'category': '科技媒体'},
        {'name': '机核', 'url': 'https://www.gcores.com/rss', 'category': '游戏文化'},
    ]
    
    return feeds

def main():
    """主函数"""
    print("=" * 60)
    print("RSS源测试工具 v1.0")
    print("=" * 60)
    
    # 创建测试器
    tester = RSSTester()
    
    # 获取要测试的RSS源
    feeds_to_test = get_rss_feeds_to_test()
    
    # 测试所有RSS源
    results = tester.test_all_feeds(feeds_to_test)
    
    # 保存结果
    json_file = tester.save_results()
    
    # 生成摘要
    summary = tester.generate_summary()
    
    print("\n" + "=" * 60)
    print("测试摘要:")
    print("=" * 60)
    print(f"测试时间: {summary['test_time']}")
    print(f"总测试数: {summary['total_feeds']}")
    print(f"成功数: {summary['successful_feeds']}")
    print(f"失败数: {summary['failed_feeds']}")
    print(f"成功率: {summary['success_rate']}%")
    print(f"平均响应时间: {summary['average_response_time']}秒")
    
    print("\n分类统计:")
    for category, stats in summary['categories'].items():
        rate = stats['success'] / stats['total'] * 100 if stats['total'] > 0 else 0
        print(f"  {category}: {stats['success']}/{stats['total']} (成功率: {rate:.1f}%)")
    
    print("\n详细结果已保存到:")
    print(f"1. JSON文件: {json_file}")
    print("2. 请运行 generate_reports.py 生成Word文档和测试报告")
    
    return results, summary

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
    except Exception as e:
        print(f"\n发生错误: {e}")