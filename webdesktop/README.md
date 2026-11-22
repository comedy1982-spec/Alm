# Web Desktop

ECU ALM과 보조 앱(계산기·메모장·엑셀·브라우저·터미널)을 브라우저 하나에서 창으로 띄워 쓰는 웹 데스크톱입니다. HTML 파일 하나로 되어 있고 설치할 것은 없습니다.

## 실행 (Windows)

1. ECU ALM을 먼저 켭니다: 저장소 루트의 `run_windows.bat` (http://localhost:8765)
2. 이 폴더의 `start_web_desktop.bat`을 실행합니다. 크롬에서 http://localhost:8000/web-desktop.html 이 열립니다.
3. 바탕화면의 **ECU ALM** 아이콘을 누르면 ALM이 웹 데스크톱 창 안에 열립니다.

macOS·Linux에서는 이 폴더에서 `python3 -m http.server 8000 --bind 127.0.0.1`을 실행하고 같은 주소를 엽니다.

> `web-desktop.html`을 더블클릭해서 바로(file://) 열지 마세요. ECU ALM 로그인 쿠키가 `SameSite=Strict`라서 창 안에서 로그인이 유지되지 않습니다. 웹 데스크톱도 `localhost`에서 열어야 합니다.

## 앱

| 앱 | 내용 |
|---|---|
| ECU ALM | 로컬 ECU ALM 서버를 창 안에 띄웁니다. 웹 데스크톱을 localhost가 아닌 곳에서 열면 주소 입력과 새 탭 열기 런처로 바뀝니다. 폰처럼 다른 기기에서 열 때는 PC의 IP 주소를 입력하고, ALM을 `ecualm serve --host 0.0.0.0`으로 실행합니다. |
| 엑셀 | 수식(사칙연산, 비교, `&`, 셀·범위 참조)과 SUM·AVERAGE·MIN·MAX·COUNT·COUNTA·PRODUCT·IF·AND·OR·NOT·ROUND·ABS·SQRT·CONCAT·LEN·UPPER·LOWER를 지원합니다. .xlsx/.xls/.csv를 열고 .xlsx로 저장합니다(SheetJS를 cdnjs에서 필요할 때 불러옴). 엑셀과 복사·붙여넣기로 주고받을 수 있습니다. |
| 브라우저 | 주소창이 있는 iframe 브라우저입니다. 로컬 서버는 창 안에 열리고, 다른 페이지 안에 뜨는 걸 막아 둔 사이트(구글, 네이버 등)는 `↗ 새 탭`으로 엽니다. |
| 메모장 | 여러 메모를 브라우저(localStorage)에 자동 저장합니다. |
| 계산기 | 키보드 입력을 지원합니다. |
| 터미널 | `help`, `ls`, `open <앱>`, `web <주소>`, `calc <수식>`, `memo <내용>`, `notes`, `ps`, `kill <pid>`, `focus <pid>` |

## 앱 추가하기

`web-desktop.html`의 `APPS` 목록에 항목을 하나 추가하면 바탕화면 아이콘, 시작 메뉴, 터미널 `open` 명령에 자동으로 들어갑니다.

```js
myapp: { name: "내 앱", glyph: "A", color: "#2563eb", w: 600, h: 400, mount: (root, opts) => { root.innerHTML = "..."; } },
```

`mount`가 함수를 반환하면 창을 닫을 때 그 함수가 호출됩니다(정리용).

## 데이터

메모, 엑셀 시트, ALM 주소는 이 브라우저의 localStorage에만 저장됩니다. 다른 브라우저나 기기와는 공유되지 않습니다.
