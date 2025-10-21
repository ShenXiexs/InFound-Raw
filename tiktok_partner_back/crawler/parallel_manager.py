"""
并行任务管理器
管理多个爬虫进程的创建、监控和资源分配
"""
import multiprocessing as mp
from multiprocessing import Process, Queue, Manager, Lock
import sqlite3
import time
import os
import sys
import logging
from typing import Dict, List, Optional
from datetime import datetime
import json
from pathlib import Path
from queue import Empty

def worker_entry(worker_id, task_queue, result_queue, db_path, db_lock, 
                status_dict, shared_records, account_pool_config=None):
    """Worker 进程入口点 - 清理 asyncio 环境"""
    
    # 步骤1: 清理 asyncio 环境
    import asyncio
    import logging
    
    try:
        # 方法1: 尝试获取当前事件循环并关闭
        try:
            loop = asyncio.get_event_loop()
            if loop and not loop.is_closed():
                # 如果循环正在运行，停止它
                if loop.is_running():
                    loop.stop()
                # 关闭循环
                loop.close()
                logging.info(f"[{worker_id}] 已关闭继承的事件循环")
        except RuntimeError:
            # 没有事件循环，这是好事
            logging.debug(f"[{worker_id}] 没有现有事件循环")
        
        # 方法2: 创建一个全新的事件循环
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        logging.info(f"[{worker_id}] 已设置新的事件循环")
        
    except Exception as e:
        logging.warning(f"[{worker_id}] 清理 asyncio 环境时出错: {e}")
    
    # 步骤2: 启动正常的 Worker 逻辑
    from crawler.task_worker import TaskWorker

    worker = TaskWorker(
        worker_id=worker_id,
        task_queue=task_queue,
        result_queue=result_queue,
        db_path=db_path,
        db_lock=db_lock,
        status_dict=status_dict,
        account_pool_config=account_pool_config
    )
    worker.run()

