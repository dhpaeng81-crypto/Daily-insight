# 부동산 경매/공매 추천 에이전트 — 설정 가이드

설계 배경은 [`DESIGN.md`](./DESIGN.md) 참고. 이 문서는 실행에 필요한 키 발급과
로컬 실행 방법만 다룬다.

## 1. 온비드(공공데이터포털) API 키 발급

1. https://www.data.go.kr 회원가입 후 로그인.
2. `한국자산관리공사_차세대 온비드 부동산 물건목록 조회서비스`를 검색해서
   **활용신청**을 누른다 (무료, 개발계정 기준 일 약 1,000건 트래픽). 이
   프로젝트의 `onbid_source.py`는 이 서비스의 물건목록 기능
   (`getRlstCltrList2`, End Point:
   `https://apis.data.go.kr/B010003/OnbidRlstListSrvc2/getRlstCltrList2`)을
   직접 HTTP로 호출한다 — 이름이 비슷한 `한국자산관리공사_온비드 물건 정보
   조회서비스`(구버전)나 `차세대 온비드 공고상세 조회서비스`(개별 물건
   상세용, 목록 조회는 안 됨)는 지금 코드와 맞지 않으니 신청하지 않아도 된다.
   나중에 물건 상세(권리관계 등)나 코드 조회가 필요해지면
   `한국자산관리공사_온비드 코드 조회서비스`도 추가로 신청하면 된다.
3. 승인은 대개 자동 또는 몇 시간 내로 완료된다. 승인 후 **마이페이지 >
   오픈API > 개발계정**에서 인증키(서비스키)를 확인한다.
4. 발급받은 키를 환경변수 `ONBID_SERVICE_KEY`로 설정한다. **절대 이 키를
   코드에 하드코딩하거나 git에 커밋하지 말 것** — 운영 환경에서는 기존
   `TELEGRAM_TOKEN`/`OPENAI_API_KEY`와 동일하게 GitHub Actions Secrets에
   등록해서 워크플로의 `env:`로 주입한다.

## 2. 텔레그램 봇 생성

기존 레포가 이미 `TELEGRAM_TOKEN`/`TELEGRAM_CHAT_ID`를 알림용으로 쓰고 있다면
그 봇을 재사용해도 되고, 대화형 명령어를 분리하고 싶다면 `@BotFather`에게
`/newbot`으로 새 봇을 만들어도 된다. 발급받은 토큰을 `TELEGRAM_TOKEN`에 설정.

## 3. 환경변수

```
ONBID_SERVICE_KEY=...
TELEGRAM_TOKEN=...
AUCTION_PROFILES_PATH=auction_agent/data/profiles.json   # 선택, 기본값 동일
ENABLE_COURT_SCRAPING=false                               # 선택, 기본 false
```

## 4. 설치 및 실행 (로컬 폴링 방식)

```bash
pip install -r auction_agent/requirements.txt
python -m auction_agent.telegram_bot
```

폴링 방식은 프로세스가 켜져 있는 동안만 동작한다. 상시 운영하려면 DESIGN.md
3.4절에서 설명한 대로 웹훅 + 서버리스, 또는 소형 상시 서버에 배포해야 한다.

## 5. 알려진 한계

- `onbid_source.py`는 GitHub Actions의 `auction_agent_smoke_test.yml`
  워크플로(workflow_dispatch로 수동 실행 가능)로 실제 라이브 호출을 통해
  검증했다. 재산종류코드(`prptDivCd`)는 확인된 `0007,0005`(압류재산,
  기타일반재산) 두 가지만 기본값으로 쓴다 — 다른 코드(공유재산·물류센터 등)를
  넓히려면 실제 호출로 유효성을 먼저 확인하자. 존재하지 않는 코드를 섞으면
  요청 전체가 거부된다.
- 공매(온비드)와 법원 경매는 법적으로 다른 절차다. 법원 경매 커버리지가
  필요하면 `court_auction_source.py`를 직접 구현하되, ToS 검토를 먼저 하자.
- 권리분석(등기부등본 기반 임차인·근저당 확인)은 자동화되어 있지 않다. 답변에는
  항상 "직접 확인 필요" 안내가 포함된다.
- 사용자 프로필은 `auction_agent/data/`에 로컬 JSON으로 저장되며 이 디렉터리는
  `.gitignore` 처리되어 있다. 실서비스에서는 별도 비공개 스토리지를 쓰자.
