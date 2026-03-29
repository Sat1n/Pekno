import re
from typing import Any, Dict, List

import httpx

from shared.plugins.base import BasePlugin, PluginContext

class BilibiliPlugin(BasePlugin):
    def _extract_bvid(self, url: str) -> str | None:
        bv_match = re.search(r'(BV[a-zA-Z0-9]+)', url)
        return bv_match.group(1) if bv_match else None

    def _clean_html_text(self, html_content: str) -> str:
        clean_text = re.sub(r'<[^>]+>', ' ', html_content or "")
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        if clean_text == "-":
            return "该视频暂无详细简介"
        return clean_text

    def _normalize_video_item(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        raw_link = (
            raw_data.get("short_link")
            or raw_data.get("short_link_v2")
            or raw_data.get("url", "")
            or raw_data.get("link", "")
        )
        bvid = raw_data.get("bvid") or self._extract_bvid(raw_link)
        aid = raw_data.get("aid")
        uid = bvid or aid or raw_link

        owner = raw_data.get("owner") or {}
        authors = raw_data.get("authors", [])
        up_name = owner.get("name") or (authors[0].get("name") if authors else None) or "未知 UP 主"
        up_mid = owner.get("mid")

        html_content = raw_data.get("content_html", "") or raw_data.get("summary", "")
        clean_text = (raw_data.get("desc") or "").strip() or self._clean_html_text(html_content)

        cover_url = raw_data.get("pic", "")
        if not cover_url and html_content:
            img_match = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', html_content)
            if img_match:
                cover_url = img_match.group(1)

        tags = []
        if raw_data.get("tname"):
            tags.append(raw_data.get("tname"))
        if up_name and up_name not in tags:
            tags.append(up_name)

        auto_ai = raw_data.get("_ctx_enable_ai", False)

        return {
            "id": uid,
            "title": raw_data.get("title", "未命名视频"),
            "source_type": "bilibili_subscribed",
            "raw_link": raw_link or (f"https://www.bilibili.com/video/{bvid}" if bvid else ""),
            "content_text": clean_text,
            "intent": "video",
            "tags": tags,
            "auto_ai_processing": auto_ai,
            "capabilities": ["summarize"],
            "metadata_extra": {
                "up_name": up_name,
                "up_mid": up_mid,
                "pubdate": raw_data.get("pubdate") or raw_data.get("date_published"),
                "duration": raw_data.get("duration", 0),
                "cover_url": cover_url,
            }
        }

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
        return self._normalize_video_item(raw_data)

    async def extract_text_for_ai(self, ctx: PluginContext, raw_data: Dict[str, Any]) -> str:
        # B站视频的核心文本要素就是标题、UP主和纯文本简介
        norm = self.normalize_item(raw_data)
        up_name = norm["metadata_extra"]["up_name"]
        
        text = f"【视频标题】: {norm['title']}\n"
        text += f"【UP 主】: {up_name}\n"
        text += f"【视频简介】: {norm['content_text']}\n"
        
        # 探针测试 (Dry Run) - 尝试脱壳解析视频本体流
        cookie = ctx.config.get("cookie", "")
        try:
            import asyncio
            from hub.core.media.downloader import YTDlpService
            ctx.log.info(f"YTDlp 探针测试启动: {norm['raw_link']}")
            
            # 使用 asyncio.to_thread 包装底层阻塞的 yt-dlp 发包调用
            info = await asyncio.to_thread(YTDlpService.extract_info, norm["raw_link"], cookie)
            duration = info.get("duration", "未知")
            resolution = info.get("resolution", "未知")
            format_ext = info.get("ext", "未知")
            
            ctx.log.info(f"🎯 [YTDlp 探针洞穿成功] 视频: {norm['title']} | 时长: {duration}s | 画质: {resolution} | 格式: {format_ext}")
        except Exception as e:
            ctx.log.error(f"❌ [YTDlp 探针穿透失败] 针对 {norm['raw_link']} 的解析受阻: {e}")
        
        return text

    async def parse_single_item(self, url: str, ctx: PluginContext | None = None) -> Dict[str, Any]:
        bvid = self._extract_bvid(url)
        if not bvid:
            raise ValueError("暂时仅支持直接包含 BV 号的 Bilibili 视频链接")
        api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": f"https://www.bilibili.com/video/{bvid}",
        }
        if ctx and ctx.config.get("cookie"):
            headers["Cookie"] = ctx.config["cookie"]

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(api_url, headers=headers)
            response.raise_for_status()
            payload = response.json()

        if payload.get("code") != 0 or "data" not in payload:
            raise ValueError("Bilibili 视频解析失败，请确认链接有效")

        data = payload["data"]
        raw_item = {
            "bvid": bvid,
            "aid": data.get("aid"),
            "title": data.get("title", ""),
            "desc": data.get("desc", ""),
            "short_link": data.get("short_link_v2") or data.get("short_link") or f"https://www.bilibili.com/video/{bvid}",
            "owner": data.get("owner", {}),
            "pubdate": data.get("pubdate"),
            "duration": data.get("duration", 0),
            "pic": data.get("pic", ""),
            "tname": data.get("tname"),
            "_ctx_enable_ai": False,
        }
        normalized = self._normalize_video_item(raw_item)
        normalized["_pipeline_raw_data"] = raw_item
        return normalized

    async def get_hover_blocks(self, item_url: str, user_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        import httpx
        import time
        
        # 提取 BVID
        bv_match = re.search(r'(BV[a-zA-Z0-9]+)', item_url)
        if not bv_match:
            return []
            
        bvid = bv_match.group(1)
        cookie = user_config.get("cookie", "")
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/"
        }
        if cookie:
            headers["Cookie"] = cookie
            
        blocks = []
        aid = None
        view_api = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        
        async with httpx.AsyncClient() as client:
            # 1. 获取视频底层数据 (投币 点赞 播放量) 和 aid
            try:
                resp1 = await client.get(view_api, headers=headers, timeout=10.0)
                resp1.raise_for_status()
                data1 = resp1.json()
                
                if data1.get("code") == 0 and "data" in data1:
                    stat = data1["data"].get("stat", {})
                    aid = data1["data"].get("aid")
                    
                    blocks.append({
                        "block_type": "kv",
                        "kv_data": {
                            "播放": self._format_num(stat.get("view", 0)),
                            "点赞": self._format_num(stat.get("like", 0)),
                            "投币": self._format_num(stat.get("coin", 0))
                        }
                    })
            except Exception as e:
                pass
                
            # 2. 抓取热评数据
            if aid:
                reply_api = f"https://api.bilibili.com/x/v2/reply?type=1&oid={aid}&sort=1"
                try:
                    resp2 = await client.get(reply_api, headers=headers, timeout=10.0)
                    resp2.raise_for_status()
                    data2 = resp2.json()
                    
                    if data2.get("code") == 0 and data2.get("data"):
                        reply_data = data2["data"]
                        # 优先读取 hots 热评数组，如果为空再读 replies 普通数组
                        comments = reply_data.get("hots") or reply_data.get("replies") or []
                        
                        # 取前3条
                        for item in comments[:3]:
                            member = item.get("member", {})
                            content = item.get("content", {})
                            
                            date_str = ""
                            ctime = item.get("ctime")
                            if ctime:
                                date_str = time.strftime("%Y-%m-%d", time.localtime(ctime))
                                
                            blocks.append({
                                "block_type": "quote",
                                "author": member.get("uname", "未知用户"),
                                "avatar_url": member.get("avatar", ""),
                                "content": content.get("message", "无内容"),
                                "date": date_str
                            })
                except Exception as e:
                    pass
                    
        return blocks

    def _format_num(self, num: int) -> str:
        if num >= 10000:
            return f"{num/10000:.1f}w"
        return str(num)

# 铁律：末尾必须暴露 plugin 实例
plugin = BilibiliPlugin()
