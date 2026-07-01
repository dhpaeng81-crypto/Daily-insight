# 부동산 경매/공매 추천 에이전트 — 설정 가이드

설계 배경은 [`DESIGN.md`](./DESIGN.md) 참고. 이 문서는 실행에 필요한 키 발급과
로컬 실행 방법만 다룬다.

## 1. 온비드(공공데이터포털) API 키 발급

1. https://www.data.go.kr 회원가입 후 로그인.
2. 아래 서비스들을 각각 검색해서 **활용신청**을 누른다 (모두 무료, 개발계정
   기준 일 약 1,000건 트래픽):
   - `한국자산관리공사_차세대 온비드 부동산 물건목록 조회서비스`
   - `한국자산관리공사_차세대 온비드 물건상세 입찰정보 조회서비스`
   - `한국자산관리공사_온비드 코드 조회서비스`
3. 승인은 대개 자동 또는 몇 시간 내로 완료된다. 승인 후 **마이페이지 >
   오픈API > 개발계정**에서 인증키(서비스키)를 확인한다. 세 서비스가 같은
   공급기관(캠코)이면 서비스키 하나를 공용으로 쓸 수 있는 경우가 많다.
4. 발급받은 키를 환경변수 `ONBID_SERVICE_KEY`로 설정한다.

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

- 공매(온비드)와 법원 경매는 법적으로 다른 절차다. 법원 경매 커버리지가
  필요하면 `court_auction_source.py`를 직접 구현하되, ToS 검토를 먼저 하자.
- 권리분석(등기부등본 기반 임차인·근저당 확인)은 자동화되어 있지 않다. 답변에는
  항상 "직접 확인 필요" 안내가 포함된다.
- 사용자 프로필은 `auction_agent/data/`에 로컬 JSON으로 저장되며 이 디렉터리는
  `.gitignore` 처리되어 있다. 실서비스에서는 별도 비공개 스토리지를 쓰자.
