"""
SpringMVC WM Context Generator

WM 온라인 타입 전용 Context Generator입니다.

주요 기능:
1. generate(): call_stack 기반 파일 그룹핑
   - AnyframeContextGenerator(import-chasing)와 독립적으로 동작합니다.
   - call_stack 데이터를 사용하여 context 구성에 직접 적용합니다.
   - access_files -> Controller 식별 -> call_stack 시작점 매칭 -> 하위 Service 수집.

2. create_batches(): Service 메서드 레벨 토큰 계산
   - Service 파일은 call_stack 기반 메서드만으로 토큰을 계산하여 배치 분할 최적화.
"""

import json
import logging
import os
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Optional, Set

from config.config_manager import Configuration
from models.modification_context import ModificationContext
from models.table_access_info import TableAccessInfo
from modifier.code_generator.base_code_generator import BaseCodeGenerator
from modifier.context_generator.base_context_generator import BaseContextGenerator
from parser.java_ast_parser import JavaASTParser

logger = logging.getLogger(__name__)


class MybatisWmContextGenerator(BaseContextGenerator):
    """Mybatis WM Context Generator

    Groups files based on import relationships between Controller and Service layers.
    """

    # VO 파일 최대 토큰 예산 (80k = 128k 모델의 ~62%. 출력용 48k 여유)
    MAX_VO_TOKENS = 80000

    # 토큰 제한 사용 여부 (False로 설정하면 모든 VO 파일 포함)
    USE_TOKEN_LIMIT = True

    def __init__(self, config: Configuration, code_generator: BaseCodeGenerator):
        super().__init__(config, code_generator)
        self.java_parser = JavaASTParser()
        self.table_access_info: Optional[TableAccessInfo] = None

    # ========== generate 오버라이드 (call_stack 기반) ==========

    def generate(
        self,
        layer_files: Dict[str, List[str]],
        table_name: str,
        columns: List[str],
        table_access_info: Optional[TableAccessInfo] = None,
        endpoint_method: Optional[str] = None
    ) -> List[ModificationContext]:
        """call_stack 기반 파일 그룹으로 배치를 생성합니다."""

        """
        알고리즘:
        1. access_files에서 Controller 파일 식별
        2. 각 Controller 기준으로 모든 sql_queries 순회
        3. call_stack 시작이 현재 Controller와 같으면 하위 Service를 수집
        4. Controller + Service/ServiceImpl 파일 그룹 생성
        5. VO 파일 선택 (import 기반)
        6. 배치 생성
        """

        self.table_access_info = table_access_info

        if not table_access_info:
            logger.error("table_access_info가 없습니다. (wm은 항상 필요)")
            return []

        # --- STEP 1: 레이어별 파일 추출 (부모와 동일) ---
        controller_files_raw = layer_files.get("controller", [])
        service_files_raw = layer_files.get("service", [])
        repository_files = layer_files.get("repository", [])

        service_impl_files = [x for x in service_files_raw if x.endswith("Impl.java")]
        service_interface_files = [x for x in service_files_raw if not x.endswith("Impl.java")]

        # VO 파일
        vo_files = [x for x in repository_files if x.endswith("VO.java")]

        # Mapper 파일
        mapper_files = [x for x in repository_files if x.endswith("Mapper.java")]

        # --- STEP 2: class_name -> file_path 매핑 ---
        controller_name_to_path = {Path(f).stem: f for f in controller_files_raw}
        service_ifc_name_to_path = {Path(f).stem: f for f in service_interface_files}
        service_impl_name_to_path = {Path(f).stem: f for f in service_impl_files}
        mapper_name_to_path = {Path(f).stem: f for f in mapper_files}

        # Service 전체 (interface + impl) 매칭
        service_name_to_path: Dict[str, str] = {}
        service_name_to_path.update(service_ifc_name_to_path)
        service_name_to_path.update(service_impl_name_to_path)

        # --- STEP 3: access_files에서 Controller 파일 식별 ---
        access_files = table_access_info.access_files
        controller_in_access: List[str] = []
        for af in access_files:
            stem = Path(af).stem
            if stem in controller_name_to_path:
                controller_in_access.append(stem)

        # anchor는 Controller 기준
        anchor_names = controller_in_access

        if not anchor_names:
            logger.error(
                "access_files에서 Controller 파일을 찾을 수 없습니다. "
                "call_stack 기반 그룹핑을 수행할 수 없습니다."
            )
            return []

        logger.info(f"call_stack 기반 그룹핑 시작: anchor Controller {len(anchor_names)}개")

        # --- STEP 4: 각 Controller 기준으로 call_stack 순회 -> Service 수집 ---
        impl_to_controller_names: Dict[str, Set[str]] = {}
        impl_to_service_names: Dict[str, Set[str]] = {}
        impl_to_mapper_names: Dict[str, Set[str]] = {}

        for controller_name in anchor_names:
            impl_to_controller_names.setdefault(controller_name, set())
            impl_to_service_names.setdefault(controller_name, set())
            impl_to_mapper_names.setdefault(controller_name, set())

            for sq in table_access_info.sql_queries:
                for cs in sq.get("call_stacks", []):
                    if not isinstance(cs, list) or not cs:
                        continue

                    # call_stack 시작이 현재 Controller와 같은지 확인 (첫 2개 entry)
                    cs_starts_with_this_controller = False
                    for entry in cs[:2]:
                        if not isinstance(entry, str) or "." not in entry:
                            continue
                        entry_class = entry.split(".")[0]
                        if entry_class == controller_name:
                            cs_starts_with_this_controller = True
                            break

                    if not cs_starts_with_this_controller:
                        continue

                    # 이 call_stack의 모든 entry에서 Service/Mapper 분류
                    for entry in cs:
                        if not isinstance(entry, str) or "." not in entry:
                            continue
                        class_name = entry.split(".")[0]

                        if class_name in controller_name_to_path:
                            impl_to_controller_names[controller_name].add(class_name)
                        elif class_name in service_name_to_path:
                            impl_to_service_names[controller_name].add(class_name)
                        elif class_name in mapper_name_to_path:
                            impl_to_mapper_names[controller_name].add(class_name)

        # --- STEP 5: 파일 그룹 생성 ---
        java_parser = JavaASTParser()
        file_groups: Dict[str, List[str]] = {}
        context_file_groups: Dict[str, List[str]] = {}

        for controller_name in anchor_names:
            controller_path = controller_name_to_path.get(controller_name)
            service_names = impl_to_service_names.get(controller_name, set())

            if not controller_path:
                continue

            file_group_paths: List[str] = [controller_path]

            # Service Interface/Impl 페어 추가 (call_stack에서 찾은 것)
            matched_services_files: List[str] = []
            for service_name in sorted(list(service_names)):
                service_path = service_name_to_path.get(service_name)
                if service_path:
                    matched_services_files.append(service_path)
                else:
                    logger.warning(f"call_stack Service '{service_name}' not found in layer_files")

            file_group_paths.extend(matched_services_files)

            # Mapper 파일 제외 (SQL 쿼리 접근 클래스이므로 수정 대상 아님)
            file_group_paths = [
                fp
                for fp in file_group_paths
                if not Path(fp).stem.endswith("Mapper")
            ]

            # VO 선택: 그룹 내 파일 + imports 기반
            all_imports_for_vo: Set[str] = set()
            for fp in file_group_paths:
                try:
                    tree, error = java_parser.parse_file(Path(fp))
                    if not error:
                        classes = java_parser.extract_class_info(tree, Path(fp))
                        if classes:
                            cls = next((c for c in classes if c.access_modifier == "public"), classes[0])
                            all_imports_for_vo.update(cls.imports)
                except Exception:
                    pass

            # Mapper imports도 VO 선택에 포함
            for mapper_name in impl_to_mapper_names.get(controller_name, set()):
                mapper_path = mapper_name_to_path.get(mapper_name)
                if mapper_path:
                    try:
                        tree, error = java_parser.parse_file(Path(mapper_path))
                        if not error:
                            classes = java_parser.extract_class_info(tree, Path(mapper_path))
                            if classes:
                                cls = next((c for c in classes if c.access_modifier == "public"), classes[0])
                                all_imports_for_vo.update(cls.imports)
                    except Exception:
                        pass

            vo_group_paths = self._select_vo_files_by_token_budget(
                vo_files=vo_files,
                all_imports=list(all_imports_for_vo),
                max_tokens=self.MAX_VO_TOKENS,
            )

            logger.info(
                f"{controller_name}: Controller={len([p for p in file_group_paths if p not in matched_services_files])}, "
                f"Service={len(matched_services_files)}, Service List={','.join(sorted(service_names))}, "
                f"VO={len(vo_group_paths)}"
            )

            file_groups[controller_name] = file_group_paths
            context_file_groups[controller_name] = vo_group_paths

        # --- STEP 6: 배치 생성 ---
        all_batches: List[ModificationContext] = []
        for controller_name, file_group_paths in file_groups.items():
            if not file_group_paths:
                continue
            vo_files_for_group = context_file_groups.get(controller_name, [])
            batches = self.create_batches(
                file_paths=file_group_paths,
                table_name=table_name,
                columns=columns,
                layer="",
                context_files=vo_files_for_group,
            )
            all_batches.extend(batches)

        logger.info(f"=== Total Batches Created: {len(all_batches)} ===")
        return all_batches

    # ========== create_batches 오버라이드 ==========

    def create_batches(
        self,
        file_paths: List[str],
        table_name: str,
        columns: List[str],
        layer: str = "",
        context_files: List[str] = None,
        anchor_pair: str = None
    ) -> List[ModificationContext]:
        """Service 파일은 메서드 레벨 토큰으로 계산하여 배치 분할

        BaseContextGenerator.create_batches()와 동일한 배치 분할 로직이지만,
        Service 파일의 토큰을 전체 파일 대신 call_stack 참조 메서드만으로 계산합니다.

        table_access_info가 없으면 BaseContextGenerator의 전체 파일 기반 로직으로 fallback.
        """
        if not self.table_access_info:
            return super().create_batches(
                file_paths, table_name, columns, layer, context_files
            )

        if context_files is None:
            context_files = []
        if not file_paths:
            return []

        # call_stacks 추출
        raw_call_stacks = self._extract_raw_call_stacks(
            file_paths, self.table_access_info
        )

        batches: List[ModificationContext] = []
        current_paths: List[str] = []

        # 기본 정보 준비 (부모와 동일)
        from models.code_generator import CodeGeneratorInput

        table_info = {
            "table_name": table_name,
            "columns": columns,
        }
        formatted_table_info = json.dumps(table_info, indent=2, ensure_ascii=False)
        max_tokens = self.config.max_tokens_per_batch

        input_empty_data = CodeGeneratorInput(
            file_paths=[], table_info=formatted_table_info, layer_name=layer
        )

        empty_prompt = self.code_generator.create_prompt(input_empty_data)
        empty_num_tokens = self.code_generator.calculate_token_size(empty_prompt)
        separator_tokens = self.code_generator.calculate_token_size("\n\n")

        current_batch_tokens = empty_num_tokens

        for file_path in file_paths:
            try:
                path_obj = Path(file_path)
                if not path_obj.exists():
                    logger.warning(f"File not found during batch creation: {file_path}")
                    continue

                # --- 핵심 차이: Service 파일은 메서드만으로 토큰 계산 ---
                if self._is_service_file(file_path):
                    content = self._get_service_method_content(file_path, raw_call_stacks)
                else:
                    with open(path_obj, "r", encoding="utf-8") as f:
                        content = f.read()

            except Exception as e:
                logger.error(f"Failed to read file {file_path}: {e}")
                continue

            snippet_formatted = f"=== File Path (Absolute): {file_path} ===\n{content}"
            snippet_tokens = self.code_generator.calculate_token_size(snippet_formatted)

            tokens_to_add = snippet_tokens
            if current_paths:
                tokens_to_add += separator_tokens

            if current_paths and (current_batch_tokens + tokens_to_add) > max_tokens:
                batches.append(
                    ModificationContext(
                        file_paths=current_paths,
                        table_name=table_name,
                        columns=columns,
                        layer=layer,
                        context_files=context_files,
                    )
                )
                current_paths = [file_path]
                current_batch_tokens = empty_num_tokens + snippet_tokens
            else:
                current_paths.append(file_path)
                current_batch_tokens += tokens_to_add

        if current_paths:
            batches.append(
                ModificationContext(
                    file_paths=current_paths,
                    table_name=table_name,
                    columns=columns,
                    layer=layer,
                    context_files=context_files,
                )
            )

        return batches

    # ========== Service 메서드 추출 헬퍼 ==========

    def _is_service_file(self, file_path: str) -> bool:
        """Service 파일 여부 판별 - stem이 'Service' 또는 'ServiceImpl'로 끝나는 파일만"""
        return Path(file_path).stem.upper().endswith("SERVICEIMPL") or Path(file_path).stem.upper().endswith("SERVICE")

    def _extract_raw_call_stacks(
        self,
        file_paths: List[str],
        table_access_info: TableAccessInfo,
    ) -> List[List[str]]:
        """call_stacks를 List[List[str]]로 반환합니다."""
        call_stacks_list: List[List[str]] = []
        file_class_names = [Path(fp).stem for fp in file_paths]

        for sql_query in table_access_info.sql_queries:
            call_stacks = sql_query.get("call_stacks", [])
            if not call_stacks:
                continue

            for call_stack in call_stacks:
                if not isinstance(call_stack, list) or not call_stack:
                    continue

                first_method = call_stack[0]
                if not isinstance(first_method, str):
                    continue

                if "." in first_method:
                    method_class_name = first_method.split(".")[0]
                else:
                    method_class_name = first_method

                if method_class_name in file_class_names:
                    if call_stack not in call_stacks_list:
                        call_stacks_list.append(call_stack)

        return call_stacks_list

    def _get_target_methods_for_file(
        self,
        file_path: str,
        raw_call_stacks: List[List[str]]
    ) -> Set[str]:
        """call_stacks에서 특정 파일 클래스에 해당되는 메서드명을 수집합니다."""
        class_name = Path(file_path).stem
        target_methods: Set[str] = set()

        for call_stack in raw_call_stacks:
            for method_sig in call_stack:
                if "." in method_sig:
                    cls, method = method_sig.split(".", 1)
                    if cls == class_name:
                        target_methods.add(method)

        return target_methods

    def _get_service_method_content(
        self,
        file_path: str,
        raw_call_stacks: List[List[str]]
    ) -> str:
        """Service 파일에서 call_stack 참조 메서드만 추출하여 텍스트 반환합니다."""
        target_methods = self._get_target_methods_for_file(file_path, raw_call_stacks)

        if not target_methods:
            logger.debug(f"Service 파일에 call_stack 메서드 없음, 전체 포함: {Path(file_path).name}")
            return self._read_full_file(file_path)

        # JavaASTParser로 메서드 정보 획득
        tree, error = self.java_parser.parse_file(Path(file_path))
        if error:
            logger.warning(f"Service 파일 파싱 실패, 전체 포함: {Path(file_path).name} - {error}")
            return self._read_full_file(file_path)

        classes = self.java_parser.extract_class_info(tree, Path(file_path))

        # 매칭 메서드의 라인 범위 수집
        method_ranges: List[tuple] = []
        for cls_info in classes:
            for method_name in cls_info.methods:
                if method_name in target_methods:
                    method_ranges.append(
                        (method_name, method_name.line_number, method_name.end_line_number)
                    )

        if not method_ranges:
            logger.debug(f"Service 파일에서 매칭 메서드 없음, 전체 포함: {Path(file_path).name}")
            return self._read_full_file(file_path)

        # 파일에서 해당 라인만 추출
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                all_lines = f.readlines()
        except Exception as e:
            logger.warning(f"Service 파일 읽기 실패: {file_path} - {e}")
            return ""

        extracted_parts: List[str] = []
        for method_name, start_line, end_line in sorted(method_ranges, key=lambda x: x[1]):
            lines = all_lines[start_line - 1: end_line]
            extracted_parts.append("".join(lines))

        return "\n\n".join(extracted_parts)

    def _read_full_file(self, file_path: str) -> str:
        """단일 파일의 전체 내용을 읽습니다."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.warning(f"파일 읽기 실패: {file_path} - {e}")
            return ""

    # ========== VO 선택 관련 메서드 ==========

    def _match_import_to_file_path(
        self, import_statement: str, target_files: List[str]
    ) -> Optional[str]:
        """import 문과 일치하는 파일을 target_files에서 찾습니다."""
        expected_path_parts = import_statement.split(".")
        expected_class_name = expected_path_parts[-1]

        for file_path in target_files:
            file_path_obj = Path(file_path)
            if file_path_obj.stem != {expected_class_name}:
                continue

            normalized_path = str(file_path_obj).replace("\\", "/")
            file_parts = normalized_path.split("/")

            match_found = False
            for i in range(len(file_parts) - len(expected_path_parts) + 1):
                if all(
                    file_parts[i + j] == expected_path_parts[j]
                    for j in range(len(expected_path_parts) - 1)
                ):
                    match_found = True
                    break

            if match_found:
                return file_path

        return None

    def _select_vo_files_by_token_budget(
        self,
        vo_files: List[str],
        all_imports: List[str],
        max_tokens: int,
    ) -> List[str]:
        """토큰 예산 내에서 VO 파일들을 선택합니다."""
        selected_files: List[str] = []
        current_tokens = 0

        if not self.USE_TOKEN_LIMIT:
            for imp in all_imports:
                matched = self._match_import_to_file_path(imp, vo_files)
                if matched and matched not in selected_files:
                    selected_files.append(matched)
            return selected_files

        for imp in all_imports:
            matched = self._match_import_to_file_path(imp, vo_files)
            if matched and matched not in selected_files:
                try:
                    with open(matched, "r", encoding="utf-8") as f:
                        content = f.read()
                    file_tokens = self.calculate_token_size(content)

                    if current_tokens + file_tokens <= max_tokens:
                        selected_files.append(matched)
                        current_tokens += file_tokens
                    else:
                        break
                except Exception as e:
                    logger.warning(f"VO 파일 읽기 실패: {matched} - {e}")

        return selected_files