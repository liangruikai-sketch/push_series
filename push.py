import os
import requests
import json
import pandas as pd
import random
from io import BytesIO
from google import genai
import re
from google.genai import types


APP_ID = os.environ.get('FEISHU_APP_ID')
APP_SECRET = os.environ.get('FEISHU_APP_SECRET')
CHAT_ID = os.environ.get('FEISHU_CHAT_ID')
CSV_FILE_PATH = '车系_url.csv'

SENT_IDS_PATH = 'sent_car_ids.txt'
CAR_SERIES_BASE_URL = "https://www.dongchedi.com/auto/series/"


GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')


def get_tenant_access_token(app_id, app_secret):
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    headers = {"Content-Type": "application/json"}
    body = {"app_id": app_id, "app_secret": app_secret}
    try:
        response = requests.post(url, headers=headers, json=body)
        response.raise_for_status()
        data = response.json()
        if data.get("code") == 0:
            print("获取 tenant_access_token 成功")
            return data.get("tenant_access_token")
        else:
            print(f"获取 token 失败: {data}")
            return None
    except requests.RequestException as e:
        print(f"请求 token 时发生网络错误: {e}")
        return None

def get_new_random_car_info(csv_path, sent_ids_path):
    """
    从CSV文件中读取数据，并随机选择一个之前未发送过的车系。
    返回车系名称(outter_name)、图片URL和车系ID。
    """
    try:
        # 1. 读取已发送ID列表
        if os.path.exists(sent_ids_path):
            with open(sent_ids_path, 'r') as f:
                sent_ids = {line.strip() for line in f}
            print(f"已读取 {len(sent_ids)} 个已发送的车系ID。")
        else:
            sent_ids = set()
            print("未找到已发送记录文件，将创建新文件。")

        # 2. 读取所有车系信息
        df = pd.read_csv(csv_path, dtype={'id': str}) # 确保id作为字符串读取
        if df.empty:
            print(f"错误: CSV文件 '{csv_path}' 为空。")
            return None, None, None

        # 3. 筛选出未发送的车系
        available_cars_df = df[~df['id'].isin(sent_ids)]

        if available_cars_df.empty:
            print("所有车系均已推送完毕！任务结束。")
            # 可选：如果希望重新开始，可以删除 sent_car_ids.txt 文件
            return None, None, None

        print(f"发现 {len(available_cars_df)} 个未发送的新车系。")
        
        # 4. 从可用的车系中随机选择一个
        random_row = available_cars_df.sample(n=1).iloc[0]
        car_id = random_row['id']
        car_name = random_row['outter_name']
        image_url = random_row['image_url']
        
        print(f"本次随机选中车系: {car_name} (ID: {car_id})")
        return car_name, image_url, car_id

    except FileNotFoundError:
        print(f"错误: CSV文件未找到 at '{csv_path}'")
        return None, None, None
    except KeyError as e:
        print(f"错误: CSV文件中缺少必需的列: {e}。请确保文件包含 'id', 'outter_name' 和 'image_url' 列。")
        return None, None, None
    except Exception as e:
        print(f"读取或处理CSV时发生错误: {e}")
        return None, None, None


def sanitize_feishu_markdown(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'^(#+)([^\s#])', r'\1 \2', text, flags=re.MULTILINE)
    text = re.sub(r'^([*-])([^\s])', r'\1 \2', text, flags=re.MULTILINE)
    print("Markdown文本内容已为飞书进行净化处理。")
    return text

def generate_car_description(car_name, api_key):
    print(f"开始为 '{car_name}' 生成描述...")
    try:
        prompt = (
            f"请你作为一位专业的汽车评论员，详细介绍一下“{car_name}”这个车系。"
            "请从以下几个方面展开，并使用段落组织语言:\n"
            "1. 品牌背景和车系历史\n"
            "2. 外观设计和内饰特点\n"
            "3. 动力系统和性能表现\n"
            "4. 主要的科技配置和安全功能\n"
            "5. 市场定位、主要竞争对手和目标用户群体。\n"
            "请用流畅、吸引人的语言进行描述，分段清晰，且不要在回复的开头和结尾添加任何```markdown或```标记。"
        )
        client = genai.Client(api_key=api_key)
        grounding_tool = types.Tool(
            google_search=types.GoogleSearch()
        )

        config = types.GenerateContentConfig(
            tools=[grounding_tool]
        )
        response = client.models.generate_content(
            model="gemini-2.5-pro", contents=prompt,
            config=config
        )
        cleaned_text = response.text.strip()
        print("成功从Gemini API获取并清洗描述。")
        return cleaned_text
    except Exception as e:
        print(f"调用Gemini API时发生错误: {e}")
        return None

