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

### AI 어시스턴트 (대화창 · 새 창 모드)

오른쪽 위 **AI** 버튼을 누르면 대화창이 열립니다. **새 창 ↗**을 누르면 대화창이 별도 창으로 떨어지고, 메인 창에서 보고 있는 단계와 선택한 아이템이 문맥으로 계속 전달됩니다. 두 창의 대화 기록은 자동으로 동기화됩니다.

- **AI 모드**: ⚙에서 공급자를 고릅니다. Anthropic Claude API, 또는 사내 LLM(vLLM, Ollama, LM Studio 같은 OpenAI 호환 서버) 중 하나입니다. 질문을 보낼 때 현재 화면, 선택 아이템과 그 상·하위 추적, 질문과 관련된 요구사항을 문맥으로 함께 보냅니다. AI는 답변과 함께 **전개, 링크, 아이템 생성, 문장 수정, 상태 변경**을 제안할 수 있습니다. 제안은 버튼으로만 표시되고 사용자가 눌러야 실행됩니다. 문장 수정 제안은 바뀐 부분을 표시해 보여 줍니다.
- **로컬 명령 모드**: 공급자를 연결하지 않았거나 호출이 실패하면 이 모드로 답합니다. `현황`, `감사`, `Suspect`, `FAIL`, `고아`, `모호`, ID(`SYS2-MOT-0003` 또는 원문 `REQ-ADAS-001`) 설명, `SYS2 → HWE1 전개`, 키워드 검색을 쓸 수 있습니다.
- **API 키**: 화면에서 입력하면 프로젝트의 `.alm/secrets.json`에만 저장되고 Git에서 제외됩니다. 브라우저로 다시 보내지 않으며, 환경변수(`ANTHROPIC_API_KEY`)가 있으면 그것을 먼저 씁니다. 사내 문서를 밖으로 보내면 안 되는 환경이라면 사내 LLM을 쓰세요.

### 원문 대조 (나란히 보기)

가져온 요구사양서 원문(PDF·DOC·DOCX·RTF·ODT)과 ALM 항목을 나란히 놓고 서로 연결해 봅니다.

- **여는 곳**: 단계 문서 화면 왼쪽 "원천"의 **원문 대조** 링크, 항목 상세의 **원문에서 보기**, 변경 분석 보고서의 **원문 비교**.
- **ALM 항목 ↔ 원문**: 왼쪽 항목을 누르면 오른쪽 원문 페이지의 해당 위치로 이동해 문장을 강조합니다. 표의 행이면 원문 ID 칸까지 강조합니다. 반대로 원문의 강조 영역을 누르면 왼쪽 항목으로 이동합니다. 이번 개정에서 바뀐 항목은 노랑, 신규는 초록으로 표시됩니다. 원문 이후 ALM에서 문장이 고쳐진 항목은 위쪽에 차이가 나옵니다.
- **개정 ↔ 개정**: 왼쪽을 이전 개정으로 바꾸면 두 개정 원문을 나란히 보여 줍니다. 한쪽에서 누른 항목이 양쪽에서 함께 강조되고, 위쪽에 이전 → 이후 문장 차이가 나옵니다. "바뀐 항목만"으로 변경점만 볼 수 있습니다.
- **위치 찾기 방식**: 각 개정 당시의 항목 문장을 원문의 글자 위치와 맞춥니다. 공백·줄바꿈·기호는 무시하고, 가져올 때 기록한 쪽 번호를 우선합니다. 여러 줄, 표 칸, 쪽 경계에 걸친 문장도 전체가 강조됩니다. eLSD 샘플(PDF·DOCX)에서 요구사항 위치를 모두 찾았습니다.
- **원문 보관**: 가져올 때마다 원문 파일이 `.alm/sources/<import_id>/`에 보관됩니다.
  - DOC·DOCX는 LibreOffice가 있으면 PDF로 바꿔 쪽 모양 그대로 보여 주고(Windows 기본 설치 경로도 찾습니다), 없으면 문단·표 구조 보기로 보여 줍니다.
  - 이 기능 전에 가져온 개정은 원문이 없을 수 있습니다. 그때는 화면에서 같은 파일을 올리면 됩니다.

