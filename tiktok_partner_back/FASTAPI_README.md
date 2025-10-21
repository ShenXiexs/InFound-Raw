# TikTok Partner Management System - FastAPI 版本

## 📋 项目简介

这是一个基于 **FastAPI** 的 TikTok Shop 创作者爬虫管理系统，包含完整的用户登录认证功能。

### 主要功能

- 🔐 **用户认证系统**: JWT Token 认证，支持注册、登录、登出
- 📊 **任务管理**: 提交、查询、取消爬虫任务
- 👥 **账号池管理**: 管理多个 TikTok Shop 账号
- 🌍 **多区域支持**: 支持 FR、MX 等多个区域
- 📈 **并行处理**: 多进程并行执行爬虫任务
- 📚 **自动文档**: Swagger UI 和 ReDoc 自动生成 API 文档

## 🚀 快速开始

### 1. 安装依赖

```bash
cd tiktok_partner_back
pip install -r requirements.txt
```

### 2. 安装 Playwright 浏览器

```bash
playwright install
```

### 3. 启动服务

#### 开发模式（支持热重载）

```bash
python run_fastapi.py --reload
```

#### 生产模式

```bash
python run_fastapi.py --workers 4
```

### 4. 访问 API 文档

启动后访问：

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **健康检查**: http://localhost:8000/api/health

## 📖 API 使用指南

### 认证流程

#### 1. 注册账号

```bash
curl -X POST "http://localhost:8000/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "email": "admin@example.com",
    "password": "password123",
    "full_name": "系统管理员"
  }'
```

#### 2. 登录获取 Token

```bash
curl -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "password123"
  }'
```

返回示例：

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "admin",
    "email": "admin@example.com",
    "full_name": "系统管理员",
    "is_superuser": false
  }
}
```

#### 3. 使用 Token 访问受保护的 API

在请求头中添加 `Authorization: Bearer <access_token>`

```bash
curl -X GET "http://localhost:8000/api/accounts/status" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### 任务管理

#### 提交任务

```bash
curl -X POST "http://localhost:8000/api/tasks/submit" \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "region": "FR",
    "brand": {
      "name": "REDHUT",
      "only_first": "0",
      "key_word": "..."
    },
    "search_strategy": { ... },
    "email_first": { ... },
    "email_later": { ... }
  }'
```

#### 查询任务状态

```bash
curl -X GET "http://localhost:8000/api/tasks/status/{task_id}" \
  -H "Authorization: Bearer <your_token>"
```

#### 列出所有任务

```bash
curl -X GET "http://localhost:8000/api/tasks/list?limit=100" \
  -H "Authorization: Bearer <your_token>"
```

#### 取消任务

```bash
curl -X POST "http://localhost:8000/api/tasks/cancel/{task_id}" \
  -H "Authorization: Bearer <your_token>"
```

### 账号管理

#### 查看账号池状态

```bash
curl -X GET "http://localhost:8000/api/accounts/status" \
  -H "Authorization: Bearer <your_token>"
```

## 🔧 配置说明

### 环境变量（可选）

创建 `.env` 文件（参考 `.env.example`）：

```env
# 应用配置
APP_NAME=TikTok Partner Management System
DEBUG=true

# JWT 配置（生产环境务必修改！）
SECRET_KEY=your-secret-key-change-this-in-production-2024
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# 数据库配置
DATABASE_URL=sqlite:///./data/record/system.db
CRAWLER_DB_PATH=data/record/central_record.db

# 服务器配置
HOST=0.0.0.0
PORT=8000

# CORS 配置（添加你的前端域名）
CORS_ORIGINS=["http://localhost:3000", "http://localhost:5173"]
```

### 数据库

系统使用两个 SQLite 数据库：

1. **system.db**: 用户认证数据库（FastAPI 新增）
2. **central_record.db**: 任务记录数据库（原有系统）

数据库文件位置：`data/record/`

## 📁 项目结构

