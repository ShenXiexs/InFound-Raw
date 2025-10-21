"""
API服务 - 接收前端请求并调度爬虫任务
支持单任务调用和任务队列管理
"""
import multiprocessing as mp
mp.set_start_method('fork', force=True)

from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import logging
from pathlib import Path
from datetime import datetime
import threading
import uuid
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入现有的任务管理器和账号池
from crawler.parallel_manager import ParallelTaskManager
from models.account_pool import get_account_pool

def get_or_create_manager():
    """获取或创建全局任务管理器"""
    global task_manager
    
    with task_manager_lock:
        if task_manager is None:
            logger.info("初始化任务管理器...")
            task_manager = ParallelTaskManager(
                max_workers=3,  # 可根据需要调整
                db_path='data/record/central_record.db',
                account_pool_config='config/accounts.json'
            )
            
            # 启动工作进程
            logger.info("正在启动 Worker 进程...")
            for i in range(min(3, 1)):  # 先启动1个worker测试
                worker_id = f"worker_{i}"
                task_manager.start_worker(worker_id)
                logger.info(f"✓ Worker 进程 {worker_id} 已启动")
            
            # 启动管理器监控线程（守护模式）
            logger.info("启动任务管理器监控线程...")
            threading.Thread(
                target=task_manager.run,
                kwargs={'daemon': True},
                daemon=True,
                name='TaskManagerThread'
            ).start()
            logger.info("✓ 任务管理器已启动（守护模式）")
        
        return task_manager

app = Flask(__name__)
CORS(app)  # 允许跨域

# 全局任务管理器（单例模式）
task_manager = None
task_manager_lock = threading.Lock()

# 配置日志到 logs/api/ 目录
log_dir = Path("logs/api")
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='[API] %(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / f"{datetime.now():%Y%m%d}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def get_or_create_manager():
    """获取或创建全局任务管理器"""
    global task_manager
    
    with task_manager_lock:
        if task_manager is None:
            logger.info("=" * 60)
            logger.info("初始化任务管理器...")
            
            task_manager = ParallelTaskManager(
                max_workers=3,
                db_path='data/record/central_record.db',
                account_pool_config='config/accounts.json'
            )
            
            # 启动 Worker 进程
            logger.info("正在启动 Worker 进程...")
            for i in range(1):  # 至少启动 1 个 Worker
                worker_id = f"worker_{i}"
                task_manager.start_worker(worker_id)
                logger.info(f"✓ Worker 进程 {worker_id} 已启动")
            
            # 启动管理器监控线程
            logger.info("启动任务管理器监控线程...")
            
            def run_manager():
                try:
                    task_manager.run(daemon=True)
                except Exception as e:
                    logger.error(f"任务管理器异常: {e}", exc_info=True)
            
            threading.Thread(
                target=run_manager,
                daemon=True,
                name='TaskManagerThread'
            ).start()
            
            logger.info("✓ 任务管理器已启动（守护模式）")
            logger.info("=" * 60)
        
        return task_manager  # ← 这里必须返回！


def validate_task_config(data):
    """验证前端传来的配置是否完整"""
    required_fields = ['region', 'brand', 'search_strategy', 'email_first', 'email_later']
    
    for field in required_fields:
        if field not in data:
            return False, f"缺少必需字段: {field}"
    
    if 'name' not in data['brand']:
        return False, "brand.name 不能为空"
    
    if not isinstance(data['search_strategy'], dict):
        return False, "search_strategy 必须是对象"
    
    return True, None