### 요구사양서 개정 변경 분석 (AI)

같은 문서명으로 새 개정본을 가져오면 **변경 미리보기** 화면에 변경 분석이 먼저 나옵니다. 가져오기를 마치면 분석 보고서가 저장되고 보고서 화면으로 이동합니다(이력·베이스라인 → "요구사양서 변경 분석 보고서"에서 다시 볼 수 있습니다).

- **변경 유형**: 바뀐 요구사항마다 변경 유형을 판별합니다.
  - 수치 변경: 이전 → 이후 값과 증감률. 한계값이면 강화·완화를, 조건 문장이면 판정 임계값으로 구분합니다.
  - 의무 수준 변경(필수 ↔ 권고), 금지 조건 추가·삭제
  - ASIL 변경: 표의 ASIL 칸만 바뀐 것도 잡습니다.
  - 검증 방법 변경, 내용 추가·삭제
  - 표현만 수정, 신규·삭제
  - 의무 해제: "해야 한다"가 "바람직하다"로 바뀌어 요구사항으로 잡히지 않게 된 항목은 삭제가 아니라 의무 해제로 표시합니다.
- **영향과 조치**: 추적 링크를 따라 재검토할 하위 항목, 재시험할 TC, 영향받는 ASIL 항목을 세고, 영향도(높음·보통·낮음)와 권장 조치를 붙입니다.
- **AI 설명**: AI(Claude API 또는 사내 LLM)가 설정되어 있으면 항목별 설명, 개정 전체 요약, 고객에게 보낼 확인 질의를 더합니다. AI는 영향도를 올릴 수만 있고 내릴 수는 없습니다. AI가 없거나 호출이 실패하면 규칙 분석만으로 보고서를 만듭니다.
- **보고서 화면**: 영향 높은 기존 항목이 미리 선택돼 있고, **선택 항목으로 변경 요청 만들기**를 누르면 SUP.10 변경 요청이 생기며 영향 분석이 함께 저장됩니다. Excel로도 내보냅니다.
- 개정 비교 시 문장이 같아도 표의 ASIL·검증 방법 칸이 바뀌면 변경으로 잡습니다(이전에는 "동일"로 처리됐습니다).
- 샘플: `samples/CRS_eLSD_ECU_rev1.1.docx`(`python samples/make_elsd_rev.py`)는 rev 1.0 대비 다음 변경을 담고 있습니다: 응답 시간 강화, 협조 타임아웃 변경, 암전류 완화, ASIL B→C, 필수→권고, 금지 조건 추가, 전환 조건 추가, 표현 수정, 요구사항 1건 삭제, 1건 신규. rev 1.0을 `CRS_eLSD`로 가져온 뒤 같은 문서명으로 rev 1.1을 가져와 보세요.

### 지원 프로세스 (SUP.1 · SUP.8 · SUP.9 · SUP.10)

상단 **지원(SUP)** 버튼으로 엽니다. 다섯 종류의 기록이 같은 방식으로 동작합니다. 각 기록에는 필드, 연결 항목(역할 포함), 관련 기록(양방향), 담당, 기한, 전체 이력(누가·언제·무엇을, 상태 전환과 코멘트)이 있습니다. 상태 전환에는 조건이 걸려 있어, 빠진 것이 있으면 무엇이 부족한지 알려 줍니다.

