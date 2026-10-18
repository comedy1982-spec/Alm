# ECU-ALM — ASPICE PAM 4.0 요구사항 관리 도구

SRS·고객 요구사항 문서(DOCX/PDF)를 넣으면 요구사항을 원자 단위로 분리합니다. 이어서 SYS.2와 SWE.1을 나누고, 영구 ID를 붙이고, 표와 그림을 구조화합니다. 그 위에 추적 링크, Suspect 관리, PAM 4.0 감사, 베이스라인을 제공하는 로컬 ALM입니다. 서버나 DB 설치 없이 Python과 SQLite 파일 하나로 동작합니다.

## 설치

```bash
pip install -e .          # Python 3.10+
# 선택: LibreOffice — .doc/.rtf/.odt 입력과 EMF/WMF 그림 변환에 사용 (soffice 가 PATH 에 있어야 함)
```

## 작업 흐름 (ASPICE 단계 기반)

화면 상단의 단계 띠(SYS.1 → SYS.2 → SYS.3 → SWE.1 → SWE.2 → SWE.3 ⇄ SWE.4 … SYS.5)를 따라 일합니다. 각 단계는 **라이브 문서**이고, 그 아래 리뷰 보드 · 추적 · 품질 탭이 있습니다.

1. **요구사항 가져오기** — 고객 CRS(DOCX/PDF)를 SYS.1로 넣습니다. 저장 전에 신규·변경·삭제를 미리 봅니다(개정 비교 화면).
2. **SYS.2 SRS 생성** — 가져오기 직후 `SYS.1 → SYS.2` 전개가 실행되어 PAM 4.0 구조(목적·참조·용어·도메인별 요구사항·검증 기준·추적 매트릭스)의 SRS 초안이 만들어집니다. Word로 바로 내보낼 수 있습니다.
3. **다음 단계로 전개 →** — SRS에서 SYS.3 시스템 요소·HSI, SWE.1 SW 요구사항([Pre]→[Trigger]→[Timing]→[Output] 템플릿), SYS.5 TC를 만들고, SWE.1에서 SWE.2 AUTOSAR 컴포넌트·SWE.6 TC, SWE.2에서 SWE.3 유닛·SWE.5 TC를 만듭니다. 전개된 것은 모두 draft이고 추적 링크가 자동으로 걸립니다.
4. **리뷰 보드** — 재검토 필요(Suspect) / 초안 / 검토중 / 승인 칸반으로 승인 흐름을 돌리고, 베이스라인 준비도를 봅니다.
5. **링크 작업대** — 화면을 2~4개의 창으로 나누어(타일) 각 창에 단계를 띄우고, 카드를 다른 창의 카드 위로 **드래그&드롭**하면 링크 규칙에 맞는 역할로 추적 링크가 생깁니다. "새 창으로 열기"로 브라우저 창을 하나 더 띄워 창 사이에서도 끌어다 놓을 수 있습니다(창끼리 자동 동기화). 마우스를 올리면 연결된 상대가 강조되고, 키보드 사용자는 "연결 시작 → 여기로 연결" 버튼으로 같은 일을 합니다.
6. **감사 콘솔** — 고아 요구사항, 수치 불일치, Suspect를 한 번에 보고, 같은 검사를 CI에서 `ecualm audit --fail-on error`로 돌립니다.

상위 문서의 개정본을 다시 넣으면 변경된 항목의 하위 전개물(SYS.2, SWE.1, TC …)이 자동으로 Suspect가 되어 재검토 대상에 올라옵니다.

```bash
ecualm import CRS.pdf --mode crs --rev 1.0      # SYS.1
ecualm derive SYS1 SYS2                         # PAM 4.0 SRS 초안
ecualm derive SYS2 SWE1 && ecualm derive SYS2 SYS3 && ecualm derive SYS2 SYS5
ecualm derive SWE1 SWE2 && ecualm derive SWE1 SWE6
ecualm stagedoc SYS2                            # 터미널에서 SRS 구조 보기
ecualm export docx SRS.docx --stage SYS2        # Word 로 내보내기
```

### 30페이지 SRS 전개 예시

`samples/SRS_BLDC_Full_revA.docx`(30쪽, 요구사항 169건, 표 20개, 그림 5개)를 통합 SRS로 넣으면 다음과 같이 전개됩니다.