class ParallelTaskManager:
    """并行任务管理器"""

    def __init__(self, max_workers=5, task_root="task", 
                db_path="data/record/central_record.db",
                account_pool_config="config/accounts.json"):
        self.max_workers = max_workers
        self.db_path = db_path
        self.account_pool_config = account_pool_config
        
        
        # 进程管理
        self.manager = Manager()
        self.task_queue = Queue()
        self.result_queue = Queue()
        self.workers = {}
        self.task_status = self.manager.dict()
        
        # 数据库锁
        self.db_lock = Lock()
        
        # 初始化数据库
        self._init_database()
        
        # 日志配置
        self.setup_logging()
        
        # 统计信息
        self.total_tasks = 0
        self.completed_tasks = 0
        self.failed_tasks = 0
        
        from models.account_pool import get_account_pool

        self.account_pool = get_account_pool(account_pool_config)
        
        available_accounts = self.account_pool.get_available_count()
        logging.info(f"账号池状态: 总计 {self.account_pool.get_total_count()} 个账号, "
                    f"可用 {available_accounts} 个")
        
        if available_accounts == 0:
            logging.warning("没有可用账号！请检查 config/accounts.json")

    def setup_logging(self):
        """配置日志"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='[Manager] %(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_dir / f"manager_{datetime.now():%Y%m%d}.log"),
                logging.StreamHandler()
            ]
        )
    
    def _init_database(self):
        """初始化中央数据库"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 创建任务表（添加 call_count 字段）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    task_name TEXT,
                    status TEXT,
                    start_time TIMESTAMP,
                    end_time TIMESTAMP,
                    total_creators INTEGER DEFAULT 0,
                    call_count INTEGER DEFAULT 0,
                    config TEXT
                )
            """)
            
            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_status ON tasks(status)")
            conn.commit()
    
    
    def generate_task_id(self, task_name):
        """生成唯一的任务ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{task_name}_{timestamp}_{self.total_tasks}"
    
    def add_task(self, task_config, task_file=None):
        """添加任务到队列"""
        task_name = task_config.get('name', 'task')
        task_id = self.generate_task_id(task_name)
        
        # 创建任务工作目录
        # 从任务名中提取产品文件夹名（取第一个下划线前的部分）
        # 例如: "GOOJODOQ_dify_out_1" -> "GOOJODOQ"
        product_folder = task_name.split('_')[0] if '_' in task_name else task_name
        
        # 创建两级目录: data/tasks/产品名/任务ID
        task_dir = Path(f"data/tasks/{product_folder}/{task_id}")
        task_dir.mkdir(parents=True, exist_ok=True)
        
        # 记录到数据库
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tasks (task_id, task_name, status, start_time, config)
                VALUES (?, ?, 'pending', ?, ?)
            """, (task_id, task_name, datetime.now(), json.dumps(task_config)))
            conn.commit()
        
        # 添加到队列
        task = {
            'task_id': task_id,
            'task_dir': str(task_dir),
            'config': task_config,  # ← 这里已经包含 _product_group
            'source_file': task_file
        }
        self.task_queue.put(task)
        self.task_status[task_id] = 'pending'
        self.total_tasks += 1
        
        logging.info(f"添加任务到队列: {task_id}")
        return task_id
    
        
    def start_worker(self, worker_id):
        process = Process(
            target=worker_entry,
            args=(
                worker_id,
                self.task_queue,
                self.result_queue,
                self.db_path,
                self.db_lock,
                self.task_status,
                self.account_pool_config
            )
        )
        process.start()

        self.workers[worker_id] = {
            'process': process,
            'start_time': datetime.now(),
            'status': 'running'
        }

        logging.info(f"启动工作进程: {worker_id}")
        return process
    
    def check_worker_health(self):
        """检查工作进程健康状态"""
        for worker_id, worker_info in list(self.workers.items()):
            process = worker_info['process']
            if not process.is_alive():
                if worker_info['status'] == 'running':
                    logging.warning(f"工作进程 {worker_id} 异常退出，重启中...")
                    self.start_worker(worker_id)
    
    def process_results(self):
        """处理工作进程返回的结果"""
        while True:
            try:
                result = self.result_queue.get_nowait()
                task_id = result['task_id']
                status = result['status']
                
                if status == 'completed':
                    self.completed_tasks += 1
                    logging.info(f"任务完成: {task_id}, 处理达人数: {result.get('creators_processed', 0)}")
                else:
                    self.failed_tasks += 1
                    logging.error(f"任务失败: {task_id}, 错误: {result.get('error', 'Unknown')}")
                
                # 更新数据库
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE tasks 
                        SET status = ?, end_time = ?, total_creators = ?
                        WHERE task_id = ?
                    """, (status, datetime.now(), result.get('creators_processed', 0), task_id))
                    conn.commit()
                    
            except Empty:
                break
    
    def run(self, daemon=False):
        logging.info(f"启动并行任务管理器，最大工作进程数: {self.max_workers}")
        
        # 启动工作进程
        for i in range(min(self.max_workers, self.total_tasks)):
            self.start_worker(f"worker_{i}")
        
        # 监控循环
        last_status = None  # 记录上次状态
        status_unchanged_count = 0  # 状态未变化的次数
        
        while True:
            self.check_worker_health()
            self.process_results()
            
            pending_count = sum(1 for status in self.task_status.values() if status == 'pending')
            running_count = sum(1 for status in self.task_status.values() if status == 'running')
            
            if pending_count == 0 and running_count == 0:
                if daemon:
                    logging.info("当前没有任务，守护模式下继续等待新任务...")
                    time.sleep(10)
                    continue
                else:
                    logging.info("所有任务已完成")
                    break
            
            # 构建当前状态
            current_status = (pending_count, running_count, self.completed_tasks, self.failed_tasks)
            
            # 只在以下情况输出日志：
            # 1. 状态发生变化
            # 2. 状态持续未变化超过5次（50秒），则输出一次作为"心跳"
            if current_status != last_status:
                logging.info(f"任务进度 - 待处理: {pending_count}, 运行中: {running_count}, "
                            f"已完成: {self.completed_tasks}, 失败: {self.failed_tasks}")
                last_status = current_status
                status_unchanged_count = 0
            else:
                status_unchanged_count += 1
                # 每5次（50秒）输出一次心跳日志
                if status_unchanged_count >= 5:
                    logging.info(f"[心跳] 任务进度 - 待处理: {pending_count}, 运行中: {running_count}, "
                                f"已完成: {self.completed_tasks}, 失败: {self.failed_tasks}")
                    status_unchanged_count = 0
            
            time.sleep(10)
        
        self.cleanup()
    
    def cleanup(self):
        """清理资源"""
        logging.info("清理资源...")
        
        # 发送退出信号给所有工作进程
        for _ in range(len(self.workers)):
            self.task_queue.put(None)
        
        # 等待所有进程结束
        for worker_id, worker_info in self.workers.items():
            process = worker_info['process']
            if process.is_alive():
                process.join(timeout=30)
                if process.is_alive():
                    logging.warning(f"强制终止进程 {worker_id}")
                    process.terminate()
        
        logging.info("清理完成")
    
    def get_summary(self):
        """获取执行总结"""
        account_status = self.account_pool.get_status()
        
        return {
            'total_tasks': self.total_tasks,
            'completed': self.completed_tasks,
            'failed': self.failed_tasks,
            'account_pool': {
                'total': account_status['total'],
                'available': account_status['available'],
                'in_use': account_status['in_use']
            }
        }