| 기록 | 흐름 | 주요 조건 |
|---|---|---|
| **문제 PR (SUP.9)** | 접수 → 분석 → 조치 → 검증 → 종결 (반려·중복) | 조치로 가려면 원인 분류·근본 원인, 검증으로 가려면 영구 조치가 필요합니다. 종결하려면 확인 TC가 조치 이후 PASS여야 하고, 안전 관련 문제는 PM이 종결합니다. |
| **변경 요청 CR (SUP.10)** | 접수 → 영향 분석 → CCB 검토 → 승인 → 반영 → 검증 → 종결 (반려·보류) | CCB에 올리려면 영향 분석 저장, 추정 공수, 안전 영향이 필요합니다. 승인·반려는 PM이 결정 근거를 남겨야 합니다. 종결하려면 재시험 TC가 승인 이후 PASS여야 하고, 바뀌지 않은 변경 대상 항목은 사유를 남겨야 합니다. |
| **QA 점검 (SUP.1)** | 계획 → 완료 | 단계·프로세스별 체크리스트가 만들어지고, 일부 항목은 ALM 데이터로 자동 판정합니다. 완료하려면 모든 항목을 판정하고 요약을 써야 합니다. |
| **QA 지적 (SUP.1)** | 열림 → 조치 중 → 조치 완료 → 확인 완료 | 시정 조치를 기록해야 합니다. 조치한 사람은 직접 확인할 수 없습니다(독립성). 에스컬레이션도 기록됩니다. |
| **릴리스 (SUP.8)** | 준비 → 릴리스 | 감사 오류, 포함 세션 FAIL, 미해결 안전 문제, 이 릴리스 대상 미종결 CR, 커밋 기록을 검사합니다. 통과하지 못하면 예외 사유가 있어야 하며, 릴리스할 때 항목 베이스라인을 자동으로 만듭니다. |

- **문제 등록**: 테스트 세션에서 FAIL·BLOCKED 행의 "문제 등록"을 누르면 기대·실제 결과와 조건으로 문제 기록이 만들어집니다. TC는 발견·확인 TC로, 검증 대상 요구사항은 영향 항목으로 연결되고, 결함 칸에 PR 번호가 들어갑니다. 대상이 ASIL이면 안전 관련이 "확인 필요"로 표시됩니다.
- **8D 보고서**: 문제 기록을 D1~D8 양식의 Word 파일로 내보냅니다.
- **영향 분석**: 변경 대상 항목에서 하위 추적 링크를 따라가 변경·검토·재시험 대상을 단계별로 나누고, ASIL 항목, 관련 일정 작업, 추정 공수를 계산해 근거(시점·버전 포함)로 저장합니다. 승인 후에는 항목별로 "v3→v4"처럼 실제로 바뀌었는지, 재시험 TC의 현재 결과가 함께 보입니다.
- **QA 자동 판정**: 요구사항 단계는 문장 품질, 필수 속성, 상위 추적, TC 커버, Suspect, 승인 상태를 봅니다. 시험 단계는 추적, 실행, FAIL의 문제 등록 여부, 증빙, 재시험 필요를 봅니다. SUP.8·9·10·MAN.3 같은 프로세스는 기한 초과, 근본 원인 기록, 영향 분석·결정 근거, 베이스라인·릴리스, 일정 기준선을 봅니다. NOK 항목은 버튼 하나로 QA 지적이 됩니다.
- **형상 관리**: 베이스라인 두 개(또는 베이스라인과 현재)를 비교해 추가·변경·삭제 항목과 링크 변화를 보여 줍니다. 백업은 관리자만 받을 수 있고, DB 일관성 사본·증빙·이미지·alm.json을 zip으로 묶습니다(API 키 제외). `ecualm backup x.zip` / `ecualm --root <폴더> restore x.zip`
- **개요**: 미해결 문제, 안전 문제, MTTR, CCB 대기, 열린 QA 지적, 기한 초과, 최근 릴리스, 주별 접수·종결, 원인 분류, 오래된 미해결 문제를 보여 줍니다.
- **감사 콘솔 연동**: 기한 초과 기록과 미해결 안전 문제는 경고, 영향 분석 없이 승인된 CR은 오류로 나옵니다.
- 항목 상세 화면에 그 항목과 연결된 문제·변경 요청·QA 기록이 보입니다. 종류별 Excel 내보내기를 지원합니다.
- SUP.11(머신러닝 데이터 관리)은 ML 컴포넌트가 있는 프로젝트에만 해당해서 넣지 않았습니다.