@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/accounts/status', methods=['GET'])
def get_accounts_status():
    """获取账号池状态"""
    try:
        pool = get_account_pool()
        status = pool.get_status()
        
        return jsonify({
            'success': True,
            'data': {
                'total': status['total'],
                'available': status['available'],
                'in_use': status['in_use'],
                'accounts': [
                    {
                        'id': acc['id'],
                        'name': acc['name'],
                        'email': acc['email'],
                        'region': acc['region'],
                        'status': acc['status'],
                        'usage_count': acc.get('usage_count', 0),
                        'using_tasks': acc.get('using_tasks', [])
                    }
                    for acc in status['accounts']
                ]
            }
        })
    except Exception as e:
        logger.error(f"获取账号状态失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/task/submit', methods=['POST'])
def submit_task():
    """接收前端任务并提交到队列"""
    try:
        data = request.get_json()
        
        # 验证配置
        is_valid, error_msg = validate_task_config(data)
        if not is_valid:
            logger.warning(f"配置验证失败: {error_msg}")
            return jsonify({'success': False, 'error': error_msg}), 400
        
        # 检查账号池
        pool = get_account_pool()
        region = data.get('region', '').upper()
        
        status = pool.get_status()
        has_region_account = any(
            acc['region'].upper() == region
            for acc in status['accounts']
            if acc.get('enabled', True)
        )
        
        if not has_region_account:
            logger.error(f"没有可用的 {region} 区域账号")
            return jsonify({'success': False, 'error': f'没有可用的 {region} 区域账号'}), 400
        
        # 生成任务ID
        brand_name = data['brand']['name']
        task_id = f"{brand_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        
        # 创建任务目录
        task_dir = Path(f"data/tasks/{brand_name}/{task_id}")
        task_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存配置文件
        config_file = task_dir / "dify_out.txt"
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # 准备任务配置
        task_config = {
            'name': task_id,
            'source_dir': str(task_dir),
            'config_files': [{
                'file': str(config_file),
                'name': task_id,
                'data': data
            }],
            'config_count': 1,
            '_product_group': brand_name
        }
        
        # 提交任务到管理器
        manager = get_or_create_manager()
        submitted_task_id = manager.add_task(task_config, str(config_file))
        
        logger.info(f"✓ 任务已提交: {submitted_task_id} (品牌: {brand_name}, 区域: {region})")
        
        return jsonify({
            'success': True,
            'data': {
                'task_id': submitted_task_id,
                'brand_name': brand_name,
                'region': region,
                'status': 'pending',
                'message': '任务已提交到队列'
            }
        }), 201
        
    except Exception as e:
        logger.error(f"提交任务失败: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/task/status/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """查询任务状态"""
    try:
        import sqlite3
        
        db_path = 'data/record/central_record.db'
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT task_id, task_name, status, start_time, end_time, total_creators
                FROM tasks WHERE task_id = ?
            """, (task_id,))
            
            row = cursor.fetchone()
            
            if not row:
                return jsonify({'success': False, 'error': '任务不存在'}), 404
            
            return jsonify({
                'success': True,
                'data': {
                    'task_id': row[0],
                    'task_name': row[1],
                    'status': row[2],
                    'start_time': row[3],
                    'end_time': row[4],
                    'total_creators': row[5]
                }
            })
    except Exception as e:
        logger.error(f"查询任务状态失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tasks/list', methods=['GET'])
def list_tasks():
    """列出所有任务"""
    try:
        import sqlite3
        
        status_filter = request.args.get('status')
        limit = int(request.args.get('limit', 100))
        
        db_path = 'data/record/central_record.db'
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            if status_filter:
                cursor.execute("""
                    SELECT task_id, task_name, status, start_time, end_time, total_creators
                    FROM tasks WHERE status = ? ORDER BY start_time DESC LIMIT ?
                """, (status_filter, limit))
            else:
                cursor.execute("""
                    SELECT task_id, task_name, status, start_time, end_time, total_creators
                    FROM tasks ORDER BY start_time DESC LIMIT ?
                """, (limit,))
            
            rows = cursor.fetchall()
            
            tasks = [
                {
                    'task_id': row[0],
                    'task_name': row[1],
                    'status': row[2],
                    'start_time': row[3],
                    'end_time': row[4],
                    'total_creators': row[5]
                }
                for row in rows
            ]
            
            return jsonify({'success': True, 'data': {'tasks': tasks, 'total': len(tasks)}})
    except Exception as e:
        logger.error(f"列出任务失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/task/cancel/<task_id>', methods=['POST'])
def cancel_task(task_id):
    """取消任务"""
    try:
        import sqlite3
        
        db_path = 'data/record/central_record.db'
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tasks SET status = 'cancelled'
                WHERE task_id = ? AND status IN ('pending', 'running')
            """, (task_id,))
            conn.commit()
            
            if cursor.rowcount == 0:
                return jsonify({'success': False, 'error': '任务不存在或已完成'}), 404
            
            return jsonify({'success': True, 'message': '任务已标记为取消'})
    except Exception as e:
        logger.error(f"取消任务失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000, help='端口号 (默认: 8000)')
    parser.add_argument('--host', default='0.0.0.0', help='监听地址')
    args = parser.parse_args()
    
    # 显示启动信息
    print("=" * 60)
    print("🚀 TikTok Partner API 服务")
    print("=" * 60)
    print(f"📡 监听地址: http://{args.host}:{args.port}")
    print(f"📋 日志位置: logs/api/{datetime.now():%Y%m%d}.log")
    print(f"📊 健康检查: http://localhost:{args.port}/api/health")
    print("=" * 60)
    print("按 Ctrl+C 停止服务\n")
    
    app.run(host=args.host, port=args.port, debug=True)


def validate_task_config(data):
    """验证前端传来的配置是否完整"""
    required_fields = ['region', 'brand', 'search_strategy', 'email_first', 'email_later']
    
    for field in required_fields:
        if field not in data:
            return False, f"缺少必需字段: {field}"
    
    # 验证 brand 字段
    if 'name' not in data['brand']:
        return False, "brand.name 不能为空"
    
    # 验证 search_strategy 字段
    if not isinstance(data['search_strategy'], dict):
        return False, "search_strategy 必须是对象"
    
    return True, None


@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/accounts/status', methods=['GET'])
def get_accounts_status():
    """获取账号池状态"""
    try:
        pool = get_account_pool()
        status = pool.get_status()
        
        return jsonify({
            'success': True,
            'data': {
                'total': status['total'],
                'available': status['available'],
                'in_use': status['in_use'],
                'accounts': [
                    {
                        'id': acc['id'],
                        'name': acc['name'],
                        'email': acc['email'],
                        'region': acc['region'],
                        'status': acc['status'],
                        'usage_count': acc.get('usage_count', 0),
                        'using_tasks': acc.get('using_tasks', [])
                    }
                    for acc in status['accounts']
                ]
            }
        })
    except Exception as e:
        logger.error(f"获取账号状态失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/task/submit', methods=['POST'])
def submit_task():
    """
    接收前端任务并提交到队列
    
    请求体示例：
    {
        "region": "FR",
        "brand": {
            "name": "REDHUT",
            "only_first": "0",
            "key_word": "..."
        },
        "search_strategy": { ... },
        "email_first": { ... },
        "email_later": { ... }
    }
    """
    try:
        data = request.get_json()
        
        # 验证配置
        is_valid, error_msg = validate_task_config(data)
        if not is_valid:
            return jsonify({
                'success': False,
                'error': error_msg
            }), 400
        
        # 检查账号池
        pool = get_account_pool()
        region = data.get('region', '').upper()
        
        # 检查是否有对应区域的账号
        status = pool.get_status()
        has_region_account = any(
            acc['region'].upper() == region and acc['status'] == 'available'
            for acc in status['accounts']
        )
        
        if not has_region_account:
            return jsonify({
                'success': False,
                'error': f'没有可用的 {region} 区域账号'
            }), 400
        
        # 生成任务ID
        brand_name = data['brand']['name']
        task_id = f"{brand_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        
        # 创建任务目录
        task_dir = Path(f"data/tasks/{brand_name}/{task_id}")
        task_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存配置文件
        config_file = task_dir / "dify_out.txt"
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # 准备任务配置（适配现有系统）
        task_config = {
            'name': task_id,
            'source_dir': str(task_dir),
            'config_files': [
                {
                    'file': str(config_file),
                    'name': task_id,
                    'data': data
                }
            ],
            'config_count': 1,
            '_product_group': brand_name  # 用于产品锁
        }
        
        # 提交任务到管理器
        manager = get_or_create_manager()
        submitted_task_id = manager.add_task(task_config, str(config_file))
        
        logger.info(f"任务已提交: {submitted_task_id}")
        
        return jsonify({
            'success': True,
            'data': {
                'task_id': submitted_task_id,
                'brand_name': brand_name,
                'region': region,
                'status': 'pending',
                'message': '任务已提交到队列'
            }
        }), 201
        
    except Exception as e:
        logger.error(f"提交任务失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/task/status/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """查询任务状态"""
    try:
        import sqlite3
        
        db_path = 'data/record/central_record.db'
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT task_id, task_name, status, start_time, end_time, total_creators
                FROM tasks
                WHERE task_id = ?
            """, (task_id,))
            
            row = cursor.fetchone()
            
            if not row:
                return jsonify({
                    'success': False,
                    'error': '任务不存在'
                }), 404
            
            return jsonify({
                'success': True,
                'data': {
                    'task_id': row[0],
                    'task_name': row[1],
                    'status': row[2],
                    'start_time': row[3],
                    'end_time': row[4],
                    'total_creators': row[5]
                }
            })
    except Exception as e:
        logger.error(f"查询任务状态失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/tasks/list', methods=['GET'])
def list_tasks():
    """列出所有任务"""
    try:
        import sqlite3
        
        # 获取查询参数
        status_filter = request.args.get('status')  # pending/running/completed/failed
        limit = int(request.args.get('limit', 100))
        
        db_path = 'data/record/central_record.db'
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            if status_filter:
                cursor.execute("""
                    SELECT task_id, task_name, status, start_time, end_time, total_creators
                    FROM tasks
                    WHERE status = ?
                    ORDER BY start_time DESC
                    LIMIT ?
                """, (status_filter, limit))
            else:
                cursor.execute("""
                    SELECT task_id, task_name, status, start_time, end_time, total_creators
                    FROM tasks
                    ORDER BY start_time DESC
                    LIMIT ?
                """, (limit,))
            
            rows = cursor.fetchall()
            
            tasks = [
                {
                    'task_id': row[0],
                    'task_name': row[1],
                    'status': row[2],
                    'start_time': row[3],
                    'end_time': row[4],
                    'total_creators': row[5]
                }
                for row in rows
            ]
            
            return jsonify({
                'success': True,
                'data': {
                    'tasks': tasks,
                    'total': len(tasks)
                }
            })
    except Exception as e:
        logger.error(f"列出任务失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/task/cancel/<task_id>', methods=['POST'])
def cancel_task(task_id):
    """取消任务（标记为取消，但不强制停止）"""
    try:
        import sqlite3
        
        db_path = 'data/record/central_record.db'
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tasks
                SET status = 'cancelled'
                WHERE task_id = ? AND status IN ('pending', 'running')
            """, (task_id,))
            conn.commit()
            
            if cursor.rowcount == 0:
                return jsonify({
                    'success': False,
                    'error': '任务不存在或已完成'
                }), 404
            
            return jsonify({
                'success': True,
                'message': '任务已标记为取消'
            })
    except Exception as e:
        logger.error(f"取消任务失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000, help='端口号 (默认: 8000)')
    parser.add_argument('--host', default='0.0.0.0', help='监听地址')
    args = parser.parse_args()
    
    # 开发模式
    logging.info(f"启动 API 服务: http://{args.host}:{args.port}")
    app.run(
        host=args.host,
        port=args.port,
        debug=True
    )
    
    # 生产模式建议使用 gunicorn:
    # gunicorn -w 4 -b 0.0.0.0:8000 api_server:app