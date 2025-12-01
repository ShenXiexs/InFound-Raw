"""
TikTok账号池管理器
管理多个TikTok账号,支持任务分配和释放
"""
import json
import logging
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime
import threading

logger = logging.getLogger(__name__)

class AccountPool:
    """账号池管理器（支持账号共享）"""
    
    def __init__(self, config_file="config/accounts.json"):
        self.config_file = Path(config_file)
        self.accounts: List[Dict] = []
        self.account_usage: Dict[int, List[str]] = {}  # account_id -> [task_id1, task_id2, ...]
        self.account_locks: Dict[int, threading.Lock] = {}
        self.lock = threading.Lock()
        
        # 加载账号配置
        self._load_accounts()
        
    def _load_accounts(self):
        """从配置文件加载账号"""
        if not self.config_file.exists():
            logger.warning(f"账号配置文件不存在: {self.config_file}")
            self._create_default_config()
            return
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            self.accounts = config.get('accounts', [])
            
            # 初始化账号使用记录
            for i, account in enumerate(self.accounts):
                self.account_usage[i] = []  # 空列表表示未被使用
                self.account_locks[i] = threading.Lock()
                account['id'] = i
            
            logger.info(f"成功加载 {len(self.accounts)} 个账号")
            
            # 验证账号配置
            for account in self.accounts:
                if not self._validate_account(account):
                    logger.warning(f"账号配置不完整: {account.get('name', 'unknown')}")
                    
        except Exception as e:
            logger.error(f"加载账号配置失败: {e}")
            self._create_default_config()
    
    def _validate_account(self, account: Dict) -> bool:
        """验证账号配置是否完整"""
        required_fields = ['login_email', 'login_password', 'gmail_username', 'gmail_app_password']
        return all(field in account for field in required_fields)
    
    def _create_default_config(self):
        """创建默认配置文件"""
        default_config = {
            "accounts": [
                {
                    "name": "SampleAccount",
                    "login_email": "sample-account@example.com",
                    "login_password": "CHANGE_ME",
                    "gmail_username": "sample-notifications@example.com",
                    "gmail_app_password": "CHANGE_ME",
                    "region": "MX",
                    "enabled": True,
                    "notes": "Placeholder account; replace with your own credentials."
                }
            ]
        }
        
        # 确保目录存在
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)
        
        logger.info(f"已创建默认账号配置: {self.config_file}")
        self.accounts = default_config['accounts']
        
        for i, account in enumerate(self.accounts):
            self.account_usage[i] = []
            self.account_locks[i] = threading.Lock()
            account['id'] = i
    
    def acquire_account_by_region(self, task_id: str, region: str) -> Optional[Dict]:
        """
        根据区域为任务分配账号（支持多任务共享账号）
        
        优先级：
        1. 匹配区域且未被使用的账号
        2. 匹配区域且已被使用的账号（共享）
        
        Args:
            task_id: 任务ID
            region: 区域代码 (如 'MX', 'US', 'BR')
            
        Returns:
            账号信息字典,如果没有可用账号则返回None
        """
        with self.lock:
            region_upper = region.upper() if region else ''
            
            # 优先分配：匹配区域且未被使用的账号
            for account_id in self.account_usage:
                account = self.accounts[account_id]
                
                if not account.get('enabled', True):
                    continue
                
                account_region = account.get('region', '').upper()
                if account_region == region_upper and len(self.account_usage[account_id]) == 0:
                    # 找到未被使用的匹配区域账号
                    self.account_usage[account_id].append(task_id)
                    account['task_id'] = task_id
                    account['acquire_time'] = datetime.now().isoformat()
                    
                    logger.info(
                        f"✓ 为任务 {task_id} (区域: {region}) 分配账号: {account.get('name')} "
                        f"【独占模式】"
                    )
                    return account.copy()
            
            # 次优分配：匹配区域但已被使用的账号（共享）
            for account_id in self.account_usage:
                account = self.accounts[account_id]
                
                if not account.get('enabled', True):
                    continue
                
                account_region = account.get('region', '').upper()
                if account_region == region_upper:
                    # 找到已被使用的匹配区域账号，共享使用
                    if task_id not in self.account_usage[account_id]:
                        self.account_usage[account_id].append(task_id)
                    
                    using_tasks = ', '.join(self.account_usage[account_id])
                    usage_count = len(self.account_usage[account_id])
                    logger.info(
                        f"✓ 为任务 {task_id} (区域: {region}) 分配账号: {account.get('name')} "
                        f"【共享模式 {usage_count}/∞】当前共享任务: [{using_tasks}]"
                    )
                    return account.copy()
            
            # 如果找不到匹配区域的账号，返回None
            logger.error(
                f"✗ 没有找到区域 {region} 的账号！任务 {task_id} 无法执行"
            )
            return None
    
    def acquire_account(self, task_id: str) -> Optional[Dict]:
        """
        为任务分配账号（不限区域，支持共享）
        
        Args:
            task_id: 任务ID
            
        Returns:
            账号信息字典,如果没有可用账号则返回None
        """
        with self.lock:
            # 优先分配未被使用的账号
            for account_id in self.account_usage:
                account = self.accounts[account_id]
                
                if not account.get('enabled', True):
                    continue
                
                if len(self.account_usage[account_id]) == 0:
                    self.account_usage[account_id].append(task_id)
                    account['task_id'] = task_id
                    account['acquire_time'] = datetime.now().isoformat()
                    
                    logger.info(f"为任务 {task_id} 分配账号: {account.get('name', f'账号{account_id}')} (独占)")
                    return account.copy()
            
            # 如果所有账号都被使用，则共享使用第一个可用账号
            for account_id in self.account_usage:
                account = self.accounts[account_id]
                
                if not account.get('enabled', True):
                    continue
                
                if task_id not in self.account_usage[account_id]:
                    self.account_usage[account_id].append(task_id)
                
                using_tasks = ', '.join(self.account_usage[account_id])
                logger.info(f"为任务 {task_id} 分配账号: {account.get('name', f'账号{account_id}')} (共享，当前使用: [{using_tasks}])")
                return account.copy()
            
            logger.warning(f"没有可用账号分配给任务 {task_id}")
            return None
    
    def release_account(self, account_id: int, task_id: str = None):
        """
        释放账号（从使用列表中移除任务ID）
        
        Args:
            account_id: 账号ID
            task_id: 任务ID (可选,用于验证)
        """
        with self.lock:
            if account_id in self.account_usage:
                account = self.accounts[account_id]
                
                if task_id:
                    # 从使用列表中移除该任务
                    if task_id in self.account_usage[account_id]:
                        self.account_usage[account_id].remove(task_id)
                        
                        remaining = len(self.account_usage[account_id])
                        if remaining > 0:
                            remaining_tasks = ', '.join(self.account_usage[account_id])
                            logger.info(
                                f"任务 {task_id} 释放账号: {account.get('name', f'账号{account_id}')} "
                                f"(仍有 {remaining} 个任务使用中: [{remaining_tasks}])"
                            )
                        else:
                            logger.info(
                                f"任务 {task_id} 释放账号: {account.get('name', f'账号{account_id}')} "
                                f"(完全空闲)"
                            )
                            # ← 清理时间戳字段
                            account['task_id'] = None
                            account['release_time'] = datetime.now().isoformat()
                    else:
                        # ← 新增：如果任务不在列表中，记录警告
                        logger.warning(
                            f"任务 {task_id} 尝试释放账号 {account.get('name', f'账号{account_id}')}，"
                            f"但该任务不在使用列表中"
                        )
                else:
                    # 清空所有使用记录
                    cleared_tasks = ', '.join(self.account_usage[account_id])
                    self.account_usage[account_id].clear()
                    account['task_id'] = None
                    account['release_time'] = datetime.now().isoformat()
                    logger.info(
                        f"完全释放账号: {account.get('name', f'账号{account_id}')} "
                        f"(清除了任务: [{cleared_tasks}])"
                    )
            else:
                logger.warning(f"无效的账号ID: {account_id}")
    
    def get_available_count(self) -> int:
        """获取可用账号数量（未被使用的账号）"""
        with self.lock:
            return sum(1 for tasks in self.account_usage.values() if len(tasks) == 0)
    
    def get_total_count(self) -> int:
        """获取总账号数量"""
        return len(self.accounts)
    
    def get_status(self) -> Dict:
        """获取账号池状态"""
        with self.lock:
            total_enabled = sum(1 for acc in self.accounts if acc.get('enabled', True))
            available = sum(1 for tasks in self.account_usage.values() if len(tasks) == 0)
            in_use = sum(1 for tasks in self.account_usage.values() if len(tasks) > 0)
            
            status = {
                'total': total_enabled,
                'available': available,
                'in_use': in_use,
                'accounts': []
            }
            
            for i, account in enumerate(self.accounts):
                if not account.get('enabled', True):
                    continue
                
                usage_count = len(self.account_usage[i])
                using_tasks = self.account_usage[i].copy() if usage_count > 0 else []
                
                status['accounts'].append({
                    'id': i,
                    'name': account.get('name', f'账号{i}'),
                    'email': account.get('login_email', ''),
                    'region': account.get('region', 'N/A'),
                    'status': 'available' if usage_count == 0 else 'in_use',
                    'usage_count': usage_count,  # 新增：使用次数
                    'using_tasks': using_tasks,  # 新增：使用该账号的任务列表
                    'enabled': account.get('enabled', True)
                })
            
            return status
    
    def reload_config(self):
        """重新加载配置文件"""
        logger.info("重新加载账号配置...")
        
        # 保存当前使用中的账号状态
        in_use_accounts = {}
        with self.lock:
            for account_id, tasks in self.account_usage.items():
                if len(tasks) > 0:
                    in_use_accounts[account_id] = tasks.copy()
        
        # 重新加载
        self._load_accounts()
        
        # 恢复使用中的账号状态
        with self.lock:
            for account_id, tasks in in_use_accounts.items():
                if account_id < len(self.accounts):
                    self.account_usage[account_id] = tasks


# 全局账号池实例
_account_pool = None

def get_account_pool(config_file="config/accounts.json") -> AccountPool:
    """获取全局账号池实例"""
    global _account_pool
    if _account_pool is None:
        _account_pool = AccountPool(config_file)
    return _account_pool