### 테스트 세션 · 결과 · 증빙 · 시험 대시보드

상단 **시험** 버튼으로 엽니다.

- **새 테스트 세션**: 검증 단계(SWE.4~6, HWE.3~4, SYS.4~5), 빌드/SW 버전, HW 샘플, 시험 환경, 계획 기간, 담당을 정하고 TC를 고릅니다. 고르는 조건은 모든 TC, 미합격·재시험 필요, FAIL·BLOCKED만(재시험), 실행 이력 없음, 대상이 바뀐 TC 중 하나이고, 도메인과 검색어로 더 좁힐 수 있습니다. 고르는 동안 선택될 TC 수가 바로 보입니다.
- **결과 입력**: 행마다 PASS / FAIL / BLK / N/A 버튼, 실제 결과, 결함 번호를 입력합니다. FAIL은 실제 결과가 있어야 저장됩니다. 결과는 TC의 최근 결과에도 반영되므로 감사의 `test_fail`·`result_stale`, 항목 화면의 결과 표시가 함께 갱신됩니다. 실행자·시각·실행 당시 TC 버전이 기록되고, 실행 후 TC가 바뀌면 "TC 변경"이 표시됩니다.
- **증빙**: TC 행 또는 세션 전체에 파일(사진·파형·로그·보고서, 50MB 이하)을 끌어 놓거나 선택해 올립니다. `.alm/evidence`에 SHA-256 이름으로 저장되고, 보고서에 해시가 남습니다. 이미지는 썸네일로 보이며 PDF·텍스트는 브라우저에서, 나머지는 내려받기로 엽니다.
- **세션 상태**: 계획 → 진행(첫 결과 입력 시 자동) → 완료(판정 PASS/FAIL/BLOCKED 기록, 결과·증빙 잠김) 또는 중단. 닫힌 세션은 PM·관리자만 다시 열 수 있습니다.
- **결과 보고서 (Excel, 15-52)**: 요약(환경·기간·판정·집계), TC 결과(대상·기대 결과·합격 기준·실제 결과·결함·실행자·증빙), 증빙 목록(SHA-256) 시트로 내보냅니다.
- **대시보드**: TC 수, 실행률, 합격률, FAIL, BLOCKED, 재시험 필요, 진행 세션, 증빙 수를 보여 줍니다. 차트는 단계별 최근 결과 막대, 요구사항 검증 커버리지(대상 항목 중 연결 TC가 모두 PASS인 비율), 일별 누적 실행·PASS 추이, 세션 목록, 열린 실패(결함·관찰 내용·대상 요구사항), 도메인별 FAIL, 불안정(PASS↔FAIL 반복) TC입니다.

### 산출물 표 보기 · 필수 컬럼 · 컬럼 추가

단계 화면의 **표** 탭에서 그 단계의 산출물을 스프레드시트처럼 봅니다. 산출물마다 PAM 4.0 정보 항목에 맞춘 필수 컬럼(머리글에 `*`)이 정해져 있고, 비어 있는 필수 칸은 빨간 배경과 "필수"로 표시됩니다. 표 위에는 필수 충족률, 누락 칸 수, 완료 행 수가 나옵니다.