def upload_image(token, image_url):
    try:
        print(f"开始下载图片: {image_url}")
        image_response = requests.get(image_url)
        image_response.raise_for_status()
        image_bytes = image_response.content
        print("图片下载成功。")
    except requests.RequestException as e:
        print(f"下载图片失败: {e}")
        return None

    url = "https://open.feishu.cn/open-apis/im/v1/images"
    headers = {"Authorization": f"Bearer {token}"}
    form_data = {
        'image_type': (None, 'message'),
        'image': ('image.png', BytesIO(image_bytes), 'image/png')
    }
    
    try:
        print("开始上传图片到飞书...")
        response = requests.post(url, headers=headers, files=form_data)
        response_data = response.json()
        
        if response_data.get("code") == 0:
            image_key = response_data.get("data", {}).get("image_key")
            print(f"图片上传成功, image_key: {image_key}")
            return image_key
        else:
            print(f"上传图片失败，业务错误: {response_data}")
            return None
    except requests.RequestException as e:
        print(f"上传图片时发生网络错误: {e}")
        return None

def send_message(token, chat_id, car_name, image_key, car_id, description):
    url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    car_link = f"{CAR_SERIES_BASE_URL}{car_id}"
    print(f"生成车系详情链接: {car_link}")

    card_dict = {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "green",
            "title": {"tag": "plain_text", "content": f"每日车系介绍：{car_name}"}
        },
        "elements": [
            {"tag": "img", "img_key": image_key, "alt": {"tag": "plain_text", "content": f"{car_name} 的图片"}},
            {"tag": "hr"},
            {"tag": "markdown", "content": "**以下描述由GEMINI生成（仅供参考），点击下方按钮查看详情。**"},
            {"tag": "action", "actions": [{"tag": "button", "text": {"tag": "plain_text", "content": "查看车系详情"}, "url": car_link, "type": "primary"}]},
            {"tag": "markdown", "content": description}
        ]
    }
    body = {"receive_id": chat_id, "msg_type": "interactive", "content": json.dumps(card_dict)}

    try:
        payload = json.dumps(body).encode('utf-8')
        response = requests.post(url, headers=headers, data=payload)
        response_data = response.json()
        print(f"Feishu API Response: {response_data}")
        response.raise_for_status()

        if response_data.get("code") == 0:
            print(f"向群聊 {chat_id} 发送图文消息成功")
            return True
        else:
            print(f"发送消息失败，业务错误码: {response_data.get('code')}, 错误信息: {response_data.get('msg')}")
            return False
    except requests.RequestException as e:
        print(f"发送消息时发生网络错误: {e}")
        return False

def update_sent_ids(file_path, new_id):
    """将新发送的ID追加到文件中"""
    try:
        with open(file_path, 'a') as f:
            f.write(f"{new_id}\n")
        print(f"已将ID {new_id} 添加到记录文件 {file_path} 中。")
    except Exception as e:
        print(f"更新记录文件失败: {e}")

# --- Main execution logic ---
def cronjon():
    print('------ 开始执行每日推送任务 ------')

    if not all([APP_ID, APP_SECRET, CHAT_ID, GEMINI_API_KEY]):
        print("错误: 请先设置环境变量 APP_ID, APP_SECRET, CHAT_ID, 和 GEMINI_API_KEY")
        return

    token = get_tenant_access_token(APP_ID, APP_SECRET)
    if not token:
        return

    car_name, image_url, car_id = get_new_random_car_info(CSV_FILE_PATH, SENT_IDS_PATH)
    if not all([car_name, image_url, car_id]):
        print("未能获取到新的车辆信息，任务终止。")
        return
        
    description = generate_car_description(car_name, GEMINI_API_KEY)
    if not description:
        print("生成车辆描述失败，将使用默认文本。")
        description = f"**车系介绍**\n检测到新车系 **{car_name}**，请相关同事关注。"
    else:
        description = sanitize_feishu_markdown(description)

    image_key = upload_image(token, image_url)
    if not image_key:
        print("未能上传图片，任务终止。")
        return

    # 发送消息并检查是否成功
    success = send_message(token, CHAT_ID, car_name, image_key, car_id, description)

    # 如果发送成功，则更新记录文件
    if success:
        update_sent_ids(SENT_IDS_PATH, car_id)

    print('------ 每日推送任务执行完毕 ------')


if __name__ == "__main__":
    cronjon()