#!/usr/bin/env python3
"""
创建管理员账号的初始化脚本
"""
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from fastapi_app.database import SessionLocal, init_db
from fastapi_app.models.user import User
from fastapi_app.auth.password import hash_password


def create_admin_user(
    username: str = "admin",
    email: str = "admin@example.com",
    password: str = "admin123",
    full_name: str = "系统管理员",
):
    """创建管理员用户"""
    # 初始化数据库
    init_db()

    db = SessionLocal()
    try:
        # 检查用户是否已存在
        existing_user = db.query(User).filter(User.username == username).first()
        if existing_user:
            print(f"❌ 用户 '{username}' 已存在！")
            return

        # 创建管理员用户
        admin_user = User(
            username=username,
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            is_active=True,
            is_superuser=True,  # 管理员权限
        )

        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)

        print("=" * 60)
        print("✅ 管理员账号创建成功！")
        print("=" * 60)
        print(f"用户名: {username}")
        print(f"邮箱: {email}")
        print(f"密码: {password}")
        print(f"姓名: {full_name}")
        print(f"管理员: {'是' if admin_user.is_superuser else '否'}")
        print("=" * 60)
        print("⚠️  请妥善保管账号密码，建议登录后立即修改密码！")
        print("=" * 60)

    except Exception as e:
        print(f"❌ 创建管理员失败: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="创建管理员账号")
    parser.add_argument("--username", default="admin", help="用户名 (默认: admin)")
    parser.add_argument("--email", default="admin@example.com", help="邮箱")
    parser.add_argument("--password", default="admin123", help="密码 (默认: admin123)")
    parser.add_argument("--fullname", default="系统管理员", help="全名")
    args = parser.parse_args()

    create_admin_user(
        username=args.username,
        email=args.email,
        password=args.password,
        full_name=args.fullname,
    )
