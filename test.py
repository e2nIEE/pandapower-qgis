import pandapower as pp
import pandapower.networks as nw


net = nw.mv_oberrhein()

pp.runpp(net, algorithm='nr', v_debug=True)

kwargs = {
    'algorithm': 'nr',
    'max_iteration': 300,
    'v_debug': True
}

#pp.runpp(net, **kwargs)

pp.to_json(net, r"C:\Users\slee\Documents\pp_old\test_runpp.json")



def post_process_results(parent, uri, network_data, parameters):
    """
    계산 결과를 후처리합니다.
    이 함수는 "마무리 작업" 역할을 합니다:
    - 계산 결과를 네트워크 컨테이너에 업데이트
    - 필요시 레이어 색상 업데이트
    - 결과 표시 옵션 처리
    Args:
        parent: 부모 객체
        uri (str): 네트워크 URI
        network_data (dict): 네트워크 데이터
        parameters (dict): 사용자 설정 매개변수
    """
    # 디버깅 파일 설정
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    debug_file_path = f"C:\\Users\\slee\\Documents\\pp_old\\test\\detailed_post_process_{timestamp}.txt"

    try:
        os.makedirs(os.path.dirname(debug_file_path), exist_ok=True)
    except:
        pass

    def debug_print(message):
        """화면 출력 + 파일 저장"""
        print(message)
        try:
            with open(debug_file_path, 'a', encoding='utf-8') as f:
                f.write(message + '\n')
        except:
            print("디버깅 로그 파일 생성 실패")
            pass

    try:
        print("[DEBUG] post_process_results 0608 version")

        debug_print("🔬 [DETAIL-1] 세밀한 후처리 분석 시작...")
        # 🔬 단계 A: NetworkContainer.register_network 분석
        debug_print("🔬 [DETAIL-A] NetworkContainer.register_network 테스트...")
        debug_print(f"   - URI: {uri}")
        debug_print(f"   - network_data 키들: {list(network_data.keys())}")
        debug_print(f"   - 현재 NetworkContainer에 등록된 URI 개수: {len(NetworkContainer._networks)}")


        #🆕 URI Decoder를 사용해서 파일 경로 추출
        from qgis.core import QgsProviderRegistry

        print(f"🔍 URI 분석 중: {uri}")

        # 1단계: Provider 메타데이터 가져오기
        metadata_provider = QgsProviderRegistry.instance().providerMetadata("PandapowerProvider")

        # 2단계: URI를 딕셔너리로 분해하기
        uri_parts = metadata_provider.decodeUri(uri)
        print(f"🔍 URI 분해 결과: {uri_parts}")

        # 3단계: 파일 경로 추출
        file_path = uri_parts.get('path')
        if not file_path:
            print("❌ URI에서 파일 경로를 찾을 수 없습니다.")
            print(f"❌ URI 구성 요소: {uri_parts}")
            return

        print(f"✅ 파일 경로 추출 성공: {file_path}")
        print(f"📁 파일 경로: {file_path}")

        # 🔍 현재 NetworkContainer에 등록된 모든 URI 확인
        all_uris = list(NetworkContainer._networks.keys())
        related_uris = []

        for existing_uri in all_uris:
            # 같은 파일에서 온 URI인지 확인
            if f'path="{file_path}"' in existing_uri:
                related_uris.append(existing_uri)
                print(f"🎯 관련 URI 발견: {existing_uri}")
        if not related_uris:
            print("⚠️ 관련된 URI를 찾을 수 없습니다.")
            return

        # 🔄 같은 파일의 모든 URI를 업데이트
        print(f"📦 {len(related_uris)}개의 관련 URI 업데이트 시작...")

        for related_uri in related_uris:
            # 각 URI의 기존 데이터 가져오기
            existing_data = NetworkContainer.get_network(related_uri)
            if existing_data:
                # 네트워크 객체만 업데이트 (다른 정보는 그대로 유지)
                updated_data = existing_data.copy()
                updated_data['net'] = network_data['net']  # 계산 결과가 포함된 최신 네트워크

                # NetworkContainer에 업데이트 (알림 발송됨)
                NetworkContainer.register_network(related_uri, updated_data)
                print(f"✅ URI 업데이트 완료: {related_uri}")
            else:
                print(f"⚠️ 기존 데이터를 찾을 수 없음: {related_uri}")

        print("🎉 모든 관련 레이어 업데이트 완료!")

        # 2. 레이어 색상 업데이트 (사용자가 선택한 경우)
        if parameters.get('update_renderer', False):
            print("🎨 레이어 색상 업데이트 시작...")
            debug_print("🔬 [DETAIL-B] 렌더러 업데이트 테스트...")
            # 모든 관련 URI에 대해 색상 업데이트
            for related_uri in related_uris:
                debug_print(f"   🚨 {related_uri}에 대해 safe_renderer_update 호출 중...")
                update_layer_colors_for_uri(related_uri)    # v1+v2
                #safe_renderer_update_test(uri, debug_print)    # detailed_post_process_analysis method
                debug_print("   ✅ 렌더러 업데이트 테스트 성공!")
            print("✅ 전체 레이어 색상 업데이트 완료")

            # 3. 결과 표시 (필요시)
            if parameters.get('show_results', False):
                print("📊 상세 결과 표시...")
                # 이 부분은 추후 구현 가능
                pass

            print("🎉 결과 후처리 완료!")

        # 🔬 단계 C: 기타 후처리 작업들
        debug_print("🔬 [DETAIL-C] 기타 후처리 작업 테스트...")
        try:
            debug_print("   - 메모리 정리 테스트...")
            # 간단한 메모리 정리 작업
            import gc
            gc.collect()
            debug_print("   ✅ 메모리 정리 완료")

            debug_print("   - 상태 확인 테스트...")
            # NetworkContainer 상태 확인
            container_count = len(NetworkContainer._networks)
            debug_print(f"   ✅ NetworkContainer에 {container_count}개 URI 등록됨")

        except Exception as misc_error:
            debug_print(f"   ❌ 기타 후처리 실패: {str(misc_error)}")
            # 이것도 전체를 중단하지 않음

        debug_print("🎉 [DETAIL-완료] 세밀한 후처리 분석 완료!")
        debug_print(f"📁 세부 디버깅 파일 저장됨: {debug_file_path}")

    except Exception as e:
        debug_print(f"❌ [DETAIL-오류] 세밀한 후처리 분석 중 오류: {str(e)}")
        import traceback
        debug_print(f"상세 오류:\n{traceback.format_exc()}")
        debug_print(f"📁 오류 디버깅 파일 저장됨: {debug_file_path}")
        raise  # 오류를 상위로 전파

    # except Exception as e:
    #     print(f"⚠️ 결과 후처리 중 오류 발생: {str(e)}")
    #     import traceback
    #     traceback.print_exc()



