# -*- coding: utf-8 -*-
import os, glob, argparse, tempfile
from pathlib import Path
from datetime import datetime
import pandas as pd

from extract_multi_subtitles_from_web import main as subs_main
from take_multi_screenshots_from_web import main as frames_main
from scrape_multi_comments_from_web import main as comments_main
from product_description import main as product_main
from auto_api import main as api_main

# ================== 默认参数 ================== 
DEFAULT_URLS_FILE = r"/Users/samxie/Research/Infound_Influencer/tiktok_partner_back/part2_multiVideos/urls.txt"
DEFAULT_SHOP_URL = "https://www.tiktok.com/view/product/1729512876806413127?region=FR"
DEFAULT_OUTDIR = r"/Users/samxie/Research/Infound_Influencer/tiktok_partner_back/data/video_part"
DEFAULT_PROMPT_FILE = r"/Users/samxie/Research/Infound_Influencer/tiktok_partner_back/part2_multiVideos/prompt_10fields_tsv.txt"
DEFAULT_SUMMARY_PROMPT_FILE = r"/Users/samxie/Research/Infound_Influencer/tiktok_partner_back/part2_multiVideos/summary_prompt.txt"
DEFAULT_EDGE_PROFILE = None
DEFAULT_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
DEFAULT_MAX_COMMENTS = 150
DEFAULT_MAIN_ONLY = False
DEFAULT_MAX_IMAGES = 50
DEFAULT_COOKIES = None
DEFAULT_API_KEY = "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"
# =====================================

def video_id_from_url(url: str) -> str:
    import re
    m = re.search(r'/video/(\d+)', url)
    return m.group(1) if m else "unknown"

def ensure_file(path: Path, empty_content: str = ""):
    """如果文件不存在，则生成空文件"""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(empty_content)
    return path

