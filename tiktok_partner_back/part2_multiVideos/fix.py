#!/usr/bin/env python3
"""自动修复所有 Windows 路径为 macOS 路径"""

import re
from pathlib import Path

# 定义修复规则
fixes = {
    'extract_multi_subtitles_from_web.py': [
        # 第 34 行：模型路径
        (
            r'MODEL_PATH = r"C:\\TK\\part2\\models\\.*?"',
            'MODEL_PATH = "/Users/samxie/Research/Infound_Influencer/tiktok_partner_back/models/faster-whisper-small"'
        ),
        # 第 40 行：ffmpeg 路径
        (
            r'FFMPEG = os\.environ\.get\("FFMPEG", r"C:\\TK\\part2\\ffmpeg.*?"\)',
            'FFMPEG = os.environ.get("FFMPEG", "ffmpeg")'
        ),
        # 第 298 行：download_root
        (
            r'download_root=r"D:\\models"',
            'download_root="/Users/samxie/Research/Infound_Influencer/tiktok_partner_back/models"'
        ),
    ],
    'take_multi_screenshots_from_web.py': [
        # 第 10-11 行：ffmpeg 路径
        (
            r'FFMPEG\s*=.*?r"C:\\TK\\part2\\ffmpeg.*?"',
            'FFMPEG = os.environ.get("FFMPEG", "ffmpeg")'
        ),
        (
            r'FFPROBE\s*=.*?r"C:\\TK\\part2\\ffmpeg.*?"',
            'FFPROBE = os.environ.get("FFPROBE", "ffprobe")'
        ),
    ],
    'workflow1_multi.py': [
        # 所有 Windows 路径替换
        (
            r'r"C:\\Users\\yang_zih\\Downloads\\part2\\urls\.txt"',
            'r"/Users/samxie/Research/Infound_Influencer/tiktok_partner_back/part2_multiVideos/urls.txt"'
        ),
        (
            r'r"C:/TK/part2/workflow_output_multi"',
            'r"/Users/samxie/Research/Infound_Influencer/tiktok_partner_back/data/video_part"'
        ),
        (
            r'r"C:/TK/part2/scratch_from_website/prompt_10fields_tsv\.txt"',
            'r"/Users/samxie/Research/Infound_Influencer/tiktok_partner_back/part2_multiVideos/prompt_10fields_tsv.txt"'
        ),
        (
            r'r"C:/TK/part2/scratch_from_website/summary_prompt\.txt"',
            'r"/Users/samxie/Research/Infound_Influencer/tiktok_partner_back/part2_multiVideos/summary_prompt.txt"'
        ),
        (
            r'r"C:\\Users\\yang_zih\\AppData\\Local\\Google\\Chrome"',
            'None  # macOS Chrome 路径需手动指定或留空'
        ),
    ],
}

def fix_file(filepath, replacements):
    """修复单个文件"""
    path = Path(filepath)
    if not path.exists():
        print(f"⚠️  文件不存在: {filepath}")
        return False
    
    # 读取原文件
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 备份
    backup = path.with_suffix(path.suffix + '.win_backup')
    with open(backup, 'w', encoding='utf-8') as f:
        f.write(content)
    
    # 执行替换
    modified = False
    for pattern, replacement in replacements:
        new_content = re.sub(pattern, replacement, content)
        if new_content != content:
            content = new_content
            modified = True
            print(f"  ✓ 修复: {pattern[:50]}...")
    
    if modified:
        # 保存修改
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ {filepath} 已修复（备份: {backup.name}）")
        return True
    else:
        print(f"ℹ️  {filepath} 无需修改")
        backup.unlink()  # 删除不必要的备份
        return False

# 执行修复
print("🔧 开始修复 Windows 路径...\n")
total_fixed = 0

for filename, replacements in fixes.items():
    print(f"📄 处理 {filename}:")
    if fix_file(filename, replacements):
        total_fixed += 1
    print()

print(f"\n🎉 完成！共修复 {total_fixed} 个文件")
print("\n💡 提示：如果需要回滚，删除 .py 文件并将 .py.win_backup 重命名即可")