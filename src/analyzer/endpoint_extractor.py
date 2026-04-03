import json
import re
import argparse
from pathlib import Path
import javalang
import fnmatch
from lxml import etree
from pydantic import BaseModel
from typing import List, Optional
from config.config_manager import Configuration
from util.extract_resolved_sql import extract_resolved_sql

class Parameter(BaseModel):
    class_name: Optional[sql] = None
    path: Optional[str] = None

class Return(BaseModel):
    class_name: Optional[str] = None
    path: Optional[str] = None

class Call(BaseModel):
    class_name: Optional[str] = None
    method: Optional[str] = None
    path: Optional[str] = None
    parameter: List[Parameter] = []
    return_info: Optional[Return] = None
    calls: List['Call'] = []
    sql: Optional[str] = None
    has_sensitive_fields: bool = False
    tables: List[str] = []

class Endpoint(BaseModel):
    method_name: Optional[str] = None
    http_method: Optional[str] = None
    url_pattern: Optional[str] = None
    calls: List[Call] = []

class Controller(BaseModel):
    class_name: Optional[str] = None
    path: Optional[str] = None
    uri: Optional[str] = None
    endpoints: List[Endpoint] = []  

class Project(BaseModel):
    project_name: Optional[str] = None
    controllers: List[Controller] = []
    
    class Config:
        fromm_attribute = True

    def update_sensitive_flags(self, sensitive_tables: List[self.dict]):
        """
        프로젝트 트리 전체에서 민감한 필드 사용 여부를 업데이트합니다.
        """
        
        def check_sensitive_sql(sql: str, sensitive_tables: List[dict]) -> bool:
            """
            SQL 쿼리가 민감한 테이블을 사용하는지 확인합니다.
            """
            sql_lover = sql.lower()
            matched_results = []

            for table in sensitive_tables:
                table_name = table.get("table_name", "").lower()

                if table_name in sql_lover:
                    matched_columns = [
                        column for column in table.colums
                        if column.name.lower() in sql_lover
                    ]
                    if matched_columns:
                        matched_results.append({
                            "table_name": table.table_name,
                            "columns": matched_columns
                        })

            return matched_results
        
        def propagate_sensitive_flags(calls: List[Call]):
            for call in calls:
                propagate_sensitive_flags(call.calls)

                if any(sub_call.has_sensitive_fields for sub_call in call.calls):
                    call.has_sensitive_fields = True

                    for sub_call in call.calls:
                        for table in sub_call.tables:
                            if table not in call.tables:
                                call.tables.append(table)

        def update_calls(calls: List[Call], sensitive_tables: List[dict]):
            """
            호출(call) 리스트 내에서 SQL 민감 필드 여부를 재귀적으로 확인합니다.
            """
            for call in calls:
                matched_tables = check_sensitive_sql(call.sql, sensitive_tables)
                if matched_tables:
                    call.has_sensitive_fields = True
                    call.tables = matched_results
                update_calls(call.calls, sensitive_tables)
            
            propagate_sensitive_flags(calls)

        for controller in self.controllers:
            for endpoint in controller.endpoints:
                update_calls(endpoint.calls, sensitive_tables)


