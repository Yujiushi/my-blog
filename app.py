import os
import json
import yaml
import markdown
import requests
import os
import sys
from flask import Flask, render_template, jsonify, send_from_directory, abort, request
from datetime import datetime
from flask import Flask, render_template_string
import jinja2
import shutil

app = Flask(__name__)

# 导入必要的库
import time

# 读取配置文件
config = None

def load_config():
    global config
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        # 如果config.json不存在，尝试从default文件夹复制
        default_config_path = os.path.join('default', 'default_config.json')
        if os.path.exists(default_config_path):
            print(f"config.json不存在，从{default_config_path}复制默认配置")
            shutil.copy2(default_config_path, 'config.json')
            # 读取复制过来的配置
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 同时检查background.jpg是否存在，如果不存在也从default文件夹复制
            if 'background' in config and 'image' in config['background']:
                background_image = config['background']['image']
                if not os.path.exists(background_image) and os.path.exists(os.path.join('default', background_image)):
                    print(f"{background_image}不存在，从default文件夹复制")
                    shutil.copy2(os.path.join('default', background_image), background_image)
        else:
            # 如果default_config.json也不存在，使用内置默认配置
            print("default/default_config.json不存在，使用内置默认配置")
            config = {
                "github_url": "https://github.com/example",
                "dark_mode": "auto",
                "name": "Example User",
                "bio": "Python Developer",
                "introduction_file": "Introduction.md",
                "github_token": "",  # 添加GitHub令牌配置项
                "theme": {
                    "primary_color": "#6a11cb",
                    "secondary_color": "#2575fc"
                },
                "background": {
                    "image": "background.png",
                    "blur": 8,
                    "overlay_opacity": 0.6,
                    "overlay_color": "#121212"
                }
            }
            # 保存默认配置
            with open('config.json', 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

load_config()

# ===== 笔记库 =====
NOTES_CATEGORY_ORDER = ["life", "academic", "career"]

def load_notes_manifest():
    notes_path = os.path.join(os.getcwd(), "notes.json")
    if not os.path.exists(notes_path):
        return {"categories": {}}
    with open(notes_path, "r", encoding="utf-8") as f:
        return json.load(f)

def count_note_items(children):
    if not children:
        return 0
    total = 0
    for item in children:
        if item.get("type") == "folder":
            total += 1 + count_note_items(item.get("children", []))
        elif item.get("type") == "page":
            total += 1
    return total

def get_notes_summary():
    manifest = load_notes_manifest()
    categories = manifest.get("categories", {})
    summary = []
    total_pages = 0
    last_date = ""

    for key in NOTES_CATEGORY_ORDER:
        cat = categories.get(key)
        if not cat:
            continue
        count = count_note_items(cat.get("children", []))

        def walk_pages(children):
            nonlocal total_pages, last_date
            for item in children or []:
                if item.get("type") == "page":
                    total_pages += 1
                    d = item.get("date", "")
                    if d > last_date:
                        last_date = d
                elif item.get("type") == "folder":
                    walk_pages(item.get("children", []))

        walk_pages(cat.get("children", []))
        summary.append({
            "id": key,
            "label": cat.get("label", key),
            "emoji": cat.get("emoji", "📁"),
            "desc": cat.get("desc", ""),
            "count": count,
            "browse_url": f"/browse?c={key}",
        })

    return {
        "categories": summary,
        "total_pages": total_pages,
        "last_updated": last_date,
    }

AVATAR_DIR = os.path.join(os.getcwd(), 'static', 'avatars')
BACKGROUND_DIR = os.path.join(os.getcwd(), 'static', 'backgrounds')
DEFAULT_BACKGROUND_SRC = os.path.join('default', 'background.jpg')
DEFAULT_BACKGROUND_IMAGE = 'background.jpg'
ALLOWED_AVATAR_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
ALLOWED_BACKGROUND_EXT = ALLOWED_AVATAR_EXT

def save_config_file():
    with open('config.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def get_notes_repo_config():
    notes_cfg = config.get('notes', {})
    return {
        'owner': notes_cfg.get('github_owner', ''),
        'repo': notes_cfg.get('github_repo', ''),
        'branch': notes_cfg.get('github_branch', 'main'),
    }

def get_request_github_token():
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        return auth[7:].strip()
    return request.form.get('github_token', '').strip()

def verify_github_write_access(token):
    if not token:
        return False, '请先在 ⚙️ 中配置 GitHub Token'

    repo_cfg = get_notes_repo_config()
    owner = repo_cfg['owner']
    repo = repo_cfg['repo']
    if not owner or not repo:
        return False, '未配置笔记仓库信息'

    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }
    try:
        response = requests.get(
            f'https://api.github.com/repos/{owner}/{repo}',
            headers=headers,
            timeout=10,
            verify=False,
        )
    except requests.RequestException:
        return False, '无法连接 GitHub，请稍后重试'

    if response.status_code == 401:
        return False, 'Token 无效或已过期'
    if response.status_code == 404:
        return False, '无法访问该仓库，请检查 Token 权限'
    if response.status_code != 200:
        return False, 'Token 验证失败'

    perms = response.json().get('permissions', {})
    if perms.get('push') or perms.get('admin'):
        return True, None
    if perms.get('contents') in ('write', 'admin'):
        return True, None

    return False, 'Token 没有写入权限'

def check_edit_permission():
    ok, error = verify_github_write_access(get_request_github_token())
    if not ok:
        return jsonify({'error': error}), 403
    return None

def get_avatar_url():
    avatar = config.get('avatar', '')
    if avatar:
        if avatar.startswith('http'):
            return avatar
        if avatar.startswith('/'):
            rel = avatar.lstrip('/').replace('/', os.sep)
            if os.path.exists(os.path.join(os.getcwd(), rel)):
                return avatar
    os.makedirs(AVATAR_DIR, exist_ok=True)
    for name in ['avatar.jpg', 'avatar.jpeg', 'avatar.png', 'avatar.webp', 'avatar.gif', 'default.svg']:
        if os.path.exists(os.path.join(AVATAR_DIR, name)):
            return f'/static/avatars/{name}'
    return '/static/avatars/default.svg'

def get_background_info():
    """返回背景图是否存在及用于模板的 URL 路径。"""
    image = config.get('background', {}).get('image', '')

    if image:
        if image.startswith('http'):
            return {'exists': True, 'path': image}
        if image.startswith('/'):
            rel = image.lstrip('/').replace('/', os.sep)
            if os.path.exists(os.path.join(os.getcwd(), rel)):
                return {'exists': True, 'path': image}

    for legacy in ('background.jpg', 'background.png'):
        root_path = os.path.join(os.getcwd(), legacy)
        if os.path.exists(root_path):
            return {'exists': True, 'path': legacy}
        static_path = os.path.join(os.getcwd(), 'static', legacy)
        if os.path.exists(static_path):
            return {'exists': True, 'path': f'/static/{legacy}'}

    os.makedirs(BACKGROUND_DIR, exist_ok=True)
    for name in ('background.jpg', 'background.jpeg', 'background.png', 'background.webp', 'background.gif'):
        if os.path.exists(os.path.join(BACKGROUND_DIR, name)):
            return {'exists': True, 'path': f'/static/backgrounds/{name}'}

    return {'exists': False, 'path': ''}

def clear_uploaded_backgrounds():
    if not os.path.isdir(BACKGROUND_DIR):
        return
    for old in os.listdir(BACKGROUND_DIR):
        if old.startswith('background.'):
            try:
                os.remove(os.path.join(BACKGROUND_DIR, old))
            except OSError:
                pass

def restore_default_background():
    """恢复为项目自带的默认背景图。"""
    global config
    default_src = os.path.join(os.getcwd(), DEFAULT_BACKGROUND_SRC)
    if not os.path.exists(default_src):
        return None, '未找到默认背景图'

    shutil.copy2(default_src, os.path.join(os.getcwd(), DEFAULT_BACKGROUND_IMAGE))
    clear_uploaded_backgrounds()

    if 'background' not in config:
        config['background'] = {}
    config['background']['image'] = DEFAULT_BACKGROUND_IMAGE
    save_config_file()
    return DEFAULT_BACKGROUND_IMAGE, None

def get_display_profile():
    """使用 config.json 中的中文虚拟资料展示主页，不依赖 GitHub API。"""
    notes = get_notes_summary()
    stats = config.get('profile_stats', {})
    return {
        "avatar_url": get_avatar_url(),
        "name": config.get('name', '访客'),
        "bio": config.get('bio', '记录生活点滴'),
        "total_repos": notes['total_pages'],
        "total_repos_label": stats.get('stat1_label', '笔记数量'),
        "total_stars": len(NOTES_CATEGORY_ORDER),
        "total_stars_label": stats.get('stat2_label', '学习主题'),
        "readme_content": get_local_readme(),
        "activity_data": config.get(
            'activity_data',
            [12, 19, 8, 15, 22, 18, 25, 20, 14, 28, 16, 21],
        ),
        "tech_stack": config.get('tech_stack', [
            {"name": "阅读", "color": "#6a11cb"},
            {"name": "写作", "color": "#2575fc"},
            {"name": "Python", "color": "#560bad"},
            {"name": "笔记整理", "color": "#1e40af"},
        ]),
        "recent_repos": [],
    }

# 创建通用的GitHub API请求函数
def make_github_request(url, timeout=5):
    try:
        # 配置requests不验证SSL证书（解决本地环境中的证书验证问题）
        import ssl
        ssl._create_default_https_context = ssl._create_unverified_context
        
        # 准备请求头
        headers = {'Accept': 'application/vnd.github.v3+json'}
        github_token = ''
        
        # 首先尝试从github_token.txt文件中读取令牌
        token_file = os.path.join(app.root_path, 'github_token.txt')
        try:
            if os.path.exists(token_file):
                with open(token_file, 'r', encoding='utf-8') as f:
                    github_token = f.read().strip()
                # 移除可能的空白字符和引号
                github_token = github_token.replace('"', '').replace("'", '')
                print(f"从github_token.txt文件中读取令牌成功")
            else:
                # 如果文件不存在，尝试从配置中获取
                github_token = config.get('github_token', '')
                print("github_token.txt文件不存在，尝试从配置中获取令牌")
        except Exception as e:
            print(f"读取GitHub令牌时出错: {e}")
            # 出错时，尝试从配置中获取
            github_token = config.get('github_token', '')
        
        # 如果配置了GitHub令牌，添加到请求头
        if github_token:
            headers['Authorization'] = f'token {github_token}'
            print(f"使用GitHub令牌进行认证")
        else:
            print("未使用GitHub令牌，使用匿名访问")
        
        # 发送请求
        response = requests.get(url, headers=headers, timeout=timeout, verify=False)
        print(f"GitHub API请求: {url}, 状态码: {response.status_code}")
        
        # 检查是否达到速率限制
        if response.status_code == 403 and 'rate limit' in response.text.lower():
            print("GitHub API速率限制已达，建议配置GitHub令牌")
        
        return response
    except Exception as e:
        print(f"GitHub API请求异常: {e}")
        # 创建一个模拟的响应对象
        class MockResponse:
            def __init__(self):
                self.status_code = 500
                self.text = "模拟错误响应"
        return MockResponse()

# 从 GitHub API 获取用户信息
def get_github_user_info():
    print("开始获取GitHub用户信息")
    github_url = config.get('github_url', 'https://github.com/example')
    username = github_url.rstrip('/').split('/')[-1]
    print(f"配置的GitHub URL: {github_url}")
    print(f"提取的用户名: {username}")

    try:
        print(f"准备请求GitHub API: https://api.github.com/users/{username}")
        
        # 获取用户信息
        user_response = make_github_request(f'https://api.github.com/users/{username}')
        print(f"GitHub API响应状态码: {user_response.status_code}")

        if user_response.status_code == 200:
            user_data = user_response.json()
            print(f"成功获取用户数据: {user_data.get('name')}, {user_data.get('login')}")

            # 获取用户的仓库信息
            repos_response = make_github_request(f'https://api.github.com/users/{username}/repos?sort=pushed&per_page=100')
            if repos_response.status_code == 200:
                repos = repos_response.json()

                # 获取总仓库数和总 stars 数
                total_repos = len(repos)
                total_stars = sum(repo.get('stargazers_count', 0) for repo in repos)

                # 获取同名仓库的 README
                readme_content = get_readme_content(username)

                # 获取最近有推送的 5 个仓库
                recent_repos = sorted(repos, key=lambda x: x.get('pushed_at', ''), reverse=True)[:5]

                # 获取用户的活动数据（过去12个月的提交统计）
                # 传递已获取的repos参数，避免重复获取
                activity_data = get_github_activity_data(username, repos)

                # 分析用户的技术栈
                tech_stack = analyze_tech_stack(repos)

                return {
                    "avatar_url": user_data.get('avatar_url'),
                    "name": user_data.get('name') or username,
                    "bio": config.get('bio', 'Python Developer'),  # 使用配置文件中的bio
                    "total_repos": total_repos,
                    "total_stars": total_stars,
                    "readme_content": readme_content,
                    "recent_repos": recent_repos,
                    "activity_data": activity_data,
                    "tech_stack": tech_stack
                }
    except Exception as e:
        print(f"GitHub API调用异常: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
    
    # 如果获取失败，返回默认值
    return {
        "avatar_url": "https://avatars.githubusercontent.com/u/1000000?v=4",
        "name": config.get('name', 'Example User'),
        "bio": config.get('bio', 'Python Developer'),
        "total_repos": 0,
        "total_stars": 0,
        "readme_content": get_local_readme(),
        "recent_repos": [],
        "activity_data": [65, 59, 80, 81, 56, 55, 70, 65, 85, 75, 60, 75],  # 默认数据
        "tech_stack": [
            {"name": "Python", "color": "#6a11cb"},
            {"name": "JavaScript", "color": "#2575fc"},
            {"name": "HTML/CSS", "color": "#560bad"},
            {"name": "Flask", "color": "#1e40af"}
        ]
    }

# 获取用户的GitHub活动数据（过去12个月的推送统计）
# 使用GitHub Events API获取更准确的活动数据
# 确保数据按正确的月份顺序显示
import calendar
def get_github_activity_data(username, repos=None):
    try:
        print(f"开始获取GitHub活动数据: {username}")
        
        # 创建一个过去12个月的计数器，索引0表示当前月份，索引11表示11个月前
        from datetime import datetime, timedelta
        now = datetime.now()
        activity_counts = [0] * 12  # 初始化过去12个月的计数
        
        # 计算过去12个月的开始日期（12个月前的今天）
        # 注意：GitHub Events API返回的事件是按时间倒序排列的
        earliest_date = now - timedelta(days=365)  # 过去一年的日期
        
        # 1. 首先尝试通过用户Events API获取PushEvent数据
        page = 1
        max_pages = 5  # 限制获取的页数，避免过多API调用
        event_found = False
        
        while page <= max_pages:
            events_url = f"https://api.github.com/users/{username}/events?page={page}&per_page=100"
            events_response = make_github_request(events_url)
            
            if events_response.status_code != 200:
                print(f"无法获取事件数据，状态码: {events_response.status_code}")
                break
            
            events = events_response.json()
            
            if not events:
                break  # 没有更多事件了
            
            # 处理每个事件
            page_has_recent_events = False
            for event in events:
                # 只处理PushEvent类型的事件
                if event['type'] == 'PushEvent':
                    event_found = True
                    # 获取事件发生时间
                    event_date_str = event['created_at']
                    event_date = datetime.strptime(event_date_str, '%Y-%m-%dT%H:%M:%SZ')
                    
                    # 检查事件是否在过去12个月内
                    if event_date >= earliest_date:
                        page_has_recent_events = True
                        # 计算这个事件是多少个月前的
                        # 精确计算月份差异，考虑日期
                        years_diff = now.year - event_date.year
                        months_diff = now.month - event_date.month
                        
                        # 如果当前日期小于事件日期的日期部分，需要调整
                        if now.day < event_date.day:
                            months_diff -= 1
                            if months_diff < 0:
                                years_diff -= 1
                                months_diff = 11
                        
                        total_months_diff = years_diff * 12 + months_diff
                        
                        # 确保在0-11范围内
                        if 0 <= total_months_diff < 12:
                            # 增加这个月的推送次数
                            activity_counts[total_months_diff] += 1
            
            # 如果当前页没有最近事件，可能是因为已经获取了足够旧的数据
            # 但继续获取下一页以确保覆盖所有可能的事件
            page += 1
        
        # 2. 如果通过Events API没有获取到足够的数据，使用仓库提交历史作为补充
        # 这里改进：无论Events API获取了多少数据，都用仓库数据作为补充，以确保完整性
        if repos and len(repos) > 0:
            print("使用仓库提交历史作为补充数据")
            
            # 限制处理的仓库数量
            if len(repos) > 5:
                repos = repos[:5]
            
            for repo in repos:
                try:
                    # 获取仓库的提交历史（限制为最近100个提交）
                    commits_url = f"https://api.github.com/repos/{username}/{repo['name']}/commits?author={username}&per_page=100"
                    commits_response = make_github_request(commits_url)
                    
                    if commits_response.status_code == 200:
                        commits = commits_response.json()
                        
                        # 计算每个月的提交数量
                        for commit in commits:
                            commit_date_str = commit['commit']['author']['date']
                            commit_date = datetime.strptime(commit_date_str, '%Y-%m-%dT%H:%M:%SZ')
                            
                            # 检查提交是否在过去12个月内
                            if commit_date >= earliest_date:
                                # 计算这个提交是多少个月前的
                                years_diff = now.year - commit_date.year
                                months_diff = now.month - commit_date.month
                                
                                # 如果当前日期小于提交日期的日期部分，需要调整
                                if now.day < commit_date.day:
                                    months_diff -= 1
                                    if months_diff < 0:
                                        years_diff -= 1
                                        months_diff = 11
                                
                                total_months_diff = years_diff * 12 + months_diff
                                
                                # 确保在0-11范围内
                                if 0 <= total_months_diff < 12:
                                    # 增加这个月的提交计数（不考虑是否已有Events数据）
                                    activity_counts[total_months_diff] += 1
                except Exception as e:
                    print(f"获取仓库 {repo['name']} 的提交历史时出错: {e}")
                    continue
        
        # 3. 调整数据顺序，使其与图表标签顺序一致
        # 图表通常期望数据从最旧的月份到最新的月份显示
        # 但为了确保顺序与UI期望一致，我们需要确认月份顺序的逻辑
        
        # 创建一个新的数组，按照从最早到最近的顺序排列（从12个月前到当前月）
        # 例如，如果现在是10月，那么顺序应该是：10月(去年)、11月(去年)、12月(去年)、1月、2月...9月、10月(今年)
        ordered_activity = []
        current_month = now.month
        
        for i in range(12):
            # 计算当前需要取的月份索引
            # 从当前月的上个月开始，往前推11个月
            # 例如，当前是10月(索引9)，那么顺序是: 9, 8, 7, 6, 5, 4, 3, 2, 1, 0, 11, 10
            # 这样ordered_activity[0]就是最旧的数据，ordered_activity[11]是最新的数据
            month_index = (now.month - 1 - i) % 12
            ordered_activity.append(activity_counts[month_index])
        
        # 反转数组，使ordered_activity[0]是最旧的月份，ordered_activity[11]是最新的月份
        ordered_activity = ordered_activity[::-1]
        
        # 4. 确保数据合理性
        if sum(ordered_activity) == 0:
            print("没有获取到活动数据，返回默认数据")
            return [65, 59, 80, 81, 56, 55, 70, 65, 85, 75, 60, 75]  # 默认数据
        
        # 5. 对数据进行平滑处理，但保持数据的真实性
        # 只在数据波动较大时进行轻微平滑
        smoothed_data = []
        for i in range(12):
            # 简单的移动平均，但保留原始数据的相对大小
            values = [ordered_activity[i]]
            if i > 0:
                values.append(ordered_activity[i-1])
            if i < 11:
                values.append(ordered_activity[i+1])
            
            # 计算平均值，但确保不小于最小值的80%
            avg_value = int(sum(values) / len(values))
            min_value = min(values)
            smoothed_data.append(max(avg_value, int(min_value * 0.8)))
        
        # 6. 限制最大值，避免图表比例失调
        max_value = max(smoothed_data)
        if max_value > 200:
            # 只对特别大的值进行缩放
            scaled_data = []
            for v in smoothed_data:
                if v > 200:
                    scaled_data.append(int(v * 200 / max_value))
                else:
                    scaled_data.append(v)
            return scaled_data
        
        return smoothed_data
    except Exception as e:
        print(f"获取GitHub活动数据异常: {e}")
    
    # 如果发生任何错误，返回默认数据
    return [65, 59, 80, 81, 56, 55, 70, 65, 85, 75, 60, 75]  # 默认数据

# 分析用户的技术栈
# 限制处理的仓库数量，优化性能
cached_tech_stack = None
cached_timestamp = 0

CACHE_DURATION = 3600  # 缓存1小时
def analyze_tech_stack(repos):
    global cached_tech_stack, cached_timestamp
    
    # 检查缓存是否有效（如果启用了缓存）
    current_time = time.time()
    if cached_tech_stack and (current_time - cached_timestamp < CACHE_DURATION):
        print("使用缓存的技术栈数据")
        return cached_tech_stack
    
    try:
        print("开始分析用户的技术栈")
        
        # 创建语言统计字典
        language_stats = {}
        total_bytes = 0
        
        # 限制处理的仓库数量，只处理最近活跃的前10个仓库
        if len(repos) > 10:
            repos = repos[:10]
        
        # 遍历仓库，统计语言使用情况
        for repo in repos:
            # 获取仓库的语言信息（先尝试从仓库数据中获取，减少API调用）
            if 'language' in repo and repo['language']:
                lang = repo['language']
                if lang not in language_stats:
                    language_stats[lang] = 1  # 给主要语言一个基础分
                else:
                    language_stats[lang] += 1  # 增加主要语言的权重
                    
            # 仅对前几个重要的仓库进行详细的语言统计
            if len(language_stats) < 5 and 'languages_url' in repo:
                try:
                    languages_response = make_github_request(repo['languages_url'])
                    
                    if languages_response.status_code == 200:
                        languages_data = languages_response.json()
                        
                        # 更新语言统计
                        for lang, bytes_count in languages_data.items():
                            if lang not in language_stats:
                                language_stats[lang] = 0
                            language_stats[lang] += bytes_count
                            total_bytes += bytes_count
                except Exception as e:
                    print(f"获取仓库 {repo['name']} 的语言信息时出错: {e}")
                    continue
            

        
        # 如果没有获取到语言数据，返回默认技术栈
        if not language_stats:
            print("没有获取到语言数据，返回默认技术栈")
            # 更新缓存
            cached_tech_stack = [
                {"name": "Python", "color": "#6a11cb"},
                {"name": "JavaScript", "color": "#2575fc"},
                {"name": "HTML/CSS", "color": "#560bad"},
                {"name": "Flask", "color": "#1e40af"}
            ]
            cached_timestamp = time.time()
            return cached_tech_stack
        
        # 计算每种语言的使用比例
        language_ratios = {}
        for lang, bytes_count in language_stats.items():
            # 考虑仓库数量和代码量的权重
            language_ratios[lang] = bytes_count
        
        # 按使用比例排序，取前10种语言
        sorted_languages = sorted(language_ratios.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # 获取配置中的主题色
        from flask import current_app
        theme = current_app.config.get('theme', {
            'primary_color': '#6a11cb',
            'secondary_color': '#2575fc',
            'dark_primary_color': '#a855f7',
            'dark_secondary_color': '#60a5fa'
        })
        
        # 根据主题色生成和谐的标签颜色
        def generate_harmonious_color(base_color, index, is_dark=False):
            # 简单的颜色变体生成算法
            # 将HEX颜色转换为RGB
            hex_color = base_color.lstrip('#')
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            
            # 根据索引调整颜色亮度和饱和度
            factor = 1.0 - (index * 0.15)  # 递减因子
            if factor < 0.4:
                factor = 0.4  # 确保颜色不会太暗
                
            # 考虑暗色模式调整
            if is_dark:
                # 在暗色模式下，使用较亮的颜色变体
                factor = 0.6 + (index * 0.1)  # 递增因子，确保至少有一定亮度
                if factor > 0.9:
                    factor = 0.9  # 避免颜色过亮
            
            # 应用调整
            r = int(r * factor)
            g = int(g * factor)
            b = int(b * factor)
            
            # 转换回HEX
            return f'#{r:02x}{g:02x}{b:02x}'
        
        # 检查是否为暗色模式
        is_dark = current_app.config.get('dark_mode', 'auto') == 'dark'
        if is_dark:
            base_colors = [theme['dark_primary_color'], theme['dark_secondary_color']]
        else:
            base_colors = [theme['primary_color'], theme['secondary_color']]
        color_map = {
            'Python': generate_harmonious_color(base_colors[0], 0, is_dark),
            'JavaScript': generate_harmonious_color(base_colors[1], 0, is_dark),
            'Java': generate_harmonious_color(base_colors[0], 1, is_dark),
            'TypeScript': generate_harmonious_color(base_colors[1], 1, is_dark),
            'Go': generate_harmonious_color(base_colors[0], 2, is_dark),
            'Rust': generate_harmonious_color(base_colors[1], 2, is_dark),
            'PHP': generate_harmonious_color(base_colors[0], 3, is_dark),
            'C++': generate_harmonious_color(base_colors[1], 3, is_dark),
            'C': generate_harmonious_color(base_colors[0], 4, is_dark),
            'C#': generate_harmonious_color(base_colors[1], 4, is_dark),
            'Ruby': generate_harmonious_color(base_colors[0], 5, is_dark),
            'Swift': generate_harmonious_color(base_colors[1], 5, is_dark),
            'Kotlin': generate_harmonious_color(base_colors[0], 6, is_dark),
            'HTML': generate_harmonious_color(base_colors[1], 6, is_dark),
            'CSS': generate_harmonious_color(base_colors[0], 7, is_dark),
            'SCSS': generate_harmonious_color(base_colors[1], 7, is_dark),
            'Less': generate_harmonious_color(base_colors[0], 8, is_dark),
            'Flask': generate_harmonious_color(base_colors[1], 8, is_dark),
            'Django': generate_harmonious_color(base_colors[0], 9, is_dark),
            'React': generate_harmonious_color(base_colors[1], 9, is_dark),
            'Vue': generate_harmonious_color(base_colors[0], 10, is_dark),
            'Angular': generate_harmonious_color(base_colors[1], 10, is_dark),
            'Node.js': generate_harmonious_color(base_colors[0], 11, is_dark)
        }
        
        # 创建技术栈列表
        tech_stack = []
        for lang, _ in sorted_languages:
            # 特殊处理HTML和CSS，合并为HTML/CSS
            if lang == 'HTML' or lang == 'CSS':
                # 检查是否已经添加了HTML/CSS
                html_css_exists = False
                for tech in tech_stack:
                    if tech['name'] == 'HTML/CSS':
                        html_css_exists = True
                        break
                if not html_css_exists:
                    tech_stack.append({
                        "name": "HTML/CSS",
                        "color": color_map.get('HTML', 'orange')
                    })
            else:
                # 添加其他语言
                tech_stack.append({
                    "name": lang,
                    "color": color_map.get(lang, 'gray')  # 默认灰色
                })
        
        # 如果没有HTML/CSS但有SCSS或Less等，也添加HTML/CSS
        html_css_exists = False
        for tech in tech_stack:
            if tech['name'] == 'HTML/CSS':
                html_css_exists = True
                break
        
        if not html_css_exists:
            for lang, _ in sorted_languages:
                if lang in ['SCSS', 'Less', 'Sass']:
                    tech_stack.append({
                        "name": "HTML/CSS",
                        "color": color_map.get('HTML', 'orange')
                    })
                    break
        
        # 确保返回的技术栈不超过10个
        if len(tech_stack) > 10:
            tech_stack = tech_stack[:10]
        
        # 更新缓存
        cached_tech_stack = tech_stack
        cached_timestamp = time.time()
        
        print(f"分析完成的技术栈: {[tech['name'] for tech in tech_stack]}")
        return tech_stack
    except Exception as e:
        print(f"分析技术栈时发生异常: {e}")
        # 发生错误时返回默认技术栈
        return [
            {"name": "Python", "color": "blue"},
            {"name": "JavaScript", "color": "yellow"},
            {"name": "HTML/CSS", "color": "orange"},
            {"name": "Flask", "color": "green"}
        ]

# 获取同名仓库的 README","}]}}}
def get_readme_content(username):
    try:
        print(f"尝试获取GitHub同名仓库README: {username}/{username}")
        # 配置requests不验证SSL证书（解决本地环境中的证书验证问题）
        import ssl
        ssl._create_default_https_context = ssl._create_unverified_context
        
        # 尝试获取同名仓库的 README（main分支）
        readme_url_main = f'https://raw.githubusercontent.com/{username}/{username}/main/README.md'
        print(f"尝试获取README URL (main): {readme_url_main}")
        readme_response = requests.get(readme_url_main, timeout=5, verify=False)
        print(f"README响应状态码 (main): {readme_response.status_code}")
        
        if readme_response.status_code == 200:
            print("成功获取main分支的README")
            # 将 Markdown 转换为 HTML 使用扩展
            return markdown.markdown(
                readme_response.text,
                extensions=['extra', 'codehilite', 'toc', 'tables', 'md_in_html'],
                extension_configs={
                    'codehilite': {
                        'css_class': 'highlight',
                        'linenums': False
                    }
                }
            )
        
        # 尝试其他分支（master）
        readme_url_master = f'https://raw.githubusercontent.com/{username}/{username}/master/README.md'
        print(f"尝试获取README URL (master): {readme_url_master}")
        readme_response = requests.get(readme_url_master, timeout=5, verify=False)
        print(f"README响应状态码 (master): {readme_response.status_code}")
        
        if readme_response.status_code == 200:
            print("成功获取master分支的README")
            return markdown.markdown(
                readme_response.text,
                extensions=['extra', 'codehilite', 'toc', 'tables', 'md_in_html'],
                extension_configs={
                    'codehilite': {
                        'css_class': 'highlight',
                        'linenums': False
                    }
                }
            )
        
        print(f"GitHub README获取失败，状态码: {readme_response.status_code}")
    except Exception as e:
        print(f"GitHub README获取异常: {type(e).__name__}: {str(e)}")
    
    # 如果获取失败，读取本地文件
    print("使用本地README文件")
    return get_local_readme()

# 读取本地 README 文件
def get_local_readme():
    try:
        introduction_file = config.get('introduction_file', 'Introduction.md')
        if os.path.exists(introduction_file):
            with open(introduction_file, 'r', encoding='utf-8') as f:
                # 使用多个扩展来增强 Markdown 转换
                md_text = f.read()
                return markdown.markdown(
                    md_text,
                    extensions=['extra', 'codehilite', 'toc', 'tables', 'md_in_html'],
                    extension_configs={
                        'codehilite': {
                            'css_class': 'highlight',
                            'linenums': False
                        }
                    }
                )
    except Exception:
        pass
    
    # 如果都没有，返回默认信息
    return "<p>这个人很懒，什么都没有留下～ 可以在 Introduction.md 中编写个人介绍。</p>"

@app.route('/')
def index():
    if config.get('use_local_profile', True):
        github_info = get_display_profile()
    else:
        github_info = get_github_user_info()
        github_info['avatar_url'] = get_avatar_url()
        github_info.setdefault('total_repos_label', '总仓库数')
        github_info.setdefault('total_stars_label', '总 Stars')
    
    # 检查背景图片是否存在
    bg = get_background_info()
    notes_cfg = config.get('notes', {})
    
    return render_template('index.html', 
                          github_info=github_info, 
                          config=config,
                          notes_info=get_notes_summary(),
                          now=datetime.now(),
                          background_exists=bg['exists'],
                          background_path=bg['path'],
                          notes_repo={
                              'owner': notes_cfg.get('github_owner', 'Yujiushi'),
                              'repo': notes_cfg.get('github_repo', 'my-note-website'),
                              'branch': notes_cfg.get('github_branch', 'main'),
                          })

@app.route('/browse')
def browse_notes():
    bg = get_background_info()
    notes_cfg = config.get('notes', {})
    return render_template(
        'browse.html',
        config=config,
        background_exists=bg['exists'],
        background_path=bg['path'],
        notes_repo={
            'owner': notes_cfg.get('github_owner', 'Yujiushi'),
            'repo': notes_cfg.get('github_repo', 'my-note-website'),
            'branch': notes_cfg.get('github_branch', 'main'),
        },
    )

@app.route('/notes.json')
def serve_notes_json():
    return send_from_directory(os.getcwd(), 'notes.json')

@app.route('/notes/<path:filepath>')
def serve_note_file(filepath):
    notes_dir = os.path.join(os.getcwd(), 'notes')
    return send_from_directory(notes_dir, filepath)

@app.route('/private/')
@app.route('/private/<path:filepath>')
def serve_private_file(filepath='index.html'):
    private_dir = os.path.join(os.getcwd(), 'private')
    return send_from_directory(private_dir, filepath)

@app.route('/api/config')
def get_config():
    return jsonify(config)

@app.route('/api/avatar', methods=['POST'])
def upload_avatar():
    global config
    denied = check_edit_permission()
    if denied:
        return denied

    if 'avatar' not in request.files:
        return jsonify({'error': '请选择图片文件'}), 400

    file = request.files['avatar']
    if not file or not file.filename:
        return jsonify({'error': '未选择文件'}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_AVATAR_EXT:
        return jsonify({'error': '仅支持 JPG、PNG、GIF、WebP 格式'}), 400

    os.makedirs(AVATAR_DIR, exist_ok=True)
    for old in os.listdir(AVATAR_DIR):
        if old.startswith('avatar.'):
            try:
                os.remove(os.path.join(AVATAR_DIR, old))
            except OSError:
                pass

    filename = f'avatar{ext}'
    file.save(os.path.join(AVATAR_DIR, filename))
    config['avatar'] = f'/static/avatars/{filename}'
    save_config_file()

    return jsonify({'success': True, 'avatar_url': config['avatar']})

@app.route('/api/background', methods=['POST'])
def upload_background():
    global config
    denied = check_edit_permission()
    if denied:
        return denied

    if 'background' not in request.files:
        return jsonify({'error': '请选择图片文件'}), 400

    file = request.files['background']
    if not file or not file.filename:
        return jsonify({'error': '未选择文件'}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_BACKGROUND_EXT:
        return jsonify({'error': '仅支持 JPG、PNG、GIF、WebP 格式'}), 400

    os.makedirs(BACKGROUND_DIR, exist_ok=True)
    clear_uploaded_backgrounds()

    filename = f'background{ext}'
    file.save(os.path.join(BACKGROUND_DIR, filename))
    if 'background' not in config:
        config['background'] = {}
    config['background']['image'] = f'/static/backgrounds/{filename}'
    save_config_file()

    return jsonify({'success': True, 'background_url': config['background']['image']})

@app.route('/api/background/reset', methods=['POST'])
def reset_background():
    denied = check_edit_permission()
    if denied:
        return denied

    background_url, error = restore_default_background()
    if error:
        return jsonify({'error': error}), 400
    return jsonify({'success': True, 'background_url': background_url})

# 提供根目录下的静态文件访问
@app.route('/<path:filename>')
def serve_root_file(filename):
    # 只允许访问特定的文件类型
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.svg', '.css', '.js'}
    file_ext = os.path.splitext(filename)[1].lower()
    
    if file_ext in allowed_extensions:
        try:
            return send_from_directory(os.getcwd(), filename)
        except FileNotFoundError:
            abort(404)
    
    # 对于不允许的文件类型，返回404
    abort(404)

def generate_static_html():
    """
    生成静态HTML文件，用于部署到GitHub Pages
    """
    print("开始生成静态HTML文件...")
    
    # 创建静态文件目录
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static_build')
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)
    else:
        # 清空目录中的所有文件
        for file in os.listdir(static_dir):
            file_path = os.path.join(static_dir, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
    
    try:
        # 确保配置已加载
        if 'config' not in globals():
            print("加载配置文件...")
            try:
                with open('config.json', 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except FileNotFoundError:
                # 默认配置
                config = {
                    "github_url": "https://github.com/example",
                    "dark_mode": "auto",
                    "name": "Example User",
                    "bio": "Python Developer",
                    "introduction_file": "Introduction.md",
                    "github_token": "",
                    "theme": {
                        "primary_color": "#6a11cb",
                        "secondary_color": "#2575fc"
                    },
                    "background": {
                        "image": "background.png",
                        "blur": 8,
                        "overlay_opacity": 0.6,
                        "overlay_color": "#121212"
                    }
                }
        
        # 读取介绍内容
        introduction_content = ""
        if 'introduction_file' in config and os.path.exists(config['introduction_file']):
            try:
                with open(config['introduction_file'], 'r', encoding='utf-8') as f:
                    introduction_content = f.read()
                # 转换Markdown为HTML
                introduction_content = markdown.markdown(introduction_content)
            except Exception as e:
                print(f"警告：无法读取或解析介绍文件: {e}")
        
        # 创建一个临时的Jinja2环境来渲染模板
        template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_dir),
            autoescape=jinja2.select_autoescape(['html', 'xml'])
        )
        
        # 获取模板
        template = env.get_template('index.html')
        
        # 准备渲染参数
        render_args = {
            'config': config,
            'introduction_content': introduction_content,
            'tech_stack': [],  # 由于没有GitHub数据，这里使用空列表
            'activity_data': [],  # 由于没有GitHub数据，这里使用空列表
            'error_message': None,
            'github_info': {
                'name': config.get('name', 'Example User'),
                'bio': config.get('bio', ''),
                'avatar_url': 'https://avatars.githubusercontent.com/u/10000000?v=4',  # 默认头像
                'html_url': config.get('github_url', 'https://github.com/example'),
                'public_repos': 0,
                'followers': 0,
                'activity_data': []  # 添加可序列化的activity_data键
            },
            'now': datetime.now()  # 添加当前时间对象，用于显示年份
        }
        
        # 渲染模板
        print("渲染HTML模板...")
        html_content = template.render(**render_args)
        
        # 保存HTML文件
        html_path = os.path.join(static_dir, 'index.html')
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"静态HTML文件已保存到: {html_path}")
        
        # 复制必要的静态资源
        resources_to_copy = []
        # 检查是否有背景图片
        if 'background' in config and 'image' in config['background']:
            background_image = config['background']['image']
            if os.path.exists(background_image):
                resources_to_copy.append(background_image)
        
        # 检查一些常见的资源文件
        for file in ['background.jpg', '1background.jpg', 'favicon.ico']:
            if os.path.exists(file):
                resources_to_copy.append(file)
        
        # 复制资源文件
        for resource in resources_to_copy:
            try:
                dst = os.path.join(static_dir, os.path.basename(resource))
                shutil.copy(resource, dst)
                print(f"已复制资源文件: {resource}")
            except Exception as e:
                print(f"警告：无法复制资源文件 {resource}: {e}")
        
        print("\n静态文件生成成功！")
        print(f"\n如何部署到GitHub Pages:")
        print("1. 进入static_build目录")
        print("2. 初始化git仓库（如果尚未初始化）")
        print("3. 添加并提交所有文件")
        print("4. 将文件推送到GitHub仓库的gh-pages分支")
        print("\n示例命令：")
        print("cd static_build")
        print("git init")
        print("git add .")
        print("git commit -m 'Deploy to GitHub Pages'")
        print("git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git")
        print("git push -f origin master:gh-pages")
        print("\n注意：您需要替换YOUR_USERNAME和YOUR_REPO为您的GitHub用户名和仓库名。")
        
    except Exception as e:
        print(f"错误：生成静态文件失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == '__main__':
    # 检查是否需要生成静态HTML
    if len(sys.argv) > 1 and sys.argv[1] == 'generate_static':
        generate_static_html()
    else:
        # 设置环境变量，使得 GitHub Pages 能够正确运行
        os.environ['FLASK_APP'] = 'app.py'
        # 在开发环境中运行
        app.run(debug=True, host='0.0.0.0', port=5000)