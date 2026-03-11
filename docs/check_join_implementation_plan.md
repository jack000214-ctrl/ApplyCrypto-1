# check_join 기능 구현 계획

## 1. 개요

- **목적**: `config`의 `target_project`와 `access_tables`, 그리고 `analyze` 결과(`table_access_info.json`)를 이용해, access_tables에 명시된 각 테이블·컬럼을 **source**로 해서 **join**으로 연결되는 **target 테이블·컬럼**을 LLM으로 추출한다.
- **진입점**: CLI 명령 `check_join` (옵션: `--config`, `--export`).
- **구현 위치**: `src/generator/check_join.py`, `src/generator/check_join_prompt.md`.

---

## 2. 입력 데이터

### 2.1 config

- `target_project`: 대상 프로젝트 경로 (`.applycrypto/results` 기준).
- `access_tables`: 분석 대상 테이블·컬럼 목록 (테이블별로 `table_name`, `columns`).
- `llm_provider`: check_join에서 사용할 LLM 프로바이더 (기존 `create_llm_provider` 활용).

### 2.2 table_access_info.json

- **경로**: `{target_project}/.applycrypto/results/table_access_info.json`
- **형태**: `TableAccessInfo`의 `to_dict()` 리스트 (또는 동일 스키마의 JSON 배열).
- **주요 필드** (테이블 단위):
  - `table_name`, `columns` (예: `[{"name": "col1", "new_column": false}, ...]`)
  - `sql_queries`: `List[Dict]`, 각 항목에 최소 `sql` (쿼리 문자열), `query_type`, `id` 등.

- **필터링**: `config.access_tables`에 있는 테이블만 처리하고, 각 테이블에서는 `access_tables`에 정의된 컬럼만 source 컬럼으로 사용한다.

---

## 3. 출력 스키마

### 3.1 check_join_results.json

- **경로**: `{target_project}/.applycrypto/results/check_join_results.json`
- **형식** (요구사항 8 반영):

```json
{
  "results": [
    {
      "source_table": "<INPUT TABLE NAME>",
      "source_columns": [
        {
          "column_name": "<INPUT COLUMN NAME>",
          "joins": [
            {
              "target_table": "<TARGET TABLE NAME>",
              "alias": "<ALIAS OF TARGET TABLE>",
              "target_column": "<TARGET COLUMN NAME>",
              "join_type": "<JOIN_TYPE>",
              "condition": "<USED CONDITION IN JOIN>"
            }
          ]
        }
      ]
    }
  ]
}
```

- **의미**: `results`의 각 요소는 **테이블 하나**에 대한 결과. `source_columns`는 그 테이블의 컬럼별로, 해당 컬럼이 join되는 target 테이블/컬럼 정보(`joins`)를 가진다.
- **저장 시점**: 테이블 루프가 끝날 때마다 해당 테이블 결과를 메모리 리스트에 추가하고, **전체 테이블 처리 후 한 번** `check_join_results.json`에 저장한다. (요구사항 7: “column loop 완료 시 해당 table 결과를 … 추가” → 테이블 단위로 결과 리스트에 추가 후 일괄 저장.)

---

## 4. 처리 흐름 (check_join 명령, --export 없음)

1. **설정 로드**  
   - `--config`(기본 `config.json`)로 `Configuration` 로드.  
   - `target_project` 경로 검증.

2. **table_access_info 로드**  
   - `DataPersistenceManager(target_project)` 생성.  
   - `load_from_file("table_access_info.json")`로 리스트 로드.  
   - 항목이 `dict`면 그대로, `TableAccessInfo` 복원이 필요하면 `TableAccessInfo.from_dict` 등으로 통일.

3. **access_tables 기준 필터**  
   - `config.access_tables`에 있는 `table_name`만 사용.  
   - 각 테이블에 대해 `access_tables`에 정의된 `columns`(이름 목록)만 source 컬럼으로 사용.

4. **테이블 루프**  
   - 필터된 각 테이블에 대해:
     - 해당 테이블의 `table_access_info` 항목에서 `sql_queries` 취득.
     - **컬럼 루프**: 해당 테이블의 (필터된) 각 source 컬럼에 대해:
       - **쿼리 루프**: `sql_queries`의 각 `query`(예: `sql_query_info["sql"]`)에 대해:
         - **프롬프트 구성**: `check_join_prompt.md` 파일을 읽어, 선택된 **테이블명**, **컬럼명**, **SQL 쿼리**를 입력으로 넣어 프롬프트 문자열 생성.
         - **LLM 호출**: `create_llm_provider(config.llm_provider).call(prompt)` 호출.
         - **파싱**: 응답에서 JSON 블록 추출 후 파싱. 스키마는 위 `results[].source_columns[].joins` 형식에 맞춤 (컬럼 단위로 나올 수 있으므로, 컬럼 단위 결과를 모아서 해당 테이블의 `source_columns` 리스트 구성).
       - 컬럼 루프가 끝날 때까지 위 결과를 **메모리**에 누적 (테이블 단위로 `source_columns` 리스트 구성).
     - 테이블 루프 한 번 끝나면: 해당 테이블에 대한 `{ "source_table", "source_columns" }` 항목을 **메모리 상의 `results` 리스트에 추가**.

5. **저장**  
   - 위에서 모은 `results` 전체를 `{"results": results}` 형태로 `check_join_results.json`에 저장.  
   - 저장 경로: `DataPersistenceManager.output_dir` (= `target_project/.applycrypto/results`) 아래.

---

## 5. check_join_prompt.md 설계

