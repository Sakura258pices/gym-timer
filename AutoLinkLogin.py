#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re, sys, time, uuid, socket, logging, requests
from pathlib import Path

# ===== 用户配置 =====
USERNAME = "632562020133"
PASSWORD = "010031"
ISP = "联通"  # 联通 / 电信 / 移动 / 教师
CHECK_INTERVAL = 60*60
RETRY_TIMES = 3
TIMEOUT = (2, 5)

# ===== Portal配置 =====
PORTAL_HOST = "172.19.7.17"
PORTAL_URL = f"http://{PORTAL_HOST}/"
LOGIN_URL = f"http://{PORTAL_HOST}:801/eportal/portal/login"
ISP_SUFFIX = {"联通": "@unicom", "电信": "@telecom", "移动": "@cmcc", "教师": ""}

# ===== 日志 =====
LOG_FILE = Path(__file__).resolve().with_name("AutoLink.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===== HTTP Session =====
session = requests.Session()
session.trust_env = False
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": PORTAL_URL
})

def get_local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((PORTAL_HOST, 80))
            return s.getsockname()[0]
    except Exception:
        return ""

def get_local_mac():
    try:
        return f"{uuid.getnode():012x}"
    except Exception:
        return ""

def is_online():
    logger.info("开始检测外网连接...")
    try:
        r = session.get("http://1.1.1.1/", timeout=(2, 3), allow_redirects=False)
        location = r.headers.get("Location", "").lower()
        content = r.text[:2000].lower()
        if PORTAL_HOST in location or "eportal" in location or PORTAL_HOST in content or "eportal" in content:
            logger.info("检测到校园网Portal")
            return False
        if r.status_code in (200, 204, 301, 302, 307, 308, 403):
            logger.info("外网连接正常，HTTP状态码: %s", r.status_code)
            return True
        logger.info("外网检测异常，HTTP状态码: %s", r.status_code)
    except requests.RequestException as e:
        logger.info("外网不可访问: %s", e)
    return False

def get_portal_params():
    logger.info("访问Portal页面: %s", PORTAL_URL)
    try:
        r = session.get(PORTAL_URL, timeout=TIMEOUT)
        logger.info("Portal页面状态码: %s", r.status_code)
        html = r.content.decode("gbk", errors="ignore")

        ip_match = re.search(r"v4ip='([^']*)'", html) or re.search(r'ss5="([^"]*)"', html)
        mac_match = re.search(r'mac\s*[:=]\s*["\']?([0-9a-fA-F]{12})', html, re.I)

        user_ip = ip_match.group(1) if ip_match else get_local_ip()
        user_mac = mac_match.group(1).lower() if mac_match else get_local_mac()

        logger.info("Portal参数: IP=%s, MAC=%s", user_ip or "未获取", user_mac or "未获取")
        return user_ip, user_mac
    except requests.RequestException as e:
        logger.error("访问Portal失败: %s", e)
        return get_local_ip(), get_local_mac()

def login():
    logger.info("开始Portal认证...")
    user_ip, user_mac = get_portal_params()
    user_account = f",0,{USERNAME}{ISP_SUFFIX.get(ISP, '')}"
    ua = f"{session.headers['User-Agent']}|sw:2048|sh:1152|dpr:1.25"

    params = [
        ("callback", "dr1106"),
        ("login_method", "1"),
        ("user_account", user_account),
        ("user_password", PASSWORD),
        ("wlan_user_ip", user_ip),
        ("wlan_user_ipv6", ""),
        ("wlan_user_mac", user_mac),
        ("wlan_vlan_id", "0"),
        ("wlan_ac_ip", ""),
        ("wlan_ac_name", ""),
        ("mac_type", "0"),
        ("UA", ua),
        ("jsVersion", "4.2.2"),
        ("terminal_type", "1"),
        ("lang", "zh-cn"),
        ("v", "5222"),
        ("lang", "zh")
    ]

    for attempt in range(1, RETRY_TIMES + 1):
        logger.info("登录尝试 %d/%d", attempt, RETRY_TIMES)
        try:
            r = session.get(LOGIN_URL, params=params, timeout=TIMEOUT)
            logger.info("登录接口HTTP状态码: %s", r.status_code)
            text = r.text

            if re.search(r'"result"\s*:\s*1', text) or "Portal协议认证成功" in text:
                logger.info("Portal认证成功")
                for delay in (2, 4, 6):
                    time.sleep(delay)
                    if is_online():
                        logger.info("网络连接成功")
                        return True
                logger.warning("Portal认证成功，但外网仍不可访问")
                return False

            if re.search(r'"result"\s*:\s*0', text):
                logger.error("Portal认证失败: %s", text[:500])
                return False

            logger.warning("未识别Portal响应: %s", text[:500])
        except requests.RequestException as e:
            logger.error("登录请求异常: %s", e)

        if attempt < RETRY_TIMES:
            time.sleep(2)

    logger.error("达到最大登录重试次数")
    return False

def run_once():
    logger.info("=" * 40)
    if is_online():
        logger.info("当前网络正常")
        return True
    logger.info("当前无法访问外网，开始校园网认证")
    return login()

def run_daemon():
    logger.info("启动守护模式，检查间隔 %d 秒", CHECK_INTERVAL)
    while True:
        try:
            run_once()
        except Exception:
            logger.exception("程序发生未处理异常")
        time.sleep(CHECK_INTERVAL)


def main():
    print("校园网自动登录程序启动", flush=True)
    print(f"日志文件: {LOG_FILE}", flush=True)
    logger.info("程序启动")
    if USERNAME == "你的学号" or PASSWORD == "你的密码":
        logger.error("请先设置 USERNAME 和 PASSWORD")
        return
    try:
        if "--daemon" in sys.argv:
            run_daemon()
        elif "--test" in sys.argv:
            logger.info("测试登录")
            result=login()
        else:
            result=run_once() 
        print("网络正常" if result else "网络连接失败")
    except KeyboardInterrupt:
        logger.info("用户终止程序")
    except Exception:
        logger.exception("程序异常退出")

if __name__ == "__main__":
    main()