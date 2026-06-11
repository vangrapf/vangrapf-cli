#!/usr/bin/env python3
"""
Vangrapf CLI - video downloader/streamer with Rich GUI, auto-proxy for YouTube,
search and interactive selection.
"""

import argparse
import subprocess
import sys
import os
import re
import requests
from pathlib import Path
from typing import Optional, List, Dict, Any
from urllib.parse import quote

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn

console = Console()

# ---------- Constants ----------
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
DEFAULT_TIMEOUT = 30

PROXY_LIST_URL = "https://raw.githubusercontent.com/vangrapf/proxylist/refs/heads/main/proxylist.txt"

# ---------- Platform detection (used without proxy) ----------
PLATFORM_CONFIGS = {
    "rutube": {"extractor_args": {"rutube": {"player_client": "web"}}, "format": "best[height<=1080]"},
    "vk": {"extractor_args": {"vk": {"player_client": "web"}}, "format": "best[height<=1080]"},
    "ok": {"extractor_args": {"ok": {}}, "format": "best[height<=1080]"},
    "youtube": {"extractor_args": {"youtube": {"player_client": "default,-android_sdkless"}}, "format": "best[height<=1080]"},
    "tiktok": {"extractor_args": {"tiktok": {"webapp": "true"}}, "format": "best"},
}

def detect_platform(url: str) -> str:
    if "rutube.ru" in url: return "rutube"
    if "vk.com/video" in url or "vk.ru/video" in url or "vkvideo.ru" in url or "vkvideo.com" in url: return "vk"
    if "ok.ru" in url: return "ok"
    if "youtube.com" in url or "youtu.be" in url: return "youtube"
    if "tiktok.com" in url or "vm.tiktok.com" in url or "vt.tiktok.com" in url: return "tiktok"
    return "unknown"

# ---------- Auto-proxy loading ----------
def load_proxy_from_url(url: str) -> Optional[str]:
    """Download proxy.txt and return the first non-comment URL."""
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        lines = resp.text.splitlines()
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                if line.startswith('http://') or line.startswith('https://'):
                    return line
        console.print("[yellow]No working proxy found in the list[/yellow]")
        return None
    except Exception as e:
        console.print(f"[red]Failed to load proxy list: {e}[/red]")
        return None

def apply_auto_proxy(video_url: str, args) -> None:
    """If no proxy is set and the video is from YouTube, try to load an auto-proxy."""
    if args.proxy:
        return
    platform = detect_platform(video_url)
    if platform == "youtube":
        auto_proxy = load_proxy_from_url(PROXY_LIST_URL)
        if auto_proxy:
            console.print(f"[green]Using auto-proxy: {auto_proxy}[/green]")
            args.proxy = auto_proxy
        else:
            console.print("[yellow]Auto-proxy not available. Falling back to direct access (may not work).[/yellow]")

# ---------- YouTube API search ----------
def search_youtube_api(query: str, api_key: str, max_results: int = 10) -> List[Dict[str, str]]:
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "maxResults": max_results,
        "type": "video",
        "key": api_key
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("items", []):
            video_id = item["id"]["videoId"]
            title = item["snippet"]["title"]
            channel = item["snippet"]["channelTitle"]
            results.append({
                "title": title,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "channel": channel,
                "duration": "?"
            })
        return results
    except Exception as e:
        console.print(f"[red]YouTube API error: {e}[/red]")
        return []

# ---------- Search via yt-dlp (fallback) ----------
def search_youtube_ytdlp(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    import yt_dlp
    search_query = f"ytsearch{max_results}:{query}"
    ydl_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_query, download=False)
            entries = info.get('entries', [])
            results = []
            for entry in entries:
                results.append({
                    "title": entry.get('title', 'Unknown'),
                    "url": entry.get('url'),
                    "channel": entry.get('uploader', '?'),
                    "duration": str(entry.get('duration', '?'))
                })
            return results
    except Exception as e:
        console.print(f"[red]yt-dlp search error: {e}[/red]")
        return []

