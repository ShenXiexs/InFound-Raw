import pandas as pd
import re
from datetime import datetime
import os
import argparse

def extract_email_from_text(text):
    """
    从文本中提取邮箱地址
    """
    if pd.isna(text) or not isinstance(text, str):
        return None
    
    # 邮箱正则表达式
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(email_pattern, text)
    
    # 返回找到的第一个邮箱，如果没有找到则返回None
    return emails[0] if emails else None

def process_creator_data(region_filter='ALL'):
    """
    处理creator数据文件
    
    参数:
        region_filter: 区域过滤器，可选值为 'ALL', 'MX', 'FR'
    """
    # 定义文件路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    
    input_file = os.path.join(parent_dir, 'data', 'creator_GOKOCO.MX.xlsx')
    
    # 生成输出文件名，包含操作时间和区域过滤器
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = os.path.join(parent_dir, 'data', f'creator_email_{region_filter}_{timestamp}.xlsx')
    
    try:
        # 读取Excel文件
        print(f"正在读取文件: {input_file}")
        df = pd.read_excel(input_file)
        
        print(f"原始数据行数: {len(df)}")
        
        # 根据region参数过滤数据
        if region_filter.upper() != 'ALL':
            if 'region' in df.columns:
                original_count = len(df)
                df = df[df['region'] == region_filter.upper()].copy()
                filtered_count = len(df)
                print(f"根据region={region_filter.upper()}过滤: {original_count} -> {filtered_count} 行")
            else:
                print("警告: region列不存在，无法进行过滤")
        
        # 检查所需列是否存在
        required_columns = ['region', 'creator_name', 'followers', 'intro', 'brand_name', 'whatsapp', 'email', 'creator_chaturl']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            print(f"警告: 以下列在文件中不存在: {missing_columns}")
            print(f"可用的列: {list(df.columns)}")
        
        # 提取指定的列（只提取存在的列）
        available_columns = [col for col in required_columns if col in df.columns]
        df_extracted = df[available_columns].copy()
        
        # 从intro列中提取邮箱
        print("正在从intro列提取邮箱...")
        if 'intro' in df_extracted.columns:
            df_extracted['email_extracted'] = df_extracted['intro'].apply(extract_email_from_text)
            
            # 统计提取到邮箱的数量
            extracted_count = df_extracted['email_extracted'].notna().sum()
            print(f"从intro列中提取到 {extracted_count} 个邮箱地址")
        else:
            print("警告: intro列不存在，跳过邮箱提取")
        
        # 根据creator_name去重，保留最后一行
        if 'creator_name' in df_extracted.columns:
            original_count = len(df_extracted)
            df_extracted = df_extracted.drop_duplicates(subset=['creator_name'], keep='last')
            deduplicated_count = len(df_extracted)
            removed_count = original_count - deduplicated_count
            print(f"根据creator_name去重: {original_count} -> {deduplicated_count} 行 (移除了 {removed_count} 个重复项)")
        else:
            print("警告: creator_name列不存在，跳过去重")
        
        # 保存到新的Excel文件
        print(f"正在保存文件: {output_file}")
        df_extracted.to_excel(output_file, index=False)
        
        print(f"\n处理完成！")
        print(f"区域过滤器: {region_filter.upper()}")
        print(f"最终保存了 {len(df_extracted)} 行数据")
        print(f"输出文件: {output_file}")
        
        return output_file
        
    except FileNotFoundError:
        print(f"错误: 找不到输入文件 {input_file}")
        print(f"请确保文件存在于正确的路径")
        return None
    except Exception as e:
        print(f"处理过程中出现错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='处理Creator数据并提取邮箱信息')
    parser.add_argument(
        'region',
        nargs='?',
        default='ALL',
        choices=['ALL', 'MX', 'FR', 'all', 'mx', 'fr'],
        help='选择要处理的区域: ALL (所有区域), MX (墨西哥), FR (法国)'
    )
    
    args = parser.parse_args()
    
    # 转换为大写
    region_filter = args.region.upper()
    
    print(f"=== Creator邮箱数据处理工具 ===")
    print(f"选择的区域: {region_filter}")
    print(f"{'='*40}\n")
    
    process_creator_data(region_filter)

# 处理所有区域
# python data_process/email_process.py ALL

# 只处理墨西哥(MX)区域
# python data_process/email_process.py MX

# 只处理法国(FR)区域
# python data_process/email_process.py FR

# 不指定参数，默认为ALL
# python data_process/email_process.py