```bash
ecualm import samples/SRS_BLDC_Full_revA.docx --doc SRS_BLDC_ACT --mode srs --rev A
#  SYS2 60 · SWE1 117 · HSI 29 · 표 24 · 그림 5, 원문 "근거: REQ-xxx" 참조로 링크 12건
ecualm derive SYS2 SYS3 ; ecualm derive SYS2 SYS5 ; ecualm derive SWE1 SWE2 ; ecualm derive SWE1 SWE6
ecualm derive SWE2 SWE3 ; ecualm derive SWE2 SWE5 ; ecualm derive SWE3 SWE4 ; ecualm derive SYS3 SYS4
ecualm export docx SRS.docx --stage SYS2 ; ecualm export docx SWRS.docx --stage SWE1 ; ecualm export docx SWE6_TC.docx --stage SWE6
```

문서 안의 `ASIL B · 검증: HIL · 근거: REQ-PWR-009` 같은 줄은 앞 요구사항의 속성(ASIL, 검증 방법, 근거)과 추적 링크로 들어갑니다.

## 5분 사용법

```bash
mkdir BLDC_ECU && cd BLDC_ECU
ecualm init --project BLDC_ECU                         # alm.json + .alm/ 생성
ecualm import SRS.docx --doc SRS_BLDC --rev A          # 첫 임포트: 모든 아이템에 ID 부여
ecualm import CRS_고객사양.pdf --mode crs --rev 1.0    # 고객 요구사항(SYS.1)
ecualm serve                                           # http://127.0.0.1:8765 웹 UI
```

개정본이 나오면 **같은 `--doc` 이름으로 다시 임포트**합니다.

```bash
ecualm import SRS_revB.docx --doc SRS_BLDC --rev B --dry-run   # 먼저 변경 내용만 확인
ecualm import SRS_revB.docx --doc SRS_BLDC --rev B
```

결과는 **신규 / 변경 / 동일 / 삭제** 네 가지로 분류됩니다.
- 기존 ID는 유지됩니다.
- 변경된 아이템이 approved 상태였다면 draft로 되돌아가 재승인을 받아야 합니다.
- 변경된 아이템에 연결된 하위 링크는 **Suspect**로 표시됩니다.

## 무엇을 자동으로 하나

| 기능 | 내용 |
|---|---|
| 문서 파싱 | DOCX: 본문 순서대로 제목, 문단, 목록, 표, 그림, 텍스트박스, 콘텐츠 컨트롤을 읽음. PDF: 글자 좌표로 줄과 문단을 재구성(한글 띄어쓰기, 줄바꿈 처리)하고 머리글·바닥글을 제거 |
| 표 변환 | 병합 셀(rowspan/colspan)을 보존. PDF에서 페이지를 넘어간 표와 행을 이어 붙임. 표 종류를 판별해 처리 (아래 참고) |
| 그림 변환 | 이미지를 추출하고, EMF/WMF는 PNG로 변환. PDF의 벡터 도면은 캡션 위치를 기준으로 렌더링. 캡션("그림 N"/"Figure N")과 도면 안 라벨을 함께 연결 |
| 요구사항 분리 | `~해야 한다 / shall / must` 문장을 검출. 문단 안에 의무 문장이 여러 개면 각각 별도 아이템으로 분리. 원문 ID(REQ-COM-001 등)도 보존 |
| SYS.2 / SWE.1 분리 | 키워드 점수로 분류하고 분류 신뢰도를 함께 기록. 잘못 분류되면 UI나 `reclassify`로 타입을 변경 (새 ID 발급, 기존 ID는 폐기) |
| ID 부여 | `SWE1-COM-0007` 형식(타입-도메인-일련번호). 한 번 쓴 ID는 재사용하지 않음. 형식은 `alm.json`의 `id_format`으로 변경 |
| 개정 매칭 | 원문 ID, 동일 내용 해시, 유사도(문장 + 섹션) 순서로 기존 아이템과 매칭해 ID를 유지 |
| 품질 Lint | 모호어(빠르게·적절히 등), 복합 문장, 수치·단위 누락, TBD, 앞 문장 참조("이때") 검출 |
| 추적성 | 링크 역할 스키마를 강제함 (예: SWE6 TC → SYS2 링크 거부). 자동 링크 제안 기능 제공 |
| 감사 | 고아 요구사항, 할당 누락, 검증 누락, Suspect, 삭제된 아이템 참조를 검사. 상·하위 아이템 간 **수치·단위 불일치**와 **TC의 경계값 누락**도 검사 |
| 단계 전개 | CRS→SYS.2→SYS.3/HSI→SWE.1→SWE.2→SWE.3, 각 명세 단계→검증 TC. 규칙은 `alm.json`의 `sys3_allocation`, `swe2_allocation`, `stages` |
| 내보내기 | 아래 표 참고 |

표 종류별 처리:
- **요구사항 표**: 행마다 아이템을 만들고, 나머지 열(검증방법, ASIL 등)은 속성으로 저장
- **핀맵 표**: 행마다 HSI(SYS.3) 아이템 생성
- **그 외 표**: 표 아이템 하나로 저장