```
tiktok_partner_back/
├── fastapi_app/              # FastAPI 应用
│   ├── main.py              # 主入口
│   ├── config.py            # 配置
│   ├── database.py          # 数据库连接
│   ├── models/              # 数据模型
│   │   └── user.py          # 用户模型
│   ├── schemas/             # Pydantic schemas
│   │   ├── user.py
│   │   ├── auth.py
│   │   └── task.py
│   ├── routers/             # API 路由
│   │   ├── auth.py          # 认证路由
│   │   ├── tasks.py         # 任务路由
│   │   └── accounts.py      # 账号路由
│   ├── auth/                # 认证模块
│   │   ├── jwt_handler.py   # JWT 处理
│   │   ├── password.py      # 密码加密
│   │   └── dependencies.py  # 依赖注入
│   └── utils/               # 工具函数
│       └── responses.py     # 统一响应
├── crawler/                  # 爬虫模块（原有）
├── models/                   # 业务模型（原有）
├── run_fastapi.py           # FastAPI 启动脚本
├── api_server.py            # Flask 版本（旧）
└── requirements.txt         # 依赖列表
```

## 🔒 安全说明

### 生产环境部署前必须修改：

1. **SECRET_KEY**: 在 `fastapi_app/config.py` 或 `.env` 中修改 JWT 密钥
2. **CORS_ORIGINS**: 配置允许的前端域名
3. **数据库**: 考虑使用 PostgreSQL 或 MySQL 替代 SQLite
4. **HTTPS**: 使用 Nginx 反向代理，启用 SSL/TLS

### JWT Token 安全

- Token 默认有效期：7 天
- Token 存储在前端（localStorage 或 sessionStorage）
- 登出时前端删除 Token 即可

## 🧪 测试

### 使用 Swagger UI 测试

1. 访问 http://localhost:8000/docs
2. 点击 `/api/auth/register` 注册账号
3. 点击 `/api/auth/login` 登录获取 token
4. 点击右上角 🔒 **Authorize** 按钮
5. 输入 token（不需要加 "Bearer " 前缀）
6. 测试其他受保护的 API

### 使用 Python 测试

```python
import requests

# 1. 登录
response = requests.post("http://localhost:8000/api/auth/login", json={
    "username": "admin",
    "password": "password123"
})
token = response.json()["access_token"]

# 2. 访问受保护的 API
headers = {"Authorization": f"Bearer {token}"}
response = requests.get("http://localhost:8000/api/accounts/status", headers=headers)
print(response.json())
```

## 🆚 与 Flask 版本的区别

| 特性 | Flask 版本 | FastAPI 版本 |
|------|-----------|-------------|
| 认证系统 | ❌ 无 | ✅ JWT 认证 |
| 用户管理 | ❌ 无 | ✅ 完整的用户系统 |
| API 文档 | ❌ 手动编写 | ✅ 自动生成 (Swagger/ReDoc) |
| 类型验证 | ❌ 手动验证 | ✅ Pydantic 自动验证 |
| 性能 | 较慢 (WSGI) | 更快 (ASGI) |
| 异步支持 | ❌ 有限 | ✅ 原生支持 |

## 📝 常见问题

### Q: 如何创建管理员账号？

A: 首次注册的用户可以手动修改数据库将 `is_superuser` 设置为 `true`，或者在代码中添加创建管理员的逻辑。

### Q: Token 过期怎么办？

A: Token 过期后需要重新登录获取新的 token。可以通过修改 `ACCESS_TOKEN_EXPIRE_MINUTES` 调整过期时间。

### Q: 如何重置密码？

A: 当前版本未实现重置密码功能，可以手动修改数据库中的 `hashed_password` 字段。

### Q: 可以同时运行 Flask 和 FastAPI 吗？

A: 可以，但需要使用不同的端口。Flask 默认 8000，FastAPI 可以改为 8001。

## 📞 技术支持

如有问题，请参考：

- API 文档: http://localhost:8000/docs
- 日志文件: `logs/fastapi/*.log`
- 数据库文件: `data/record/*.db`

## 📄 许可证

内部项目使用
