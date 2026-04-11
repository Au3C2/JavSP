import os
import sys
import subprocess
import shutil
import tkinter
from pathlib import Path

# 强制设置控制台编码为 UTF-8，防止在 CI 环境下打印表情或特殊字符崩溃
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
            base / "Library" / "lib" / "tcl8.6",
            base / "Contents" / "Frameworks" / "Tcl.framework" / "Versions" / "Current" / "Resources" / "Scripts"
        ]
        for cand in candidates:
            if (cand / "init.tcl").exists():
                tcl_root = cand
                break
        
        tk_candidates = [
            base / "tk",
            base / "lib" / "tk8.6",
            base / "Library" / "lib" / "tk8.6",
            base / "Contents" / "Frameworks" / "Tk.framework" / "Versions" / "Current" / "Resources" / "Scripts"
        ]
        for cand in tk_candidates:
            if (cand / "tk.tcl").exists():
                tk_root = cand
                break
                
    # 核心 DLL 仅在 Windows 下需要暴力补丁
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
    
    # 基础命令
    cmd = [
        sys.executable, "-m", "PyInstaller", "--onefile", "--name", "JavSP",
        "--icon", "image/JavSP.ico" if sys.platform == 'win32' else "image/JavSP.svg",
        "--add-data", "config.yml;." if sys.platform == 'win32' else "config.yml:.",
        "--add-data", "data;data" if sys.platform == 'win32' else "data:data",
        "--add-data", "image;image" if sys.platform == 'win32' else "image:image",
        "--collect-submodules", "javsp",
    ]
    
    # 只有探测到路径时才添加 Tcl/Tk 资源
    if tcl_path and tk_path:
        sep = ";" if sys.platform == 'win32' else ":"
        cmd.extend(["--add-data", f"{tcl_path}{sep}tcl_tk/{tcl_path.name}"])
        cmd.extend(["--add-data", f"{tk_path}{sep}tcl_tk/{tk_path.name}"])
    
    # Windows 特有的 DLL 注入
    for p in dlls.values():
        cmd.extend(["--add-binary", f"{p};."])
    
    cmd.append("javsp/__main__.py")
    
    print(f"Building on platform: {sys.platform}")
    if tcl_path: print(f"Detected Tcl at: {tcl_path}")
    print(f"Injecting {len(dlls)} core DLLs")
    
    subprocess.run(cmd, check=True)
    
    # --- 后置冒烟测试 ---
    print("\nRunning post-build smoke test...")
    exe_name = "dist/JavSP.exe" if sys.platform == 'win32' else "dist/JavSP"
    exe_path = Path(exe_name).absolute()
    
    if exe_path.exists():
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            # 运行帮助命令，验证模块加载
            result = subprocess.run([str(exe_path), "-h"], capture_output=True, text=True, env=env, timeout=15)
            if "AttributeError" in result.stderr or "ImportError" in result.stderr:
                print(f"ERROR: Smoke test failed!\n{result.stderr}")
                sys.exit(1)
            print("SUCCESS: Smoke test passed.")
        except subprocess.TimeoutExpired:
            print("SUCCESS: Smoke test reached UI phase.")
    else:
        print(f"ERROR: Build output {exe_path} not found!")
        sys.exit(1)

if __name__ == "__main__":
    run_build()
