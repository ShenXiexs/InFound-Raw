"""
Browser Process Killer Script
关闭所有由爬虫脚本启动的浏览器进程
"""

import psutil
import subprocess
import sys
import os
import signal
import time
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BrowserProcessKiller:
    """浏览器进程终止器"""
    
    def __init__(self):
        # 需要终止的进程名称列表
        self.target_processes = [
            'chromium',
            'chrome',
            'chromium-browser',
            'google-chrome',
            'google-chrome-stable',
            'playwright',
            'node',  # Playwright 可能使用的 Node.js 进程
        ]
        
        # Playwright 相关的进程特征
        self.playwright_keywords = [
            'playwright',
            'chromium',
            'chrome-headless',
            '--headless',
            '--remote-debugging-port',
            'ms-playwright'
        ]
    
    def get_running_processes(self):
        """获取所有运行中的进程"""
        processes = []
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    processes.append(proc.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            logger.error(f"获取进程列表失败: {e}")
        return processes
    
    def is_playwright_process(self, process_info):
        """判断是否是 Playwright 相关进程"""
        if not process_info:
            return False
            
        name = process_info.get('name', '').lower()
        cmdline = process_info.get('cmdline', [])
        
        # 检查进程名
        if any(target in name for target in self.target_processes):
            # 进一步检查命令行参数
            if cmdline:
                cmdline_str = ' '.join(cmdline).lower()
                if any(keyword in cmdline_str for keyword in self.playwright_keywords):
                    return True
                    
                # 检查是否包含 TikTok 相关的 URL 或路径
                if any(url in cmdline_str for url in ['tiktok.com', 'affiliate.tiktok']):
                    return True
        
        return False
    
    def kill_process_by_pid(self, pid):
        """通过 PID 终止进程"""
        try:
            process = psutil.Process(pid)
            process.terminate()
            
            # 等待进程终止
            try:
                process.wait(timeout=5)
                logger.info(f"进程 {pid} 已正常终止")
                return True
            except psutil.TimeoutExpired:
                # 如果进程没有在 5 秒内终止，强制杀死
                process.kill()
                logger.info(f"进程 {pid} 已强制终止")
                return True
                
        except psutil.NoSuchProcess:
            logger.info(f"进程 {pid} 已不存在")
            return True
        except psutil.AccessDenied:
            logger.error(f"没有权限终止进程 {pid}")
            return False
        except Exception as e:
            logger.error(f"终止进程 {pid} 失败: {e}")
            return False
    
    def kill_playwright_browsers(self):
        """终止所有 Playwright 浏览器进程"""
        logger.info("开始搜索并终止 Playwright 浏览器进程...")
        
        processes = self.get_running_processes()
        playwright_processes = []
        
        # 找到所有 Playwright 相关进程
        for proc_info in processes:
            if self.is_playwright_process(proc_info):
                playwright_processes.append(proc_info)
        
        if not playwright_processes:
            logger.info("未找到 Playwright 浏览器进程")
            return True
        
        logger.info(f"找到 {len(playwright_processes)} 个 Playwright 相关进程")
        
        # 终止进程
        success_count = 0
        for proc_info in playwright_processes:
            pid = proc_info['pid']
            name = proc_info['name']
            cmdline = proc_info.get('cmdline', [])
            
            logger.info(f"终止进程: PID={pid}, Name={name}")
            if cmdline:
                logger.info(f"  命令行: {' '.join(cmdline[:3])}...")  # 只显示前3个参数
            
            if self.kill_process_by_pid(pid):
                success_count += 1
        
        logger.info(f"成功终止 {success_count}/{len(playwright_processes)} 个进程")
        return success_count == len(playwright_processes)
    
    def kill_by_system_command(self):
        """使用系统命令终止浏览器进程（备用方法）"""
        logger.info("使用系统命令终止浏览器进程...")
        
        commands = []
        
        if sys.platform.startswith('linux') or sys.platform == 'darwin':
            # Linux 和 macOS
            commands = [
                "pkill -f 'chromium.*headless'",
                "pkill -f 'chrome.*headless'", 
                "pkill -f 'playwright'",
                "pkill -f 'ms-playwright'",
            ]
        elif sys.platform.startswith('win'):
            # Windows
            commands = [
                'taskkill /f /im "chromium.exe"',
                'taskkill /f /im "chrome.exe"', 
                'taskkill /f /im "node.exe"',
            ]
        
        for cmd in commands:
            try:
                logger.info(f"执行命令: {cmd}")
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.returncode == 0:
                    logger.info(f"命令执行成功")
                else:
                    logger.info(f"命令执行完成 (可能没有找到相关进程)")
            except Exception as e:
                logger.warning(f"执行命令失败: {e}")
    
    def clean_temp_files(self):
        """清理临时文件"""
        logger.info("清理 Playwright 临时文件...")
        
        temp_dirs = []
        
        if sys.platform.startswith('linux') or sys.platform == 'darwin':
            temp_dirs = [
                '/tmp/playwright*',
                '/tmp/chrome*',
                '/tmp/chromium*',
            ]
        elif sys.platform.startswith('win'):
            temp_dirs = [
                os.path.expandvars('%TEMP%\\playwright*'),
                os.path.expandvars('%TEMP%\\chrome*'),
                os.path.expandvars('%TEMP%\\chromium*'),
            ]
        
        for temp_pattern in temp_dirs:
            try:
                if sys.platform.startswith('win'):
                    cmd = f'del /f /q "{temp_pattern}" 2>nul'
                else:
                    cmd = f'rm -rf {temp_pattern} 2>/dev/null'
                    
                subprocess.run(cmd, shell=True)
                logger.info(f"清理临时文件: {temp_pattern}")
            except Exception as e:
                logger.warning(f"清理临时文件失败: {e}")
    
    def run(self, clean_temp=True):
        """执行完整的清理流程"""
        logger.info("=" * 50)
        logger.info("开始清理 Playwright 浏览器进程")
        logger.info("=" * 50)
        
        # 方法1: 使用 psutil 精确终止
        success = self.kill_playwright_browsers()
        
        # 等待一段时间
        time.sleep(2)
        
        # 方法2: 使用系统命令（备用）
        self.kill_by_system_command()
        
        # 清理临时文件
        if clean_temp:
            time.sleep(1)
            self.clean_temp_files()
        
        logger.info("=" * 50)
        logger.info("浏览器进程清理完成")
        logger.info("=" * 50)
        
        return success

def main():
    """主函数"""
    killer = BrowserProcessKiller()
    
    try:
        # 显示帮助信息
        print("浏览器进程终止器")
        print("此脚本将终止所有由 Playwright 启动的浏览器进程")
        print("=" * 50)
        
        # 询问用户确认
        response = input("是否继续？(y/N): ").strip().lower()
        if response not in ['y', 'yes']:
            print("操作已取消")
            return
        
        # 执行清理
        killer.run()
        
        print("\n清理完成！建议重新启动爬虫脚本。")
        
    except KeyboardInterrupt:
        print("\n操作已被用户中断")
    except Exception as e:
        logger.error(f"脚本执行失败: {e}")

if __name__ == '__main__':
    main()