- **위치**: `src/generator/check_join_prompt.md`
- **역할**: “주어진 source 테이블·컬럼과 SQL 쿼리에서, 이 source를 기준으로 join되는 target 테이블/컬럼과 join 타입·조건을 찾아라”라고 LLM에 지시.
- **입력 치환자** (프롬프트 내 placeholder):
  - `{{source_table}}`: 현재 테이블명.
  - `{{source_column}}`: 현재 컬럼명.
  - `{{sql_query}}`: 현재 SQL 쿼리 문자열.
- **출력 지시**:  
  - 반드시 지정한 JSON 구조만 출력하도록 명시.  
  - 한 번에 **하나의 source 컬럼**에 대한 결과를 요청하는 형태가 구현하기 쉬움 (컬럼 루프와 1:1 대응).  
  - 예: `{"source_table": "...", "source_columns": [{"column_name": "...", "joins": [...]}]}` 형태로, 단일 컬럼이면 `source_columns` 길이 1.
- **내용 구성**:
  - 목적 설명 (한국어 가능).
  - 입력: source table, source column, SQL query.
  - 출력 형식: 위 JSON 스키마와 필드 설명 (target_table, alias, target_column, join_type, condition).
  - join이 없으면 `joins: []`로 응답하도록 안내.

---

## 6. LLM 호출 및 파싱

- **프로바이더**: `config.llm_provider`로 `create_llm_provider()` 호출 (기존 `llm_factory` 사용).
- **호출**: `response = provider.call(prompt)` → `response["content"]`에서 텍스트 추출.
- **파싱**:  
  - 응답 텍스트에서 JSON 블록만 추출 (코드 블록 마커 ` ```json ... ``` ` 제거 등).  
  - `json.loads()` 후, 한 컬럼에 대한 결과가 오면 해당 테이블의 `source_columns` 항목으로 병합.  
  - 파싱 실패 시: 해당 (테이블, 컬럼, 쿼리)에 대해 `joins: []` 또는 로그 후 스킵으로 처리.

---

## 7. check_join --export (엑셀 내보내기)

- **트리거**: `check_join --export` 실행 시.
- **동작**:
  1. `config` 로드 후 `target_project` 결정.
  2. `{target_project}/.applycrypto/results/check_join_results.json` 로드.
  3. **평탄화**: `results`와 `source_columns`, `joins`를 펼쳐서 **행(row)** 생성.  
     - 한 행 = (source_table, column_name, target_table, alias, target_column, join_type, condition) (+ 필요 시 기타 키).
  4. **엑셀 저장**:  
     - 파일명: `check_join_results.json_{timestamp}.xlsx` (예: `check_join_results.json_20250310143052.xlsx`).  
     - 저장 위치: **target_project** (또는 요구에 따라 `target_project/.applycrypto/results`).  
     - 구현: **`openpyxl`**로 워크북/시트를 생성하고, 1행에 헤더(=JSON 키)를 쓰고, 이후 행에 값들을 기록.
     - 컬럼: JSON 키를 컬럼명으로 사용하고, 연관된 값을 채워 넣음 (위 평탄화 시 사용한 키 = 엑셀 컬럼명).

---

## 8. CLI 연동

- **서브파서 추가**: `check_join` 명령 추가.
  - 인자: `--config` (기본 `config.json`), `--export` (플래그).
- **실행 분기**:
  - `check_join` (--export 없음): 위 4절 흐름 실행 → `check_join_results.json` 생성/갱신.
  - `check_join --export`: 위 7절 흐름 실행 → `check_join_results_{timestamp}.xlsx` 생성.
- **등록 위치**: `cli_controller.py`의 `_create_parser()`에 서브파서 추가, `execute()`에서 `parsed_args.command == "check_join"`일 때 `_handle_check_join(parsed_args)` 호출.

---

## 9. 파일/모듈 구성

| 대상 | 내용 |
|------|------|
| `src/generator/check_join.py` | CheckJoinRunner(또는 함수 그룹): 설정·경로 로드, table_access_info 로드·필터, 테이블/컬럼/쿼리 루프, 프롬프트 조립, LLM 호출, JSON 파싱, 결과 누적, check_join_results.json 저장. export 모드: JSON 로드, 평탄화, 엑셀 저장. |
| `src/generator/check_join_prompt.md` | 프롬프트 템플릿. placeholder: `{{source_table}}`, `{{source_column}}`, `{{sql_query}}`. 출력 형식 명시. |
| `src/generator/__init__.py` | `CheckJoinRunner`(또는 공개 함수) export 추가. |
| `src/cli/cli_controller.py` | `check_join` 서브파서 및 `_handle_check_join()` 구현. |

---

## 10. 의존성

- **기존**: `config`, `DataPersistenceManager`, `create_llm_provider`, `TableAccessInfo`(필요 시).
- **엑셀**: **`openpyxl` 사용(고정)**. 프로젝트에 없으면 `requirements.txt` / `pyproject.toml`에 추가.

---

## 11. 구현 순서 제안

1. **check_join_prompt.md** 작성 (placeholder 및 출력 형식 명확히).
2. **check_join.py** 핵심 로직:  
   - 설정·경로, table_access_info 로드·필터.  
   - 한 테이블·한 컬럼·한 쿼리에 대해 프롬프트 로드·치환 → LLM 호출 → 파싱 → 메모리 누적.  
   - 테이블별로 `results`에 추가 후 `check_join_results.json` 저장.
3. **CLI** check_join 서브파서 및 `_handle_check_join` (--export 분기).
4. **--export**: check_join_results.json 로드, 평탄화, 엑셀 저장 (타임스탬프 파일명).
5. **테스트**: (선택) mock LLM으로 check_join 한 테이블/한 컬럼 플로우 및 export 플로우 검증.

이 순서대로 구현하면 요구사항 1~10을 모두 반영할 수 있습니다.
