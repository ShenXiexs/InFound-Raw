"""
认证服务
"""
import json
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime
from core.config import settings
from core.security import verify_password, get_password_hash, create_access_token

class AuthService:
    """认证服务"""
    
    def __init__(self):
        self.users_file = Path(settings.USERS_CONFIG_PATH)
        self._ensure_users_file()
    
    def _ensure_users_file(self):
        """确保用户配置文件存在"""
        if not self.users_file.exists():
            # 创建默认管理员账号
            default_users = {
                "users": [
                    {
                        "username": "admin",
                        "hashed_password": get_password_hash("admin123"),
                        "email": "admin@example.com",
                        "role": "admin",
                        "enabled": True,
                        "created_at": datetime.now().isoformat()
                    }
                ]
            }
            self.users_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.users_file, 'w', encoding='utf-8') as f:
                json.dump(default_users, f, indent=2, ensure_ascii=False)
    
    def _load_users(self) -> dict:
        """加载用户配置"""
        with open(self.users_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _save_users(self, data: dict):
        """保存用户配置"""
        with open(self.users_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def get_user(self, username: str) -> Optional[dict]:
        """获取用户信息"""
        data = self._load_users()
        for user in data.get("users", []):
            if user["username"] == username:
                return user
        return None
    
    def authenticate_user(self, username: str, password: str) -> Optional[dict]:
        """验证用户"""
        user = self.get_user(username)
        if not user:
            return None
        if not verify_password(password, user["hashed_password"]):
            return None
        return user
    
    def create_token(self, username: str) -> str:
        """创建访问令牌"""
        return create_access_token(data={"sub": username})
    
    def create_user(self, username: str, password: str, role: str = "user", 
                    email: Optional[str] = None) -> Tuple[bool, str]:
        """创建新用户"""
        # 检查用户是否已存在
        if self.get_user(username):
            return False, "用户名已存在"
        
        data = self._load_users()
        new_user = {
            "username": username,
            "hashed_password": get_password_hash(password),
            "email": email,
            "role": role,
            "enabled": True,
            "created_at": datetime.now().isoformat()
        }
        
        data["users"].append(new_user)
        self._save_users(data)
        
        return True, "用户创建成功"
