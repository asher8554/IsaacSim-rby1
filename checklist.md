# 체크리스트 — RB-Y1 A × Isaac Sim 6.2 환경

- [x] 환경 조사: Isaac Sim 6.2.0 `C:\isaacsim-6.2`, RTX 3070 8 GB, WSL Ubuntu-24.04, Docker 없음
- [x] Notion 기존 지식 확인 (RB-Y1 모델 가이드, LeRobot × Isaac Sim 가이드)
- [x] 공식 저장소 clone: rby1-sim-isaac, rby1-sdk
- [x] 공식 이미지 `0.11.0-a_v1.2-isaac6.2.0`에서 rby1 core만 추출 (`tools/fetch_rby1_core.py`)
- [x] app_main 의존 라이브러리 확인 (`ldd`, 누락 없음)
- [x] TCP 링크 코덱 + TcpBridge 작성, 자체 점검 통과 (WSL·Isaac 양쪽)
- [x] Windows→WSL 왕복 측정: 평균 0.383 ms
- [x] 모드 A Action Graph 스크립트 작성, headless 검증 PASS (최대 오차 2.84°)
- [x] 모드 B 스크립트(RBY1Task + TcpBridge), WSL 릴레이, start_core.sh 작성
- [x] WSL venv `~/rby1-venv`에 rby1-sdk 0.10.1 오프라인 설치
- [x] 가이드 문서 README.md
- [ ] 승인 후: `verify_headless.py builtin` (공식 RBY1Task 실행)
- [ ] 승인 후: `start_core.sh` 실행, `udp_protocol.so` import 확인
- [ ] 승인 후: `verify_headless.py core` + SDK 예제 03/23 실행
- [ ] GUI(바로가기)에서 두 모드 화면 확인
- [ ] (사용자 판단) WSL DNS 근본 해결 `.wslconfig dnsTunneling=false`
