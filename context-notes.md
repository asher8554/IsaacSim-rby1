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
- **실행 차단 → 승인 후 검증.** 자동 권한 분류기가 외부 코드 실행을 막았다. 대상은 udp_protocol.so import와 공식 rby1-sim-isaac RBY1Task 실행이다. 우회하지 않고 사용자 승인("승인, 검증 진행")을 받은 뒤 실행했다.
- **공식 config는 경로로 직접 로드.** Kit은 top-level `config`를 sys.path 순서와 무관하게 번들 cv2/config.py로 해석한다(`NameError: LOADER_DIR`). `importlib.util.spec_from_file_location`으로 공식 src/config.py를 `sys.modules["config"]`에 먼저 등록한다.
- **udp_protocol.so 확인 결과.** 상태 패킷은 공개 헤더 형식과 같다(N=24일 때 808 B). 명령 파서는 7-튜플을 돌려주고, gains가 없는 패킷이면 kp/kd가 `None`이다. 범용 코덱이 None을 그대로 전달한다.
- **모드 A 넘어짐 수정.** headless 검증은 팔 각도만 봤다(최대 2.84°). GUI 화면에서 로봇이 뒤로 누운 것을 발견했다. 공식 RBY1Task 설정을 그대로 적용했다. 자기충돌 OFF, 솔버 4/1, 물리 500 Hz, 기본 Grid 바닥이다. 적용 후 0.36°, 직립 1.000이다. verify에 베이스 직립 검사(up.z > 0.9)를 추가했다.
- **core는 자체 2 ms 클록으로 돈다.** 명령 흐름이 시작되기 전에는 Isaac이 자유 주행했다(headless rtf 1.5). 흐름이 시작되면 lockstep으로 rtf ≈ 1.0이 된다. GUI에서는 0.84~0.91이다.
- **app_main은 SIGINT 종료 시 segfault(139).** 공식 바이너리의 종료 단계 동작이다. 동작 중 영향은 없었다. 가이드에 명시했다.
- **GUI 확인 방법.** computer-use가 kit.exe를 앱으로 인식하지 못했다. 그래서 `isaac-sim.bat --exec`로 같은 앱을 띄웠다. 결과는 Kit 로그와 창 영역 캡처(PowerShell CopyFromScreen)로 확인했다. 메뉴·패널을 손으로 조작해 보지는 않았다.
- **Leader Arm 텔레옵은 공식 35번 예제를 import해 재사용.** 텔레옵 로직(손잡이 버튼 데드맨, 중력 보상, 관절 한계 클리핑, 0.02 m 충돌 차단, 안전 종료)을 새로 쓰지 않는다. 모듈 전역 `Gripper`와 `LeaderArm`을 바꾸고 `rby.create_robot`을 감싸는 방식이다. 공식 코드가 갱신돼도 그대로 따라간다.
- **시뮬레이션 core에는 `12v` 전원 장치와 툴 플랜지 전원이 없다.** 전원 장치는 `main` 하나이고 `set_tool_flange_output_voltage`는 False를 돌려준다. 실기에서 12V는 Leader Arm과 그리퍼 전원이므로 이 두 호출만 성공으로 응답한다. `12v`를 `main`에 연결하지 않은 이유가 있다. 종료 시 `power_off("12v")`가 시뮬레이션 로봇 전체 전원을 끄게 되기 때문이다.
- **모의 Leader Arm은 공식 LeaderArm 인터페이스를 덕 타이핑.** `DynamixelBus.ButtonState`는 읽기 전용이라 SimpleNamespace로 대신했다. 공식 안전 종료는 `ev.stop()`을 부른 뒤 스트림을 취소한다. 그래서 모의 루프도 `ev.stop()`에 맞춰 멈추게 했다(만료된 스트림 오류 수정).
- **실물 연결 경로는 usbipd → WSL `/dev/rby1_leader_arm` 심볼릭 링크.** 공식 코드가 이 경로를 기본으로 열기 때문에 코드 수정이 필요 없다. Windows COM 포트 직접 사용은 검증 수단이 없어 대안으로만 언급했다.