def main():
    parser = argparse.ArgumentParser(description="多视频 TikTok 工作流")
    parser.add_argument("--urls-file")
    parser.add_argument("--outdir")
    parser.add_argument("--shop_url")
    parser.add_argument("--prompt-file")
    parser.add_argument("--summary-prompt-file")
    parser.add_argument("--edge-user-data-dir")
    parser.add_argument("--api-key")
    args = parser.parse_args()

    urls_path = Path(args.urls_file or DEFAULT_URLS_FILE)
    if not urls_path.exists():
        raise FileNotFoundError(f"视频链接文件不存在: {urls_path}")

    with open(urls_path, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    outdir = Path(args.outdir or DEFAULT_OUTDIR)
    shop_url = args.shop_url or DEFAULT_SHOP_URL
    prompt_file = Path(args.prompt_file or DEFAULT_PROMPT_FILE)
    summary_prompt_file = Path(args.summary_prompt_file or DEFAULT_SUMMARY_PROMPT_FILE)
    edge_profile = args.edge_user_data_dir or DEFAULT_EDGE_PROFILE
    api_key = args.api_key or DEFAULT_API_KEY

    outdir.mkdir(parents=True, exist_ok=True)

    video_csvs = []

    for video in urls:
        vid = video_id_from_url(video)
        print(f"▶ 处理视频: {video} (vid={vid})")

        # 输出目录
        out_subs = outdir / "subtitles"; out_subs.mkdir(exist_ok=True)
        out_frames = outdir / "frames"; out_frames.mkdir(exist_ok=True)
        out_comments = outdir / "comments"; out_comments.mkdir(exist_ok=True)
        out_desc = outdir / "description"; out_desc.mkdir(exist_ok=True)
        out_api = outdir / "api_results"; out_api.mkdir(exist_ok=True)

        # ---------------- 字幕 ----------------
        try:
            subs_main(argparse.Namespace(
                video=[video], outdir=str(out_subs),
                proxy=None, ua=DEFAULT_UA, referer=None,
                cookies=DEFAULT_COOKIES, edge_user_data_dir=None, no_browser=True
            ))
        except Exception as e:
            print(f"⚠️ 视频 {vid} 字幕提取失败: {e}")

        cand_txt = glob.glob(str(out_subs / f"*{vid}*.txt"))
        cand_srt = glob.glob(str(out_subs / f"*{vid}*.srt"))
        subs_candidates = cand_txt or cand_srt
        if subs_candidates:
            subs_path = max(subs_candidates, key=os.path.getctime)
        else:
            subs_path = out_subs / f"{vid}_empty.txt"
            ensure_file(subs_path)

        # ---------------- 截图 ----------------
        try:
            frames_main(argparse.Namespace(
                video=[video], outdir=str(out_frames),
                proxy=None, ua=DEFAULT_UA, referer=None,
                cookies=DEFAULT_COOKIES,
                start=None, end=None, strict=False
            ))
        except Exception as e:
            print(f"⚠️ 视频 {vid} 截图失败: {e}")
        frames_dir = out_frames / vid

        # ---------------- 评论 ----------------
        try:
            comments_main(argparse.Namespace(
                video=[video], videos_file=None, outdir=str(out_comments),
                edge_user_data_dir=edge_profile,
                max_comments=DEFAULT_MAX_COMMENTS,
                main_only=DEFAULT_MAIN_ONLY
            ))
        except Exception as e:
            print(f"⚠️ 视频 {vid} 评论抓取失败: {e}")

        comment_candidates = glob.glob(str(out_comments / "tiktok_comments" / f"*{vid}*.txt"))
        if comment_candidates:
            comments_txt = max(comment_candidates, key=os.path.getctime)
        else:
            comments_txt = out_comments / f"{vid}_empty.txt"
            ensure_file(comments_txt)

        # ---------------- 商品 ----------------
        try:
            product_main(argparse.Namespace(
                shop_url=[shop_url], outdir=str(out_desc),
                user_data_dir=edge_profile,
                headless=True, timeout_ms=20000
            ))
        except Exception as e:
            print(f"⚠️ 视频 {vid} 商品抓取失败: {e}")

        # ---------------- GPT 分析 ----------------
        try:
            api_main(argparse.Namespace(
                video=video, outdir=str(out_api),
                subs=str(subs_path),  # 已保证存在
                comments=str(comments_txt),  # 已保证存在
                frames=str(frames_dir),
                custom_prompt_file=str(prompt_file) if prompt_file.exists() else None,
                custom_prompt_text=None,
                max_images=DEFAULT_MAX_IMAGES, proxy=None,
                api_key=api_key, model="gpt-4o"
            ))
        except Exception as e:
            print(f"⚠️ 视频 {vid} GPT 分析失败: {e}")

        # 收集 GPT 输出 CSV
        gpt_csvs = list(Path(out_api).glob("*.csv"))
        if gpt_csvs:
            latest_csv = max(gpt_csvs, key=os.path.getctime)
            video_csvs.append(latest_csv)

    # ---------------- summary ----------------
    if video_csvs:
        out_summary = outdir / "summary_api"
        out_summary.mkdir(exist_ok=True)

        # 拼接每个视频 CSV 内容（直接读取文本，不做 DataFrame 合并）
        merged_text = ""
        for csv_file in video_csvs:
            try:
                with open(csv_file, "r", encoding="utf-16") as f:
                    merged_text += f.read() + "\n"
            except Exception as e:
                print(f"⚠️ 读取 CSV {csv_file} 失败: {e}")

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-16", suffix=".txt") as tmpf:
            tmpf.write(merged_text)
            tmp_path = tmpf.name

        try:
            api_main(argparse.Namespace(
                video="all_videos", outdir=str(out_summary),
                subs=tmp_path, comments=tmp_path, frames=tmp_path,
                custom_prompt_file=str(summary_prompt_file) if summary_prompt_file.exists() else None,
                custom_prompt_text=None,
                max_images=0, proxy=None,
                api_key=api_key, model="gpt-4o"
            ))
        except Exception as e:
            print(f"⚠️ summary GPT 调用失败: {e}")

        summary_csvs = list(out_summary.glob("*.csv"))
        if summary_csvs:
            summary_csv = max(summary_csvs, key=os.path.getctime)
            print(f"✅ 总结 summary 已生成: {summary_csv}")
        else:
            print("⚠️ summary GPT 输出 CSV 未找到")
    else:
        print("⚠️ 没有任何视频 CSV 可用于生成 summary")

if __name__ == "__main__":
    main()
