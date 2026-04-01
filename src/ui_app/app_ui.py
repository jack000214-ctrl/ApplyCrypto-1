"""
ApplyCrypto UI - NiceGUI 기반 IBM Carbon Design 스타일
- TOP + LNB + Main 레이아웃
- 단계별 워크플로우 (명령 선택 → 옵션 설정 → Config 확인 → 실행)
"""

import json
import os
import sys
import asyncio
import subprocess
import argparse
import locale
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from nicegui import ui, app

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config.config_manager import load_config, Configuration
from cli.cli_controller import CLIController

UI_ASSETS_ROUTE = '/ui-assets'
UI_ASSETS_DIR = Path(__file__).resolve().parent
CI_LOGO_WEB_PATH = f"{UI_ASSETS_ROUTE}/img-ci.png"

# ============================================================================
# 전역 변수 초기화
# ============================================================================
output_label = None
error_label = None
status_label = None
execute_button = None
stop_button = None
json_editor_ref = None  # Step 3의 JSON 에디터 참조
session_tabs_container = None

# ============================================================================
# 전역 상태
# ============================================================================
@dataclass
class AppState:
    session_id: str = ""
    session_name: str = ""
    session_name_customized: bool = False
    step: int = 1
    selected_command: Optional[str] = None
    selected_options: Optional[Dict[str, Any]] = None
    config_content: str = ""
    loaded_config_file: Optional[str] = None  # 현재 로드된 config 파일명 추적
    config_validated: bool = False
    validation_message: str = ""
    execution_output: str = ""
    execution_error: str = ""
    is_executing: bool = False
    current_process: Optional[Any] = None
    preflight_ready: bool = False
    preflight_confirmed_in_step4: bool = False
    preflight_message: str = ""
    preflight_items: Optional[List[Dict[str, str]]] = None
    
    def __post_init__(self):
        if self.selected_options is None:
            self.selected_options = {}
        if self.preflight_items is None:
            self.preflight_items = []

session_states: Dict[str, AppState] = {}
session_order: List[str] = []
session_counter = 0
current_session_id = ""
app_state = AppState()


def _create_session_id() -> str:
    """탭 ID 생성"""
    global session_counter
    session_counter += 1
    return f"S{session_counter}"


def create_session() -> str:
    """새 작업 탭 생성"""
    session_id = _create_session_id()
    state = AppState(session_id=session_id, session_name=f"작업 {session_counter}")
    session_states[session_id] = state
    session_order.append(session_id)
    log_event("UI", "탭 생성", f"탭 생성: {session_id}")
    return session_id


def switch_session(session_id: str):
    """활성 작업 탭 전환"""
    global current_session_id, app_state
    if session_id not in session_states:
        log_event("WARN", "탭 전환 무시", f"알 수 없는 탭: {session_id}")
        return
    prev = current_session_id
    current_session_id = session_id
    app_state = session_states[session_id]
    log_event("UI", "탭 전환", f"탭 전환: {prev or '-'} -> {session_id}", app_state.step)
    update_ui()


def ensure_default_session():
    """기본 탭 보장"""
    global current_session_id, app_state
    if session_order:
        if current_session_id and current_session_id in session_states:
            app_state = session_states[current_session_id]
            return
        current_session_id = session_order[0]
        app_state = session_states[current_session_id]
        return

    session_id = create_session()
    current_session_id = session_id
    app_state = session_states[session_id]

LEVEL_COLORS = {
    "UI": "\033[95m",       # magenta
    "CLICK": "\033[96m",    # cyan
    "STEP": "\033[94m",     # blue
    "INFO": "\033[94m",     # blue
    "RUN": "\033[92m",      # green
    "WARN": "\033[93m",     # yellow
    "ERROR": "\033[91m",    # red
    "DEBUG": "\033[90m",    # gray
}
ANSI_RESET = "\033[0m"