| 산출물 | 필수 컬럼 |
|---|---|
| SYS.1 CRS (17-00) | ID, 고객 요구사항, 준수 여부(C/PC/NC), SYS.2 전개, 상태 |
| SYS.2 SyRS (17-00, 17-54) | ID, 요구사항, 분야(HW/SW), ASIL, 검증 기준, 상위(CRS), 검증 TC(SYS.5), 상태 |
| SYS.3 SAD·HSI (04-06) | ID, 요소명, 설명, 할당 요구사항, 통합 TC(SYS.4), 상태 |
| HWE.1 HWRS · HWE.2 HWAD (04-52/53) | 요구사항/블록명, ASIL, 검증 기준·부품 번호, 상위·할당, 하위 블록, 검증 TC, 상태 |
| SWE.1 SWRS (17-00, 17-54) | ID, SW 요구사항, ASIL, Pre-condition, Timing, Output, 검증 기준, 상위, SW 컴포넌트, 검증 TC(SWE.6), 상태 |
| SWE.2 SWAD (04-04) · SWE.3 SWDD (04-05/11-05) | 컴포넌트/유닛, 책임, AUTOSAR 계층·주기 / 소스 파일·시그니처, 할당, 통합·유닛 TC, 상태 |
| 검증 명세·결과 (08-60, 15-52) | ID, 시험명, 시험 종류, 사전 조건, 절차·입력, 기대 결과, 합격 기준, 검증 대상, 최근 결과, 상태 |

- 칸을 누르면 바로 고칠 수 있습니다(엔지니어 이상). 수정은 이력에 남습니다. 요구사항 내용(본문·ASIL·검증 기준·스펙)이 바뀌면 하위 항목이 Suspect가 되고, 관리용 값(준수 여부·의견·검증 방법·추가 컬럼)은 Suspect를 만들지 않습니다.
- 링크 컬럼(상위·하위·검증 TC)은 추적 링크에서 자동으로 채워지며, 눌러서 해당 항목을 열 수 있습니다.
- **컬럼 추가**(PM·관리자): 이름, 유형(텍스트·긴 텍스트·선택 목록·숫자·날짜·담당자), 선택 항목, 설명, 필수 여부를 정합니다. 단계별로 저장되고 Excel 내보내기에도 들어갑니다.
- **컬럼** 버튼으로 선택 컬럼을 숨기거나 보일 수 있습니다(브라우저에 기억). 필수 컬럼은 항상 보입니다. 머리글을 누르면 정렬되고, 검색·상태 필터·"필수 누락 행만" 필터가 있습니다.
- 감사 콘솔에 `wp_required` 규칙이 추가되었습니다: 검토·승인 상태인데 필수 컬럼이 비면 경고, 초안이면 정보로 나옵니다.
- **Excel**: 표 그대로(필수 머리글 파랑, 누락 칸 빨강, 자동 필터) 내보냅니다.
- SYS.1 → SYS.2 전개 시 고객 문서 표의 ASIL·검증 방법을 SYS.2로 옮겨 옵니다.

### 로그인 · 권한

웹 UI는 로그인해야 쓸 수 있습니다. 처음 열면 **첫 관리자 계정 만들기** 화면이 나오며, 이 화면은 서버 PC(localhost)에서만 동작합니다. 그 뒤 관리자가 오른쪽 위 이름 → **사용자 관리**에서 계정을 만듭니다. 새 계정과 초기화한 비밀번호는 임시 비밀번호라서 첫 로그인 때 바꾸게 됩니다.

| 역할 | 할 수 있는 일 |
|---|---|
| 조회 | 모든 화면 보기, AI 어시스턴트 질문 |
| 엔지니어 | 요구사항·링크 편집, 전개, 가져오기, **본인 작업의 진척·실적 공수 입력** |
| PM | 엔지니어 권한 + 일정·공수 계획 편집, 일정 기준선, 아이템 베이스라인 |
| 관리자 | 전체 + 사용자 관리, AI 설정 |

- 비밀번호는 PBKDF2-SHA256(솔트, 24만 회)으로, 세션·API 토큰은 SHA-256 해시로만 `.alm/alm.db`에 저장됩니다. 세션은 12시간, 2시간 동안 활동이 없으면 끝납니다(`alm.json`의 `auth.session_hours`, `auth.idle_minutes`).
- 로그인을 5번 틀리면 1분 동안 잠깁니다. 로그인·실패·계정 변경 기록은 사용자 관리 화면에 남습니다.
- 이력의 작성자는 로그인한 아이디로 기록됩니다.
- CI·스크립트는 API 토큰을 씁니다: `ecualm user token ci-bot` → `curl -H "Authorization: Bearer alm_…" -d @results.json http://서버:8765/api/results`
- 명령줄: `ecualm user list | add <id> --role engineer | passwd <id> | role <id> --role manager | disable <id> | token <id>`
- 혼자 쓰는 PC에서 로그인을 끄려면 `alm.json`에 `"auth": {"enabled": false}`를 넣습니다.

