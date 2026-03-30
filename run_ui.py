"""
Runner script for the NiceGUI application.
Resolves the path to the app inside src/ui_app and runs it.
"""

import os
import sys
import subprocess
import platform

def kill_process_on_port(port):
    """포트를 사용 중인 프로세스 종료"""
    try:
        if platform.system() == "Windows":
            # Windows: netstat으로 PID 찾기
            result = subprocess.run(
                f'netstat -ano | findstr :{port}',
                shell=True,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0 and result.stdout:
                lines = result.stdout.strip().split('\n')
                pids = set()
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 5 and 'LISTENING' in line:
                        pid = parts[-1]
                        if pid.isdigit():
                            pids.add(pid)
                
                for pid in pids:
                    print(f"포트 {port}를 사용 중인 프로세스(PID {pid})를 종료합니다...")
                    subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True)
                    print(f"프로세스 {pid} 종료 완료")
        else:
            # Linux/Mac: lsof로 PID 찾기
            result = subprocess.run(
                f'lsof -ti:{port}',
                shell=True,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0 and result.stdout:
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    if pid:
                        print(f"포트 {port}를 사용 중인 프로세스(PID {pid})를 종료합니다...")
                        subprocess.run(f'kill -9 {pid}', shell=True)
                        print(f"프로세스 {pid} 종료 완료")
    except Exception as e:
        print(f"프로세스 종료 중 오류 (무시됨): {e}")

def main():
    # Get the absolute path of the current file's directory (root of the project)
    project_root = os.path.dirname(os.path.abspath(__file__))
    
    # Path to the NiceGUI app file
    app_path = os.path.join(project_root, "src", "ui_app", "app_ui.py")
    
    if not os.path.exists(app_path):
        print(f"Error: Could not find NiceGUI app at {app_path}")
        sys.exit(1)
    
    # 포트 8502를 사용 중인 프로세스 정리
    print("기존 프로세스 확인 중...")
    kill_process_on_port(8502)
    
    print(f"\nStarting NiceGUI app from: {app_path}")
    print("Open your browser at: http://localhost:8502")
    print("Press Ctrl+C to stop the server")
    print()
    
    # Run the app as a subprocess to preserve __name__ == "__main__"
    try:
        subprocess.run([sys.executable, app_path], cwd=project_root, check=True)
    except KeyboardInterrupt:
        print("\nStopping NiceGUI app...")
    except subprocess.CalledProcessError as e:
        print(f"\nError running NiceGUI app: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

# Made with Bob