# ---------- Interactive selection ----------
def interactive_select(videos: List[Dict[str, str]], prompt_msg: str = "Select video") -> Optional[Dict[str, str]]:
    if not videos:
        console.print("[yellow]No results[/yellow]")
        return None
    table = Table(title="Search results")
    table.add_column("#", style="cyan", no_wrap=True)
    table.add_column("Title", style="white")
    table.add_column("Channel", style="green")
    table.add_column("Duration", style="yellow")
    for idx, v in enumerate(videos, 1):
        table.add_row(str(idx), v['title'][:70], v['channel'], v.get('duration', '?'))
    console.print(table)
    while True:
        choice = Prompt.ask(f"{prompt_msg} [1-{len(videos)}] or 'q' to quit", default="1")
        if choice.lower() == 'q':
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(videos):
            return videos[int(choice)-1]
        console.print("[red]Invalid input[/red]")

# ---------- Direct mode (no proxy) ----------
def watch_direct(url: str, cookies_path: Optional[str] = None) -> bool:
    import yt_dlp
    try:
        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get("title", "Video")
        cmd = ["mpv", f"--user-agent={DEFAULT_USER_AGENT}", "--cache=yes", url]
        if cookies_path and os.path.exists(cookies_path):
            cmd.extend(["--cookies", f"--cookies-file={cookies_path}"])
        console.print(f"[green]Playing:[/green] {title}")
        subprocess.run(cmd, check=False)
        return True
    except Exception as e:
        console.print(f"[red]Direct watch failed: {e}[/red]")
        return False

def download_direct(url: str, output_dir: str, cookies_path: Optional[str] = None) -> bool:
    import yt_dlp
    out_dir = Path(output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "quiet": True, "no_warnings": True, "user_agent": DEFAULT_USER_AGENT,
        "outtmpl": str(out_dir / "%(title)s.%(ext)s"), "merge_output_format": "mp4",
    }
    if cookies_path and os.path.exists(cookies_path):
        opts["cookiefile"] = cookies_path
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        console.print("[green]Download complete.[/green]")
        return True
    except Exception as e:
        console.print(f"[red]Download failed: {e}[/red]")
        return False

# ---------- Proxy mode (using your backend) ----------
def watch_via_proxy(proxy_base: str, video_url: str, cookies_path: Optional[str] = None) -> bool:
    stream_endpoint = proxy_base.rstrip('/') + '/stream'
    full_stream_url = f"{stream_endpoint}?url={quote(video_url)}"
    mpv_cmd = [
        "mpv", f"--user-agent={DEFAULT_USER_AGENT}", "--cache=yes", "--cache-secs=30",
        "--demuxer-max-bytes=50MiB", "--demuxer-max-back-bytes=20MiB", "--osd-bar",
        full_stream_url
    ]
    if cookies_path and os.path.exists(cookies_path):
        mpv_cmd.extend(["--cookies", f"--cookies-file={cookies_path}"])
    try:
        console.print(f"[cyan]Streaming via proxy:[/cyan] {proxy_base}")
        subprocess.run(mpv_cmd, check=False)
        return True
    except FileNotFoundError:
        console.print("[red]mpv not found. Install: sudo apt install mpv[/red]")
        return False
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped[/yellow]")
        return True

