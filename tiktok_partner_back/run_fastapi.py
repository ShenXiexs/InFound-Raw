#!/usr/bin/env python3
"""
FastAPI 应用启动脚本
"""
import uvicorn
import argparse
from pathlib import Path
import sys

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="启动 TikTok Partner FastAPI 服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="端口号 (默认: 8000)")
    parser.add_argument("--reload", action="store_true", help="启用热重载（开发模式）")
    parser.add_argument("--workers", type=int, default=1, help="工作进程数（生产模式）")
    args = parser.parse_args()

    print("=" * 60)
    print("🚀 TikTok Partner Management System - FastAPI")
    print("=" * 60)
    print(f"📡 服务器地址: http://{args.host}:{args.port}")
    print(f"📚 API 文档 (Swagger): http://{args.host}:{args.port}/docs")
    print(f"📋 API 文档 (ReDoc): http://{args.host}:{args.port}/redoc")
    print("=" * 60)
    print("按 Ctrl+C 停止服务\n")

    uvicorn.run(
        "fastapi_app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers if not args.reload else 1,
        log_level="info",
    )