# ============================================================================
# IBM Carbon Design CSS
# ============================================================================
CARBON_CSS = """
<style>
/* IBM Carbon Design 색상 */
:root {
    --carbon-gray-100: #161616;
    --carbon-gray-90: #262626;
    --carbon-gray-80: #393939;
    --carbon-gray-70: #525252;
    --carbon-gray-50: #8d8d8d;
    --carbon-gray-30: #c6c6c6;
    --carbon-gray-20: #e0e0e0;
    --carbon-gray-10: #f4f4f4;
    --carbon-blue-60: #0f62fe;
    --carbon-blue-70: #0353e9;
    --carbon-green-60: #24a148;
}

/* 전역 리셋 */
body {
    margin: 0 !important;
    padding: 0 !important;
    font-family: "Malgun Gothic", "맑은 고딕", -apple-system, BlinkMacSystemFont, system-ui, "Apple SD Gothic Neo", "Helvetica Neue", Helvetica, Arial, Dotum, "돋움", sans-serif;
    background-color: #f4f4f4;
}

.nicegui-content {
    margin: 0 !important;
    padding: 0 !important;
}

.nicegui-column {    
    height: 100% !important;
}

.content-wrapper > .nicegui-column {
    height: 100% !important;
    min-height: 100% !important;
}

/* TOP 헤더 */
.top-header {
    height: 48px;
    background-color: #e4edfb;
    color: #161616;
    display: flex;
    align-items: center;
    padding: 0 2px;
    border-bottom: 1px solid #d0dff5;
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 1000;
}

.top-header-ci-logo {
    width: 101px;
    height: 33px;
    display: block;
    object-fit: contain;
    object-position: left center;
    margin-left: 20px;
    flex-shrink: 0;
}

.top-header-logo {
    font-size: 14px;
    font-weight: 600;
    color: var(--carbon-gray-90);
    letter-spacing: 0.16px;
    margin-right: 5px;
}

.top-header-title {
    font-size: 11px;
    font-weight: 200;
    color: var(--carbon-gray-50);
}

.session-tabs-wrap {
    height: 36px;
    background: linear-gradient(180deg, #d8e1ee 0%, #c8d4e5 100%);
    border-bottom: none;
    position: fixed;
    top: 48px;
    left: 0;
    right: 0;
    z-index: 999;
    display: flex;
    align-items: flex-end;
    padding: 3px 10px 0 10px;
}

.session-tab-shell {
    border: 1px solid #8ea3bd;
    border-bottom: 1px solid #8ea3bd;
    background: linear-gradient(180deg, #d9e2ef 0%, #c8d4e5 100%);
    border-radius: 8px 8px 0 0;
    height: 33px;
    margin-right: 6px;
    min-width: 180px;
    max-width: 260px;
    display: inline-flex;
    align-items: center;
    padding: 0 4px 0 8px;
    box-shadow: inset 0 1px 0 #ffffff;
    position: relative;
}

.session-tab-shell.active {
    border-color: #5f7fa5;
    border-bottom-color: #ffffff;
    background: #ffffff;
    box-shadow: 0 -1px 0 #bdd9da, 0 2px 8px rgba(30, 67, 97, 0.08);
    transform: translateY(0);
    z-index: 2;
}

.session-tab-shell.active::after {
    content: '';
    position: absolute;
    left: 0;
    right: 0;
    bottom: -1px;
    height: 2px;
    background: #ffffff;
}

.session-tab {
    border: none !important;
    background: linear-gradient(180deg, #d9e2ef 0%, #c8d4e5 100%) !important;
    box-shadow: none !important;
    color: #50647e !important;
    font-size: 12px;
    font-weight: 500;
    text-transform: none;
    padding: 0 8px;
    min-height: 28px;
    height: 28px;
    width: calc(100% - 30px);
    justify-content: flex-start;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.session-tab-shell.active .session-tab {
    background: #ffffff !important;
    color: #0f2f57 !important;
    font-weight: 700;
}

.session-tab-shell.running .session-tab {
    position: relative;
    padding-left: 16px;
}

.session-tab-shell.running .session-tab::before {
    content: '';
    position: absolute;
    left: 2px;
    top: 50%;
    width: 8px;
    height: 8px;
    margin-top: -4px;
    border-radius: 50%;
    background: #24a148;
    box-shadow: 0 0 0 2px rgba(36, 161, 72, 0.15);
}

.session-close-btn,
.session-close-btn.q-btn {
    border: none !important;
    background: rgba(210, 210, 240, 0.3) !important;
    box-shadow: none !important;
    min-width: 22px;
    width: 22px;
    height: 22px;
    min-height: 22px;
    border-radius: 11px;
    color: #61758f !important;
    font-size: 13px;
    padding: 0 0 3px 0 !important;
    margin-left: 2px;
}

.session-close-btn:hover,
.session-close-btn.q-btn:hover {
    background: rgba(140, 150, 180, 0.5) !important;
    color: #0f62fe !important;
}

.session-close-btn .q-focus-helper {
    opacity: 0 !important;
}

.session-add-btn,
.session-add-btn.bg-primary {
    height: 26px;
    min-height: 26px;
    border-radius: 26px;
    border: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
    color: #ffffff !important;
    font-size: 20px;
    font-weight: 600;
    line-height: 1;
    text-transform: none;
    padding: 0 8px;
    margin: 0 0 5px 0;
}

.session-add-btn:hover,
.session-add-btn.bg-primary:hover {
    background: rgba(255, 255, 255, 0.35) !important;
    color: #4f6279 !important;
}

/* 콘텐츠 영역 */
.content-wrapper {
    display: flex !important;
    flex-direction: row !important;
    margin: 0 !important;
    padding: 0 !important;
    height: calc(100vh - 84px) !important;
    width: 100% !important;
    position: fixed !important;
    top: 84px !important;
    left: 0 !important;
    right: 0 !important;
    gap: 0 !important;
}

/* 좌측 LNB */
.left-nav {
    width: 240px !important;
    min-width: 240px !important;
    max-width: 240px !important;
    background: #ffffff;
    border-right: 1px solid #e0e0e0;
    overflow-y: visible !important;
    flex-shrink: 0 !important;
    height: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
    display: flex !important;
    flex-direction: column !important;
    position: relative;
}

.nav-section {
    padding: 16px 0;
    width: 100%;
    cursor: pointer;
    border-bottom: 1px solid #f0f0f0;
}

.nav-section:first-child {
    padding-top: 20px;
}

.nav-section:last-child {
    border-bottom: none;
    position: sticky;
    bottom: 0;
    background: #ffffff;
    padding: 16px 0 20px 0;
    box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.05);
}

.nav-title {
    font-size: 14px;
    font-weight: 700;
    color: #161616;
    text-transform: none;
    letter-spacing: -0.3px;
    margin-bottom: 16px;
    padding: 0 20px;
}

.nav-item {
    padding: 10px 20px;
    margin: 0;
    border-radius: 0;
    font-size: 14px;
    color: #333333;
    transition: all 0.15s ease;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-left: 3px solid transparent;
    background-color: transparent;
}

.nav-item::after {
    content: '›';
    color: #cccccc;
    font-size: 16px;
    opacity: 0;
    transition: opacity 0.15s ease;
}

.nav-item:hover {
    background-color: #f8f8f8;
}

.nav-item:hover::after {
    opacity: 1;
}

.nav-item.completed {
    background-color: transparent;
    color: #24a148;
    font-weight: 500;
    border-left-color: #24a148;
}

.nav-item.completed::after {
    content: '✓';
    color: #24a148;
    opacity: 1;
}

.nav-item.current {
    background-color: #f0f7ff;
    color: #0f62fe;
    font-weight: 600;
    border-left-color: #0f62fe;
}

.nav-item.current::after {
    content: '▶';
    color: #0f62fe;
    opacity: 1;
}

.nav-item.pending {
    color: #999999;
    background-color: transparent;
}

.nav-item.pending::after {
    opacity: 0;
}

/* 우측 Main */
.main-content {
    flex: 1 !important;
    background-color: #ffffff;
    overflow-y: scroll !important;
    overflow-x: hidden !important;
    padding: 12px 32px 32px 32px;
    height: 100% !important;
    max-height: 100% !important;
    width: 100% !important;
    margin: 0 !important;
}

.main-content h1 {
    margin-top: 0;
    margin-bottom: 2px;
    font-size: 24px;
    line-height: 1.2;
}

.main-content > p {
    margin-top: 0;
    margin-bottom: 8px;
    font-size: 12px;
    color: var(--carbon-gray-70);
}

.main-content hr {
    margin: 8px 0 12px 0;
}

/* 버튼 */
.carbon-btn {
    background-color: var(--carbon-blue-60);
    color: #ffffff;
    border: 1px solid var(--carbon-blue-10);
    padding: 2px 16px;
    font-size: 13px;
    font-weight: 400;
    cursor: pointer;
    transition: background-color 0.1s;
    height: 28px;
    box-sizing: border-box;
}

.carbon-btn:hover {
    background-color: var(--carbon-blue-70);
    border-color: var(--carbon-blue-70);
}

.carbon-btn-secondary {
    background-color: transparent;
    color: var(--carbon-blue-60);
    border: 1px solid var(--carbon-blue-30);
    padding: 2px 16px;
    font-size: 13px;
    font-weight: 400;
    cursor: pointer;
    transition: all 0.1s;
    height: 28px;
    box-sizing: border-box;
}

.carbon-btn-secondary:hover {
    background-color: var(--carbon-blue-60);
    color: #ffffff;
}

/* 명령 카드 */
.command-card {
    border: 1px solid var(--carbon-gray-20);
    padding: 8px 14px !important;
    margin-bottom: 4px !important;
    display: flex !important;
    flex-direction: row !important;
    justify-content: space-between !important;
    align-items: center !important;
    background-color: #ffffff;
    transition: background-color 0.2s;
    width: 100% !important;
    box-sizing: border-box;
    min-height: 35px;
}

.command-card:hover {
    background-color: var(--carbon-gray-10);
}

.command-card > * {
    margin: 0 !important;
}

.command-name {
    min-width: 180px;
    max-width: 180px;
    font-size: 14px;
    font-weight: 600;
    color: var(--carbon-gray-100);
    text-align: left;
    margin-right: 16px !important;
    flex-shrink: 0;
}

.command-description {
    flex: 1;
    color: var(--carbon-gray-70);
    font-size: 13px;
    text-align: left;
    margin-right: 16px !important;
    line-height: 1.3;
}

.command-card button {
    flex-shrink: 0;
    margin-left: auto !important;
    padding: 3px 12px !important;
    font-size: 13px !important;
    height: auto !important;
}

/* 제목 */
h1 {
    font-size: 32px;
    font-weight: 400;
    color: var(--carbon-gray-100);
    margin-bottom: 8px;
}

h2 {
    font-size: 24px;
    font-weight: 400;
    color: var(--carbon-gray-100);
    margin-bottom: 16px;
}

/* 구분선 */
hr {
    border: none;
    border-top: 1px solid var(--carbon-gray-20);
    margin: 24px 0;
}

/* 옵션 입력 */
.options-container {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-bottom: 24px;
}

.option-group {
    padding: 20px;
    background: #ffffff;
    border: 1px solid #e0e0e0;
    border-left: 3px solid #0f62fe;
    border-radius: 4px;
    transition: all 0.2s ease;
    display: flex;
    flex-direction: column;
    min-height: 140px;
}

.option-group:hover {
    background: #f8f9fa;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.option-title {
    display: block;
    font-size: 15px;
    font-weight: 600;
    color: #161616;
    margin-bottom: 12px;
    letter-spacing: 0;
    line-height: 1.3;
}

.option-description {
    font-size: 12px;
    color: #666666;
    margin-bottom: 16px;
    font-style: italic;
    line-height: 1.4;
    flex: 1;
}

.option-input-wrapper {
    margin-top: auto;
}

/* 실행 결과 */
.output-container {
    background-color: var(--carbon-gray-10);
    border: 1px solid var(--carbon-gray-20);
    padding: 10px;
    border-radius: 4px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    white-space: pre-wrap;
    max-height: 550px;
    overflow-y: auto;
    width: 900px;
    max-width: 1100px;
}

.output-success {
    color: #333333;
}

.output-error {
    color: #da1e28;
}

/* CLI 명령어 표시 */
.cli-command {
    background-color: #f4f4f4;
    border: 1px solid #e0e0e0;
    border-left: 3px solid #0f62fe;
    padding: 8px 12px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    color: #161616;
    border-radius: 4px;
    margin: 3px 0;
    white-space: nowrap !important;
    overflow-x: auto;
    overflow-wrap: normal !important;
    word-break: normal !important;
    line-height: 1.4;
}

/* Config 편집기 */
.config-editor-container {
    display: flex;
    flex-direction: column;
    gap: 12px;
    margin: 10px 0;
    width: 900px;
    max-width: 1100px;
    height: calc(100vh - 350px);
}

.config-editor-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.config-editor-title {
    font-size: 15px;
    font-weight: 600;
    color: #161616;
}

.config-editor {
    width: 100%;
    height: 98%;
    flex: 1;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    padding: 5px;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    background-color: #ffffff;
    resize: vertical;
}

/* JSON 에디터 내부 텍스트 크기 */
.config-editor .jsoneditor,
.config-editor .jsoneditor-tree,
.config-editor .jsoneditor-text,
.config-editor .ace_editor,
.config-editor div,
.config-editor span,
.config-editor input,
.config-editor textarea {
    font-size: 12px !important;
}

.config-editor * {
    font-size: 12px !important;
}

.config-editor:focus {
    outline: 2px solid #0f62fe;
    outline-offset: -2px;
}

.validate-message {
    padding: 6px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 300;
    text-align: right;
}

.validate-success {
    background-color: #ffffff;
    color: #24a148;
    border: 0px solid #24a148;
}

.validate-error {
    background-color: #ffffff;
    color: #da1e28;
    border: 0px solid #da1e28;
}

.preflight-box {
    width: 900px;
    max-width: 1100px;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    padding: 10px 12px;
    background: #fafafa;
    margin-bottom: 12px;
}

.preflight-item {
    font-size: 12px;
    margin: 2px 0;
}

.preflight-pass {
    color: #24a148;
}

.preflight-fail {
    color: #da1e28;
}

.preflight-warn {
    color: #8a6d00;
}

/* 버튼 비활성화 */
.carbon-btn:disabled {
    background-color: #c6c6c6;
    border-color: #c6c6c6;
    color: #8d8d8d;
    cursor: not-allowed;
}
</style>
"""

