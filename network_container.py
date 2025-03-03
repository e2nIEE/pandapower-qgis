import sys
from typing import Dict

if 'network_container' not in sys.modules:
    class NetworkContainer:
        _services = {}
        _initialized = False  # 초기화 상태를 추적

        @classmethod
        def register_network(cls, uri, network_data):
            """네트워크 데이터를 등록합니다"""
            if not cls._initialized:
                cls._initialized = True
            cls._services[uri] = dict(network_data)
            #cls._services[uri] = network_data
            print(f"\nRegistering network with uri: {uri}")
            print(f"Available uris: {list(cls._services.keys())}")
            print("initialized in registry? ", cls._initialized)
            print(f"Register: NetworkContainer at {id(cls)}\n")

        @classmethod
        def get_network(cls, uri):
            """등록된 네트워크 데이터를 가져옵니다"""
            print(f"\nGetting network with uri: {uri}")
            print(f"Available uris: {list(cls._services.keys())}")
            print("initialized in get method? ", cls._initialized)
            print(f"Get: NetworkContainer at {id(cls)}\n")
            if uri in cls._services:
                return cls._services[uri]
            return None
            #return cls._services.get(uri, None)

        @classmethod
        def clear(cls):
            """모든 네트워크 데이터를 제거합니다"""
            cls._services.clear()

        @classmethod
        def is_initialized(cls):
            """컨테이너가 초기화되었는지 확인"""
            return cls._initialized

    # 모듈 레지스트리에 등록
    sys.modules['network_container'] = NetworkContainer
else:
    # 이미 존재하는 클래스를 사용
    NetworkContainer = sys.modules['network_container']