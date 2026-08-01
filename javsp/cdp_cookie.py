"""Module for fetching JavDB cookies interactively using Edge CDP"""
import os
import sys
import time
import json
import shutil
import socket
import struct
import base64
import tempfile
import subprocess
import urllib.request
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def find_executable_browser() -> str | None:
    """Detect available Chromium-based browser executable across Windows, macOS, and Linux"""
    # 1. Check system PATH first
    for binary_name in [
        'msedge', 'google-chrome', 'chrome', 'chromium',
        'chromium-browser', 'microsoft-edge', 'brave-browser', 'vivaldi'
    ]:
        path = shutil.which(binary_name)
        if path and Path(path).is_file():
            return str(path)

    # 2. Windows specific registry and path candidates
    if sys.platform == 'win32':
        # Registry lookup for exact installed binary path
        try:
            import winreg
            reg_paths = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
                (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"),
                (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
            ]
            for hkey, subkey in reg_paths:
                try:
                    with winreg.OpenKey(hkey, subkey) as key:
                        val, _ = winreg.QueryValueEx(key, "")
                        if val and Path(val).is_file():
                            return str(val)
                except Exception:
                    pass
        except Exception:
            pass

        # Candidate path fallback
        pf = os.getenv('ProgramFiles', r'C:\Program Files')
        pfx86 = os.getenv('ProgramFiles(x86)', r'C:\Program Files (x86)')
        local = os.getenv('LOCALAPPDATA', r'C:\Users\Default\AppData\Local')

        candidates = [
            Path(pfx86) / 'Microsoft' / 'Edge' / 'Application' / 'msedge.exe',
            Path(pf) / 'Microsoft' / 'Edge' / 'Application' / 'msedge.exe',
            Path(pf) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe',
            Path(pfx86) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe',
            Path(local) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe',
            Path(local) / 'Microsoft' / 'Edge' / 'Application' / 'msedge.exe',
            Path(pf) / 'BraveSoftware' / 'Brave-Browser' / 'Application' / 'brave.exe',
            Path(pfx86) / 'BraveSoftware' / 'Brave-Browser' / 'Application' / 'brave.exe',
        ]
        for c in candidates:
            if c.is_file():
                return str(c)

    # 3. macOS candidates
    elif sys.platform == 'darwin':
        mac_candidates = [
            Path('/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'),
            Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
            Path('/Applications/Chromium.app/Contents/MacOS/Chromium'),
            Path('/Applications/Brave Browser.app/Contents/MacOS/Brave Browser'),
            Path('/Applications/Vivaldi.app/Contents/MacOS/Vivaldi'),
            Path.home() / 'Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            Path.home() / 'Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
        ]
        for c in mac_candidates:
            if c.is_file():
                return str(c)

    # 4. Linux candidates
    elif sys.platform.startswith('linux'):
        linux_candidates = [
            '/usr/bin/google-chrome',
            '/usr/bin/google-chrome-stable',
            '/usr/bin/chromium',
            '/usr/bin/chromium-browser',
            '/usr/bin/microsoft-edge',
            '/usr/bin/microsoft-edge-stable',
            '/usr/bin/brave-browser',
        ]
        for c in linux_candidates:
            if Path(c).is_file():
                return c

    return None


def send_ws_message(sock: socket.socket, msg: str) -> None:
    """Send text frame over WebSocket socket"""
    data = msg.encode('utf-8')
    length = len(data)
    mask = os.urandom(4)
    masked_data = bytearray(length)
    for i in range(length):
        masked_data[i] = data[i] ^ mask[i % 4]
    
    header = bytearray()
    header.append(0x81)  # Text frame, FIN=1
    if length <= 125:
        header.append(0x80 | length)
    elif length <= 65535:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", length))
    
    sock.sendall(header + mask + masked_data)


def recv_ws_message(sock: socket.socket) -> str | None:
    """Receive text frame from WebSocket socket"""
    try:
        header = sock.recv(2)
        if not header or len(header) < 2:
            return None
        b1, b2 = header[0], header[1]
        payload_len = b2 & 0x7f
        if payload_len == 126:
            ext = sock.recv(2)
            payload_len = struct.unpack("!H", ext)[0]
        elif payload_len == 127:
            ext = sock.recv(8)
            payload_len = struct.unpack("!Q", ext)[0]
        
        is_masked = (b2 & 0x80) != 0
        if is_masked:
            mask = sock.recv(4)
        
        payload = bytearray()
        while len(payload) < payload_len:
            chunk = sock.recv(payload_len - len(payload))
            if not chunk:
                break
            payload.extend(chunk)
            
        if is_masked:
            for i in range(len(payload)):
                payload[i] ^= mask[i % 4]
                
        return payload.decode('utf-8', errors='ignore')
    except Exception as e:
        logger.debug(f"Error receiving WebSocket message: {e}")
        return None


def fetch_cookies_from_cdp(port: int = 9222) -> dict[str, str]:
    """Connect to Chrome DevTools Protocol port and fetch all cookies"""
    try:
        req = urllib.request.urlopen(f'http://127.0.0.1:{port}/json', timeout=2)
        targets = json.loads(req.read().decode('utf-8'))
        ws_url = None
        for t in targets:
            if t.get('type') == 'page' and 'javdb' in t.get('url', ''):
                ws_url = t.get('webSocketDebuggerUrl')
                break
        if not ws_url and targets:
            for t in targets:
                if t.get('type') == 'page':
                    ws_url = t.get('webSocketDebuggerUrl')
                    break

        if not ws_url:
            return {}

        ws_path = '/' + ws_url.split('/', 3)[3]
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3.0)
        s.connect(('127.0.0.1', port))
        key = base64.b64encode(os.urandom(16)).decode('utf-8')
        req_str = (
            f"GET {ws_path} HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        s.sendall(req_str.encode('utf-8'))
        resp = s.recv(1024)
        if b"101" not in resp:
            s.close()
            return {}

        send_ws_message(s, json.dumps({"id": 1, "method": "Network.getAllCookies"}))
        msg = recv_ws_message(s)
        s.close()

        if not msg:
            return {}

        res = json.loads(msg)
        cookies_list = res.get('result', {}).get('cookies', [])
        result = {}
        for c in cookies_list:
            domain = c.get('domain', '')
            if 'javdb' in domain:
                result[c.get('name')] = c.get('value')
        return result
    except Exception as e:
        logger.debug(f"CDP cookie extraction error: {e}")
        return {}


def interactive_fetch_cookie(target_url: str = 'https://javdb.com', port: int = 9222, timeout: int = 180) -> str:
    """Launch isolated Chromium browser window for user verification and auto extract cookie string"""
    browser_bin = find_executable_browser()
    if not browser_bin or not Path(browser_bin).exists():
        logger.error("No valid Chromium-based browser (Edge/Chrome/Chromium/Brave) found on system.")
        return ""

    temp_dir = Path(tempfile.gettempdir()) / 'javsp_edge_cdp_session'
    if temp_dir.exists():
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass

    cmd = [
        browser_bin,
        f'--remote-debugging-port={port}',
        f'--user-data-dir={temp_dir}',
        '--no-first-run',
        '--no-default-browser-check',
        target_url
    ]

    logger.info("=" * 60)
    logger.info("JavSP: 正在启动内置 Edge 浏览器窗口进行过盾/登录...")
    logger.info("提示: 请在弹出的浏览器窗口中完成 Cloudflare 验证或登录 JavDB。")
    logger.info("验证成功后，本工具会自动捕获凭证并关闭浏览器窗口。")
    logger.info("=" * 60)

    proc = subprocess.Popen(cmd)
    start_time = time.time()
    cookies_dict = {}

    try:
        while time.time() - start_time < timeout:
            time.sleep(2)
            c_dict = fetch_cookies_from_cdp(port)
            if '_jdb_session' in c_dict or 'cf_clearance' in c_dict:
                logger.info("成功检测并捕获到有效的 JavDB 过盾/登录 Cookie!")
                cookies_dict = c_dict
                break

            if proc.poll() is not None:
                logger.warning("用户手动关闭了浏览器窗口。")
                break
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait()
        if temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass

    if cookies_dict:
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])
        return cookie_str
    return ""


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    print("正在启动 JavDB 登录/过盾弹窗助手...")
    c_str = interactive_fetch_cookie("https://javdb.com")
    if c_str:
        print("\n" + "=" * 60)
        print("提取成功! 捕获的 JavDB Cookie:")
        print(c_str)
        print("=" * 60)
        from javsp.config import save_javdb_cookie_to_config
        save_javdb_cookie_to_config(c_str)
        print("已自动将 Cookie 写入配置文件 config.yml 和 dist/config.yml")
    else:
        print("未能捕获到 Cookie 或操作超时/关闭。")
