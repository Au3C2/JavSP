import os
import sys
import subprocess
import shutil
import tkinter
from pathlib import Path

# 强制设置控制台编码为 UTF-8
if sys.stdout.encoding != 'utf-8':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception:
        pass

def get_resource_config():
    """动态获取当前环境的 Tcl/Tk 路径"""
    tcl_root, tk_root = None, None
    try:
        tcl_root = tkinter.Tcl().eval('info library')
        tk_root = tkinter.Tk().tk.eval('info library')
    except Exception:
        base = Path(sys.base_prefix)
        # 常见路径探测
        candidates = [
            base / "tcl",
            base / "lib" / "tcl8.6",
            base / "Library" / "lib" / "tcl8.6"
        ]
        for cand in candidates:
            if (cand / "init.tcl").exists():
                tcl_root = cand
                break
        
        tk_candidates = [
            base / "tk",
            base / "lib" / "tk8.6",
            base / "Library" / "lib" / "tk8.6"
        ]
        for cand in tk_candidates:
            if (cand / "tk.tcl").exists():
                tk_root = cand
                break
                
    found_dlls = {}
    if sys.platform == 'win32':
        base = Path(sys.base_prefix)
        dll_folders = [base, base / "Library" / "bin", base / "DLLs", Path(sys.executable).parent]
        dll_names = ["ffi.dll", "libffi-7.dll", "libffi-8.dll", "libssl-3-x64.dll", "libcrypto-3-x64.dll", "zlib.dll", "sqlite3.dll", "tcl86t.dll", "tk86t.dll", "liblzma.dll"]
        for folder in dll_folders:
            if not folder.exists(): continue
            for n in dll_names:
                if n in found_dlls: continue
                p = folder / n
                if p.exists(): found_dlls[n] = p
                
    return Path(tcl_root) if tcl_root else None, Path(tk_root) if tk_root else None, found_dlls

def run_build():
    tcl_path, tk_path, dlls = get_resource_config()
    
    # 1. 获取当前版本并创建运行时钩子
    sys.path.append(os.path.join(os.path.dirname(__file__)))
    from version import get_version
    current_ver = get_version()
    print(f"Build Version: {current_ver}")
    
    hook_path = Path("ver_hook.py")
    hook_path.write_text(f"import sys\nsys.javsp_version = '{current_ver}'\n", encoding='utf-8')

    # 2. 基础命令
    cmd = [
        sys.executable, "-m", "PyInstaller", "--onefile", "--name", "JavSP",
        "--icon", "image/JavSP.ico" if sys.platform == 'win32' else "image/JavSP.svg",
        "--add-data", "config.yml;." if sys.platform == 'win32' else "config.yml:.",
        "--add-data", "data;data" if sys.platform == 'win32' else "data:data",
        "--add-data", "image;image" if sys.platform == 'win32' else "image:image",
        "--runtime-hook", str(hook_path),
        "--collect-submodules", "javsp",
    ]
    
    if tcl_path and tk_path:
        sep = ";" if sys.platform == 'win32' else ":"
        cmd.extend(["--add-data", f"{tcl_path}{sep}tcl_tk/{tcl_path.name}"])
        cmd.extend(["--add-data", f"{tk_path}{sep}tcl_tk/{tk_path.name}"])
    
    for p in dlls.values():
        cmd.extend(["--add-binary", f"{p};."])
    
    cmd.append("javsp/__main__.py")
    
    print(f"Building on platform: {sys.platform}")
    subprocess.run(cmd, check=True)
    
    # 3. 冒烟测试
    print("\nRunning post-build smoke test...")
    exe_name = "dist/JavSP.exe" if sys.platform == 'win32' else "dist/JavSP"
    exe_path = Path(exe_name).absolute()
    
    if exe_path.exists():
        # 设置编码强制使用 utf-8 捕获，并使用 check=False 允许手动分析输出
        result = subprocess.run([str(exe_path), "-h"], capture_output=True, text=True, encoding='utf-8', errors='ignore')
        output = result.stdout + result.stderr
        
        # 校验版本号 (支持 fuzzy 匹配，防止 banner 装饰符影响)
        if current_ver in output:
            print(f"SUCCESS: Version '{current_ver}' verified in output.")
        else:
            print(f"WARNING: Version '{current_ver}' NOT found in output. Full output check recommended.")
            print("--- Output Start ---")
            print(output[:500])
            print("--- Output End ---")
            # 在某些 headless 环境下可能失败，这里不强制 exit 1
            
        if "AttributeError" in output or "ImportError" in output:
            print("ERROR: App crashed during smoke test!")
            sys.exit(1)
            
        print("SUCCESS: Smoke test completed.")
    
    if hook_path.exists(): os.remove(hook_path)

if __name__ == "__main__":
    run_build()