내보내기 형식:

| 형식 | 내용 |
|---|---|
| Excel | 표마다 시트를 만들고 병합 셀을 유지 |
| Polarion 스타일 JSON | Polarion 이관·연동용 |
| Markdown | docs-as-code용 |
| 정적 HTML 스냅샷 | 읽기 전용 공유용 |
| Word (단계 문서) | PAM 4.0 구조의 SRS/SWRS 등, `ecualm export docx out.docx --stage SYS2` |

## 주요 명령

```bash
ecualm list --type SWE1 --status draft
ecualm show SWE1-COM-0002 --history
ecualm edit SWE1-COM-0002 --text "..."            # 버전 +1, 하위 링크 Suspect
ecualm approve SWE1-COM-0002 SYS2-PWR-0001
ecualm add --type SWE6_TC --domain COM --text "..." --doc SRS_BLDC
ecualm link SWE6-TC-COM-0001 verifies SWE1-COM-0002
ecualm import-links links.csv                    # src,role,dst 열
ecualm suggest-links --src SWE1 --dst SYS2       # proposed 상태로 저장 → UI에서 ✓/✕
ecualm clear-suspect --src SWE6-TC-COM-0001       # 검토 완료
ecualm audit --report audit.html --fail-on error  # CI 게이트 (오류 시 exit 2)
ecualm baseline create BL_v1.0 && ecualm baseline diff BL_v1.0
ecualm export xlsx out.xlsx | json out.json | md ./md | html snapshot.html
```

## 링크 방향 규칙

링크는 항상 **하위 → 상위** 방향으로 겁니다. 상위 아이템이 바뀌면 그 아이템을 가리키는 링크가 Suspect가 됩니다.

| 하위 | 역할 | 상위 |
|---|---|---|
| SYS2 | derives | CRS |
| SWE1 | refines | SYS2 |
| SWE1 | uses | HSI |
| SWE2 | allocates | SWE1 |
| SWE3 | refines | SWE2 |
| SWE6_TC | verifies | SWE1 |
| SWE5_TC | verifies | SWE2 |
| SWE4_TC | verifies | SWE3 |
| SYS5_TC | verifies | SYS2 |
| SYS4_TC | verifies | SYS3/HSI |

규칙은 `alm.json`의 `link_rules`와 `coverage_rules`에서 수정합니다.

## AI 정제 (선택)

규칙 기반만으로 오프라인에서 동작합니다. AI를 쓰려면 `alm.json`의 `llm`을 설정하고 `--ai` 옵션으로 임포트합니다.

```json
"llm": {"provider": "anthropic", "model": "claude-sonnet-5-5", "api_key_env": "ANTHROPIC_API_KEY"}
"llm": {"provider": "openai_compatible", "base_url": "http://사내-LLM:8000", "model": "..."}
```

AI가 하는 일:
- SYS.2 / SWE.1 재분류
- 원자 단위 분할
- 품질 이슈 지적
- 검증 기준 초안 작성
- 그림 → Mermaid 코드 초안 생성

AI 결과는 모두 `draft` 상태로 들어가므로 반드시 사람이 검토·승인합니다. 고객 문서를 외부로 보낼 수 없다면 사내 LLM(`openai_compatible`)을 쓰면 됩니다.

## 저장 구조

```
프로젝트/
  alm.json          설정 (타입, ID 형식, 키워드, 링크 규칙) — Git 관리 권장
  .alm/alm.db       아이템, 링크, 이력, 베이스라인 (SQLite)
  .alm/assets/      추출된 그림 (원본 EMF/WMF 는 *.orig.* 로 보관)
```

## 한계와 다음 단계

- **Word 도형만으로 그린 다이어그램**: 비트맵이 없어 라벨만 추출합니다. 문서를 PDF로 변환해 임포트하면 벡터 렌더링으로 그림이 들어옵니다.
- **HWP**: 직접 지원하지 않습니다. 한컴오피스에서 DOCX나 PDF로 저장한 뒤 임포트하세요.
- **스캔본 PDF(이미지)**: OCR이 필요합니다. 먼저 `ocrmypdf` 등으로 텍스트 레이어를 만든 뒤 임포트하세요.
- **다중 사용자**: 사내 서버에서 `ecualm serve --host 0.0.0.0`으로 띄우면 여러 사람이 쓸 수 있습니다. 다만 아직 로그인·권한 기능은 없습니다.
- **전략 문서의 다음 단계**: Polarion REST 연동(push/pull), SWE.2 ARXML 연동, SWE.5/SWE.6 TC 자동 생성 스킬을 같은 저장소 위에 붙일 수 있게 설계했습니다.
