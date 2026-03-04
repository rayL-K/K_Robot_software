import subprocess

def copy_file_to_clipboard(file_path: str) -> bool:
    """
    通过 PowerShell 将文件复制到系统剪贴板。
    """
    cmd = f'Set-Clipboard -Path "{file_path}"'
    try:
        result = subprocess.run(
            ['powershell', '-Command', cmd],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return True
        else:
            print(f"[ 系统控件 - 剪贴板 ] PowerShell错误: {result.stderr}")
            return False
    except Exception as e:
        print(f"[ 系统控件 - 剪贴板 ] 执行异常: {e}")
        return False
