import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget
from typing import Dict, Any, Optional
from pathlib import Path
import re

class YTDlpService:
    @staticmethod
    def _get_base_opts() -> Dict[str, Any]:
        """
        初始化核心请求伪装参数，防止遭遇防爬虫机制 (例如 WAF 拦截或验证码)
        """
        opts = {
            'quiet': True,
            'no_warnings': True,
            'impersonate': ImpersonateTarget.from_str('chrome'), # 利用 cffi 等插件开启浏览器特征伪装
        }
        return opts

    @staticmethod
    def _apply_cookies(ydl, cookies: Any):
        if not cookies:
            return
            
        cookie_str = ""
        if isinstance(cookies, dict):
            cookie_str = '; '.join([f"{k}={v}" for k, v in cookies.items()])
        elif isinstance(cookies, str):
            cookie_str = cookies
            
        ydl.params['http_headers'] = ydl.params.get('http_headers', {})
        ydl.params['http_headers']['Cookie'] = cookie_str

    @staticmethod
    def _extract_bilibili_bvid(url: str) -> Optional[str]:
        match = re.search(r'(BV[a-zA-Z0-9]+)', url or '')
        return match.group(1) if match else None

    @staticmethod
    def _build_bilibili_fallback_url(url: str) -> Optional[str]:
        if "bilibili.com" not in (url or "") and "b23.tv" not in (url or "") and "BV" not in (url or ""):
            return None

        bvid = YTDlpService._extract_bilibili_bvid(url)
        if not bvid:
            return None

        fallback_url = f"https://www.bilibili.com/video/{bvid}"
        return None if fallback_url == url else fallback_url

    @staticmethod
    def _run_with_bilibili_fallback(action_name: str, url: str, runner):
        try:
            return runner(url)
        except Exception as primary_exc:
            fallback_url = YTDlpService._build_bilibili_fallback_url(url)
            if not fallback_url:
                raise

            try:
                return runner(fallback_url)
            except Exception as fallback_exc:
                raise RuntimeError(
                    f"{action_name} 失败: original_url={url}; fallback_url={fallback_url}; "
                    f"primary_error={primary_exc}; fallback_error={fallback_exc}"
                ) from fallback_exc
        
    @staticmethod
    def extract_info(url: str, cookies: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        干跑模式：穿透目标视频防线提取直链及流媒体元数据，不执行系统级下载
        """
        opts = YTDlpService._get_base_opts()
        opts['extract_flat'] = False
        opts['download'] = False
        
        def _runner(target_url: str):
            with yt_dlp.YoutubeDL(opts) as ydl:
                YTDlpService._apply_cookies(ydl, cookies)
                return ydl.extract_info(target_url, download=False)

        return YTDlpService._run_with_bilibili_fallback("extract_info", url, _runner)

    @staticmethod
    def download_audio(url: str, output_path: str, cookies: Optional[Dict[str, str]] = None) -> str:
        """
        下载最佳音质，并依靠 ffmpeg 强制封构为 MP3
        """
        target_path = Path(output_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        base_path = target_path.with_suffix("")

        opts = YTDlpService._get_base_opts()
        opts.update({
            'format': 'bestaudio/best',
            'outtmpl': str(base_path) + '.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        })
        def _runner(target_url: str):
            with yt_dlp.YoutubeDL(opts) as ydl:
                YTDlpService._apply_cookies(ydl, cookies)
                ydl.download([target_url])

        YTDlpService._run_with_bilibili_fallback("download_audio", url, _runner)

        expected_path = base_path.with_suffix(".mp3")
        if expected_path.exists():
            return str(expected_path)

        candidates = sorted(expected_path.parent.glob(f"{base_path.name}.*"))
        if candidates:
            return str(candidates[0])

        raise FileNotFoundError(f"yt-dlp 未在预期位置生成音频文件: {expected_path}")

    @staticmethod
    def download_video_1080p(url: str, output_path: str, cookies: Optional[Dict[str, str]] = None) -> str:
        """
        精准切分视频源，硬锁定最高 1080p (防止 4K/8K 文件爆炸)，混入本地 ffmpeg 将音轨缝合入 mp4
        """
        target_path = Path(output_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        base_path = target_path.with_suffix("")

        opts = YTDlpService._get_base_opts()
        opts.update({
            'format': 'bestvideo[height<=1080]+bestaudio/best',
            'merge_output_format': 'mp4',
            'outtmpl': str(base_path) + '.%(ext)s',
        })
        def _runner(target_url: str):
            with yt_dlp.YoutubeDL(opts) as ydl:
                YTDlpService._apply_cookies(ydl, cookies)
                ydl.download([target_url])

        YTDlpService._run_with_bilibili_fallback("download_video_1080p", url, _runner)

        expected_path = base_path.with_suffix(".mp4")
        if expected_path.exists():
            return str(expected_path)

        candidates = sorted(expected_path.parent.glob(f"{base_path.name}.*"))
        if candidates:
            return str(candidates[0])

        raise FileNotFoundError(f"yt-dlp 未在预期位置生成视频文件: {expected_path}")
