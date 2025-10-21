# -*- coding: utf-8 -*-
# 依赖: ffmpeg/ffprobe, yt-dlp（解析页面直链或管道）
import os, sys, subprocess, math, argparse, json
from pathlib import Path
from typing import Optional, List
from urllib.parse import urlparse

FFMPEG   = os.environ.get("FFMPEG", "ffmpeg")
FFPROBE  = os.environ.get("FFPROBE", "ffprobe")

# 区间与策略
MAX_LT30, MAX_LT40, MAX_LT60, MAX_LE90 = 30, 40, 60, 90
INTERVAL_LT30, INTERVAL_30_40, INTERVAL_40_60, INTERVAL_60_90 = 1.0, 1.5, 2.0, 3.0
STRICT_ALIGN = False  # True=select 按间隔对齐；False=fps 更稳健

def is_url(s: str) -> bool:
    return isinstance(s, str) and s.startswith(("http://", "https://"))

def infer_name_from_source(source: str) -> str:
    if not is_url(source):
        return Path(source).stem
    p = urlparse(source)
    base = Path(p.path).name or "remote"
    name = Path(base).stem or "remote"
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name)[:80] or "remote"

def get_duration_seconds_local(video_path: str) -> float:
    cmd = [FFPROBE, "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", video_path]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(res.stdout.strip())
    except Exception:
        return math.nan

def _ytdlp_base(args: list, cookies: Optional[str], proxy: Optional[str], ua: Optional[str], referer: Optional[str]) -> list:
    cmd = [sys.executable, "-m", "yt_dlp"]
    cmd += ["--extractor-args", "tiktok:app_id=1233"]
    if cookies: cmd += ["--cookies", cookies]
    if proxy:   cmd += ["--proxy", proxy]
    if ua:      cmd += ["--user-agent", ua]
    if referer: cmd += ["--referer", referer]
    cmd += args
    return cmd

def resolve_direct_media_url(page_url: str, cookies: Optional[str], proxy: Optional[str], ua: Optional[str], referer: Optional[str]) -> Optional[str]:
    try:
        cmd = _ytdlp_base(
            ["-f", "bestvideo[ext=mp4][vcodec!=none]/bestvideo[vcodec!=none]/best[vcodec!=none]", "-g", page_url],
            cookies, proxy, ua, referer
        )
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)
        lines = [ln.strip() for ln in out.strip().splitlines() if ln.strip()]
        if lines:
            print(f"yt-dlp 直链解析成功: {lines[-1][:120]}...")
            return lines[-1]
        print("yt-dlp 未返回直链")
        return None
    except subprocess.CalledProcessError as e:
        print(f"yt-dlp 解析失败: {e.output.strip() if e.output else e}")
        return None
    except Exception as e:
        print(f"yt-dlp 异常: {e}")
        return None

def probe_duration(source: str, cookies: Optional[str], proxy: Optional[str], ua: Optional[str], referer: Optional[str]) -> float:
    if not is_url(source):
        return get_duration_seconds_local(source)
    try:
        meta_cmd = _ytdlp_base(["-J", source], cookies, proxy, ua, referer)
        meta_out = subprocess.check_output(meta_cmd, text=True, stderr=subprocess.STDOUT)
        j = json.loads(meta_out)
        if "duration" in j and j["duration"]:
            return float(j["duration"])
        if "entries" in j and j["entries"]:
            d = j["entries"][0].get("duration")
            if d:
                return float(d)
    except Exception:
        pass
    direct = resolve_direct_media_url(source, cookies, proxy, ua, referer)
    if direct:
        return get_duration_seconds_local(direct)
    return math.nan

def choose_interval(dur: float) -> float:
    if math.isnan(dur):
        return INTERVAL_40_60
    if dur < MAX_LT30:
        return INTERVAL_LT30
    if dur < MAX_LT40:
        return INTERVAL_30_40
    if dur < MAX_LT60:
        return INTERVAL_40_60
    if dur <= MAX_LE90:
        return INTERVAL_60_90
    raise RuntimeError(f"视频时长 {dur:.2f}s 超过 90 秒，暂不处理。")

def ffmpeg_extract(input_spec: str, out_pattern: str, interval: float, fps_val: float,
                   start: Optional[str], end: Optional[str],
                   ua: Optional[str], referer: Optional[str], proxy: Optional[str]) -> subprocess.CompletedProcess:
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error"]
    if ua:      cmd += ["-user_agent", ua]
    if referer: cmd += ["-referer", referer]
    if start:   cmd += ["-ss", start]
    if end:     cmd += ["-to", end]
    cmd += ["-i", input_spec]
    vf = f"select='not(mod(t,{interval}))',setpts=N/TB" if STRICT_ALIGN else f"fps={fps_val}"
    cmd += ["-vf", vf, "-q:v", "2", out_pattern]
    env = os.environ.copy()
    if proxy:
        env["HTTP_PROXY"] = proxy
        env["HTTPS_PROXY"] = proxy
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

