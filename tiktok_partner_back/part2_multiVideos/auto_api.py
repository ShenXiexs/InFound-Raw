# -*- coding: utf-8 -*-
"""
api_runner.py
作用：把素材与自定义提示词交给大模型，原样返回模型输出（不做解析/结构化），仅做最小包装，便于 workflow 直接调用。

示例：
python api_runner.py ^
  --video "https://www.tiktok.com/@xxx/video/7511077669191093522" ^
  --outdir "D:\Tiktok\workflow_output\api_results" ^
  --subs "D:\Tiktok\workflow_output\subtitles\7511077669191093522.en.srt" ^
  --comments "D:\Tiktok\workflow_output\comments\tiktok_comments\tiktok_comments_7511077669191093522_*.txt" ^
  --frames "D:\Tiktok\workflow_output\frames\7511077669191093522" ^
  --custom-prompt-file "D:\Tiktok\prompt_10fields_tsv.txt" ^
  --max-images 12 ^
  --api-key "sk-xxxx"
"""
import os, re, glob, argparse, mimetypes, base64
from datetime import datetime
import httpx
from openai import OpenAI


# ========== 工具 ==========
def read_text(path: str) -> str:
    """读取文本文件"""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def to_data_url(path: str) -> str:
    """将图片文件转换为data URL"""
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def parse_ts(ts: str) -> float:
    """解析时间戳 00:00:01,234 -> 秒数"""
    h, m, rest = ts.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_srt_to_text(path: str) -> str:
    """解析SRT文件为带时间戳的文本"""
    raw = read_text(path)
    out = []
    blocks = re.split(r"\n\s*\n", raw.strip())

    for b in blocks:
        lines = [ln.strip() for ln in b.splitlines() if ln.strip()]
        if len(lines) < 2:
            continue

        timing = next((ln for ln in lines if "-->" in ln), None)
        if not timing:
            continue

        m = re.match(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})", timing)
        if not m:
            continue

        start = parse_ts(m.group(1))
        end = parse_ts(m.group(2))

        started, text_lines = False, []
        for ln in lines:
            if started:
                text_lines.append(ln)
            if ln == timing:
                started = True

        text = " ".join(text_lines).strip()
        if text:
            out.append(f"[{start:.2f}-{end:.2f}] {text}")

    return "\n".join(out)


