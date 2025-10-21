#!/usr/bin/env python3
import sys
import os
import json
from pathlib import Path
from crawler.parallel_manager import ParallelTaskManager

def main():
    if len(sys.argv) < 2:
        print("用法: python add_task.py <任务文件夹>")
        return
    
    folder_path = Path(sys.argv[1])
    config_file = folder_path / "dify_out.txt"
    
    if not config_file.exists():
        print(f"配置文件不存在: {config_file}")
        return
    
    with open(config_file, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    config['name'] = folder_path.name
    manager = ParallelTaskManager()
    manager.add_task(config, str(config_file))
    print(f"任务已添加: {folder_path.name}")

if __name__ == "__main__":
    main()
