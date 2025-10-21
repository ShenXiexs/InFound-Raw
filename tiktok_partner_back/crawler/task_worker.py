"""
任务工作进程
独立运行的爬虫进程，处理单个任务（支持多次调用逻辑）
"""
import sys
import os
import json
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from queue import Empty
import time
import re

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crawler.creator_full_crawler import CreatorFullCrawler
from models.account_pool import get_account_pool

class TaskWorker:
    """任务工作进程"""
    
    def __init__(self, worker_id, task_queue, result_queue, db_path, 
                db_lock, status_dict, account_pool_config=None):
        self.worker_id = worker_id
        self.task_queue = task_queue
        self.result_queue = result_queue
        self.db_path = db_path
        self.db_lock = db_lock
        self.status_dict = status_dict
        
        # 账号池支持
        self.account_pool = get_account_pool(account_pool_config or "config/accounts.json")
        self.current_account = None
        self.current_account_id = None
        
        # 单任务多次调用配置
        self.max_calls_per_task = 10      # 每个任务最多调用10次
        self.target_creators_per_call = 50 # 每次目标处理50个达人
        self.max_creators_per_task = 500   # 每个任务最多500个达人
        self.min_new_creators = 5         # 如果新增少于5个，认为没有更多达人
        
        # 设置进程级日志
        self.setup_logging()
    
    def setup_logging(self):
        """配置进程日志"""
        log_dir = Path(f"logs/{self.worker_id}")
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建独立的logger
        self.logger = logging.getLogger(self.worker_id)
        self.logger.setLevel(logging.INFO)
        
        # 清除已有的handlers
        self.logger.handlers.clear()
        
        # 添加文件handler
        fh = logging.FileHandler(log_dir / f"{datetime.now():%Y%m%d}.log")
        fh.setFormatter(logging.Formatter(f'[{self.worker_id}] %(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(fh)
        
        # 添加控制台handler
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter(f'[{self.worker_id}] %(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(ch)
    
    def update_task_status(self, task_id, status, total_creators=None):
        """更新任务状态到数据库"""
        try:
            with self.db_lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    if total_creators is not None:
                        cursor.execute(
                            "UPDATE tasks SET status = ?, total_creators = ? WHERE task_id = ?",
                            (status, total_creators, task_id)
                        )
                    else:
                        cursor.execute(
                            "UPDATE tasks SET status = ? WHERE task_id = ?",
                            (status, task_id)
                        )
                    conn.commit()
        except Exception as e:
            self.logger.error(f"更新任务状态失败: {e}")
    
    def run_crawler_once(self, task_id, task_dir, config, attempt_num, task_name):
        """
        运行一次爬虫
        
        Returns:
            int: 本次新增处理的达人数
        """
        self.logger.info(f"[{task_name}] 第 {attempt_num}/{self.max_calls_per_task} 次调用爬虫...")
        
        try:
            # 准备任务特定的配置文件
            dify_path = Path(task_dir) / "dify_out.txt"
            with open(dify_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            
            # 创建爬虫实例（传递数据库相关参数）
            crawler = CreatorFullCrawler(
                search_strategy=config.get('search_strategy'),
                task_id=f"{task_id}_attempt_{attempt_num}",
                task_dir=task_dir,
                max_creators_to_load=self.target_creators_per_call,
                account_info=self.current_account  # 传入当前账号
            )

            # 设置爬虫的目标新增数
            crawler.target_new_count = self.target_creators_per_call
            
            # 运行爬虫
            success = crawler.run()
            
            # 获取本次新增处理的达人数量
            new_processed = getattr(crawler, 'new_processed_count', 0)
            
            self.logger.info(f"[{task_name}] 第 {attempt_num} 次调用完成，新增处理: {new_processed} 个达人")
            
            return new_processed
            
        except Exception as e:
            self.logger.error(f"[{task_name}] 第 {attempt_num} 次调用失败: {e}")
            return 0
    
    def process_task(self, task):
        """处理单个任务（包含文件夹下的所有配置文件）"""
        task_id = task['task_id']
        task_dir = task['task_dir']
        task_config = task['config']
        task_name = task_config.get('name', task_id)
        
        # 获取该任务的所有配置文件
        config_files = task_config.get('config_files', [])
        
        if not config_files:
            self.logger.error(f"任务 {task_name} 没有有效的配置文件")
            self.result_queue.put({
                'task_id': task_id,
                'worker_id': self.worker_id,
                'status': 'failed',
                'error': '没有有效的配置文件',
                'creators_processed': 0
            })
            return
        
        # 从配置中读取区域，按区域获取账号
        region = None
        # 从第一个配置文件中读取区域信息
        try:
            first_config = config_files[0]['data']
            region = first_config.get('region', '').upper()
        except:
            pass
        
        # 获取账号（优先按区域匹配）
        if region:
            self.logger.info(f"任务 {task_name} 需要区域: {region}")
            self.current_account = self.account_pool.acquire_account_by_region(task_id, region)
        else:
            self.logger.info(f"任务 {task_name} 未指定区域，使用任意可用账号")
            self.current_account = self.account_pool.acquire_account(task_id)
        
        if not self.current_account:
            error_msg = f"无可用账号 (区域: {region})" if region else "无可用账号"
            self.logger.error(f"无法为任务 {task_name} 分配账号")
            self.result_queue.put({
                'task_id': task_id,
                'worker_id': self.worker_id,
                'status': 'failed',
                'error': error_msg,
                'creators_processed': 0
            })
            return
        
        self.current_account_id = self.current_account.get('id')
        
        # 显示账号的区域信息
        account_region = self.current_account.get('region', '通用')
        self.logger.info(f"{'='*60}")
        self.logger.info(f"任务: {task_name} (ID: {task_id})")
        self.logger.info(f"配置文件数: {len(config_files)}")
        self.logger.info(f"任务区域: {region or '未指定'}")
        self.logger.info(f"使用账号: {self.current_account.get('name')} ({self.current_account.get('login_email')}) [区域: {account_region}]")
        self.logger.info(f"{'='*60}")
        
        # 更新任务状态
        self.status_dict[task_id] = 'running'
        self.update_task_status(task_id, 'running')
        
        # 统计信息
        total_processed = 0
        processed_configs = 0
        failed_configs = 0
        
        try:
            # 逐个处理配置文件
            for config_info in config_files:
                config_name = config_info['name']
                config_data = config_info['data']
                config_file = config_info['file']
                
                self.logger.info(f"\n{'='*50}")
                self.logger.info(f"处理配置 [{processed_configs + 1}/{len(config_files)}]: {config_name}")
                self.logger.info(f"{'='*50}")
                
                # 创建子任务目录
                sub_task_dir = Path(task_dir) / config_name
                sub_task_dir.mkdir(parents=True, exist_ok=True)
                
                # 复制对应的配置文件到子任务目录
                import shutil
                shutil.copy2(config_file, sub_task_dir / f"{config_name}.txt")
                
                # 从配置中读取参数
                if 'max_calls_per_task' in task_config:
                    self.max_calls_per_task = task_config['max_calls_per_task']
                if 'creators_per_call' in task_config:
                    self.target_creators_per_call = task_config['creators_per_call']
                if 'max_creators_per_task' in task_config:
                    self.max_creators_per_task = task_config['max_creators_per_task']
                
                # 多次调用爬虫处理这个配置
                config_processed = 0
                config_success = False
                
                for attempt in range(1, self.max_calls_per_task + 1):
                    # 检查是否已达到上限
                    if config_processed >= self.max_creators_per_task:
                        self.logger.info(f"[{config_name}] 已达到上限 {self.max_creators_per_task} 个达人")
                        config_success = True
                        break
                    
                    # 运行一次爬虫
                    new_processed = self.run_crawler_once(
                        f"{task_id}_{config_name}",
                        str(sub_task_dir),
                        config_data,
                        attempt,
                        config_name
                    )
                    
                    config_processed += new_processed
                    total_processed += new_processed
                    
                    # 更新进度
                    self.update_task_status(task_id, 'running', total_processed)
                    
                    # 判断是否继续
                    if new_processed < self.min_new_creators:
                        self.logger.info(f"[{config_name}] 新增达人数 {new_processed} < {self.min_new_creators}，结束该配置")
                        config_success = True
                        break
                    
                    # 任务间休息
                    if attempt < self.max_calls_per_task:
                        wait_time = 5
                        self.logger.info(f"[{config_name}] 等待 {wait_time} 秒后继续...")
                        time.sleep(wait_time)
                
                # 统计该配置的结果
                if config_success:
                    processed_configs += 1
                    self.logger.info(f"✓ 配置 {config_name} 处理成功，处理了 {config_processed} 个达人")
                else:
                    failed_configs += 1
                    self.logger.error(f"✗ 配置 {config_name} 处理失败")
                
                # 配置间休息
                if processed_configs < len(config_files):
                    self.logger.info(f"准备处理下一个配置，休息 10 秒...")
                    time.sleep(10)
            
            # 确定任务最终状态
            if processed_configs == len(config_files):
                status = 'completed'
            elif processed_configs > 0:
                status = 'partial'  # 部分成功
            else:
                status = 'failed'
            
            self.status_dict[task_id] = status
            self.update_task_status(task_id, status, total_processed)
            
            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"任务 {task_name} 完成")
            self.logger.info(f"  状态: {status}")
            self.logger.info(f"  配置文件: {processed_configs}/{len(config_files)} 成功")
            self.logger.info(f"  总处理达人数: {total_processed}")
            self.logger.info(f"{'='*60}")
            
            # 发送结果
            self.result_queue.put({
                'task_id': task_id,
                'worker_id': self.worker_id,
                'status': status,
                'creators_processed': total_processed,
                'configs_processed': processed_configs,
                'configs_failed': failed_configs
            })
            
        except Exception as e:
            self.logger.error(f"任务 {task_name} 处理失败: {e}", exc_info=True)
            self.status_dict[task_id] = 'failed'
            self.update_task_status(task_id, 'failed', total_processed)
            
            self.result_queue.put({
                'task_id': task_id,
                'worker_id': self.worker_id,
                'status': 'failed',
                'error': str(e),
                'creators_processed': total_processed
            })
        
        finally:
            if self.current_account:
                self.account_pool.release_account(self.current_account_id, task_id)
                self.logger.info(f"任务 {task_id} 释放账号: {self.current_account.get('name')}")
                self.current_account = None
                self.current_account_id = None
    
    def run(self):
        self.logger.info(f"工作进程 {self.worker_id} 启动")
        
        current_product = None  # 当前占用的产品
        
        while True:
            try:
                task = self.task_queue.get(timeout=30)
                
                if task is None:
                    self.logger.info(f"收到退出信号")
                    break
                
                product_group = task.get('config', {}).get('_product_group')
                
                if product_group:
                    # 检查产品是否被占用
                    lock_key = f'_product_lock_{product_group}'
                    
                    with self.db_lock:
                        occupied_by = self.status_dict.get(lock_key)
                        
                        if occupied_by and occupied_by != self.worker_id:
                            # 被其他Worker占用，放回队列
                            self.logger.info(f"产品 {product_group} 被 {occupied_by} 占用，放回队列")
                            self.task_queue.put(task)
                            time.sleep(3)
                            continue
                        else:
                            # 占用该产品
                            self.status_dict[lock_key] = self.worker_id
                            current_product = product_group
                            self.logger.info(f"占用产品: {product_group}")
                
                # 处理任务
                self.process_task(task)
                
                # 释放产品锁
                if current_product:
                    lock_key = f'_product_lock_{current_product}'
                    with self.db_lock:
                        if self.status_dict.get(lock_key) == self.worker_id:
                            self.status_dict.pop(lock_key, None)
                            self.logger.info(f"释放产品: {current_product}")
                    current_product = None
                
                time.sleep(2)
                
            except Empty:
                self.logger.debug("任务队列为空")
                continue
            except Exception as e:
                self.logger.error(f"异常: {e}", exc_info=True)
        
        self.logger.info(f"工作进程结束")