### 프로젝트 일정·공수 (ASPICE MAN.3 간트)

상단 **일정·공수** 버튼으로 엽니다. 행 하나가 MAN.3 작업 패키지(14-10)이고, 다음 항목을 가집니다: WBS 번호, 작업, ASPICE 프로세스, 산출물(PAM 4.0 정보 항목), 담당, 계획 시작·종료, 계획·실적 공수(MD), 진척률, 상태, 선행 작업(종료→시작), 기준선, 비고, ALM 단계 연동.

- **표준 WBS**: MAN.3·MAN.5, SYS.1~5, HWE.1~4, SWE.1~6, SUP.1/8/9/10 작업과 킥오프 및 A~D 샘플 마일스톤을 공수 초안과 함께 한 번에 만듭니다. 담당은 역할명으로 들어가니 실제 사람으로 바꾸세요. (`ecualm plan template 2026-11-02`)
- **간트**: 주·월·분기 확대, 요약 행 접기, 프로세스·담당·검색 필터를 지원합니다. 오늘 선, 선후행 화살표(충돌하면 빨강), 기준선 막대, 진척 채움, 마일스톤 ◆가 표시됩니다. PM은 막대를 끌어 일정을 옮기고 오른쪽 끝을 끌어 기간을 바꿉니다.
- **자동 판정**: 지연, 착수 지연, 기준선 초과(+일), 공수 초과(실적 > 계획 110%), 선후행 충돌을 표시합니다. 요약 행의 기간·공수·진척(공수 가중)은 하위 작업에서 집계됩니다.
- **EVM**: 오늘 기준 PV·EV·AC를 계산하고 SPI(일정)·CPI(공수)를 보여 줍니다. PV는 기준선 일정, 기준선이 없으면 계획 일정으로 계산합니다.
- **공수 부하**: 담당별 주간 계획 공수를 근무일(휴일 제외)에 고르게 나눠 보여 주고, 1인 가용(기본 5 MD/주)을 넘는 주에 ▲를 표시합니다.
- **ALM 연동**: 작업에 단계(SYS2, SWE1 …)를 연결하면 그 단계 아이템의 승인률이 함께 보이고, 버튼 하나로 진척률에 반영할 수 있습니다.
- **기준선·변경 이력**: 기준선 저장으로 승인된 계획을 고정하고, 모든 계획 변경(누가·언제·무엇을)이 이력에 남습니다(MAN.3 계획 조정 근거).
- **Excel 양식**: "프로젝트 일정·공수 계획서 (ASPICE MAN.3)" 시트(WBS 표와 주 단위 간트, A3 가로 인쇄 맞춤), 공수 부하 시트, 계획 변경 이력 시트로 내보냅니다. (`ecualm plan export plan.xlsx`)

### EPS 제어기 고객 요구사양서 샘플 (49페이지)

`samples/CRS_EPS_ECU_rev1.0.pdf` / `.docx`는 컬럼 타입 EPS ECU 고객 요구사양서 예시입니다. 회사명과 사내 규격 번호는 가상입니다. 요구사항 200개(REQ-ASSIST/ADAS/SENS/SAFE/COM/DIAG/…)에 ASIL과 검증 방법이 달려 있고, 표 67개(요구사항 표, CAN 메시지·신호, UDS·DID·DTC, 커넥터 핀, 환경·EMC, 보조 토크 맵, 캘리브레이션 파라미터)와 그림 11개(시스템 경계, 블록도, 보조 토크 맵, 상태도, 디레이팅, TAS 이중 채널, FTTI, 네트워크, 스텝 응답, 커넥터)가 들어 있습니다.

