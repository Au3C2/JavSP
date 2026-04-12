import subprocess
import os
import re
from pathlib import Path

def get_version():
    # 方案 1：尝试通过 Git 标签获取真实动态版本
    try:
        # 获取最近的标签名 (例如 v1.8.2)
        cmd = ["git", "describe", "--tags", "--always", "--dirty"]
        version = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode().strip()
        if version:
            # 移除前面的 v 并处理可能的 commit distance 
            # 例如 v1.8.2-1-gabc -> 1.8.2
            match = re.match(r'^v?(\d+\.\d+\.\d+(?:\.\d+)?)', version)
            if match:
                return match.group(1)
            return version.lstrip('v')
    except Exception:
        pass

    # 方案 2：如果 Git 失败，检查 pyproject.toml 中的占位符 (最后的兜底)
    try:
        toml_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        if toml_path.exists():
            content = toml_path.read_text(encoding='utf-8')
            # 这里的 version 可能就是 0.0.0
            match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
            if match and match.group(1) != "0.0.0":
                return match.group(1).lstrip('v')
    except Exception:
        pass

    return "1.8.2" # 终极硬核补丁：既然我们正在发布 v1.8.2，这里作为最后的保底

if __name__ == "__main__":
    print(get_version())
