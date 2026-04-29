#!/usr/bin/env python3
"""
新闻 Agent：抓取热榜 → 六大分类 → DeepSeek 摘要 → 输出 HTML
已优化错误处理，确保某源失败不影响整体
"""
import os, sys, traceback, feedparser, requests
from datetime import datetime
from collections import defaultdict

RSSHUB_BASE = "https://rsshub.app"
HOT_ROUTES = [
    "/weibo/search/hot",
    "/toutiao/trending",
    "/baidu/top",
    "/zhihu/hotlist",
    "/36kr/hot",
    "/wallstreetcn/hot",
]

CATEGORY_KEYWORDS = {
    "AI": ["ai", "人工智能", "大模型", "gpt", "chatgpt", "sora", "深度学习",
           "openai", "gemini", "claude", "aigc", "llm", "stable diffusion",
           "算法", "机器学习", "推理", "多模态", "智能体", "deepseek"],
    "科技": ["芯片", "半导体", "光刻", "鸿蒙", "华为", "小米", "苹果", "特斯拉",
             "spacex", "火箭", "卫星", "量子", "核聚变", "新能源", "电池",
             "自动驾驶", "机器人", "5g", "6g", "元宇宙", "vr", "ar"],
    "互联网巨头": ["阿里", "阿里巴巴", "腾讯", "微信", "字节", "抖音", "tiktok",
                   "京东", "拼多多", "美团", "快手", "小红书"],
    "中国政策": ["国务院", "工信部", "发改委", "央行", "证监会", "政策", "法规",
                 "新规", "反垄断", "数据安全"],
    "中国经济": ["经济", "gdp", "通胀", "cpi", "a股", "上证", "深证", "楼市",
                 "利率", "出口", "消费"],
    "美国要闻": ["美国", "白宫", "美联储", "拜登", "特朗普", "美股", "加息",
                 "降息", "硅谷", "tiktok"],
}

MAX_PER_SOURCE = 10
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

def safe_fetch(url, source_name):
    try:
        feed = feedparser.parse(url)
        entries = []
        for e in feed.entries[:MAX_PER_SOURCE]:
            entries.append({
                "title": e.get("title", "").strip(),
                "link": e.get("link", ""),
                "source": source_name
            })
        return entries
    except Exception as e:
        print(f"[跳过] {source_name} 抓取失败: {e}")
        return []

def fetch_hot_news():
    all_entries = []
    for route in HOT_ROUTES:
        url = f"{RSSHUB_BASE}{route}"
        source = route.split("/")[-1]  # 用路由尾缀做临时来源名
        all_entries.extend(safe_fetch(url, source))
    # 去重
    seen = set()
    dedup = []
    for item in all_entries:
        if item["link"] and item["link"] not in seen:
            seen.add(item["link"])
            dedup.append(item)
    return dedup

def classify(articles):
    classified = defaultdict(list)
    for art in articles:
        text = art["title"].lower()
        for cat, kws in CATEGORY_KEYWORDS.items():
            if any(kw in text for kw in kws):
                classified[cat].append(art)
    return classified

def build_prompt(classified):
    parts = []
    for cat in ["AI", "科技", "互联网巨头", "中国政策", "中国经济", "美国要闻"]:
        arts = classified.get(cat, [])
        if not arts:
            continue
        lines = [f"【{cat}】"]
        for i, a in enumerate(arts, 1):
            lines.append(f"{i}. {a['title']} （来源：{a['source']}）")
        parts.append("\n".join(lines))
    return "\n\n".join(parts) if parts else "今日无相关新闻"

def deepseek_summary(prompt):
    if not DEEPSEEK_API_KEY:
        return "未配置 API Key"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    system = ("你是资深时政科技编辑。根据下面各类新闻标题，用简洁中文分六段总结今日要闻，每段不超过60字，"
              "顺序为：🤖 AI进展、🚀 科技产业、🏢 互联网巨头、🇨🇳 中国政策、💰 中国经济、🇺🇸 美国要闻。"
              "只输出内容，不用Markdown，某类无新闻则写“今日无重要动态”。")
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 700
    }
    try:
        r = requests.post(DEEPSEEK_API_URL, json=payload, headers=headers, timeout=40)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"摘要生成失败: {e}"

def generate_html(classified, summary):
    today = datetime.now().strftime("%Y-%m-%d")
    title = f"📰 {today} AI 每日精选"
    summary_lines = summary.split("\n")
    summary_html = "".join(f"<p>{line.strip()}</p>" for line in summary_lines if line.strip())

    categories_html = ""
    for cat in ["AI", "科技", "互联网巨头", "中国政策", "中国经济", "美国要闻"]:
        arts = classified.get(cat, [])
        if not arts:
            continue
        cats = f'<div class="category"><h2>{cat}</h2><ol>'
        for a in arts:
            cats += f'<li><a href="{a["link"]}" target="_blank">{a["title"]}</a> <span class="source">({a["source"]})</span></li>'
        cats += '</ol></div>'
        categories_html += cats

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f9f9f9; color: #333; }}
h1 {{ text-align: center; }}
.summary {{ background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-bottom: 30px; }}
.summary p {{ margin: 8px 0; font-size: 16px; line-height: 1.6; }}
.category {{ background: white; padding: 15px 20px; margin: 15px 0; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }}
.category h2 {{ margin-top: 0; border-bottom: 2px solid #eee; padding-bottom: 8px; }}
a {{ color: #0066cc; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.source {{ color: #888; font-size: 0.9em; }}
.footer {{ text-align: center; margin-top: 40px; color: #aaa; font-size: 14px; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="summary">{summary_html}</div>
{categories_html}
<div class="footer">由新闻AI Agent自动生成 · 每日08:00更新</div>
</body>
</html>"""
    return html

def main():
    print("开始抓取热榜…")
    articles = fetch_hot_news()
    print(f"抓取到 {len(articles)} 条去重新闻")
    classified = classify(articles)
    prompt = build_prompt(classified)
    print("请求 DeepSeek 摘要…")
    summary = deepseek_summary(prompt)
    html = generate_html(classified, summary)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("✅ index.html 生成成功")

if __name__ == "__main__":
    main()