```bash
ecualm import samples/CRS_EPS_ECU_rev1.0.pdf --doc CRS_EPS --rev 1.0 --mode crs   # 웹에서는 "요구사항 가져오기" → SYS.1
ecualm derive SYS1 SYS2      # 고객 요구사항 → PAM 4.0 SRS 초안 (원문 ID 유지)
python samples/make_eps_crs.py   # 문서 다시 생성 (LibreOffice 가 있으면 PDF 도 생성)
```

DOCX에서는 원문 ID 200개가 모두 인식되고, PDF에서는 199개가 인식됩니다. 나머지 1개는 페이지 경계에서 ID 칸이 잘린 경우인데, 문장은 정상으로 들어옵니다.

### eLSD 제어기 고객 요구사양서 샘플 (49페이지, AUTOSAR 포함)

`samples/CRS_eLSD_ECU_rev1.0.pdf` / `.docx`는 후륜 전자식 차동제한장치(eLSD) ECU 고객 요구사양서 예시입니다(가상 회사·규격). 요구사항 178개(REQ-LOCK/YAW/MODE/CLU/THERM/SENS/COM/DIAG/SAFE/AR/NVM/SEC/UPD/ELEC/ENV/PERF/EOL), 표 86개, 그림 12개가 들어 있습니다. 9장 AUTOSAR 아키텍처에는 플랫폼·계층 구조, SWC·포트 인터페이스, OS 태스크·멀티코어 할당, BSW 모듈 구성, Dem→DTC→FiM 매핑, BswM 모드 규칙, NvM 블록, 타이밍 체인, FFI, 변형 관리·보안 BSW, ARXML·A2L 산출물 요구사항이 있습니다.

```bash
ecualm import samples/CRS_eLSD_ECU_rev1.0.pdf --doc CRS_eLSD --rev 1.0 --mode crs
ecualm derive SYS1 SYS2
python samples/make_elsd_crs.py
```

DOCX와 PDF 모두 원문 ID 178개가 전부 인식됩니다.

### HW 공정 (HWE.1 ~ HWE.4) 과 블록도

V-모델에 HW 분기가 있습니다. **SYS.2 → HWE.1**(HW 요구사항) **→ HWE.2**(HW 블록) **⇄ HWE.3**(HW 설계 검증) / **HWE.4**(HW 적격성 시험)입니다.

- **블록도 탭** (SYS.3 · HWE.2 · SWE.2): 블록 하나하나가 추적 아이템이고, 블록 사이의 선도 `IF-0001` 같은 ID를 가진 **인터페이스 아이템**입니다. 블록을 끌어 배치하면 위치만 저장되고 버전은 바뀌지 않습니다. 블록 오른쪽 ● 를 다른 블록으로 끌면 인터페이스가 생기고(신호 분류: 전원·PWM·SPI·CAN·아날로그·디지털·전력 출력), 두 블록에 `connects` 링크가 걸립니다. 블록이 바뀌면 그 블록에 연결된 인터페이스, 검증 TC, SW 쪽 링크가 모두 Suspect가 됩니다.
- **인스펙터**: 블록이나 선을 누르면 오른쪽에 ▲상위 요구사항(satisfies/refines), ▼이 블록을 제어하는 SW(`SWE2/SWE3 —controls→ HWE2`), ▼검증 TC와 PASS/FAIL, 인터페이스 목록이 나옵니다. 부품 번호, 안전 메커니즘, ASIL은 여기서 바로 고칩니다. **추적 JSON**은 아이템 하나의 추적 정보를 한 번에 담은 JSON입니다(`ecualm artifact <ID>`).
- **시험 결과와 파형**: CI, HIL, 벤치 결과를 `POST /api/results` 또는 `ecualm results results.json`으로 넣으면 TC에 결과가 붙고, 파형이 있으면 FTTI 반응 시간과 한계를 함께 그립니다. 감사에서는 FAIL이 `test_fail`(error)로, PASS를 받은 뒤 대상이 바뀐 경우가 `result_stale`(warn, 재시험 필요)로 나옵니다.
- **Diagram-as-Code**: 블록도는 `ecualm arch export HWE2 hw.json`으로 저장해 Git에 커밋하고, `ecualm arch import hw.json`으로 다시 넣습니다. 같은 파일을 여러 번 넣어도 중복되지 않습니다. 화면의 "샘플 HW 아키텍처"(또는 `ecualm arch sample`)는 30페이지 SRS의 BLDC ECU(TC364, DRV8305, TLF35584, TJA1043, AS5047) 블록도, 인터페이스 10개, HWE.3 TC 4개, 벤치 결과 3건(과전류 차단 6.2µs PASS, 와치독 11.2ms PASS, CAN 복구 FAIL)을 불러옵니다.

