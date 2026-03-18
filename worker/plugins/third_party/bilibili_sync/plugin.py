import re
from typing import List, Dict, Any
from shared.plugins.base import BasePlugin, PluginContext

class BilibiliPlugin(BasePlugin):
    async def fetch_data(self, ctx: PluginContext) -> List[Dict[str, Any]]:
        # 获取配置
        base_url = ctx.config.get("rsshub_base_url", "https://rsshub.app").rstrip("/")
        uid = ctx.config.get("uid")
        
        # 获取配置：是否开启 AI 总结 (默认为 False)
        enable_ai = ctx.config.get("enable_ai_summary", False)
        
        if not uid:
            ctx.log.error("未配置 B站 UID，跳过同步")
            return []
            
        # 拼接 RSSHub JSON 路由
        url = f"{base_url}/bilibili/followings/video/{uid}?format=json"
        ctx.log.info(f"正在从 RSSHub 拉取 Bilibili 动态: {url}")
        
        # 将 enable_ai 传入 normalize_item (这里需要修改方法签名或通过闭包传递，但 normalize_item 是基类方法)
        # 简单起见，我们直接在这个方法内处理后处理
        # 实际上 normalize_item 是同步方法，我们可以把 enable_ai 作为一个成员变量临时存起来，或者把 ctx 传进去？
        # 不行，normalize_item 签名是固定的。
        # 既然如此，我们直接在下面用 lambda 或者在这里直接把 enable_ai 注入到 item 中
        
        # 修正：fetch_data 返回的是 List[Dict]，还没变成 UniversalItem
        # 我们可以在 fetch_data 里把配置项塞进 metadata_extra，然后在 normalize_item 里读出来？
        # 或者更简单的：normalize_item 返回字典，我们在 fetch_data 里无法干预后续流程
        # 等等，pipeline 是调用的 plugin.normalize_item(raw_item)。
        # 所以我们可以在 fetch_data 里给每个 raw_item 加上 "_enable_ai": enable_ai 这样的私有字段
        
        try:
            # 发起请求
            response = await ctx.http.get(url)
            response.raise_for_status()
            data = response.json()
            
            # 返回 items 列表
            items = data.get("items", [])
            
            # 为每个 item 注入配置标记
            for item in items:
                item["_ctx_enable_ai"] = enable_ai
                
            ctx.log.info(f"成功获取到 {len(items)} 条 Bilibili 视频动态")
            return items
            
        except Exception as e:
            ctx.log.error(f"拉取 Bilibili 数据失败: {str(e)}")
            return []

    def normalize_item(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        # 提取基础字段
        raw_link = raw_data.get("url", "") or raw_data.get("link", "")
        title = raw_data.get("title", "未命名视频")
        
        # 尝试从 URL 提取 BV 号作为 ID，如果失败则用原始链接的哈希
        video_id = raw_link
        bv_match = re.search(r'(BV[a-zA-Z0-9]+)', raw_link)
        if bv_match:
            video_id = bv_match.group(1)
            
        # 提取 UP 主名称
        up_name = "未知 UP 主"
        authors = raw_data.get("authors", [])
        if authors and len(authors) > 0:
            up_name = authors[0].get("name", up_name)
            
        # 提取封面：利用正则从 content_html 或 summary 中寻找 img 标签的 src
        cover_url = ""
        html_content = raw_data.get("content_html", "") or raw_data.get("summary", "")
        img_match = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', html_content)
        if img_match:
            cover_url = img_match.group(1)
            
        # 净化 content_html 以便作为摘要 (移除 iframe, img, br 等)
        clean_text = re.sub(r'<[^>]+>', ' ', html_content)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        if clean_text == "-":  # RSSHub 经常返回一个横杠
            clean_text = "该视频暂无详细简介"
            
        # 读取 fetch_data 注入的 AI 开关
        auto_ai = raw_data.get("_ctx_enable_ai", False)
            
        return {
            "id": video_id,
            "title": title,
            "raw_link": raw_link,
            "source_type": "bilibili",
            "intent": "video",  # 明确内容类型为视频
            "content_text": clean_text,
            "tags": [up_name],
            "auto_ai_processing": auto_ai,  # 由用户配置决定
            "capabilities": ["summarize"],
            "metadata_extra": {
                "up_name": up_name,
                "cover_url": cover_url,
                "published_at": raw_data.get("date_published")
            }
        }

    async def extract_text_for_ai(self, ctx: PluginContext, raw_data: Dict[str, Any]) -> str:
        # B站视频的核心文本要素就是标题、UP主和纯文本简介
        norm = self.normalize_item(raw_data)
        up_name = norm["metadata_extra"]["up_name"]
        
        text = f"【视频标题】: {norm['title']}\n"
        text += f"【UP 主】: {up_name}\n"
        text += f"【视频简介】: {norm['content_text']}\n"
        
        return text

# 铁律：末尾必须暴露 plugin 实例
plugin = BilibiliPlugin()