#!/usr/bin/env python3
"""
并行批量处理器
支持多任务并行执行的批处理脚本
"""
import sys
import os
import json
import time
import argparse
import multiprocessing as mp
from pathlib import Path
from datetime import datetime

# 添加crawler目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crawler.parallel_manager import ParallelTaskManager

def load_tasks_from_directory(task_dir="task"):
    """按产品文件夹加载任务（每个文件夹是一个完整任务）"""
    task_path = Path(task_dir)
    if not task_path.exists():
        print(f"任务目录不存在: {task_dir}")
        return []
    
    subdirs = [d for d in task_path.iterdir() if d.is_dir()]
    if not subdirs:
        print("没有找到任务文件夹")
        return []
    
    subdirs = [d for d in subdirs if not d.name.startswith('.') and 
               not d.name.startswith('_') and d.name not in ['backup', 'processed', 'temp']]
    
    print(f"\n发现 {len(subdirs)} 个产品文件夹（任务）:")
    
    all_tasks = []
    
    for subdir in sorted(subdirs):
        print(f"\n检查任务文件夹: {subdir.name}")
        
        # 收集该文件夹下的所有配置文件
        config_files = []
        for pattern in ['*.txt', '*.json']:
            config_files.extend(subdir.glob(pattern))
        
        exclude_patterns = ['readme', 'README', 'note', 'NOTE', 'backup']
        config_files = [f for f in config_files 
                       if not any(p.lower() in f.name.lower() for p in exclude_patterns)]
        
        if not config_files:
            print(f"  ✗ 未找到配置文件，跳过")
            continue
        
        print(f"  找到 {len(config_files)} 个配置文件")
        
        # 验证所有配置文件
        valid_configs = []
        for config_file in sorted(config_files):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                    if 'search_strategy' in config_data:
                        valid_configs.append({
                            'file': str(config_file),
                            'name': config_file.stem,
                            'data': config_data
                        })
                        print(f"    ✓ {config_file.name}")
                    else:
                        print(f"    ✗ {config_file.name} (缺少search_strategy)")
            except Exception as e:
                print(f"    ✗ {config_file.name} (加载失败: {e})")
        
        if valid_configs:
            # 创建任务配置（整个文件夹作为一个任务）
            task_config = {
                'name': subdir.name,  # 使用文件夹名作为任务名
                'source_dir': str(subdir),
                'config_files': valid_configs,  # 包含所有配置文件
                'config_count': len(valid_configs)
            }
            
            all_tasks.append((task_config, str(subdir)))
            print(f"  ✓ 任务 {subdir.name} 创建成功（包含 {len(valid_configs)} 个配置）")
    
    print(f"\n总计: {len(all_tasks)} 个任务")
    return all_tasks

def load_single_config(folder_path, config_file):
    """
    加载单个配置文件
    
    Args:
        folder_path: 文件夹路径
        config_file: 配置文件路径
        
    Returns:
        (config, config_file_path) 或 None
    """
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 验证必要字段
        if 'search_strategy' not in config:
            print(f"      配置无效（缺少search_strategy）")
            return None
        
        # 添加任务元信息
        # 使用 文件夹名_配置文件名 作为任务名
        config_name = config_file.stem  # 不带扩展名的文件名
        config['name'] = f"{folder_path.name}_{config_name}"
        config['source_file'] = str(config_file)
        config['source_dir'] = str(folder_path)
        config['config_filename'] = config_file.name  # 记录原始文件名
        
        # 显示任务关键信息
        keywords = config.get('search_strategy', {}).get('search_keywords', 'N/A')
        print(f"      - 任务名: {config['name']}")
        print(f"      - 关键词: {keywords}")
        
        return (config, str(config_file))
        
    except json.JSONDecodeError as e:
        print(f"      JSON解析错误: {e}")
        return None
    except Exception as e:
        print(f"      加载失败: {e}")
        return None

