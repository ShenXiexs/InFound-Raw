#!/usr/bin/env python3
"""
测试账号共享功能
"""
import time
from account_pool import get_account_pool

# 获取账号池
pool = get_account_pool("config/accounts.json")

print("=" * 60)
print("测试账号共享功能")
print("=" * 60)

# 任务1获取FR账号
print("\n[步骤1] 任务1请求FR账号...")
acc1 = pool.acquire_account_by_region("task_1", "FR")
if acc1:
    print(f"✓ 任务1获取账号: {acc1['name']}")

# 查看状态
status = pool.get_status()
print(f"\n当前状态: 可用={status['available']}, 使用中={status['in_use']}")
for acc in status['accounts']:
    if acc['region'] == 'FR':
        print(f"  FR账号: {acc['name']}, 使用数={acc['usage_count']}, 任务={acc['using_tasks']}")

# 任务2也请求FR账号（应该共享）
print("\n[步骤2] 任务2请求FR账号（应该共享）...")
acc2 = pool.acquire_account_by_region("task_2", "FR")
if acc2:
    print(f"✓ 任务2获取账号: {acc2['name']}")

# 查看状态
status = pool.get_status()
print(f"\n当前状态: 可用={status['available']}, 使用中={status['in_use']}")
for acc in status['accounts']:
    if acc['region'] == 'FR':
        print(f"  FR账号: {acc['name']}, 使用数={acc['usage_count']}, 任务={acc['using_tasks']}")

# 任务1完成，释放账号
print("\n[步骤3] 任务1完成，释放账号...")
pool.release_account(acc1['id'], "task_1")

# 查看状态
status = pool.get_status()
print(f"\n当前状态: 可用={status['available']}, 使用中={status['in_use']}")
for acc in status['accounts']:
    if acc['region'] == 'FR':
        print(f"  FR账号: {acc['name']}, 使用数={acc['usage_count']}, 任务={acc['using_tasks']}")

# 任务2完成，释放账号
print("\n[步骤4] 任务2完成，释放账号...")
pool.release_account(acc2['id'], "task_2")

# 查看状态
status = pool.get_status()
print(f"\n当前状态: 可用={status['available']}, 使用中={status['in_use']}")
for acc in status['accounts']:
    if acc['region'] == 'FR':
        print(f"  FR账号: {acc['name']}, 使用数={acc['usage_count']}, 任务={acc['using_tasks']}")

print("\n" + "=" * 60)
print("测试完成！")
print("=" * 60)