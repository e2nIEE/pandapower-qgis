import sys
from typing import Dict

if 'network_container' not in sys.modules:
    class NetworkContainer:
        _networks = {}  # network data
        _listeners = {}  # 👈 새로 추가: 알림 받을 사람들 목록
        _initialized = False  # 초기화 상태를 추적

        # @classmethod
        # def register_network(cls, uri, network_data):
        #     """네트워크 데이터를 등록합니다 + 자동 알림"""
        #
        #     print("=" * 50)
        #     print("network_container.py, register_network method")
        #     print(f"[DEBUG] Registering network with URI: {uri}")
        #     print(f"[DEBUG] Network data keys: {list(network_data.keys())}")
        #     print(f"[DEBUG] Network object type: {type(network_data.get('net', None))}")
        #
        #     # 초기화 플래그
        #     if not cls._initialized:
        #         cls._initialized = True
        #         print("🚀 NetworkContainer 첫 사용 - 초기화 완료!")
        #     # 데이터 저장
        #     cls._networks[uri] = dict(network_data)
        #     print(f"📦 NetworkContainer: {uri} 데이터 저장 완료")
        #
        #     # 3️⃣ 🌟 새로운 코드: 알림 기능 (추가!)
        #     cls._notify_all_listeners(uri, network_data)
        #
        #     #cls._networks[uri] = network_data
        #     print(f"\nRegistering network with uri: {uri}")
        #     print(f"Available uris: {list(cls._networks.keys())}")
        #     print("initialized in registry? ", cls._initialized)
        #     print(f"Register: NetworkContainer at {id(cls)}\n")

        @classmethod
        def register_network(cls, uri, network_data):
            """
            ✅ 최종 안정화된 버전 - 디버깅 코드 제거
            네트워크 데이터를 등록하고 리스너들에게 알림을 보냅니다
            """
            print("🚚🚚🚚🚚 NetworkContainer register_network 🚚🚚🚚🚚")
            print(f"🚚 NetworkContainer: {uri} 배달 시작!")  # ← 이거 추가

            # 초기화 플래그
            if not cls._initialized:
                cls._initialized = True
                print("🚀 NetworkContainer 초기화 완료")

            # 데이터 저장
            cls._networks[uri] = dict(network_data)
            print(f"📦 NetworkContainer: {uri} 저장 완료")

            # 리스너들에게 알림 발송
            cls._notify_all_listeners(uri, network_data)


        # @classmethod
        # def _notify_all_listeners(cls, uri, network_data):
        #     """
        #     ✅ 최종 안정화된 알림 시스템
        #     """
        #     if uri in cls._listeners:
        #         listeners_count = len(cls._listeners[uri])
        #         print(f"📢 {listeners_count}개 리스너에게 알림 발송")
        #
        #         # 안전한 리스너 목록 복사
        #         listeners_copy = cls._listeners[uri].copy()
        #
        #         success_count = 0
        #         for listener in listeners_copy:
        #             try:
        #                 # 리스너 유효성 확인
        #                 if hasattr(listener, 'isValid') and not listener.isValid():
        #                     continue
        #
        #                 # 실제 업데이트 호출
        #                 listener.on_update_changed_network(network_data)
        #                 success_count += 1
        #
        #             except Exception as e:
        #                 print(f"❌ 리스너 알림 실패: {e}")
        #                 continue
        #
        #         print(f"✅ 알림 완료: {success_count}/{listeners_count} 성공")


        @classmethod
        def get_network(cls, uri):
            """등록된 네트워크 데이터를 가져옵니다"""

            print("=" * 50)
            print("network_container.py, get_network method")
            print(f"[DEBUG] Attempting to get network with URI: {uri}")
            print(f"[DEBUG] Available URIs: {list(cls._networks.keys())}")
            print(f"[DEBUG] Container initialized: {cls._initialized}")

            print(f"\nGetting network with uri: {uri}")
            print(f"Available uris: {list(cls._networks.keys())}")
            print("initialized in get method? ", cls._initialized)
            print(f"Get: NetworkContainer at {id(cls)}\n")
            if uri in cls._networks:
                return cls._networks[uri]
            print(f"[DEBUG] Network data not found for URI: {uri}")
            return None
            #return cls._networks.get(uri, None)

        @classmethod
        def add_listener(cls, uri, listener):
            """새로운 메서드 - 알림 받을 사람 등록"""
            if uri not in cls._listeners:
                cls._listeners[uri] = []
            cls._listeners[uri].append(listener)
            print(f"📢 NetworkContainer: {uri}에 알림 받을 사람 추가됨")

        @classmethod
        def remove_listener(cls, uri, listener):
            """새로운 메서드 - 알림 받을 사람 제거"""
            if uri in cls._listeners:
                if listener in cls._listeners[uri]:
                    cls._listeners[uri].remove(listener)
                    print(f"📢 NetworkContainer: {uri}에서 알림 받을 사람 제거됨")

        # @classmethod
        # def _notify_all_listeners(cls, uri, network_data):
        #     """새로운 메서드 - 모든 알림 받을 사람들에게 전달"""
        #     if uri in cls._listeners:
        #         print(f"📢 NetworkContainer: {uri} 데이터 변경 알림 시작 ({len(cls._listeners[uri])}명)")
        #         for listener in cls._listeners[uri]:
        #             try:
        #                 listener.on_update_changed_network(network_data)
        #                 print(f"✅ {listener.__class__.__name__}에게 알림 전달 완료")
        #             except Exception as e:
        #                 print(f"❌ {listener.__class__.__name__}에게 알림 전달 실패: {str(e)}")
        #     else:
        #         print(f"📢 NetworkContainer: {uri}에 등록된 알림 받을 사람이 없음")

        # network_container.py의 _notify_all_listeners 메서드를 다음과 같이 수정

        @classmethod
        def _notify_all_listeners(cls, uri, network_data):
            """
            🔒 안전한 알림 시스템 - 동시성 문제 방지
            """
            if uri in cls._listeners:
                listeners_count = len(cls._listeners[uri])
                print(f"📢 NetworkContainer: {uri} 데이터 변경 알림 시작 ({listeners_count}명)")

                # 🚨 중요: 리스너 목록을 복사해서 반복 중 변경 방지
                listeners_copy = cls._listeners[uri].copy()

                success_count = 0
                for i, listener in enumerate(listeners_copy):
                    try:
                        print(f"📤 알림 전송 중 ({i + 1}/{listeners_count}): {listener.__class__.__name__}")

                        # 🔒 리스너가 아직 유효한지 확인
                        if hasattr(listener, 'isValid') and not listener.isValid():
                            print(f"⚠️ 유효하지 않은 리스너 건너뜀: {listener.__class__.__name__}")
                            continue

                        # 실제 업데이트 호출
                        listener.on_update_changed_network(network_data)
                        success_count += 1
                        print(f"✅ {listener.__class__.__name__}에게 알림 전달 완료")

                    except Exception as e:
                        print(f"❌ {listener.__class__.__name__}에게 알림 전달 실패: {str(e)}")
                        # 개별 리스너 실패는 전체를 중단시키지 않음
                        continue

                print(f"📢 알림 완료: {success_count}/{listeners_count} 성공")
            else:
                print(f"📢 NetworkContainer: {uri}에 등록된 알림 받을 사람이 없음")

        # 추가: 리스너 정리 메서드
        @classmethod
        def cleanup_invalid_listeners(cls):
            """
            유효하지 않은 리스너들을 정리합니다.
            """
            for uri in list(cls._listeners.keys()):
                if uri in cls._listeners:
                    valid_listeners = []
                    for listener in cls._listeners[uri]:
                        if hasattr(listener, 'isValid') and listener.isValid():
                            valid_listeners.append(listener)
                        else:
                            print(f"🗑️ 유효하지 않은 리스너 제거: {listener.__class__.__name__}")

                    cls._listeners[uri] = valid_listeners
                    if not valid_listeners:
                        print(f"🗑️ 빈 리스너 목록 제거: {uri}")
                        del cls._listeners[uri]


        @classmethod
        def clear(cls):
            """모든 네트워크 데이터를 제거합니다"""
            cls._networks.clear()

        @classmethod
        def is_initialized(cls):
            """컨테이너가 초기화되었는지 확인"""
            return cls._initialized

    # 모듈 레지스트리에 등록
    sys.modules['network_container'] = NetworkContainer
else:
    # 이미 존재하는 클래스를 사용
    NetworkContainer = sys.modules['network_container']