def load_single_task_folder(folder_path):
    """加载单个任务文件夹的所有配置（返回统一格式）"""
    folder_path = Path(folder_path)
    
    if not folder_path.exists():
        print(f"文件夹不存在: {folder_path}")
        return []  # ← 返回空列表而不是 None
    
    if not folder_path.is_dir():
        print(f"不是文件夹: {folder_path}")
        return []  # ← 返回空列表
    
    print(f"加载任务文件夹: {folder_path}")
    
    # 加载所有配置文件
    config_files = []
    for pattern in ['*.txt', '*.json']:
        config_files.extend(folder_path.glob(pattern))
    
    # 排除特殊文件
    exclude_patterns = ['readme', 'README', 'note', 'NOTE', 'backup']
    config_files = [
        f for f in config_files 
        if not any(pattern.lower() in f.name.lower() for pattern in exclude_patterns)
    ]
    
    if not config_files:
        print(f"未找到配置文件")
        return []  # ← 返回空列表
    
    print(f"找到 {len(config_files)} 个配置文件")
    
    valid_configs = []
    for config_file in sorted(config_files):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                
                # 验证必要字段
                if 'search_strategy' not in config_data:
                    print(f"  ✗ {config_file.name} (缺少search_strategy)")
                    continue
                
                valid_configs.append({
                    'file': str(config_file),
                    'name': config_file.stem,
                    'data': config_data
                })
                print(f"  ✓ {config_file.name}")
                
        except json.JSONDecodeError as e:
            print(f"  ✗ {config_file.name} (JSON解析错误: {e})")
        except Exception as e:
            print(f"  ✗ {config_file.name} (加载失败: {e})")
    
    if not valid_configs:
        print(f"没有有效的配置文件")
        return []  # ← 返回空列表
    
    # 构建任务配置（与 load_tasks_from_directory 格式一致）
    task_config = {
        'name': folder_path.name,
        'source_dir': str(folder_path),
        'config_files': valid_configs,
        'config_count': len(valid_configs)
    }
    
    print(f"✓ 任务 {folder_path.name} 加载成功（包含 {len(valid_configs)} 个配置）")
    
    # 返回列表格式：[(task_config, source_dir)]
    return [(task_config, str(folder_path))]