# ============================================================================
# 헬퍼 함수
# ============================================================================
def get_config_files() -> List[str]:
    """configs 디렉토리의 config 파일 목록"""
    root = Path(os.getcwd())
    configs_dir = root / "configs"
    
    # configs 디렉토리가 있으면 그 안의 파일들
    if configs_dir.exists() and configs_dir.is_dir():
        configs = sorted([f.name for f in configs_dir.glob("*.json")])
        if configs:
            return configs
    
    # 없으면 루트의 config*.json 파일들
    configs = sorted([f.name for f in root.glob("config*.json")])
    return configs or ["config.json"]


def get_config_path(config_filename: str) -> Path:
    """config 파일의 전체 경로 반환"""
    root = Path(os.getcwd())
    configs_dir = root / "configs"
    
    # configs 디렉토리에 파일이 있는지 확인
    if configs_dir.exists():
        config_path = configs_dir / config_filename
        if config_path.exists():
            return config_path
    
    # 없으면 루트 디렉토리
    return root / config_filename


def log_event(level: str, event: str, detail: str = "", step: Optional[int] = None):
    """VS Code 터미널에서 읽기 쉬운 구조화 로그 출력"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    step_text = f" step={step}" if step is not None else ""
    suffix = f" | {detail}" if detail else ""
    message = f"[{timestamp}] [{level}] [{event}]{step_text}{suffix}"

    # 터미널이 ANSI를 지원하면 level별 색상을 적용한다.
    use_color = sys.stdout.isatty() and os.getenv("NO_COLOR") is None
    if use_color:
        color = LEVEL_COLORS.get(level.upper(), "")
        if color:
            print(f"{color}{message}{ANSI_RESET}")
            return

    print(message)


def _to_cli_flag(opt_name: str) -> str:
    """argparse dest 이름을 CLI long option 형태로 변환"""
    return f"--{opt_name.replace('_', '-')}"


def _has_meaningful_value(value: Any) -> bool:
    """텍스트 옵션 값이 실제 입력값인지 판단"""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _decode_process_line(raw_line: bytes) -> str:
    """프로세스 출력 라인을 OS 로캘을 우선으로 안전하게 디코딩"""
    encodings = []
    preferred = locale.getpreferredencoding(False)
    if preferred:
        encodings.append(preferred)
    encodings.extend(['utf-8', 'cp949'])

    tried = set()
    for enc in encodings:
        if not enc or enc in tried:
            continue
        tried.add(enc)
        try:
            return raw_line.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw_line.decode('utf-8', errors='replace')


def build_cli_command() -> str:
    """선택된 옵션으로 CLI 명령어 생성"""
    if not app_state.selected_command:
        return ""
    
    cmd_parts = ["python", "main.py", app_state.selected_command]
    
    if app_state.selected_options:
        for opt_name, opt_value in app_state.selected_options.items():
            if isinstance(opt_value, bool):
                if opt_value:
                    cmd_parts.append(_to_cli_flag(opt_name))
            elif _has_meaningful_value(opt_value):
                cmd_parts.append(_to_cli_flag(opt_name))
                cmd_parts.append(str(opt_value))
    
    return " ".join(cmd_parts)


def validate_json(json_str: str) -> tuple[bool, str]:
    """JSON 유효성 검사"""
    try:
        json.loads(json_str)
        return True, "✓ JSON 형식이 올바릅니다"
    except json.JSONDecodeError as e:
        return False, f"✗ JSON 오류: {str(e)}"


def scroll_output_to_bottom():
    """실행 로그 영역을 최신 로그(하단)로 자동 스크롤"""
    try:
        ui.run_javascript(
            """
            const el = document.querySelector('.execution-output-container');
            if (el) {
                el.scrollTop = el.scrollHeight;
            }
            """
        )
    except RuntimeError:
        # 다른 탭이 닫혀 NiceGUI 컨텍스트가 무효화된 경우 무시
        pass


def set_execute_button_running_state(is_running: bool):
    """실행 버튼의 로딩 상태/텍스트를 일관되게 갱신"""
    global execute_button, stop_button
    if execute_button:
        if is_running:
            execute_button.text = '실행 중...'
            execute_button.props(add='loading')
            execute_button.props(add='disabled')
        else:
            execute_button.text = '▶ 실행'
            execute_button.props(remove='loading')
            if app_state.preflight_ready and app_state.preflight_confirmed_in_step4:
                execute_button.props(remove='disabled')
            else:
                execute_button.props(add='disabled')
    if stop_button:
        if is_running:
            stop_button.props(remove='disabled')
        else:
            stop_button.props(add='disabled')


def invalidate_execution_readiness(reason: str = ""):
    """실행 준비 점검 상태를 무효화"""
    app_state.preflight_ready = False
    app_state.preflight_confirmed_in_step4 = False
    app_state.preflight_message = ""
    app_state.preflight_items = []
    if reason:
        log_event("INFO", "사전점검 무효화", reason, app_state.step)


def _serialize_editor_content(content: Any) -> str:
    """json_editor content payload를 문자열 JSON으로 정규화"""
    if isinstance(content, dict):
        if 'json' in content:
            return json.dumps(content['json'], indent=2, ensure_ascii=False)
        if 'text' in content:
            return json.dumps(json.loads(content['text']), indent=2, ensure_ascii=False)
    if isinstance(content, str):
        return json.dumps(json.loads(content), indent=2, ensure_ascii=False)
    return json.dumps(content, indent=2, ensure_ascii=False)


def _get_current_config_dict() -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """현재 화면 기준 config 딕셔너리를 반환"""
    try:
        config_content = app_state.config_content
        if not config_content:
            config_file = app_state.selected_options.get('config', 'config.json') if app_state.selected_options else 'config.json'
            config_path = get_config_path(config_file)
            if not config_path.exists():
                return None, f"config 파일이 없습니다: {config_path}"
            config_content = config_path.read_text(encoding='utf-8')

        return json.loads(config_content), None
    except Exception as e:
        return None, f"config 파싱 실패: {e}"


def _find_changed_file_list(target_project: Path) -> Optional[Path]:
    """target_project/.applycrypto 아래 ChangedFileList 파일 탐색"""
    applycrypto_dir = target_project / '.applycrypto'
    if not applycrypto_dir.exists():
        return None
    files = sorted(applycrypto_dir.glob('ChangedFileList_*.txt'))
    return files[0] if files else None


def _changed_file_list_has_target_extensions(changed_file: Path, exts: List[str]) -> bool:
    """ChangedFileList에 지정 확장자 파일이 있는지 확인"""
    try:
        lines = changed_file.read_text(encoding='utf-8-sig').splitlines()
        lowered_exts = [e.lower() for e in exts]
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if any(line.lower().endswith(ext) for ext in lowered_exts):
                return True
        return False
    except Exception:
        return False


def evaluate_execution_readiness() -> Tuple[bool, str, List[Dict[str, str]]]:
    """선택 명령에 필요한 실행 준비물을 점검"""
    command = app_state.selected_command or ""
    items: List[Dict[str, str]] = []
    has_fail = False

    def add_item(status: str, label: str, detail: str):
        nonlocal has_fail
        if status == 'FAIL':
            has_fail = True
        items.append({'status': status, 'label': label, 'detail': detail})

    config_dict, config_err = _get_current_config_dict()
    if config_err:
        add_item('FAIL', 'Config 로드', config_err)
        return False, '✗ 실행 준비 점검 실패 (config 확인 필요)', items

    target_project_str = (config_dict or {}).get('target_project')
    artifact_generation = (config_dict or {}).get('artifact_generation') or {}
    old_code_path_str = artifact_generation.get('old_code_path')
    modification_type = (config_dict or {}).get('modification_type')
    sql_wrapping_type = (config_dict or {}).get('sql_wrapping_type')
    framework_type = (config_dict or {}).get('framework_type')
    access_tables = (config_dict or {}).get('access_tables')
    three_step_config = (config_dict or {}).get('three_step_config')

    target_project = Path(target_project_str) if target_project_str else None
    old_code_path = Path(old_code_path_str) if old_code_path_str else None
    results_dir = (target_project / '.applycrypto' / 'results') if target_project else None

    add_item('PASS' if bool(target_project_str) else 'FAIL', 'target_project 설정값', target_project_str or '설정 필요')
    
    # ✓ target_project 경로 검증 (존재하지 않으면 FAIL)
    target_exists = target_project and target_project.exists()
    add_item('PASS' if target_exists else 'FAIL', 'target_project 경로 존재', 
             f"✓ {str(target_project)}" if target_exists else f"✗ 경로 없음: {str(target_project)}")

    changed_file = _find_changed_file_list(target_project) if target_project and target_project.exists() else None

    # ============ analyze 명령 ============
    if command == 'analyze':
        add_item('PASS' if bool(sql_wrapping_type) else 'FAIL', 'sql_wrapping_type', sql_wrapping_type or '설정 필요')
        add_item('PASS' if bool(framework_type) else 'FAIL', 'framework_type', framework_type or '설정 필요')
        add_item('PASS' if bool(access_tables) else 'FAIL', 'access_tables', '설정됨' if access_tables else '설정 필요')

    # ============ list 명령 ============
    elif command == 'list':
        add_item('PASS' if results_dir and results_dir.exists() else 'FAIL', 'analyze 결과 (.applycrypto/results)', str(results_dir) if results_dir else '경로 없음')

    # ============ modify 명령 ============
    elif command == 'modify':
        add_item('PASS' if bool(sql_wrapping_type) else 'FAIL', 'sql_wrapping_type', sql_wrapping_type or '설정 필요')
        add_item('PASS' if bool(framework_type) else 'FAIL', 'framework_type', framework_type or '설정 필요')
        add_item('PASS' if bool(modification_type) else 'FAIL', 'modification_type', modification_type or '설정 필요')
        
        # modification_type이 TwoStep 또는 ThreeStep인 경우 three_step_config 필수
        if modification_type and ('TwoStep' in str(modification_type) or 'ThreeStep' in str(modification_type)):
            add_item('PASS' if bool(three_step_config) else 'FAIL', 'three_step_config', '설정됨' if three_step_config else '설정 필요')
        
        add_item('PASS' if results_dir and results_dir.exists() else 'FAIL', 'analyze 결과 (.applycrypto/results)', str(results_dir) if results_dir else '경로 없음')

    # ============ generate-spec 명령 ============
    elif command == 'generate-spec':
        add_item('PASS' if changed_file else 'FAIL', 'ChangedFileList', str(changed_file) if changed_file else 'target_project/.applycrypto/ChangedFileList_*.txt 필요')
        if changed_file:
            has_java = _changed_file_list_has_target_extensions(changed_file, ['.java'])
            add_item('PASS' if has_java else 'FAIL', 'ChangedFileList(.java)', '.java 항목 포함' if has_java else '.java 항목이 필요합니다')

    # ============ generate-artifact 명령 ============
    elif command == 'generate-artifact':
        add_item('PASS' if old_code_path_str else 'FAIL', 'artifact_generation.old_code_path', old_code_path_str or '설정 필요')
        add_item('PASS' if old_code_path and old_code_path.exists() else 'FAIL', 'old_code_path 경로', str(old_code_path) if old_code_path else '경로 없음')
        add_item('PASS' if changed_file else 'FAIL', 'ChangedFileList', str(changed_file) if changed_file else 'target_project/.applycrypto/ChangedFileList_*.txt 필요')
        if changed_file:
            has_java_or_xml = _changed_file_list_has_target_extensions(changed_file, ['.java', '.xml'])
            add_item('PASS' if has_java_or_xml else 'FAIL', 'ChangedFileList(.java/.xml)', '.java 또는 .xml 항목 포함' if has_java_or_xml else '.java/.xml 항목이 필요합니다')

    # ============ generate-analysis_report 명령 ============
    elif command == 'generate-analysis_report':
        add_item('PASS' if bool(modification_type) else 'FAIL', 'modification_type', str(modification_type) if modification_type else '설정 필요')
        add_item('PASS' if results_dir and results_dir.exists() else 'FAIL', '.applycrypto/results', str(results_dir) if results_dir else '경로 없음')

    # ============ generate-endpoint_report 명령 ============
    elif command == 'generate-endpoint_report':
        add_item('PASS' if old_code_path_str else 'FAIL', 'artifact_generation.old_code_path', old_code_path_str or '설정 필요')
        add_item('PASS' if old_code_path and old_code_path.exists() else 'FAIL', 'old_code_path 경로', str(old_code_path) if old_code_path else '경로 없음')
        call_graph_path = (results_dir / 'call_graph.json') if results_dir else None
        add_item('PASS' if call_graph_path and call_graph_path.exists() else 'FAIL', 'call_graph.json', str(call_graph_path) if call_graph_path else '경로 없음')

    # ============ generate-ksign-report 명령 ============
    elif command == 'generate-ksign-report':
        table_access_path = (results_dir / 'table_access_info.json') if results_dir else None
        call_graph_path = (results_dir / 'call_graph.json') if results_dir else None
        endpoint_access_path = (target_project / '.applycrypto' / 'endpoint_access.txt') if target_project else None
        add_item('PASS' if table_access_path and table_access_path.exists() else 'FAIL', 'table_access_info.json', str(table_access_path) if table_access_path else '경로 없음')
        add_item('PASS' if call_graph_path and call_graph_path.exists() else 'FAIL', 'call_graph.json', str(call_graph_path) if call_graph_path else '경로 없음')
        add_item('PASS' if changed_file else 'FAIL', 'ChangedFileList', str(changed_file) if changed_file else 'modify 결과 파일 필요')
        add_item('PASS' if endpoint_access_path and endpoint_access_path.exists() else 'FAIL', 'endpoint_access.txt', str(endpoint_access_path) if endpoint_access_path else '경로 없음')

    ok = not has_fail
    fail_count = sum(1 for item in items if item['status'] == 'FAIL')
    summary = f"✓ 실행 준비 점검 통과 ({len(items)}개 항목)" if ok else f"✗ 실행 준비 점검 실패 ({fail_count}개 누락/오류)"
    return ok, summary, items


def run_execution_precheck(refresh_ui: bool = True, confirm_for_step4: bool = False):
    """실행 준비 점검 수행 및 상태 반영"""
    ok, summary, items = evaluate_execution_readiness()
    app_state.preflight_ready = ok
    app_state.preflight_confirmed_in_step4 = bool(confirm_for_step4 and ok)
    app_state.preflight_message = summary
    app_state.preflight_items = items

    log_event("INFO", "점검 완료", f"{summary} / Step4 확인={app_state.preflight_confirmed_in_step4}", app_state.step)
    if refresh_ui:
        update_ui()
    return ok


def on_config_editor_change(e):
    """Config 편집 변경 시 상태 반영"""
    try:
        app_state.config_content = _serialize_editor_content(e.content)
        log_event("CLICK", "Editor 변경", f"Config 내용 변경 ({len(app_state.config_content)} bytes)", app_state.step)
        invalidate_execution_readiness("Config 수정")
    except Exception as ex:
        log_event("ERROR", "Editor 오류", str(ex), app_state.step)


def get_command_options_from_cli() -> Dict[str, Dict[str, Any]]:
    """CLI Controller에서 명령어 정보 가져오기"""
    try:
        controller = CLIController()
        parser = controller.parser
        
        commands = {}
        
        # subparsers에서 명령어 추출
        if hasattr(parser, '_subparsers'):
            for action in parser._subparsers._actions:
                if isinstance(action, argparse._SubParsersAction):
                    cmd_help_map = {
                        choice.dest: (choice.help or "")
                        for choice in getattr(action, "_choices_actions", [])
                    }
                    for cmd_name, cmd_parser in action.choices.items():
                        # 명령어 설명 가져오기
                        description = cmd_parser.description or cmd_help_map.get(cmd_name, "")
                        
                        # 옵션 추출
                        options = {}
                        for arg_action in cmd_parser._actions:
                            if arg_action.dest in ['help', 'command']:
                                continue
                            
                            opt_name = arg_action.dest
                            
                            # 타입 결정
                            if isinstance(arg_action, argparse._StoreTrueAction):
                                opt_type = "bool"
                            elif opt_name == "config":
                                opt_type = "file"
                            else:
                                opt_type = "text"
                            
                            # 레이블 생성 (help 텍스트 간소화)
                            label = arg_action.help or opt_name
                            if len(label) > 50:
                                label = label[:47] + "..."
                            
                            options[opt_name] = {
                                "type": opt_type,
                                "label": label
                            }
                        
                        commands[cmd_name] = {
                            "description": description,
                            "options": options
                        }
        
        return commands
    except Exception as e:
        log_event("ERROR", "CLI 로딩실패", str(e))
        # 폴백: 기본 명령어만 반환
        return {
            "analyze": {
                "description": "프로젝트를 분석하여 소스 파일, Call Graph, DB 접근 정보를 수집합니다",
                "options": {
                    "config": {"type": "file", "label": "Config 파일"},
                    "cached": {"type": "bool", "label": "캐시 사용"}
                }
            },
            "list": {
                "description": "수집된 정보를 조회합니다",
                "options": {
                    "config": {"type": "file", "label": "Config 파일"}
                }
            },
            "modify": {
                "description": "식별된 파일에 암복호화 코드를 삽입합니다",
                "options": {
                    "config": {"type": "file", "label": "Config 파일"},
                    "dry-run": {"type": "bool", "label": "미리보기"},
                    "debug": {"type": "bool", "label": "디버그 모드"}
                }
            }
        }


# ============================================================================
# UI 컴포넌트
# ============================================================================
def create_top_header():
    """상단 고정 헤더(TOP) 렌더링"""
    with ui.header().classes('top-header'):
        ui.html(f'<img class="top-header-ci-logo" src="{CI_LOGO_WEB_PATH}" alt="CI logo">')
        ui.html('<div><span class="top-header-logo">ApplyCrypto</span><span class="top-header-title">암호화 적용 자동화 도구</span></div>')


def add_new_session():
    """새 작업 탭을 생성하고 즉시 전환"""
    session_id = create_session()
    switch_session(session_id)


def close_session(session_id: str):
    """작업 탭 닫기; 실행 중이면 종료 확인 다이얼로그를 표시"""
    global current_session_id, app_state

    if session_id not in session_states:
        return

    if len(session_order) <= 1:
        ui.notify('최소 1개의 탭은 유지되어야 합니다.', type='warning')
        return

    def perform_close(terminate_process: bool = True):
        """탭 종료 실제 수행"""
        nonlocal session_id
        global current_session_id, app_state

        if session_id not in session_states:
            return

        state = session_states[session_id]
        if terminate_process and state.current_process is not None:
            try:
                state.current_process.terminate()
                log_event("UI", "탭 프로세스 종료", f"탭 실행 중단: {session_id}")
            except (ProcessLookupError, OSError):
                pass
            state.current_process = None
            state.is_executing = False

        removing_index = session_order.index(session_id)
        session_order.remove(session_id)
        del session_states[session_id]
        log_event("UI", "탭 종료", f"탭 종료: {session_id}")

        if current_session_id == session_id:
            next_index = max(0, removing_index - 1)
            next_session_id = session_order[next_index]
            current_session_id = next_session_id
            app_state = session_states[next_session_id]

        update_ui()

    state = session_states[session_id]
    if state.current_process is not None or state.is_executing:
        with ui.dialog() as dialog, ui.card().style('min-width: 360px;'):
            ui.label('실행 중 탭 종료 확인')
            ui.label('현재 탭이 실행 중입니다. 종료하면 실행이 중단됩니다. 계속하시겠습니까?').style('font-size: 13px; color: #525252;')

            with ui.row().style('justify-content: flex-end; width: 100%; gap: 8px; margin-top: 8px;'):
                ui.button('아니오', on_click=dialog.close).classes('carbon-btn-secondary').props('type=button')

                def confirm_close():
                    dialog.close()
                    perform_close(terminate_process=True)

                ui.button('예', on_click=confirm_close).classes('carbon-btn').props('type=button')

        dialog.open()
        return

    perform_close(terminate_process=False)


def rename_session(session_id: str):
    """탭 이름 변경 다이얼로그 오픈"""
    state = session_states.get(session_id)
    if state is None:
        return

    with ui.dialog() as dialog, ui.card().style('min-width: 320px;'):
        ui.label('탭 이름 변경')
        name_input = ui.input('탭 이름', value=state.session_name).props('autofocus').style('width: 100%;')

        with ui.row().style('justify-content: flex-end; width: 100%; gap: 8px;'):
            ui.button('취소', on_click=dialog.close).classes('carbon-btn-secondary').props('type=button')

            def apply_name():
                new_name = (name_input.value or '').strip()
                if not new_name:
                    ui.notify('탭 이름은 비워둘 수 없습니다.', type='warning')
                    return
                state.session_name = new_name
                state.session_name_customized = True
                log_event("UI", "탭이름 변경", f"탭 이름 변경: {session_id} -> {new_name}")
                dialog.close()
                update_ui()

            ui.button('저장', on_click=apply_name).classes('carbon-btn').props('type=button')

    dialog.open()


def create_session_tabs(container):
    """작업 탭 목록 렌더링"""
    container.clear()

    with container:
        with ui.row().classes('session-tabs-wrap').style('gap: 6px; flex-wrap: nowrap; overflow-x: auto; width: 100%;'):
            for session_id in session_order:
                state = session_states[session_id]
                label = state.session_name
                is_active = session_id == current_session_id
                shell_class = 'session-tab-shell active' if is_active else 'session-tab-shell'
                if state.is_executing:
                    shell_class += ' running'

                with ui.row().classes(shell_class).style('flex-wrap: nowrap; gap: 0;'):
                    tab_background = '#ffffff' if is_active else 'linear-gradient(180deg, #d9e2ef 0%, #c8d4e5 100%)'
                    tab_btn = ui.button(label, on_click=lambda e, sid=session_id: switch_session(sid)).classes('session-tab').props('type=button flat no-caps').style(
                        f'background: {tab_background} !important;'
                    )
                    tab_btn.on('dblclick', lambda e, sid=session_id: rename_session(sid))

                    close_btn = ui.button('×', on_click=lambda e, sid=session_id: close_session(sid)).classes('session-close-btn').props('type=button flat dense round unelevated no-caps')
                    close_btn.tooltip('탭 닫기')

            new_btn = ui.button('+', on_click=add_new_session).classes('session-add-btn').props('type=button flat dense no-caps unelevated')


def create_left_nav(container):
    """좌측 내비게이션 바(LNB) 렌더링"""
    container.clear()
    
    with container:
        with ui.column().classes('left-nav').style('height: 100% !important; min-height: 100% !important; display: flex !important; flex-direction: column !important;'):
            # 진행 상황
            with ui.column().classes('nav-section').style('flex-shrink: 0;'):
                ui.html('<div class="nav-title">진행 상황</div>')
                
                steps = [
                    {"num": 1, "name": "Step 1: 명령 선택 "},
                    {"num": 2, "name": "Step 2: 옵션 설정 "},
                    {"num": 3, "name": "Step 3: Config 확인 "},
                    {"num": 4, "name": "Step 4: 실행 "}
                ]
                
                for step in steps:
                    if step["num"] < app_state.step:
                        class_name = "nav-item completed"
                        prefix = "✓ "
                    elif step["num"] == app_state.step:
                        class_name = "nav-item current"
                        prefix = "▶ "
                    else:
                        class_name = "nav-item pending"
                        prefix = "○ "
                    
                    ui.html(f'<div class="{class_name}">{prefix}{step["name"]}</div>')
            
            # 선택된 명령
            if app_state.selected_command:
                with ui.column().classes('nav-section').style('flex-shrink: 0;'):
                    ui.html('<div class="nav-title">선택된 명령</div>')
                    ui.html(f'<div style="padding: 0 20px; font-size: 13px; color: #0f62fe; font-weight: 500;">{app_state.selected_command}</div>')
            
            # 리셋 버튼
            with ui.column().classes('nav-section').style('display: flex; align-items: center;'):
                # ui.button('🔄 처음으로', on_click=reset_app).classes('carbon-btn').style('width: 90%; margin: 0 auto;')


def create_step_1(container):
    """Step 1: 명령 선택"""
    container.clear()
    
    with container:
        with ui.column().classes('main-content'):
            ui.html('<h1>명령 선택</h1>')
            ui.html('<p>실행할 작업을 선택하세요.</p>')
            ui.html('<hr>')
            
            commands = get_command_options_from_cli()
            
            for cmd_name, cmd_info in commands.items():
                with ui.card().classes('command-card').style('display: flex; flex-direction: row; align-items: center; width: 100%;'):
                    ui.html(f'<div class="command-name">{cmd_name}</div>')
                    ui.html(f'<div class="command-description">{cmd_info["description"]}</div>')
                    ui.button('선택', on_click=lambda e, c=cmd_name: select_command(c)).classes('carbon-btn')


def create_step_2(container):
    """Step 2: 옵션 설정"""
    container.clear()
    
    with container:
        with ui.column().classes('main-content'):
            ui.html('<h1>옵션 설정</h1>')

            cli_command = build_cli_command()
            ui.html(f'<div class="cli-command"><span style="font-size: 12px; font-weight: 500;">실행될 명령어</span> : {cli_command}</div>')
                          
            commands = get_command_options_from_cli()
            if app_state.selected_command:
                options = commands[app_state.selected_command]["options"]
            else:
                options = {}
            
            # 옵션 입력 필드 저장
            option_inputs = {}
            
            with ui.element('div').classes('options-container'):
                for opt_name, opt_info in options.items():
                    with ui.column().classes('option-group'):
                        # 옵션 이름을 더 읽기 쉽게 변환
                        display_name = opt_name.replace('-', ' ').replace('_', ' ').title()
                        label_text = opt_info.get("label", display_name)
                        
                        # 레이블과 설명 분리
                        if "(" in label_text and ")" in label_text:
                            main_label = label_text.split("(")[0].strip()
                            description = "(" + label_text.split("(")[1]
                        else:
                            main_label = label_text
                            description = f"(기본값: {opt_name})"
                        
                        ui.html(f'<div class="option-title">{main_label}</div>')
                        ui.html(f'<div class="option-description">{description}</div>')
                        with ui.element('div').classes('option-input-wrapper'):
                            current_value = app_state.selected_options.get(opt_name) if app_state.selected_options else None

                            if opt_info["type"] == "file":
                                config_files = get_config_files()
                                selected_config = current_value if current_value in config_files else (config_files[0] if config_files else None)
                                option_inputs[opt_name] = ui.select(
                                    options=config_files,
                                    value=selected_config
                                ).style('width: 100%;')
                            elif opt_info["type"] == "bool":
                                with ui.row().style('align-items: center;'):
                                    option_inputs[opt_name] = ui.checkbox('', value=bool(current_value)).style('margin-right: 8px;')
                                    ui.label(main_label).style('font-size: 13px; color: #525252;')
                            else:
                                option_inputs[opt_name] = ui.input(
                                    value=str(current_value) if current_value is not None else '',
                                    placeholder=main_label
                                ).style('width: 100%;')
            
            ui.html('<hr>')
            
            with ui.row().style('gap: 12px;'):
                ui.button('← 이전', on_click=go_prev).classes('carbon-btn-secondary').props('type=button')
                ui.button('다음 →', on_click=lambda: go_next(option_inputs)).classes('carbon-btn').props('type=button')


def create_step_3(container):
    """Step 3: Config 확인 및 편집"""
    container.clear()
    
    with container:
        with ui.column().classes('main-content'):
            ui.html('<h1>Config 확인 및 편집</h1>')
            
            cli_command = build_cli_command()
            ui.html(f'<div class="cli-command"><span style="font-size: 12px; font-weight: 500;">실행될 명령어</span> : {cli_command}</div>')
             
            # Config 파일 선택 및 편집
            config_file = app_state.selected_options.get('config', 'config.json') if app_state.selected_options else 'config.json'
            config_path = get_config_path(config_file)
            
            # Config 파일 변경 감지: 로드된 파일과 현재 선택된 파일이 다르면 다시 로드
            if app_state.loaded_config_file != config_file:
                app_state.config_content = ""
                app_state.loaded_config_file = None
                log_event("INFO", "config 재로딩 필요", f"선택 파일 변경: {config_file}", app_state.step)
            
            # Config 파일 내용 로드
            config_dict = {}
            if not app_state.config_content and config_path.exists():
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        app_state.config_content = f.read()
                        app_state.loaded_config_file = config_file  # 로드된 파일명 기록
                        config_dict = json.loads(app_state.config_content)
                        log_event("INFO", "config 로딩완료", f"Config 로드 완료: {config_file} ({len(app_state.config_content)} bytes)", app_state.step)
                except Exception as e:
                    app_state.config_content = f'{{"error": "파일을 읽을 수 없습니다: {str(e)}"}}'
                    config_dict = {"error": f"파일을 읽을 수 없습니다: {str(e)}"}
                    log_event("ERROR", "config_로딩오류", str(e), app_state.step)
            elif app_state.config_content:
                try:
                    config_dict = json.loads(app_state.config_content)
                    if not app_state.loaded_config_file:
                        app_state.loaded_config_file = config_file  # 메모리 로드된 파일명 기록
                except:
                    config_dict = {}
            
            # Config 편집기
            with ui.element('div').classes('config-editor-container'):
                with ui.element('div').classes('config-editor-header'):
                    ui.html(f'<div class="config-editor-title">Config 파일 편집: {config_file}</div>')
                    # Validate 버튼을 헤더에 배치
                    validate_btn_temp = ui.button('✓ Validate').classes('carbon-btn').style('padding: 3px 12px;').props('type=button')
                
                # JSON 편집기 (신택스 하이라이팅)
                editor = ui.json_editor({'content': {'json': config_dict}})
                editor.classes('config-editor')
                editor.on('change', on_config_editor_change)
                
                # 전역 editor 참조 저장 (validate 시 사용)
                global json_editor_ref
                json_editor_ref = editor
                
            # Validate 메시지와 버튼 배치
            with ui.row().style('width: 900px; max-width: 1100px; justify-content: space-between; align-items: center; margin-top: 16px;'):
                # 왼쪽: 버튼들
                with ui.row().style('gap: 8px;'):
                    ui.button('← 이전', on_click=go_prev).classes('carbon-btn-secondary').props('type=button')
                    execute_btn = ui.button('다음 →', on_click=go_next_to_execute).classes('carbon-btn').props('type=button')
                    if not app_state.config_validated:
                        execute_btn.props('disabled')
                
                async def on_validate_click():
                    await validate_json_editor(editor, validate_msg, execute_btn)
                
                validate_btn_temp.on_click(on_validate_click)
                
                # 오른쪽: Validate 메시지
                validate_msg = ui.element('div').style('text-align: right;')
                if app_state.validation_message:
                    msg_class = 'validate-success' if (app_state.config_validated and app_state.preflight_ready) else 'validate-error'
                    with validate_msg:
                        ui.html(f'<div class="validate-message {msg_class}">{app_state.validation_message}</div>')
                        for item in app_state.preflight_items or []:
                            if item.get('status') in {'FAIL', 'WARN'}:
                                item_class = 'preflight-warn' if item.get('status') == 'WARN' else 'preflight-fail'
                                status_icon = '!' if item.get('status') == 'WARN' else '✗'
                                ui.html(f'<div class="preflight-item {item_class}" style="margin-top: 6px; text-align: right;">{status_icon} {item.get("label", "")}: {item.get("detail", "")}</div>')


def create_step_4(container):
    """Step 4: 실행"""
    container.clear()
    
    with container:
        with ui.column().classes('main-content'):
            ui.html('<h1>실행</h1>')

            # CLI 명령어와 실행 버튼을 같은 행에 배치
            with ui.row().style('width: 100%; align-items: center; gap: 16px; margin: 16px 0;'):
                # 왼쪽: CLI 명령어
                cli_command = build_cli_command()
                ui.html(f'<div class="cli-command" style="flex: 1;"><span style="font-size: 12px; font-weight: 500;">실행될 명령어</span> : {cli_command}</div>')

                # 실행 준비 점검 버튼
                ui.button('실행준비 점검', on_click=lambda: run_execution_precheck(refresh_ui=True, confirm_for_step4=True)).classes('carbon-btn-secondary').props('type=button')
                
                # 오른쪽: 실행 버튼 - 이벤트 전파 방지
                global execute_button
                execute_button = ui.button('▶ 실행', on_click=execute_command).classes('carbon-btn')
                # 폼 제출 방지
                execute_button.props('type=button')
                if app_state.is_executing:
                    set_execute_button_running_state(True)
                elif not (app_state.preflight_ready and app_state.preflight_confirmed_in_step4):
                    execute_button.props('disabled')

                # 중지 버튼
                global stop_button
                stop_button = ui.button('⬛ 중지', on_click=stop_command).classes('carbon-btn-secondary')
                stop_button.props('type=button')
                if not app_state.is_executing:
                    stop_button.props('disabled')

            # 실행 준비 점검 결과
            if app_state.preflight_message or app_state.preflight_items:
                with ui.element('div').classes('preflight-box'):
                    msg_class = 'preflight-pass' if app_state.preflight_ready else 'preflight-fail'
                    ui.html(f'<div class="preflight-item {msg_class}">{app_state.preflight_message}</div>')
                    for item in app_state.preflight_items or []:
                        status = item.get('status', 'PASS')
                        status_icon = '✓' if status == 'PASS' else ('!' if status == 'WARN' else '✗')
                        item_class = 'preflight-pass' if status == 'PASS' else ('preflight-warn' if status == 'WARN' else 'preflight-fail')
                        ui.html(f'<div class="preflight-item {item_class}">{status_icon} {item.get("label", "")}: {item.get("detail", "")}</div>')

            output_container = ui.column().classes('output-container execution-output-container')
            
            # 실행 결과를 표시할 레이블 (동적 업데이트용)
            global output_label, error_label, status_label
            with output_container:
                status_label = ui.label('').style('font-size: 12px; font-weight: 400; margin-bottom: 4px; color: #0f62fe;')
                output_label = ui.label('').classes('output-success').style('white-space: pre-wrap; font-family: monospace;')
                error_label = ui.label('').classes('output-error').style('white-space: pre-wrap; font-family: monospace;')
                
                # 이전 실행 결과가 있으면 표시 (단, 텍스트만 설정하고 이벤트 트리거 안함)
                if app_state.execution_output:
                    output_label.text = app_state.execution_output
                if app_state.execution_error:
                    error_label.text = app_state.execution_error
                if app_state.execution_output or app_state.execution_error:
                    scroll_output_to_bottom()
            
            ui.html('<hr>')
            
            with ui.row().style('gap: 12px;'):
                ui.button('← 이전', on_click=go_prev).classes('carbon-btn-secondary').props('type=button')
                ui.button('🔄 처음으로', on_click=reset_app).classes('carbon-btn').props('type=button')


# ============================================================================
# 이벤트 핸들러
# ============================================================================
def select_command(cmd_name: str):
    """CLI 명령을 선택하고 Step 2로 전환"""
    log_event("CLICK", "명령 선택", f"명령 선택: {cmd_name}", app_state.step)
    if not app_state.session_name_customized:
        app_state.session_name = cmd_name
    app_state.selected_command = cmd_name
    invalidate_execution_readiness("명령 변경")
    prev_step = app_state.step
    app_state.step = 2
    log_event("STEP", "단계 변경", f"{prev_step} -> {app_state.step} (옵션 설정)", app_state.step)
    update_ui()


def go_prev():
    """현재 단계에서 이전 단계로 이동"""
    prev_step = app_state.step
    app_state.step = max(1, app_state.step - 1)
    log_event("CLICK", "이전 클릭", f"이전 단계 이동: {prev_step} -> {app_state.step}", app_state.step)
    update_ui()


def go_next(option_inputs: Optional[Dict] = None):
    """옵션 값을 저장하고 다음 단계로 이동"""
    if option_inputs:
        # 옵션 값 저장
        if app_state.selected_options is None:
            app_state.selected_options = {}
        
        # config 파일이 변경되었는지 확인 - 변경되면 config_content 초기화
        old_config_file = app_state.selected_options.get('config')
        for opt_name, input_widget in option_inputs.items():
            if hasattr(input_widget, 'value'):
                app_state.selected_options[opt_name] = input_widget.value
        
        new_config_file = app_state.selected_options.get('config')
        if old_config_file != new_config_file:
            # config 파일이 변경되었으므로 로드된 내용 초기화
            app_state.config_content = ""
            app_state.loaded_config_file = None
            log_event("INFO", "config 변경", f"Config 파일 변경: {old_config_file} -> {new_config_file}", app_state.step)
            invalidate_execution_readiness("Config 파일 변경")
        else:
            log_event("INFO", "옵션 저장", f"옵션 저장 완료: {list(app_state.selected_options.keys())}", app_state.step)
            invalidate_execution_readiness("옵션 변경")
    
    prev_step = app_state.step
    app_state.step = min(4, app_state.step + 1)
    log_event("CLICK", "다음 클릭", f"다음 단계 이동: {prev_step} -> {app_state.step}", app_state.step)
    update_ui()


def go_next_to_execute():
    """실행 단계로 이동"""
    prev_step = app_state.step
    # Step 4 재진입 시 이전 실행 결과를 초기화하여 stale 로그 노출 방지
    app_state.execution_output = ""
    app_state.execution_error = ""
    app_state.preflight_confirmed_in_step4 = False
    app_state.step = 4
    log_event("CLICK", "실행단계 이동", f"실행 단계 이동: {prev_step} -> 4", app_state.step)
    update_ui()


async def validate_json_editor(editor, validate_msg, execute_btn):
    """Config JSON 유효성 검사 (json_editor용)"""
    try:
        log_event("CLICK", "설정검증 시작", "Config 검증 시작", app_state.step)

        # 현재 editor 상태를 정식 API로 동기화
        current_content = await editor.run_editor_method('get')
        app_state.config_content = _serialize_editor_content(current_content)
        log_event("INFO", "config 동기화 완료", f"에디터 내용 동기화 완료 ({len(app_state.config_content)} bytes)", app_state.step)
        
        # json_editor는 이미 유효한 JSON만 허용하므로 항상 성공
        is_valid = True
        message = "✓ JSON 형식이 올바릅니다"
        
        app_state.config_validated = is_valid
        
        # ✓ 현재 config_content로 preflight 점검 실행
        # (on_config_editor_change에서 이미 최신 내용으로 업데이트됨)
        run_execution_precheck(refresh_ui=False, confirm_for_step4=False)
        failed_labels = [item.get('label', '') for item in app_state.preflight_items or [] if item.get('status') == 'FAIL']
        warn_labels = [item.get('label', '') for item in app_state.preflight_items or [] if item.get('status') == 'WARN']
        detail_suffix = ''
        if failed_labels:
            detail_suffix = f" / 실패: {', '.join(failed_labels)}"
        elif warn_labels:
            detail_suffix = f" / 확인: {', '.join(warn_labels)}"
        app_state.validation_message = f"{message} / {app_state.preflight_message}{detail_suffix}" if app_state.preflight_message else message
        
        # 메시지 업데이트
        validate_msg.clear()
        msg_class = 'validate-success' if app_state.preflight_ready else 'validate-error'
        with validate_msg:
            ui.html(f'<div class="validate-message {msg_class}">{app_state.validation_message}</div>')
        
        # preflight이 PASS인 경우만 실행 버튼 활성화
        if app_state.preflight_ready:
            execute_btn.props(remove='disabled')
            log_event("INFO", "설정검증 성공", "다음 버튼 활성화 (사전 점검 통과)", app_state.step)
        else:
            execute_btn.props(add='disabled')
            log_event("WARN", "설정검증 부분성공", "다음 버튼 비활성화 (사전 점검 실패)", app_state.step)
    except Exception as e:
        app_state.config_validated = False
        app_state.validation_message = f"✗ 오류: {str(e)}"
        execute_btn.props(add='disabled')
        log_event("ERROR", "설정검증 실패", str(e), app_state.step)


def reset_app():
    """현재 세션 상태를 전부 초기화하고 Step 1로 복귀"""
    log_event("CLICK", "앱 초기화", f"앱 초기화: {app_state.step} -> 1", app_state.step)
    app_state.step = 1
    app_state.selected_command = None
    app_state.selected_options = {}
    app_state.config_content = ""
    app_state.loaded_config_file = None
    app_state.config_validated = False
    app_state.validation_message = ""
    app_state.execution_output = ""
    app_state.execution_error = ""
    app_state.is_executing = False
    app_state.preflight_ready = False
    app_state.preflight_confirmed_in_step4 = False
    app_state.preflight_message = ""
    app_state.preflight_items = []
    update_ui()


async def stop_command():
    """실행 중인 프로세스 강제 종료"""
    state = app_state
    if state.current_process is not None:
        try:
            state.current_process.terminate()
            log_event("CLICK", "중지 클릭", f"실행 중지 요청: 탭 {state.session_id}", state.step)
        except (ProcessLookupError, OSError):
            pass
        state.current_process = None
        if current_session_id == state.session_id:
            set_execute_button_running_state(False)
    else:
        log_event("WARN", "중지요청 무시", f"중지할 실행 프로세스 없음 (탭={state.session_id})", state.step)


async def execute_command():
    """명령 실행 (편집된 config 사용)"""
    state = app_state
    session_id = state.session_id

    if state.is_executing:
        log_event("WARN", "실행요청 무시", f"이미 실행 중이라 요청 무시 (탭={session_id})", state.step)
        return

    if not state.preflight_ready or not state.preflight_confirmed_in_step4:
        log_event("WARN", "실행요청 차단", f"실행 차단: 사전점검={state.preflight_ready}, Step4확인={state.preflight_confirmed_in_step4}, 탭={session_id}", state.step)
        state.execution_error = "Step 4에서 '실행준비 점검' 버튼을 먼저 눌러 확인하세요."
        if error_label and current_session_id == session_id:
            error_label.text = state.execution_error
        else:
            if current_session_id == session_id:
                update_ui()
        return

    state.is_executing = True
    log_event("CLICK", "실행 클릭", f"명령 실행 시작 (탭={session_id})", state.step)
    state.step = 4

    # 새 실행 시작 시 이전 로그를 즉시 초기화
    state.execution_output = ""
    state.execution_error = ""
    if output_label and current_session_id == session_id:
        output_label.text = ""
    if error_label and current_session_id == session_id:
        error_label.text = ""
    
    try:
        if not state.selected_command:
            state.execution_error = "선택된 명령이 없습니다. Step 1에서 명령을 먼저 선택하세요."
            log_event("ERROR", "실행 중단", f"선택된 명령 없음 (탭={session_id})", state.step)
            if error_label and current_session_id == session_id:
                error_label.text = state.execution_error
            else:
                if current_session_id == session_id:
                    update_ui()
            state.is_executing = False
            if current_session_id == session_id:
                set_execute_button_running_state(False)
            return

        if status_label and current_session_id == session_id:
            status_label.text = "실행 중..."
        if current_session_id == session_id:
            set_execute_button_running_state(True)

        # 편집된 config를 임시 파일로 저장
        config_file = state.selected_options.get('config', 'config.json') if state.selected_options else 'config.json'
        config_stem = Path(config_file).name
        temp_config_name = f".temp_{session_id}_{int(datetime.now().timestamp() * 1000)}_{config_stem}"
        temp_config_path = Path(os.getcwd()) / temp_config_name
        
        if state.config_content:
            with open(temp_config_path, 'w', encoding='utf-8') as f:
                f.write(state.config_content)
        
        # 명령 구성
        cmd = ["python", "main.py", state.selected_command]
        
        if state.selected_options:
            for opt_name, opt_value in state.selected_options.items():
                if opt_name == 'config':
                    # 임시 config 파일 사용
                    cmd.append(_to_cli_flag(opt_name))
                    cmd.append(str(temp_config_path))
                elif isinstance(opt_value, bool):
                    if opt_value:
                        cmd.append(_to_cli_flag(opt_name))
                else:
                    if _has_meaningful_value(opt_value):
                        cmd.append(_to_cli_flag(opt_name))
                        cmd.append(str(opt_value).strip())

        log_event("RUN", "실행 시작", f"명령 실행: 탭={session_id} | {' '.join(cmd)}", state.step)

        # 실행: stdout/stderr를 실시간 스트리밍하여 브라우저에 즉시 반영
        child_env = os.environ.copy()
        child_env['PYTHONUNBUFFERED'] = '1'
        child_env['PYTHONIOENCODING'] = 'utf-8'
        child_env['PYTHONUTF8'] = '1'
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=os.getcwd(),
            env=child_env,
        )
        state.current_process = process

        streamed_lines = 0
        state.execution_output = ""
        while True:
            if process.stdout is None:
                break
            raw_line = await process.stdout.readline()
            if not raw_line:
                break

            line = _decode_process_line(raw_line)
            state.execution_output += line
            streamed_lines += 1

            if current_session_id == session_id and output_label:
                output_label.text = state.execution_output
            if current_session_id == session_id and status_label:
                status_label.text = f"실행 중... ({streamed_lines}줄)"
            if current_session_id == session_id:
                scroll_output_to_bottom()
            await asyncio.sleep(0)

        returncode = await process.wait()
        state.current_process = None
        log_event("RUN", "실행 종료", f"명령 종료: 탭={session_id} | 반환코드={returncode}", state.step)

        if returncode == 0:
            state.execution_error = ""
        elif returncode == -15 or (returncode == 1 and state.current_process is None):
            state.execution_error = "실행이 중지되었습니다."
        else:
            state.execution_error = f"명령 실행 실패 (exit code: {returncode})"

        if temp_config_path.exists():
            temp_config_path.unlink()
        
        log_event("INFO", "실행결과 저장", f"실행 결과 캐시 저장 완료 (탭={session_id})", state.step)
        log_event("INFO", "UI 갱신", f"Step4 결과 영역 갱신 (탭={session_id})", state.step)

        # Step 4를 유지한 채 결과 영역만 갱신
        state.step = 4
        if status_label and current_session_id == session_id:
            status_label.text = "실행 완료"
        if output_label and current_session_id == session_id:
            output_label.text = state.execution_output
        if error_label and current_session_id == session_id:
            error_label.text = state.execution_error
        if current_session_id == session_id:
            scroll_output_to_bottom()

        # 초기 로딩 직후처럼 레이블이 아직 없는 경우에만 전체 렌더링
        if current_session_id == session_id and not (status_label and output_label and error_label):
            update_ui()

        state.is_executing = False
        if current_session_id == session_id:
            set_execute_button_running_state(False)

        if state.execution_error:
            if "중지" in state.execution_error:
                log_event("RUN", "실행 완료", f"실행 중지됨 (탭={session_id})", state.step)
            else:
                log_event("RUN", "실행 완료", f"실행 실패: {state.execution_error} (탭={session_id})", state.step)
        else:
            log_event("RUN", "실행 완료", f"실행 성공 (탭={session_id})", state.step)
        
    except Exception as e:
        log_event("ERROR", "실행 예외", f"실행 예외 발생: 탭={session_id} | {str(e)}", state.step)
        state.current_process = None
        state.execution_error = str(e)
        state.step = 4
        if status_label and current_session_id == session_id:
            status_label.text = "실행 실패"
        if error_label and current_session_id == session_id:
            error_label.text = state.execution_error
        else:
            if current_session_id == session_id:
                update_ui()
        if current_session_id == session_id:
            scroll_output_to_bottom()
        state.is_executing = False
        if current_session_id == session_id:
            set_execute_button_running_state(False)


def update_ui():
    """현재 세션 상태에 맞게 탭·LNB·메인 컨텐츠를 전체 재렌더링"""
    if session_tabs_container is not None:
        create_session_tabs(session_tabs_container)
    create_left_nav(left_nav_container)
    
    if app_state.step == 1:
        create_step_1(main_content_container)
    elif app_state.step == 2:
        create_step_2(main_content_container)
    elif app_state.step == 3:
        create_step_3(main_content_container)
    elif app_state.step == 4:
        create_step_4(main_content_container)


def create_ui():
    """NiceGUI 앱의 레이아웃(헤더·탭·LNB·메인)을 초기 구성"""
    global left_nav_container, main_content_container, session_tabs_container

    log_event("UI", "UI 초기화", "UI 초기화 시작")
    ensure_default_session()

    app.add_static_files(UI_ASSETS_ROUTE, str(UI_ASSETS_DIR))
    
    # CSS 추가
    ui.add_head_html(CARBON_CSS)
    
    # TOP 헤더
    create_top_header()

    # 탭 탭 영역
    session_tabs_container = ui.column().style('padding: 0; margin: 0; width: 100%;')
    create_session_tabs(session_tabs_container)
    
    # 콘텐츠 영역
    with ui.row().classes('content-wrapper'):
        # 좌측 LNB
        left_nav_container = ui.column().style('padding: 0; margin: 0; width: 240px; min-width: 240px; height: 100%; min-height: 100%;')
        
        # 우측 Main
        main_content_container = ui.column().style('padding: 0; margin: 0; flex: 1; width: 100%; height: 100%; min-height: 100%;')
    
    # 초기 UI 렌더링
    update_ui()


# ============================================================================
# 실행
# ============================================================================
if __name__ == "__main__":
    log_event("UI", "서버 시작", "NiceGUI 서버 시작")
    create_ui()
    try:
        ui.run(
            title="ApplyCrypto - 암호화 적용 자동화 도구",
            host="127.0.0.1",
            port=8502,
            reload=False,
            show=True
        )
    except KeyboardInterrupt:
        for session_id in list(session_order):
            state = session_states.get(session_id)
            if state is None or state.current_process is None:
                continue
            try:
                state.current_process.terminate()
                log_event("UI", "하위프로세스 종료", f"Ctrl+C로 탭 프로세스 종료: {session_id}")
            except (ProcessLookupError, OSError):
                pass
            state.current_process = None
        log_event("UI", "서버 종료", "KeyboardInterrupt 수신으로 서버 종료")

# Made with Bob