def download_via_proxy(proxy_base: str, video_url: str, output_dir: str, cookies_path: Optional[str] = None) -> bool:
    endpoint = proxy_base.rstrip('/') + '/download'
    payload = {"url": video_url}
    if cookies_path:
        payload["cookies_path"] = cookies_path
    out_dir = Path(output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    output_file = out_dir / "video.mp4"
    try:
        console.print(f"Requesting download from {endpoint}")
        with requests.post(endpoint, json=payload, stream=True, timeout=120) as r:
            if r.status_code != 200:
                console.print(f"[red]Proxy error: HTTP {r.status_code} – {r.text}[/red]")
                return False
            content_disp = r.headers.get('Content-Disposition', '')
            if 'filename=' in content_disp:
                match = re.search(r'filename[*]?=["\']?([^"\']+)["\']?', content_disp)
                if match:
                    output_file = out_dir / match.group(1).strip()
            total = int(r.headers.get('content-length', 0))
            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeRemainingColumn(),
                console=console
            ) as progress:
                task = progress.add_task("[cyan]Downloading...", total=total)
                with open(output_file, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            progress.update(task, advance=len(chunk))
            console.print(f"[green]Downloaded: {output_file}[/green]")
            return True
    except Exception as e:
        console.print(f"[red]Download error: {e}[/red]")
        return False

# ---------- Main ----------
def main():
    parser = argparse.ArgumentParser(description="Vangrapf CLI - video downloader/streamer with Rich GUI")
    parser.add_argument("url", nargs="?", help="Video URL to process")
    parser.add_argument("--search", "-s", type=str, help="Search query for YouTube")
    parser.add_argument("--api-key", type=str, help="YouTube Data API v3 key (optional, otherwise uses yt-dlp search)")
    mode_group = parser.add_mutually_exclusive_group(required=False)
    mode_group.add_argument("--watch", "-w", action="store_true", help="Stream video via mpv")
    mode_group.add_argument("--download", "-d", action="store_true", help="Download video to disk")
    parser.add_argument("-o", "--output", type=str, default=".", help="Output directory for --download")
    parser.add_argument("-c", "--cookies", type=str, help="Path to cookies.txt file")
    parser.add_argument("--proxy", type=str, help="Proxy backend URL (e.g., https://a41736-1c8a.y.d-f.pw)")
    parser.add_argument("-q", "--quality", type=str, choices=["720","1080","best"], default="best", help="Quality (only without proxy)")
    parser.add_argument("--subs", type=str, choices=["all","ru","en","none"], default="none", help="Subtitles (only without proxy)")
    parser.add_argument("--embed-subs", action="store_true", help="Embed subtitles (only without proxy)")
    args = parser.parse_args()

    # ----- Search mode -----
    if args.search:
        query = args.search
        console.print(Panel(f"[bold]Search:[/bold] {query}", title="YouTube"))

        # Warning if no API key is provided
        if not args.api_key:
            console.print("[yellow]Warning: Search without --api-key uses yt-dlp and may be slow or unreliable. It is recommended to provide a YouTube Data API v3 key for fast and reliable search.[/yellow]")

        if args.api_key:
            videos = search_youtube_api(query, args.api_key)
        else:
            videos = search_youtube_ytdlp(query)

        if not videos:
            sys.exit(1)
        selected = interactive_select(videos)
        if not selected:
            sys.exit(0)
        video_url = selected['url']
        # Auto-proxy for selected video (if YouTube)
        apply_auto_proxy(video_url, args)
        if not args.watch and not args.download:
            console.print("[yellow]Specify --watch or --download after search[/yellow]")
            sys.exit(1)
        if args.watch:
            ok = watch_via_proxy(args.proxy, video_url, args.cookies) if args.proxy else watch_direct(video_url, args.cookies)
            sys.exit(0 if ok else 1)
        if args.download:
            ok = download_via_proxy(args.proxy, video_url, args.output, args.cookies) if args.proxy else download_direct(video_url, args.output, args.cookies)
            sys.exit(0 if ok else 1)

    # ----- Normal mode (URL given) -----
    if not args.url:
        parser.print_help()
        sys.exit(1)

    # Auto-proxy for direct URL
    apply_auto_proxy(args.url, args)

    if args.proxy:
        if args.watch:
            ok = watch_via_proxy(args.proxy, args.url, args.cookies)
            sys.exit(0 if ok else 1)
        elif args.download:
            ok = download_via_proxy(args.proxy, args.url, args.output, args.cookies)
            sys.exit(0 if ok else 1)
        else:
            console.print("[red]Please specify --watch or --download[/red]")
            sys.exit(1)
    else:
        platform = detect_platform(args.url)
        if platform == "unknown":
            console.print(f"[red]Unsupported platform: {args.url}[/red]")
            sys.exit(2)
        console.print(f"Platform: [bold]{platform.upper()}[/bold]")
        if args.watch:
            ok = watch_direct(args.url, args.cookies)
            sys.exit(0 if ok else 1)
        elif args.download:
            ok = download_direct(args.url, args.output, args.cookies)
            sys.exit(0 if ok else 1)
        else:
            console.print("[red]Please specify --watch or --download[/red]")
            sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped[/yellow]")
        sys.exit(130)
