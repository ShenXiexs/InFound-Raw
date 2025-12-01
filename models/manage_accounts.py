"""
账号池管理工具
用于添加、删除、查看TikTok账号
"""
import json
import sys
from pathlib import Path
from datetime import datetime

def load_config(config_file="config/accounts.json"):
    """加载配置文件"""
    config_path = Path(config_file)
    
    if not config_path.exists():
        return {"accounts": []}
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_config(config, config_file="config/accounts.json"):
    """保存配置文件"""
    config_path = Path(config_file)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    print(f"✓ 配置已保存到: {config_file}")

def list_accounts(config_file="config/accounts.json"):
    """列出所有账号"""
    config = load_config(config_file)
    accounts = config.get('accounts', [])
    
    if not accounts:
        print("没有配置任何账号")
        return
    
    print("\n" + "=" * 70)
    print("账号列表")
    print("=" * 70)
    
    for i, account in enumerate(accounts):
        status = "启用" if account.get('enabled', True) else "✗ 禁用"
        print(f"\n[{i}] {account.get('name', f'账号{i}')} {status}")
        print(f"    登录邮箱: {account.get('login_email', 'N/A')}")
        print(f"    Gmail账号: {account.get('gmail_username', 'N/A')}")
        if account.get('notes'):
            print(f"    备注: {account['notes']}")
    
    print("\n" + "=" * 70)
    print(f"总计: {len(accounts)} 个账号")
    print("=" * 70)

def add_account(config_file="config/accounts.json"):
    """添加新账号"""
    print("\n" + "=" * 70)
    print("添加新账号")
    print("=" * 70)
    
    name = input("账号名称: ").strip()
    if not name:
        print("账号名称不能为空")
        return
    
    login_email = input("TikTok登录邮箱: ").strip()
    if not login_email:
        print("登录邮箱不能为空")
        return
    
    login_password = input("TikTok登录密码: ").strip()
    if not login_password:
        print("登录密码不能为空")
        return
    
    gmail_username = input("Gmail账号 (默认同登录邮箱): ").strip()
    if not gmail_username:
        gmail_username = login_email
    
    gmail_app_password = input("Gmail应用专用密码: ").strip()
    if not gmail_app_password:
        print("Gmail应用密码不能为空")
        return
    
    enabled = input("是否启用 (Y/n): ").strip().lower() != 'n'
    notes = input("备注 (可选): ").strip()
    
    # 加载现有配置
    config = load_config(config_file)
    
    # 添加新账号
    new_account = {
        "name": name,
        "login_email": login_email,
        "login_password": login_password,
        "gmail_username": gmail_username,
        "gmail_app_password": gmail_app_password,
        "enabled": enabled,
        "notes": notes,
        "created_at": datetime.now().isoformat()
    }
    
    config['accounts'].append(new_account)
    
    # 保存
    save_config(config, config_file)
    print(f"\n账号 '{name}' 已添加")

def remove_account(config_file="config/accounts.json"):
    """删除账号"""
    config = load_config(config_file)
    accounts = config.get('accounts', [])
    
    if not accounts:
        print("没有可删除的账号")
        return
    
    # 显示列表
    list_accounts(config_file)
    
    # 选择删除
    try:
        index = int(input("\n输入要删除的账号编号: ").strip())
        if 0 <= index < len(accounts):
            removed = accounts.pop(index)
            save_config(config, config_file)
            print(f"\n账号 '{removed.get('name')}' 已删除")
        else:
            print("无效的编号")
    except ValueError:
        print("请输入有效的数字")

def toggle_account(config_file="config/accounts.json"):
    """启用/禁用账号"""
    config = load_config(config_file)
    accounts = config.get('accounts', [])
    
    if not accounts:
        print("没有可操作的账号")
        return
    
    # 显示列表
    list_accounts(config_file)
    
    # 选择操作
    try:
        index = int(input("\n输入要切换状态的账号编号: ").strip())
        if 0 <= index < len(accounts):
            account = accounts[index]
            account['enabled'] = not account.get('enabled', True)
            save_config(config, config_file)
            
            status = "启用" if account['enabled'] else "禁用"
            print(f"\n账号 '{account.get('name')}' 已{status}")
        else:
            print("无效的编号")
    except ValueError:
        print("请输入有效的数字")

def test_account(config_file="config/accounts.json"):
    """测试账号连接"""
    config = load_config(config_file)
    accounts = config.get('accounts', [])
    
    if not accounts:
        print("没有可测试的账号")
        return
    
    list_accounts(config_file)
    
    try:
        index = int(input("\n输入要测试的账号编号: ").strip())
        if 0 <= index < len(accounts):
            account = accounts[index]
            
            print(f"\n测试账号: {account.get('name')}")
            print("(此功能需要实现具体的测试逻辑)")
            
        else:
            print("无效的编号")
    except ValueError:
        print("请输入有效的数字")

def main():
    """主菜单"""
    config_file = "config/accounts.json"
    
    # 如果有命令行参数，使用指定配置文件
    if len(sys.argv) > 1:
        config_file = sys.argv[1]
    
    print("\n" + "=" * 70)
    print("TikTok账号池管理工具")
    print("=" * 70)
    print(f"配置文件: {config_file}")
    
    while True:
        print("\n请选择操作:")
        print("  1. 查看所有账号")
        print("  2. 添加新账号")
        print("  3. 删除账号")
        print("  4. 启用/禁用账号")
        print("  5. 测试账号")
        print("  0. 退出")
        
        choice = input("\n输入选项 (0-5): ").strip()
        
        if choice == '1':
            list_accounts(config_file)
        elif choice == '2':
            add_account(config_file)
        elif choice == '3':
            remove_account(config_file)
        elif choice == '4':
            toggle_account(config_file)
        elif choice == '5':
            test_account(config_file)
        elif choice == '0':
            print("退出")
            break
        else:
            print("无效的选项")

if __name__ == "__main__":
    main()