"""
Generator 모듈

암복호화 관련 코드를 자동 생성하는 모듈입니다.
- TypeHandlerGenerator: MyBatis Type Handler 생성 (해당 모듈 존재 시)
- CheckJoinRunner: access_tables 기준 JOIN 대상 테이블/컬럼 분석 (check_join 명령)
"""

from .check_join import CheckJoinRunner

try:
    from .type_handler_generator import TypeHandlerGenerator
    __all__ = ["TypeHandlerGenerator", "CheckJoinRunner"]
except ImportError:
    TypeHandlerGenerator = None  # type: ignore[misc, assignment]
    __all__ = ["CheckJoinRunner"]
