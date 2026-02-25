"""
AnyframeSarangOn Endpoint Extraction Strategy

AnyframeSarangOn 프레임워크를 위한 엔드포인트 추출 전략 구현입니다.
SpringMVC 어노테이션 패턴을 사용하여 엔드포인트를 추출합니다.
"""

import logging
from .anyframe_endpoint_extraction import AnyframeEndpointExtraction


logger = logging.getLogger(__name__)


class AnyframeSarangOnEndpointExtraction(AnyframeEndpointExtraction):
    """
    AnyframeSarangOn 프레임워크 엔드포인트 추출 전략

    AnyframeSarangOn 프레임워크에서 SpringMVC 어노테이션 패턴을 사용하여 엔드포인트를 추출합니다.
    """
    pass