def pipe_extract(page_url: str, out_pattern: str, interval: float, fps_val: float,
                 start: Optional[str], end: Optional[str],
                 cookies: Optional[str], proxy: Optional[str], ua: Optional[str], referer: Optional[str]) -> subprocess.CompletedProcess:
    y_cmd = _ytdlp_base(
        ["-f", "bestvideo[ext=mp4][vcodec!=none]/bestvideo[vcodec!=none]/best[vcodec!=none]", "-o", "-", page_url],
        cookies, proxy, ua, referer
    )
    y = subprocess.Popen(y_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error"]
    if start: cmd += ["-ss", start]
    if end:   cmd += ["-to", end]
    cmd += ["-i", "pipe:0"]
    vf = f"select='not(mod(t,{interval}))',setpts=N/TB" if STRICT_ALIGN else f"fps={fps_val}"
    cmd += ["-vf", vf, "-q:v", "2", out_pattern]
    env = os.environ.copy()
    if proxy:
        env["HTTP_PROXY"] = proxy
        env["HTTPS_PROXY"] = proxy
    try:
        res = subprocess.run(cmd, stdin=y.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    finally:
        try:
            if y.stdout: y.stdout.close()
        except Exception:
            pass
        try:
            y.wait(timeout=5)
        except Exception:
            pass
        try:
            err = y.stderr.read().decode("utf-8", "ignore")
            if err:
                print(f"yt-dlp(stderr): {err.strip()[:500]}")
        except Exception:
            pass
    return res

def process_one_video(src: str, base_outdir: Path, ua: Optional[str], referer: Optional[str],
                      proxy: Optional[str], cookies: Optional[str], start: Optional[str], end: Optional[str]) -> bool:
    name = infer_name_from_source(src)
    outdir = base_outdir / name
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"目标：{name} | 输出目录：{outdir}")

    dur = probe_duration(src, cookies=cookies, proxy=proxy, ua=ua, referer=referer)
    interval = choose_interval(dur)
    fps_val = 1.0 / interval
    print(f"检测到时长：{dur:.3f}s | 抽帧间隔：{interval}s/张（fps={fps_val:.6f}）")

    pre_count = len(list(outdir.glob("shot_*.jpg")))
    out_pattern = str(outdir / "shot_%06d.jpg")

    if is_url(src):
        direct = resolve_direct_media_url(src, cookies=cookies, proxy=proxy, ua=ua, referer=referer)
        res = None
        if direct:
            print("使用直链 + ffmpeg 拉流")
            res = ffmpeg_extract(direct, out_pattern, interval, fps_val, start, end, ua, referer, proxy)
            if res.returncode != 0:
                print("直链拉流失败，自动回落到 yt-dlp → ffmpeg 管道")
        if (not direct) or (res and res.returncode != 0):
            res = pipe_extract(src, out_pattern, interval, fps_val, start, end, cookies, proxy, ua, referer)
    else:
        res = ffmpeg_extract(src, out_pattern, interval, fps_val, start, end, ua, referer, proxy)

    post_count = len(list(outdir.glob("shot_*.jpg")))
    new_count = max(0, post_count - pre_count)

    if res.returncode != 0:
        print("❌ ffmpeg 执行失败：")
        try:
            print(res.stderr.decode("utf-8", "ignore"))
        except Exception:
            print(res.stderr)
        return False

    print(f"✅ 完成：{outdir}")
    print(f"🧮 本次输出帧数：{new_count} 张")
    return new_count > 0

def main(args=None):
    ap = argparse.ArgumentParser(description="按间隔抽帧（支持 TikTok 页面URL）")
    ap.add_argument("--video", action="append", required=True, help="可多次传入页面/媒体URL")
    ap.add_argument("--ua", help="User-Agent")
    ap.add_argument("--referer", help="Referer（如 https://www.tiktok.com/）")
    ap.add_argument("--proxy", help="代理，如 http://127.0.0.1:7890")
    ap.add_argument("--cookies", help="Netscape cookies.txt 路径（提升成功率）")
    ap.add_argument("--outdir", required=True, help="基准输出目录（每个视频会建子目录）")
    ap.add_argument("--start", help="起始时间 HH:MM:SS")
    ap.add_argument("--end", help="结束时间 HH:MM:SS")
    ap.add_argument("--strict", action="store_true", help="使用 select 对齐（默认 fps 更稳健）")
    if args is None:
        args = ap.parse_args()

    Path(args.outdir).mkdir(parents=True, exist_ok=True)
    global STRICT_ALIGN
    STRICT_ALIGN = bool(args.strict)

    all_ok = True
    for src in args.video:
        ok = process_one_video(
            src=src,
            base_outdir=Path(args.outdir),
            ua=args.ua, referer=args.referer,
            proxy=args.proxy, cookies=args.cookies,
            start=args.start, end=args.end
        )
        all_ok = all_ok and ok
    return all_ok

if __name__ == "__main__":
    main()