class EndpointExtractor:

    def __init__(self, config: Configuration):
        self.config = config
        self.root = Path(config.target_project).resolve()
        self.output_path = Path(self.config.target_project) / ".applycrypto/results/endpoint.json"
        self.java_files = list(self.root.rglob("*.java"))
        self.xml_files = list(self.root.rglob("*.xml"))

        self.class_map = {}
        self.simple_class_map = {}
        self.tree_map = {}
        self.xml_map = {}

        self.result = {
            "project_name": self.root.name,
            "controllers": []
        }

        self._index_java()
        self._index_xml()


    # ---------------------------------------
    # Indexing 
    # ---------------------------------------
    def _index_java(self):
        for file in self.java_files:
            if any(dir_name.lower() in [p.lower() for p in file.parts] for dir_name in self.config.exclude_dirs):
                continue

            if any(fnmatch.fnmatch(file.name, pattern) for pattern in self.config.exclude_files):
                continue

            try:
                tree = javalang.parse.parse(file.read_text(encoding="utf-8", errors="ignore"))
            except  Exception:
                continue

            package = tree.package.name if tree.package else ""
            for t in tree.types:
                fqcn = f"{package}.{t.name}" if package else t.name
                self.class_map[fqcn] = str(file)
                self.tree_map[fqcn] = tree
                self.simple_class_map[t.name] = fqcn
                
    def _index_xml(self):
        for file in self.xml_files:
            if any(dir_name.lower() in [p.lower() for p in file.parts] for dir_name in self.config.exclude_dirs):
                continue

            if any(fnmatch.fnmatch(file.name, pattern) for pattern in self.config.exclude_files):
                continue

            try:
                tree = etree.parse(str(file)).getroot()
            except Exception:
                continue
            
            if root.tag.endswith("mapper") and "namespace" in root.attrib:
                self.xml_map[root.attrib["namespace"]] = file

    # ---------------------------------------
    # Controller 분석
    # ---------------------------------------
    def _is_conftroller(self, clazz):
        if clazz.annotations:
            any(a.name.endswith("Controller") for a in clazz.annotations):  
            
        name = clazz.name.lower()
        
        return (
            name.endswith("controller") 
            or name.endswith("job")
            or name.endswith("ctl")
            or name.endswith("bat")
            or name.endswith("batch")
            or name.endswith("task")
            or name.endswith("tasklet")
            or name.endswith("resource")
        )

    def _extract_mapping(self, annotations):
        http = "All"
        url = ""

        for a in annotations:
            name = a.name
            if name.endswith("Mapping"):
                if name.startswith("Get"):
                    http = "GET"
                elif name.startswith("Post"):
                    http = "POST"
                elif name.startswith("Put"):
                    http = "PUT"
                elif name.startswith("Delete"):
                    http = "DELETE"
                
                el = a.element
                if el is None:
                    return http, url
                if isinstance(el, javalang.tree.Literal):
                    uri = el.value.strip('"')
                    return http, uri
                
                if isinstance(el, list):
                    for p in el:
                        if hasattr(p, "name") and p.name in ("value", "path"):
                            if hasattr(p.value, "value"):
                                uri = p.value.value.strip('"')
                            elif hasattr(p.value, "name") and p.name == "method":
                                if hasattr(p.value, "member") and "POST" in p.value.member:
                                    http = "POST"
                                elif hasattr(p.value, "member") and "GET" in p.value.member:
                                    http = "GET"
                                elif hasattr(p.value, "member") and "PUT" in p.value.member:
                                    http = "PUT"
                                elif hasattr(p.value, "member") and "DELETE" in p.value.member:
                                    http = "DELETE"

        return http, uri
 
    def _trace_method(self, fqcn, method_name, visited):
        if (fqcn, method_name) in visited:
            return []
        visited.add((fqcn, method_name))

        tree = self.tree_map.get(fqcn)
        if not tree:
            return []  
        
        calls = []

        for t in tree.types:
            if t.name != fqcn.split(".")[-1]:
                continue

            for m in t.methods:
                if m.name != method_name:
                    continue

                for _, node in m.filter(javalang.tree.MethodInvocation):
                    target_method = node.member
                    target_class = self.resolve_target_class(node, fqcn)

                    if not target_class:
                        continue

                    parameter_info = []
                    return_info = {"class": None, "path": None}

                    for param in m.parameters:
                        param_type = param.param.type
                        param_fqcn = self._find_impl_class(param_type) or param_type
                        parameter_info.append({
                            "class_name": param_fqcn,
                            "path": self.class_map.get(param_fqcn, None)
                        })  

                    if m.return_type:
                        return_class = m.return_type.name
                        return_fqcn = self._find_impl_class(return_class) or return_class
                        return_info = {
                            "class_name": return_fqcn,
                            "path": self.class_map.get(return_fqcn, None)
                        }

                    call = {
                        "class_name": target_class,
                        "method": target_method,
                        "path": self.class_map.get(target_class),
                        "parameter": parameter_info,
                        "return_info": return_info,
                        "calls": [],
                        "has_sensitive_fields": False
                    }

                    sql = self._extract_sql(target_class, target_method)
                    if sql:
                        call["sql"] = sql   
                    else:
                        call["calls"] = self._trace_method(target_class, target_method, visited)

                    calls.append(call)

            return calls
        

    # ---------------------------------------
    # Class / DI 해석 
    # ---------------------------------------
    def _resolve_target_class(self, node, current_class):
        if node.qualifier:
            tree = self.tree_map.get(current_class)
            if not tree:
                return None
            
            for t in tree.types:
                for field in t.fields:
                    for d in field.declarators:
                        if d.name == node.qualifier:
                            typename = field.type.name
                            return self._find_impl_class(typename)
            
        return None
          
    # ---------------------------------------
    # Utils 
    # ---------------------------------------
    def _find_impl_class(self, interface_name):
        impl = interface_name + "Impl"
        return self.simple_class_map.get(impl, self.simple_class_map.get(interface_name))

    # ---------------------------------------
    # SQL 추출 
    # ---------------------------------------
    def _extract_sql(self, fqcn, method):
        if fqcn in self.xml_map:
            root = self.xml_map[fqcn]
            for tag in ["select", "insert", "update", "delete"]:
                for e in root.findall(f".//{tag}"):
                    sql_id = e.attrib.get("id")
                    if sql_id == method:
                        file_path = self.xml_map[fqcn].base.replace("file:/", "")
                        orginal_text = "".join(e.itertext()).strip()
                        if Path(file_path).exists():
                            resolved_sql = extract_resolved_sql(
                                xml_path = file_path, 
                                sql_id=sql_id,
                            ) 
                            return resolved_sql if resolved_sql else orginal_text
                        
        tree = self.tree_map.get(fqcn)
        if tree:
            for t in tree.types:
                for m in t.methods:
                    if m.name == method:
                        for a in m.annotations:
                            if a.name = "Query":
                                return a.element.value.strip('"')
                            
        return None

    # ---------------------------------------
    # Main analysis
    # ---------------------------------------

    def analyze(self):
        for fqcn, tree in self.tree_map.items():
            for t in tree.types:
                if not self._is_controller(t):
                    continue

                controller = {
                    "class_name": fqcn,
                    "path": self.class_map[fqcn],
                    "uri": "",
                    "endpoints": []
                }

                for m in t.methods:
                    http, uri = self._extract_mapping(m.annotations)
                    # if not uri:
                    #     continue

                    endpoint = {
                        "method_name": m.name,
                        "http_method": http,
                        "url_pattern": uri,
                        "calls": self._trace_method(fqcn, m.name, set())
                    }
                    controller["endpoints"].append(endpoint)

                self.results["controllers"].append(controller)

        if self.results:
            project = Project.model_validate(self.results)
            project.update_sensitive_flags(self.config.access_tables)
            # self.results = json.dumps(project, indent=2, ensure_ascii=False)
            self.save(project)


    # ----------------------------------------------------------------------

    def save(self, results: Project):
        with open(self.output_path, "w", encoding="utf-8") as f:
            if results:
                json.dump(results.dict(), f, indent=2, ensure_ascii=False)
            else:
                json.dump(self.results, f, indent=2, ensure_ascii=False)


    # ----------------------------------------------------------------------
    # ----- JSON 파일 로드 및 저장 함수 -----

    def load_project(self) -> Project:
        """
        call_tree.json 파일을 로드해 Project 객체로 변환합니다.
        """
        with open(self.output_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return Project(**data)



    def save_project(self, project: Project):
        """
        Project 객체를 JSON 파일로 저장합니다.
        """
        with open(self.output_path, "w", encoding="utf-8") as file:
            json.dump(project.dict(), file, indent=2, ensure_ascii=False)



    def filter_sensitive_controllers(self, project: Project) -> List[Controller]:
        """
        has_sensitive_fields가 True인 Call 요소를 포함한 Endpoint만을 가진
        Controller의 리스트를 반환하는 함수.
        """
        filtered_controllers = []

        for controller in project.controllers:
            # 새로운 Controller 객체 생성
            new_controller = Controller(
                class_name=controller.class_name,
                path=controller.path,
                uri=controller.uri,
                endpoints=[]
            )

            for endpoint in controller.endpoints:
                # 민감한 필드를 가진 Call만 필터링
                sensitive_calls = [
                    call for call in endpoint.calls if self.has_sensitive_field_recursive(call)
                ]

                if sensitive_calls:
                    # 새로운 Endpoint로 추가
                    new_endpoint = Endpoint(
                        method_name=endpoint.method_name,
                        http_method=endpoint.http_method,
                        url_pattern=endpoint.url_pattern,
                        calls=sensitive_calls
                    )
                    new_controller.endpoints.append(new_endpoint)

            if new_controller.endpoints:
                # 민감한 Endpoint가 있는 경우만 추가
                filtered_controllers.append(new_controller)

        return filtered_controllers



    def has_sensitive_field_recursive(self, call: Call) -> bool:
        """
        재귀적으로 Call 트리에서 has_sensitive_fields가 True인 요소를 확인.
        """
        if call.has_sensitive_fields:
            return True
        return any(self.has_sensitive_field_recursive(sub_call) for sub_call in call.calls)



    def collect_file_paths(self, endpoint: Endpoint) -> List[str]:
        """
        주어진 Endpoint의 모든 Call 트리에서 file path를 취합하여 반환합니다.
        또한, 각 Call의 parameters와 return_info의 path 값도 포함합니다.

        Args:
            endpoint (Endpoint): 탐색할 Endpoint.

        Returns:
            List[str]: Endpoint의 모든 Call 트리에서 발견된 파일 경로(path) 목록.
        """
        result_paths = set()

        # 재귀적으로 Calls를 탐색하여 파일 경로를 수집
        
        def traverse_calls(calls: List[Call]):
            for call in calls:
                # Call 자체의 path 추가
                if call.path:
                    result_paths.add(call.path)

                # Parameters 각 요소의 path 추가
                for param in call.parameters:
                    if param.path:
                        result_paths.add(param.path)

                # Return의 path 추가
                if call.return_info and call.return_info.path:
                    result_paths.add(call.return_info.path)

                # 재귀적으로 Calls 내부 탐색
                traverse_calls(call.calls)

        # Endpoint의 Calls 트리 탐색 시작
        traverse_calls(endpoint.calls)

        return list(result_paths)
