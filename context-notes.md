# 작업 노트 — 결정과 이유

## 2026-11-09

- **Isaac Sim은 Windows 네이티브, rby1 core는 WSL.** 공식 시뮬레이터는 Linux Docker 전용이다. 이 PC에는 Docker가 없고, Isaac Sim RTX 렌더러는 WSL에서 돌지 않는다. 사용자는 바로가기 GUI를 쓰길 원한다.
- **core는 Docker 없이 레지스트리 API로 추출.** 10.5 GB Isaac Sim 레이어를 건너뛰고 200 MB 미만 레이어만 받았다. `/opt/rby1-sim-isaac`(sdk/app/app_main, internal/udp_protocol.so)만 꺼낸다.
- **코덱은 재구현하지 않고 공식 .so를 WSL 릴레이에서 사용.** 공개 헤더(`real_time_control_protocol.h`)의 명령 패킷에는 kp/kd가 없다. 그런데 RBY1Task는 7개 필드(kp, kd 포함)를 받는다. 즉 isaac 브랜치 core는 비공개 확장 포맷을 쓴다. 역분석하지 않고 공식 바이너리를 그대로 쓴다.
- **Windows↔WSL은 TCP 5010.** WSL2 NAT 모드에서 Windows localhost TCP는 자동으로 전달된다. UDP는 WSL IP 탐색과 Windows 방화벽 인바운드 허용이 필요하다. `.wslconfig` 미러 모드는 사용자 전역 설정을 바꾼다. 측정 RTT는 평균 0.38 ms다.
- **RBY1Task 무수정 재사용.** `sys.modules["rby1_udp_bridge"]`에 TcpBridge를 넣어 Linux 전용 import를 피했다. GUI에서는 World가 물리 콜백을 자동으로 걸지 않는다(6.2 `World.step_async`는 수동 호출). 콜백 하나에서 `post_physics_step → step_async` 순서로 불러 공식 루프와 같은 순서를 만들었다.
- **명령 대기 상한 0.2 s.** 공식 브리지는 무한 대기한다. GUI 메인 스레드라 core가 죽으면 앱이 멈춘다. 연결이 끊긴 동안은 기다리지 않는다.
- **모드 A는 USD 드라이브 기본값(K100/D10, °단위) 그대로.** 60 Hz 기본 물리에서 5 s 안에 2.84° 이내로 수렴했다.
- **WSL venv 별도 생성.** rby1-sdk 0.10.1은 numpy>=2.0.1이 필요하다. Ubuntu 기본 numpy는 1.26.4다. Isaac Sim 6.2 번들 numpy는 2.3.1이므로 udp_protocol.so도 numpy 2 기준일 가능성이 높다(미확인). 릴레이도 venv Python으로 돈다.
- **WSL DNS 고장은 건드리지 않음.** 10.255.255.254 응답 없음, 1.1.1.1 정상. `.wslconfig`는 사용자 전역 설정이라 가이드에만 적고 wheel 오프라인 설치로 우회했다.
- **실행 차단.** 자동 권한 분류기가 외부 코드 실행을 막았다. 대상은 udp_protocol.so import와 공식 rby1-sim-isaac RBY1Task 실행이다. 우회하지 않고 사용자 승인을 받기로 했다. 모드 B는 미검증이다.