```bash
ecualm derive SYS2 HWE1 && ecualm derive SYS2 SYS3 && ecualm derive SYS3 HWE2 && ecualm derive HWE1 HWE2
ecualm derive HWE2 HWE3 && ecualm derive HWE1 HWE4
ecualm arch sample                              # BLDC ECU 블록도 + 시험 결과 샘플
ecualm results ci_results.json --strict         # CI: 모르는 TC 가 있으면 종료 코드 2
ecualm audit --fail-on error                    # test_fail 이 있으면 실패
```

시험 결과 JSON 형식 (파형은 선택):

```json
{"results": [{"tc": "HWE3-TC-SAFE-0003", "status": "PASS", "run_id": "HIL-1288", "tool": "TRACE32 + NI DAQ",
  "metrics": {"reaction": 6.2, "limit": 10, "unit": "µs", "label": "단락 주입 → EN_GATE 차단"},
  "waveform": {"x_unit": "µs", "x": [0, 0.25, 0.5],
               "panels": [{"title": "상전류", "unit": "A", "series": [{"name": "I_U", "y": [8, 9, 10]}], "thresholds": [{"y": 20, "label": "20A"}]},
                          {"kind": "digital", "series": [{"name": "EN_GATE", "y": [1, 1, 0]}]}],
               "markers": [{"x": 0, "label": "단락 주입"}]}}]}
```

`tc` 에는 ECU-ALM ID 또는 TC의 원문 ID(native_id)를 씁니다. 아날로그 값과 디지털 신호는 시간축 하나를 공유하는 별도 패널로 그립니다. y축을 두 개 쓰지 않습니다.

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
| SYS4_TC | verifies | SYS3/HSI/IF |
| HWE1 | refines | SYS2 |
| HWE2 | satisfies / refines | HWE1 / SYS3 |
| IF (인터페이스) | connects | SYS3/HWE2/SWE2 블록 |
| SWE2/SWE3 | controls | HWE2 |
| HWE3_TC | verifies | HWE2/IF |
| HWE4_TC | verifies | HWE1 |

규칙은 `alm.json`의 `link_rules`와 `coverage_rules`에서 수정합니다. 예전 버전이 만든 `alm.json`에도 새 단계(HWE.1~4)와 규칙이 자동으로 추가됩니다. 이 자동 추가를 원하지 않으면 `"strict_lists": true`를 넣으세요.

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
- **다중 사용자**: 사내 서버에서 `ecualm serve --host 0.0.0.0`으로 띄우면 여러 사람이 로그인해서 씁니다. 서버는 HTTP로 동작하므로 사내망 밖에 열 때는 HTTPS 리버스 프록시(nginx 등) 뒤에 두세요.
- **전략 문서의 다음 단계**: Polarion REST 연동(push/pull), SWE.2 ARXML 연동, SWE.5/SWE.6 TC 자동 생성 스킬을 같은 저장소 위에 붙일 수 있게 설계했습니다.
