import requests
from bs4 import BeautifulSoup
import os
import re
import csv
import time
import concurrent.futures

# ==============================================================================
# 1. 配置信息
# ==============================================================================
CSV_FILENAME = "车系.csv"              # 源CSV文件名
SUCCESS_CSV_FILENAME = "车系_url.csv" # 保存成功记录（包含URL）的CSV文件名
MAX_WORKERS = 10                     # 设置线程池的最大线程数，可以根据网络情况调整

# ==============================================================================
# 2. 从CSV文件读取完整数据的函数 (此函数无需修改)
# ==============================================================================
def get_data_from_csv(filename):
    """
    从CSV文件读取表头和所有行数据。
    返回: (header, all_rows) 元组
    """
    all_rows = []
    header = []
    try:
        with open(filename, mode='r', encoding='utf-8-sig') as infile:
            reader = csv.reader(infile)
            header = next(reader, None)
            if not header:
                print(f"[错误] CSV文件 '{filename}' 为空或没有表头。")
                return None, None
            for row in reader:
                if row and row[0].strip():
                    all_rows.append(row)
    except FileNotFoundError:
        print(f"[错误] 文件未找到: '{filename}'")
        return None, None
    except Exception as e:
        print(f"[错误] 读取CSV文件时发生错误: {e}")
        return None, None
    return header, all_rows

# ==============================================================================
# 3. 核心函数 - 爬取单个URL (稍作修改以适应多线程)
# ==============================================================================
def extract_image_url(row_data):
    """
    根据单行数据中的车系ID，解析主车辆图片的URL。
    返回一个元组: (原始行数据, 解析到的URL或None)
    """
    series_id = row_data[0]
    page_url = f"https://www.dongchedi.com/auto/series/{series_id}"
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(page_url, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        image_tag = soup.find('img', {'src': re.compile(r'dcarimg\.com.*~1200x0')})

        if not image_tag:
            # 静默失败，返回None
            return row_data, None

        image_url = image_tag.get('src')
        if image_url.startswith('//'):
            image_url = 'https:' + image_url
        
        # 成功时返回解析到的URL
        return row_data, image_url

    except requests.exceptions.RequestException:
        # 网络等错误，静默失败
        return row_data, None
    except Exception:
        # 其他未知错误
        return row_data, None

# ==============================================================================
# 4. 主程序入口 (使用多线程重构)
# ==============================================================================
if __name__ == '__main__':
    start_time = time.time()

    header, all_rows = get_data_from_csv(CSV_FILENAME)

    if all_rows:
        total_series = len(all_rows)
        success_count = 0
        
        print(f"\n从 {CSV_FILENAME} 加载了 {total_series} 条数据。")
        print(f"使用 {MAX_WORKERS} 个线程开始并发处理...")
        
        # 打开文件准备写入
        with open(SUCCESS_CSV_FILENAME, 'w', newline='', encoding='utf-8-sig') as success_file:
            writer = csv.writer(success_file)
            
            # 写入新的表头
            if header:
                writer.writerow(header + ["image_url"])

            # 创建线程池
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                # 提交所有任务到线程池，executor.map会保持原始顺序
                # 将 extract_image_url 函数应用到 all_rows 列表的每一个元素上
                results = executor.map(extract_image_url, all_rows)
                
                # 按顺序处理返回的结果
                for i, (original_row, url) in enumerate(results):
                    # 打印进度
                    print(f"\r进度: {i+1}/{total_series}", end="", flush=True)

                    if url:
                        success_count += 1
                        writer.writerow(original_row + [url])

        print("\n\n" + "="*40)
        print("========== 所有任务已完成！ ==========")
        
        end_time = time.time()
        total_time = end_time - start_time
        
        print(f"总耗时: {total_time:.2f} 秒")
        print(f"总共成功解析了 {success_count} 个车系的图片URL。")
        print(f"详细列表及URL已保存至文件: {os.path.abspath(SUCCESS_CSV_FILENAME)}")
        print("="*40)