def print_banner():
    from models.account_pool import get_account_pool
    """打印启动横幅"""
    print("=" * 60)
    print("TikTok Partner 并行爬虫系统")
    print("=" * 60)
    print(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    try:
        pool = get_account_pool()
        status = pool.get_status()
        print(f"账号池: {status['total']} 个账号, {status['available']} 个可用")
    except:
        print("账号池: 未配置")
    
    print("=" * 60)

def print_summary(manager):
    """打印执行总结"""
    summary = manager.get_summary()
    
    print("\n" + "=" * 60)
    print("执行总结")
    print("=" * 60)
    print(f"总任务数: {summary['total_tasks']}")
    print(f"成功完成: {summary['completed']}")
    print(f"失败任务: {summary['failed']}")
    print("=" * 60)

    if 'account_pool' in summary:
        print(f"\n账号池状态:")
        print(f"  总账号: {summary['account_pool']['total']}")
        print(f"  可用: {summary['account_pool']['available']}")
        print(f"  使用中: {summary['account_pool']['in_use']}")
    
    print("=" * 60)

def main():
    parser = argparse.ArgumentParser(description='TikTok Partner 并行任务批处理器')
    parser.add_argument('task_folder', nargs='?', default=None,
                       help='指定单个任务文件夹 (如: task/Jeep-product)')
    parser.add_argument('--workers', '-w', type=int, default=3, 
                       help='并行工作进程数 (默认: 3)')
    parser.add_argument('--task-dir', '-d', default='task', 
                       help='任务文件夹根目录 (默认: task)')
    
    parser.add_argument('--max-calls', type=int, default=10,
                       help='每个任务最多调用次数 (默认: 10)')
    parser.add_argument('--creators-per-call', type=int, default=50,
                       help='每次调用目标达人数 (默认: 50)')
    parser.add_argument('--max-creators', '-m', type=int, default=500,
                       help='每个任务最大达人总数 (默认: 500)')
    parser.add_argument('--db-path', default='data/record/central_record.db',
                       help='中央数据库路径')
    parser.add_argument('--clean-db', action='store_true',
                       help='清空数据库后重新开始')
    parser.add_argument('--daemon', action='store_true',
                   help='以守护模式运行，任务完成后不退出，等待新任务')
    parser.add_argument('--account-config', default='config/accounts.json',
                       help='账号配置文件路径 (默认: config/accounts.json)')
    parser.add_argument('--show-accounts', action='store_true',
                       help='显示账号池状态并退出')

    parser.add_argument('--single-config', action='store_true',
                       help='每个文件夹只加载一个配置文件(旧行为)')
    parser.add_argument('--list-tasks', action='store_true',
                       help='列出所有将要执行的任务并退出')
    
    args = parser.parse_args()
    
    # 打印横幅
    print_banner()
    
    # 如果需要清空数据库
    if args.clean_db:
        db_path = Path(args.db_path)
        if db_path.exists():
            response = input(f"确定要删除数据库 {db_path}? (y/N): ")
            if response.lower() == 'y':
                db_path.unlink()
                print("数据库已删除")
    
    print_banner()

    if args.show_accounts:
        from models.account_pool import get_account_pool
        pool = get_account_pool(args.account_config)
        status = pool.get_status()
        
        print("\n" + "=" * 60)
        print("账号池状态")
        print("=" * 60)
        print(f"总账号数: {status['total']}")
        print(f"空闲: {status['available']}")
        print(f"使用中: {status['in_use']}")
        print("\n账号详情:")
        print("-" * 60)
        for account in status['accounts']:
            status_icon = "✓" if account['status'] == 'available' else "○"
            enabled_text = "启用" if account['enabled'] else "禁用"
            region_text = account.get('region', 'N/A')
            usage_count = account.get('usage_count', 0)
            
            print(f"  {status_icon} [{account['id']}] {account['name']}")
            print(f"      邮箱: {account['email']}")
            print(f"      区域: {region_text}")
            print(f"      状态: {account['status']} ({enabled_text})")
            
            # 显示共享信息
            if usage_count > 0:
                print(f"      共享数: {usage_count} 个任务")
                using_tasks = account.get('using_tasks', [])
                for task_id in using_tasks:
                    print(f"        - {task_id}")
            
            print()
        print("=" * 60)
        return
    
    load_all = not args.single_config
    # 加载任务
    tasks = []
    
    if args.task_folder:
        # 处理单个指定的任务文件夹
        print(f"\n加载指定任务文件夹: {args.task_folder}")
        tasks = load_single_task_folder(args.task_folder)  # ← 直接赋值，不再包装
        
        if not tasks:  # ← 检查是否为空列表
            print(f"无法加载任务文件夹: {args.task_folder}")
            return
    else:
        # 处理所有任务文件夹
        print(f"\n从目录加载所有任务: {args.task_dir}")
        tasks = load_tasks_from_directory(args.task_dir)

    if not tasks:
        print("没有找到有效的任务")
        return
    
    if args.list_tasks:
        print("\n" + "=" * 70)
        print("将要执行的任务列表")
        print("=" * 70)
        
        for i, (task_config, task_file) in enumerate(tasks, 1):
            print(f"\n[{i}] {task_config['name']}")
            print(f"    配置文件: {task_config['config_filename']}")
            print(f"    文件夹: {task_config['source_dir']}")
            keywords = task_config.get('search_strategy', {}).get('search_keywords', 'N/A')
            print(f"    关键词: {keywords}")
            print(f"    最多调用: {args.max_calls} 次")
            print(f"    每次目标: {args.creators_per_call} 个达人")
            print(f"    总上限: {args.max_creators} 个达人")
        
        print("\n" + "=" * 70)
        print(f"总计: {len(tasks)} 个任务")
        print("=" * 70)
        return
      
    print(f"\n准备执行 {len(tasks)} 个任务")
    
    from models.account_pool import get_account_pool
    pool = get_account_pool(args.account_config)
    available_accounts = pool.get_available_count()
    
    print(f"\n资源检查:")
    print(f"  - 任务数量: {len(tasks)}")
    print(f"  - 可用账号: {available_accounts}")
    print(f"  - 并行Worker: {args.workers}")
    
    if available_accounts == 0:
        print("\n 错误: 没有可用账号！")
        print("请配置账号文件: config/accounts.json")
        print("或使用 --account-config 参数指定配置文件")
        return
    
    if available_accounts < args.workers:
        print(f"\n  警告: 可用账号 ({available_accounts}) 少于Worker数 ({args.workers})")
        print(f"建议调整 --workers 参数为 {available_accounts} 或更少")
        
        if not args.daemon:
            response = input("是否继续? (y/N): ")
            if response.lower() != 'y':
                print("已取消")
                return
    
    if available_accounts > 0:
        pool = get_account_pool(args.account_config)
        status = pool.get_status()
        
        # 统计各区域的账号数量
        region_count = {}
        for acc in status['accounts']:
            if acc['status'] == 'available':
                region = acc.get('region', '通用')
                region_count[region] = region_count.get(region, 0) + 1
        
        if region_count:
            print(f"\n  区域分布:")
            for region, count in sorted(region_count.items()):
                print(f"    - {region}: {count} 个")

    # 如果只有一个任务，默认使用1个worker
    if len(tasks) == 1 and args.workers == 3:  # 3是默认值
        args.workers = 1
        print("单任务模式，使用1个工作进程")
    
    # 确认执行
    print(f"\n配置:")
    print(f"  - 并行工作进程数: {args.workers}")
    print(f"  - 每任务最大达人数: {args.max_creators}")
    print(f"  - 数据库路径: {args.db_path}")
    
    if not args.daemon:
        response = input("\n开始执行? (Y/n): ")
        if response.lower() == 'n':
            print("已取消")
            return
    else:
        print("\n守护模式下自动开始执行任务...")
    
    # 创建任务管理器
    manager = ParallelTaskManager(
        max_workers=args.workers,
        db_path=args.db_path,
        account_pool_config=args.account_config
    )
    
    # 添加任务到执行队列...
    print("\n添加任务到执行队列...")
    task_ids = []

    required_regions = set()
    for task_config, task_file in tasks:
        # 从配置中读取区域
        try:
            # 如果有多个配置文件，从第一个读取区域
            if 'config_files' in task_config and task_config['config_files']:
                first_config = task_config['config_files'][0]['data']
                region = first_config.get('region', '').upper()
            else:
                region = task_config.get('region', '').upper()
            
            if region:
                required_regions.add(region)
        except:
            pass
    
    # 检查账号池是否有所需区域的账号
    if required_regions:
        from models.account_pool import get_account_pool
        pool = get_account_pool(args.account_config)
        status = pool.get_status()
        
        # 获取账号池中的所有区域
        available_regions = set()
        for acc in status['accounts']:
            acc_region = acc.get('region', '').upper()
            if acc_region and acc_region != 'N/A':
                available_regions.add(acc_region)
        
        # 检查是否有缺失的区域
        missing_regions = required_regions - available_regions
        
        if missing_regions:
            print("\n" + "=" * 70)
            print("❌ 错误：缺少必需的区域账号！")
            print("=" * 70)
            print(f"\n任务需要的区域: {', '.join(sorted(required_regions))}")
            print(f"账号池中的区域: {', '.join(sorted(available_regions)) if available_regions else '无'}")
            print(f"\n缺失的区域: {', '.join(sorted(missing_regions))}")
            print("\n请在 config/accounts.json 中添加以下区域的账号:")
            for region in sorted(missing_regions):
                print(f"""
  {{
    "name": "{region}_Account",
    "login_email": "your_email@gmail.com",
    "login_password": "your_password",
    "gmail_username": "your_email@gmail.com",
    "gmail_app_password": "your_app_password",
    "region": "{region}",
    "enabled": true,
    "notes": "{region}区域账号"
  }}
""")
            print("=" * 70)
            return  # 直接退出，不执行任务

    for task_config, task_file in tasks:
        # 将命令行参数添加到任务配置中
        task_config['max_calls_per_task'] = args.max_calls
        task_config['creators_per_call'] = args.creators_per_call
        task_config['max_creators_per_task'] = args.max_creators
        
        task_id = manager.add_task(task_config, task_file)
        task_ids.append(task_id)
    
    print(f"已添加 {len(task_ids)} 个任务到队列")
    
    # 运行管理器
    print("\n开始并行执行任务...")
    print("(按 Ctrl+C 可中断执行)\n")
    
    try:
        start_time = time.time()
        manager.run(daemon=args.daemon)   # ← 传递 daemon 参数
        end_time = time.time()
        
        # 只有非守护模式才打印总结并退出
        if not args.daemon:
            print_summary(manager)
            print(f"总耗时: {(end_time - start_time) / 60:.1f} 分钟")
            print("\n所有任务执行完成！")
        
    except KeyboardInterrupt:
        print("\n\n用户中断执行")
        print("正在清理资源...")
        manager.cleanup()
        print_summary(manager)
        
    except Exception as e:
        print(f"\n执行出错: {e}")
        import traceback
        traceback.print_exc()
        manager.cleanup()

if __name__ == "__main__":
    # 设置multiprocessing启动方式（Windows需要）
    if sys.platform.startswith('win'):
        mp.set_start_method('spawn', force=True)
    
    main()