# ========== 主逻辑 ==========
def main(args=None):
    p = argparse.ArgumentParser(description="最小可用的 LLM 调用脚本（原样输出）")
    p.add_argument("--video", required=True, help="TikTok视频URL")
    p.add_argument("--outdir", required=True, help="输出目录")
    p.add_argument("--subs", required=True, help=".srt 或 .txt（字幕文件）")
    p.add_argument("--comments", required=True, help="评论 txt（可用通配符，取最新匹配文件）")
    p.add_argument("--frames", required=True, help="截图目录，内含 jpg/png")
    p.add_argument("--custom-prompt-file", help="提示词文件；和 --custom-prompt-text 二选一")
    p.add_argument("--custom-prompt-text", help="提示词文本；优先于文件")
    p.add_argument("--max-images", type=int, default=12, help="最大图片数量")
    p.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-4o"), help="模型名称")
    p.add_argument("--proxy", help="HTTP 代理，如 http://127.0.0.1:7897")
    p.add_argument("--api-key", help="OpenAI API Key；不传则读环境变量 OPENAI_API_KEY")

    if args is None:
        args = p.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    # OpenAI 客户端配置
    api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 OPENAI_API_KEY（可用 --api-key 覆盖）")

    http_client = httpx.Client(
        transport=httpx.HTTPTransport(
            proxy=args.proxy or os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY"),
            http2=False
        ),
        timeout=600,
        trust_env=False,
    )
    client = OpenAI(api_key=api_key, http_client=http_client)

    # 处理字幕
    subs_path = args.subs
    if subs_path.lower().endswith(".srt"):
        subs_text = parse_srt_to_text(subs_path)
    else:
        subs_text = read_text(subs_path)

    # 处理评论：允许通配符，取最新一个文件
    comment_path = args.comments
    cand = glob.glob(comment_path)
    if cand:
        comment_path = max(cand, key=os.path.getctime)
    comments_text = read_text(comment_path)

    # 处理截图
    img_paths = sorted(
        glob.glob(os.path.join(args.frames, "*.jpg")) +
        glob.glob(os.path.join(args.frames, "*.png"))
    )
    if args.max_images and args.max_images > 0:
        img_paths = img_paths[:args.max_images]
    image_urls = [to_data_url(p) for p in img_paths]

    # 提取视频ID
    m = re.search(r'/video/(\d+)', args.video)
    video_id = m.group(1) if m else "unknown"

    # 处理提示词
    if args.custom_prompt_text:
        prompt_tpl = args.custom_prompt_text
    elif args.custom_prompt_file:
        prompt_tpl = read_text(args.custom_prompt_file)
    else:
        # 兜底：极简提示（不限定输出格式）
        prompt_tpl = """基于以下字幕与评论，结合图片内容，输出你的完整分析结论。

—— 字幕：
{subs_text}

—— 评论：
{comments_text}

—— 视频ID：{video_id}"""

    # 格式化提示词
    try:
        final_prompt = prompt_tpl.format(
            subs_text=subs_text,
            comments_text=comments_text,
            video_id=video_id
        )
    except Exception as e:
        print(f"⚠️ 提示词格式化失败，使用原始提示词: {e}")
        final_prompt = prompt_tpl

    # 构建multimodal内容
    content = [{"type": "text", "text": final_prompt}]
    for u in image_urls:
        content.append({"type": "image_url", "image_url": {"url": u}})

    print(f"�� 准备调用模型 {args.model}")
    print(f"📊 字幕长度: {len(subs_text)} 字符")
    print(f"💬 评论长度: {len(comments_text)} 字符")
    print(f"🖼️ 图片数量: {len(image_urls)} 张")

    # 调用API
    try:
        resp = client.chat.completions.create(
            model=args.model,
            messages=[
                {"role": "system", "content": "你是严谨的分析师，直接输出你的结果，不要多余寒暄。"},
                {"role": "user", "content": content},
            ],
        )

        # 1) 拿到模型输出
        out_text = resp.choices[0].message.content or ""

        # 2) 清洗成纯文本 CSV（去代码块围栏 + 保护长数字 + 统一换行）
        def strip_code_fences(s: str) -> str:
            s = s.strip()
            if s.startswith("```"):
                nl = s.find("\n")
                if nl != -1:
                    s = s[nl + 1:]
            if s.endswith("```"):
                s = s[:-3]
            return s.strip()

        text = strip_code_fences(out_text)
        text = re.sub(r'(^|\n)(\d{10,})(?=,|\n|$)', r'\1="\2"', text)  # 保护长数字ID
        text = text.replace("\r\n", "\n").replace("\r", "\n")  # 规一为 LF

        # 3) 两行 CSV → 制表符 TSV（仅前两行）
        import csv
        def csv_to_tsv_two_lines(csv_text: str) -> str:
            lines = csv_text.split("\n")
            reader = csv.reader(lines[:2])
            rows = list(reader)
            tsv_lines = ["\t".join(row) for row in rows]
            return "\r\n".join(tsv_lines)  # 写回 CRLF

        tsv_text = csv_to_tsv_two_lines(text)

        # 4) 同时落盘 TSV 与 CSV（CSV 为 UTF‑16LE + BOM + sep=\t，Excel 直接双击）
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        tsv_path = os.path.join(args.outdir, f"llm_output_{ts}.tsv")
        with open(tsv_path, "w", encoding="utf-16", newline="") as f:
            f.write(tsv_text if tsv_text.endswith("\r\n") else tsv_text + "\r\n")

        csv_path = os.path.join(args.outdir, f"llm_output_{ts}.csv")
        with open(csv_path, "w", encoding="utf-16", newline="") as f:  # 'utf-16' 即带 BOM 的 LE
            f.write("sep=\t\r\n")
            f.write(tsv_text if tsv_text.endswith("\r\n") else tsv_text + "\r\n")

        print(f"✅ 模型调用完成，已保存 TSV：{tsv_path}")
        print(f"✅ 模型调用完成，已保存 CSV（UTF-16LE, sep=\\t）：{csv_path}")
        print(f"📄 输出长度: {len(out_text)} 字符")
        return True
    except Exception as e:
        print(f"❌ API调用失败: {e}")
        return False


if __name__ == "__main__":
    main()