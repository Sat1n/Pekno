import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget
from typing import Dict, Any, Optional
from pathlib import Path

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
    def extract_info(url: str, cookies: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        干跑模式：穿透目标视频防线提取直链及流媒体元数据，不执行系统级下载
        """
        opts = YTDlpService._get_base_opts()
        opts['extract_flat'] = False
        opts['download'] = False
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            YTDlpService._apply_cookies(ydl, cookies)
            return ydl.extract_info(url, download=False)

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
        with yt_dlp.YoutubeDL(opts) as ydl:
            YTDlpService._apply_cookies(ydl, cookies)
            ydl.download([url])

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
        with yt_dlp.YoutubeDL(opts) as ydl:
            YTDlpService._apply_cookies(ydl, cookies)
            ydl.download([url])

        expected_path = base_path.with_suffix(".mp4")
        if expected_path.exists():
            return str(expected_path)

        candidates = sorted(expected_path.parent.glob(f"{base_path.name}.*"))
        if candidates:
            return str(candidates[0])

        raise FileNotFoundError(f"yt-dlp 未在预期位置生成视频文件: {expected_path}")
