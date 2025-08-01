import ast
import sys
import traceback
from typing import Dict, Any

from qgis.core import QgsProject, QgsMessageLog, Qgis
from qgis.utils import iface
from qgis.PyQt.QtCore import QThread, pyqtSignal
from qgis.PyQt.QtWidgets import QMessageBox

from .network_container import NetworkContainer


# def run_network(parent, uri, parameters):
#     """
#     네트워크 계산을 실행하는 메인 함수입니다.
#
#     이 함수는 레스토랑의 "주방장" 같은 역할을 합니다:
#     - 고객(사용자)이 주문한 메뉴(parameters)를 받습니다
#     - 재료(network data)를 준비합니다
#     - 요리(계산)를 실행합니다
#     - 완성된 요리(결과)를 서빙합니다
#
#     Args:
#         parent: 부모 객체 (메시지 표시용)
#         uri (str): 네트워크를 식별하는 주소 (집주소 같은 개념)
#         parameters (dict): 사용자가 설정한 계산 옵션들
#     """
#     print("=" * 50)
#     print("🚀 RunPP 계산 시작!")
#     print(f"📍 네트워크 URI: {uri}")
#     print(f"⚙️  설정된 매개변수들: {parameters}")
#     print("=" * 50)
#
#     try:
#         # 1단계: 네트워크 데이터 가져오기
#         print("1️⃣ 네트워크 데이터 로딩 중...")
#         network_data = NetworkContainer.get_network(uri)
#
#         print("=" * 50)
#         print("[DEBUG] before res calculation ", network_data, "=" * 50)
#         net = network_data.get('net')
#         if hasattr(net, 'res_bus'):
#             print("✅ res_bus 발견!")
#             print(f"📊 버스 개수: {len(net.res_bus)}")
#             print("\n🔍 res_bus 내용 (처음 5개):")
#             print(net.res_bus.head())  # 처음 5줄만 출력
#         else:
#             print("❌ res_bus가 없어요! 계산이 안 된 것 같아요.")
#
#
#         if not network_data:
#             error_message = "네트워크 데이터를 찾을 수 없습니다. 먼저 네트워크를 가져와주세요!"
#             print(f"❌ {error_message}")
#             show_error_message(parent, error_message)
#             return False
#
#         # 2단계: 네트워크 객체 추출
#         net = network_data.get('net')
#         if not net:
#             error_message = "네트워크 객체가 유효하지 않습니다."
#             print(f"❌ {error_message}")
#             show_error_message(parent, error_message)
#             return False
#
#         print(f"✅ 네트워크 데이터 로딩 완료! (타입: {parameters.get('network_type', 'unknown')})")
#
#         # 3단계: 계산 실행
#         print("2️⃣ 계산 실행 중...")
#         success, result_message, updated_net = execute_calculation(net, parameters)
#
#         if success:
#             print(f"✅ 계산 완료! 결과: {result_message}")
#
#             # 4단계: 결과 처리 및 시각화
#             print("3️⃣ 결과 처리 중...")
#             # 원본 데이터를 업데이트된 결과로 교체!
#             network_data['net'] = updated_net
#             post_process_results(parent, uri, network_data, parameters)
#
#             # 성공 메시지 표시
#             show_success_message(parent, "계산이 성공적으로 완료되었습니다!", result_message)
#             print("="*50)
#             print("[DEBUG] after res calculation ", network_data, "="*50)
#
#         else:
#             print(f"❌ 계산 실패: {result_message}")
#             show_error_message(parent, f"계산 실패: {result_message}")
#             return False
#
#     except Exception as e:
#         error_message = f"예상치 못한 오류가 발생했습니다: {str(e)}"
#         print(f"❌ {error_message}")
#         print("상세 오류 정보:")
#         traceback.print_exc()
#         show_error_message(parent, error_message)
#         return False
#
#     print("🎉 RunPP 작업이 모두 완료되었습니다!")
#     return True


def execute_calculation(net, parameters):
    """
    실제 계산을 수행하는 함수입니다.

    이 함수는 "계산기" 역할을 합니다:
    - 사용자가 선택한 함수(run, runpp, runopp 등)를 실행
    - 사용자가 입력한 매개변수들을 적용
    - 계산 결과를 반환

    Args:
        net: pandapower 네트워크 객체
        parameters (dict): 계산 설정 매개변수들

    Returns:
        tuple: (성공여부, 결과메시지)
    """
    try:
        # 사용자가 선택한 실행 함수 가져오기
        run_function_name = parameters.get('run_function', 'run')
        print(f"📋 실행할 함수: {run_function_name}")

        # 사용자가 입력한 매개변수 문자열 처리
        kwargs_string = parameters.get('kwargs_string', '').strip()
        kwargs_dict = {}

        if kwargs_string:
            print(f"🔧 사용자 입력 매개변수: {kwargs_string}")
            kwargs_dict = parse_kwargs_string(kwargs_string)
            print(f"🔧 파싱된 매개변수: {kwargs_dict}")

        # 기본 매개변수 추가 (필요한 경우)
        if 'init' in parameters and parameters['init'] != 'auto':
            kwargs_dict['init'] = parameters['init']

        # 네트워크 타입에 따라 적절한 라이브러리 선택
        network_type = parameters.get('network_type', 'power')

        if network_type == 'power':
            # 전력 네트워크 계산
            print("⚡ 전력 네트워크 계산 실행")
            return execute_power_calculation(net, run_function_name, kwargs_dict)
        elif network_type == 'pipes':
            # 파이프 네트워크 계산
            print("🔧 파이프 네트워크 계산 실행")
            return execute_pipes_calculation(net, run_function_name, kwargs_dict)
        else:
            return False, f"지원하지 않는 네트워크 타입: {network_type}"

    except Exception as e:
        error_message = f"계산 실행 중 오류 발생: {str(e)}"
        print(f"❌ {error_message}")
        traceback.print_exc()
        return False, error_message


def parse_kwargs_string(kwargs_string):
    """
    사용자가 입력한 매개변수 문자열을 파싱합니다.

    예시: "algorithm='nr', max_iteration=10"
    -> {'algorithm': 'nr', 'max_iteration': 10}

    이 함수는 "번역기" 역할을 합니다:
    - 사용자가 입력한 텍스트를 파이썬이 이해할 수 있는 형태로 변환

    Args:
        kwargs_string (str): 사용자 입력 문자열

    Returns:
        dict: 파싱된 매개변수 딕셔너리
    """
    kwargs_dict = {}

    if not kwargs_string:
        return kwargs_dict

    try:
        # 방법 1: 간단한 파싱 (key=value 형태)
        if '=' in kwargs_string and not kwargs_string.startswith('{'):
            # "key1=value1, key2=value2" 형태의 문자열 처리
            pairs = kwargs_string.split(',')
            for pair in pairs:
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    key = key.strip()
                    value = value.strip()

                    # 값의 타입 자동 추정
                    try:
                        # 문자열 따옴표 제거
                        if (value.startswith('"') and value.endswith('"')) or \
                                (value.startswith("'") and value.endswith("'")):
                            kwargs_dict[key] = value[1:-1]
                        # 숫자 변환 시도
                        elif value.isdigit():
                            kwargs_dict[key] = int(value)
                        elif value.replace('.', '', 1).isdigit():
                            kwargs_dict[key] = float(value)
                        # 불린 값 처리
                        elif value.lower() in ['true', 'false']:
                            kwargs_dict[key] = value.lower() == 'true'
                        else:
                            kwargs_dict[key] = value
                    except:
                        kwargs_dict[key] = value

        # 방법 2: 딕셔너리 형태 파싱
        elif kwargs_string.startswith('{') and kwargs_string.endswith('}'):
            # "{'key1': 'value1', 'key2': value2}" 형태의 문자열 처리
            kwargs_dict = ast.literal_eval(kwargs_string)

        # 방법 3: 파이썬 표현식 파싱
        else:
            # "key1='value1', key2=value2" 형태를 딕셔너리로 변환
            exec_string = f"kwargs_dict = dict({kwargs_string})"
            exec(exec_string)

        print(f"✅ 매개변수 파싱 성공: {kwargs_dict}")
        return kwargs_dict

    except Exception as e:
        print(f"⚠️ 매개변수 파싱 실패: {str(e)}")
        print(f"⚠️ 원본 문자열: {kwargs_string}")
        # 파싱 실패 시 빈 딕셔너리 반환
        return {}


# def execute_power_calculation(net, function_name, kwargs_dict):
#     """
#     전력 네트워크 계산을 실행합니다.
#
#     Args:
#         net: pandapower 네트워크 객체
#         function_name (str): 실행할 함수명
#         kwargs_dict (dict): 매개변수 딕셔너리
#
#     Returns:
#         tuple: (성공여부, 결과메시지)
#     """
#     try:
#         import pandapower as pp
#
#         # 함수 매핑 테이블 (사용자 친화적 이름 -> 실제 함수)
#         function_map = {
#             'run': pp.runpp,          # 기본 조류 계산
#             'runpp': pp.runpp,        # 기본 조류 계산
#             'rundcpp': pp.rundcpp,    # DC 조류 계산
#             'runopp': pp.runopp,      # 최적 조류 계산
#             # 주석처리된 함수들: 현재는 사용하지 않음
#             # 'rundcopp': pp.rundcopp,
#             # 'runpm': pp.runpm,
#             # 기타 함수들은 필요시 추가 가능
#         }
#
#         # 선택된 함수 가져오기
#         if function_name not in function_map:
#             available_functions = list(function_map.keys())
#             return False, f"지원하지 않는 함수: {function_name}. 사용 가능한 함수: {available_functions}"
#
#         run_function = function_map[function_name]
#
#         print(f"⚡ 전력 네트워크 함수 실행: {function_name}")
#         print(f"⚡ 매개변수: {kwargs_dict}")
#
#         # 실제 계산 실행
#         result = run_function(net, **kwargs_dict)
#
#         # 결과 정보 생성
#         result_message = generate_power_result_message(net, function_name)
#         # return updated network
#         return True, result_message, net
#
#     except ImportError:
#         return False, "pandapower 라이브러리를 가져올 수 없습니다. 라이브러리가 설치되어 있는지 확인해주세요.", None
#     except Exception as e:
#         return False, f"전력 네트워크 계산 오류: {str(e)}", None



def post_process_results(parent, uri, network_data, parameters):
    """
    🕵️ 9단계: 후처리 과정도 단계별로 추적
    """

    # 디버깅 파일 설정
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    debug_file_path = f"C:\\Users\\slee\\Documents\\pp_old\\test\\post_process_results_{timestamp}.txt"

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
            pass

    try:
        debug_print("🔄 [POST-1] 결과 후처리 시작 (단순화된 방식)...")

        # 🎯 1단계: 네트워크 컨테이너 업데이트
        debug_print(f"📦 [POST-2] 네트워크 컨테이너 업데이트: {uri}")

        # 🚨 여기서 크래시가 발생할 수 있음!
        try:
            NetworkContainer.register_network(uri, network_data)
            debug_print("✅ [POST-2] 네트워크 컨테이너 업데이트 완료")
        except Exception as container_error:
            debug_print(f"❌ [POST-2] 컨테이너 업데이트 실패: {str(container_error)}")
            raise

        # 🎯 2단계: 렌더러 업데이트 (옵션)
        if parameters.get('update_renderer', False):
            debug_print("🎨 [POST-3] 렌더러 업데이트 요청됨...")

            # 🚨 렌더러 관련해서 크래시가 발생할 수 있음!
            try:
                debug_print("⚠️ [POST-3] 렌더러 업데이트는 일단 건너뜀 (안전 모드)")
                # 일단 렌더러 업데이트는 건너뛰고 테스트
                pass

            except Exception as renderer_error:
                debug_print(f"❌ [POST-3] 렌더러 업데이트 실패: {str(renderer_error)}")
                # 렌더러 실패는 전체를 중단하지 않음
                pass
        else:
            debug_print("ℹ️ [POST-3] 렌더러 업데이트 건너뜀 (사용자 설정)")

        debug_print("🎉 [POST-완료] 결과 후처리 완료!")
        debug_print(f"📁 디버깅 파일 저장됨: {debug_file_path}")

    except Exception as e:
        debug_print(f"⚠️ [POST-오류] 결과 후처리 중 오류 발생: {str(e)}")
        import traceback
        debug_print(f"상세 오류:\n{traceback.format_exc()}")
        debug_print(f"📁 디버깅 파일 저장됨: {debug_file_path}")
        raise  # 오류를 상위로 전파


def generate_power_result_message(net, function_name):
    """🕵️ 9단계: 결과 메시지 생성도 추적"""

    # 디버깅 파일 설정
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    debug_file_path = f"C:\\Users\\slee\\Documents\\pp_old\\test\\generate_power_result_message_{timestamp}.txt"

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
            pass

    try:
        debug_print("📝 [MSG-1] 결과 메시지 생성 시작...")

        message_parts = [
            f"⚡ 전력 네트워크 계산 완료 ({function_name})",
            f"📊 Bus 개수: {len(net.bus)}",
            f"📊 Line 개수: {len(net.line)}",
        ]
        debug_print("✅ [MSG-1] 기본 메시지 생성 완료")

        # 결과 데이터가 있는 경우에만 추가 정보 표시
        try:
            debug_print("📈 [MSG-2] 통계 정보 생성 중...")
            if hasattr(net, 'res_bus') and not net.res_bus.empty:
                # 안전하게 평균 계산
                if 'vm_pu' in net.res_bus.columns:
                    valid_voltage = net.res_bus['vm_pu'].dropna()
                    if len(valid_voltage) > 0:
                        avg_voltage = valid_voltage.mean()
                        message_parts.append(f"📈 평균 전압: {avg_voltage:.3f} p.u.")
                        debug_print(f"✅ [MSG-2] 평균 전압 계산 완료: {avg_voltage:.3f}")
            debug_print("✅ [MSG-2] 통계 정보 생성 완료")

        except Exception as stats_error:
            debug_print(f"⚠️ [MSG-2] 통계 계산 중 오류 (무시함): {stats_error}")

        result_message = "\n".join(message_parts)
        debug_print("✅ [MSG-완료] 결과 메시지 생성 완료")
        debug_print(f"📄 생성된 메시지:\n{result_message}")
        debug_print(f"📁 디버깅 파일 저장됨: {debug_file_path}")
        return result_message

    except Exception as e:
        debug_print(f"⚠️ [MSG-오류] 결과 메시지 생성 중 오류: {e}")
        debug_print(f"📁 디버깅 파일 저장됨: {debug_file_path}")
        return f"계산 완료 (메시지 생성 오류: {str(e)})"


def execute_power_calculation(net, function_name, kwargs_dict):
    """
    🚨 8단계: 매우 안전한 단계별 데이터 검증 + print 문구 파일 저장
    """

    # 디버깅용 파일 생성 (시간 스탬프 포함)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    debug_file_path = f"C:\\Users\\slee\\Documents\\pp_old\\test\\execute_power_calculation_{timestamp}.txt"

    # 폴더가 없으면 생성
    os.makedirs(os.path.dirname(debug_file_path), exist_ok=True)

    def debug_print(message):
        """화면에 출력하면서 동시에 파일에도 저장"""
        print(message)  # 기존처럼 화면에 출력
        try:
            with open(debug_file_path, 'a', encoding='utf-8') as f:
                f.write(message + '\n')
        except:
            pass  # 파일 저장 실패해도 프로그램은 계속 진행

    try:
        import pandapower as pp
        import numpy as np
        import pandas as pd

        # 함수 매핑 테이블
        function_map = {
            'run': pp.runpp,
            'runpp': pp.runpp,
            'rundcpp': pp.rundcpp,
            'runopp': pp.runopp,
        }

        if function_name not in function_map:
            available_functions = list(function_map.keys())
            debug_print(f"❌ 지원하지 않는 함수: {function_name}")
            return False, f"지원하지 않는 함수: {function_name}", None

        run_function = function_map[function_name]

        debug_print(f"⚡ 전력 네트워크 함수 실행: {function_name}")
        debug_print(f"⚡ 매개변수: {kwargs_dict}")

        # 🚨 Step 1: 계산 실행 전 간단한 확인
        debug_print("🔍 [Step 1] 계산 실행 전 기본 확인...")
        try:
            debug_print(f"   - Bus 개수: {len(net.bus)}")
            debug_print(f"   - Line 개수: {len(net.line)}")
            debug_print("✅ [Step 1] 완료")
        except Exception as e:
            debug_print(f"❌ [Step 1] 실패: {e}")
            return False, f"계산 전 확인 실패: {e}", None

        # 🚨 Step 2: 계산 실행
        debug_print("🔍 [Step 2] pandapower 계산 실행 중...")
        try:
            result = run_function(net, **kwargs_dict)
            debug_print("✅ [Step 2] pandapower 계산 완료")
        except Exception as e:
            debug_print(f"❌ [Step 2] pandapower 계산 실패: {e}")
            return False, f"pandapower 계산 오류: {e}", None

        # 🚨 Step 3: 계산 결과 존재 확인만
        debug_print("🔍 [Step 3] 계산 결과 기본 확인...")
        try:
            has_res_bus = hasattr(net, 'res_bus') and not net.res_bus.empty
            has_res_line = hasattr(net, 'res_line') and not net.res_line.empty

            debug_print(f"   - res_bus 있음: {has_res_bus}")
            if has_res_bus:
                debug_print(f"   - res_bus 크기: {net.res_bus.shape}")

            debug_print(f"   - res_line 있음: {has_res_line}")
            if has_res_line:
                debug_print(f"   - res_line 크기: {net.res_line.shape}")

            debug_print("✅ [Step 3] 계산 결과 기본 확인 완료")
        except Exception as e:
            debug_print(f"❌ [Step 3] 계산 결과 확인 실패: {e}")
            return False, f"계산 결과 확인 오류: {e}", None

        # 🚨 Step 4: 간단한 데이터 타입 확인만
        debug_print("🔍 [Step 4] 데이터 타입 간단 확인...")
        try:
            if hasattr(net, 'res_bus') and not net.res_bus.empty:
                debug_print("   - res_bus 컬럼들:")
                for col in net.res_bus.columns[:3]:  # 처음 3개만
                    dtype = net.res_bus[col].dtype
                    debug_print(f"     * {col}: {dtype}")

            debug_print("✅ [Step 4] 데이터 타입 확인 완료")
        except Exception as e:
            debug_print(f"❌ [Step 4] 데이터 타입 확인 실패: {e}")
            # 이 단계에서 실패해도 계속 진행
            debug_print("⚠️ 데이터 타입 확인은 실패했지만 계속 진행...")

        # 🚨 Step 5: 위험한 값들 확인 (매우 조심스럽게)
        debug_print("🔍 [Step 5] 위험한 값들 확인 시작...")
        dangerous_values_found = False

        try:
            if hasattr(net, 'res_bus') and not net.res_bus.empty:
                debug_print("   - res_bus NaN 확인 중...")

                # 한 컬럼씩 조심스럽게 확인
                for col in ['vm_pu']:  # 가장 중요한 컬럼만
                    if col in net.res_bus.columns:
                        try:
                            nan_count = net.res_bus[col].isnull().sum()
                            debug_print(f"     * {col}: {nan_count}개 NaN")

                            if nan_count > 0:
                                dangerous_values_found = True
                                debug_print(f"     ⚠️ {col}에 NaN 값 발견!")

                        except Exception as col_error:
                            debug_print(f"     ❌ {col} 확인 중 오류: {col_error}")
                            dangerous_values_found = True

            debug_print("✅ [Step 5] 위험한 값 확인 완료")

        except Exception as e:
            debug_print(f"❌ [Step 5] 위험한 값 확인 실패: {e}")
            dangerous_values_found = True

        # 🚨 Step 6: 위험한 값이 발견되면 안전 모드
        if dangerous_values_found:
            debug_print("⚠️ [Step 6] 위험한 값 발견 - 안전 모드 활성화")
            debug_print("⚠️ 렌더러 설정 없이 계산만 완료하고 종료합니다")

            # 간단한 결과 메시지만 생성
            result_message = f"⚡ 계산 완료 (안전 모드)\n📊 Bus: {len(net.bus)}개\n📊 Line: {len(net.line)}개"

            # ⚠️ 중요: 원본 네트워크를 수정하지 않고 그대로 반환
            debug_print("⚠️ 데이터에 문제가 있어서 원본 그대로 반환")
            debug_print(f"📁 디버깅 파일 저장됨: {debug_file_path}")
            return True, result_message, net

        else:
            debug_print("✅ [Step 6] 안전한 데이터 확인됨 - 정상 모드")
            result_message = generate_power_result_message(net, function_name)
            debug_print(f"📁 디버깅 파일 저장됨: {debug_file_path}")
            return True, result_message, net

    except Exception as e:
        debug_print(f"❌ execute_power_calculation 전체 오류: {str(e)}")
        import traceback
        traceback.print_exc()
        debug_print(f"📁 디버깅 파일 저장됨: {debug_file_path}")
        return False, f"전력 네트워크 계산 오류: {str(e)}", None


# 12단계: post_process_results 함수 정밀 분석
# ppqgis_runpp.py에 추가할 코드

import os
from datetime import datetime


def run_network(parent, uri, parameters):
    """
    🚨 12단계: post_process_results를 단계별로 세분화해서 정확한 크래시 지점 찾기
    """

    # 디버깅 파일 설정
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    debug_file_path = f"C:\\Users\\slee\\Documents\\pp_old\\test\\run_network_{timestamp}.txt"

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
            pass

    debug_print("=" * 50)
    debug_print("🚀 RunPP 계산 시작!")
    debug_print(f"📍 네트워크 URI: {uri}")
    debug_print(f"⚙️  설정된 매개변수들: {parameters}")
    debug_print("=" * 50)

    try:
        # 1단계: 네트워크 데이터 가져오기
        debug_print("1️⃣ [MAIN-1] 네트워크 데이터 로딩 중...")
        network_data = NetworkContainer.get_network(uri)

        if not network_data:
            error_message = "네트워크 데이터를 찾을 수 없습니다."
            debug_print(f"❌ [MAIN-1] {error_message}")
            show_error_message(parent, error_message)
            return False

        debug_print("✅ [MAIN-1] 네트워크 데이터 로딩 완료")

        # 2단계: 네트워크 객체 추출
        debug_print("2️⃣ [MAIN-2] 네트워크 객체 추출 중...")
        net = network_data.get('net')
        if not net:
            error_message = "네트워크 객체가 유효하지 않습니다."
            debug_print(f"❌ [MAIN-2] {error_message}")
            show_error_message(parent, error_message)
            return False

        debug_print(f"✅ [MAIN-2] 네트워크 객체 추출 완료 (타입: {parameters.get('network_type', 'unknown')})")

        # 3단계: 계산 실행
        debug_print("3️⃣ [MAIN-3] 계산 실행 시작...")
        success, result_message, updated_net = execute_calculation(net, parameters)

        if success:
            debug_print(f"✅ [MAIN-3] 계산 완료! 결과: {result_message}")

            # 🎯 4단계: 후처리를 세분화해서 정확한 문제 지점 찾기
            debug_print("4️⃣ [MAIN-4] 🔬 후처리 정밀 분석 시작 (12단계)")

            try:
                # 4-1. 네트워크 데이터 교체 (안전한 부분)
                debug_print("4️⃣-1 [MAIN-4] 네트워크 데이터 교체...")
                network_data['net'] = updated_net
                debug_print("✅ [MAIN-4-1] 네트워크 데이터 교체 완료")

                # 🔬 4-2. post_process_results를 세분화해서 실행
                debug_print("4️⃣-2 [MAIN-4] 후처리 세분화 분석 시작...")
                detailed_post_process_analysis(parent, uri, network_data, parameters)
                debug_print("✅ [MAIN-4-2] 후처리 세분화 분석 완료")

            except Exception as post_error:
                debug_print(f"❌ [MAIN-4] 후처리 중 오류: {str(post_error)}")
                import traceback
                debug_print(f"❌ [MAIN-4] 상세 오류:\n{traceback.format_exc()}")
                # 후처리 실패해도 계산은 성공으로 처리
                debug_print("⚠️ [MAIN-4] 후처리 실패했지만 계산은 성공으로 처리")

            # 5단계: 성공 메시지 표시
            debug_print("5️⃣ [MAIN-5] 성공 메시지 표시 중...")
            show_success_message(parent, "계산이 성공적으로 완료되었습니다!", result_message)
            debug_print("✅ [MAIN-5] 성공 메시지 표시 완료")

        else:
            debug_print(f"❌ [MAIN-3] 계산 실패: {result_message}")
            show_error_message(parent, f"계산 실패: {result_message}")
            return False

    except Exception as e:
        error_message = f"예상치 못한 오류가 발생했습니다: {str(e)}"
        debug_print(f"❌ [MAIN-전체] {error_message}")
        debug_print("상세 오류 정보:")
        import traceback
        debug_print(traceback.format_exc())
        show_error_message(parent, error_message)
        return False

    debug_print("🎉 [MAIN-완료] RunPP 작업이 모두 완료되었습니다!")
    debug_print(f"📁 디버깅 파일 저장됨: {debug_file_path}")
    return True


def detailed_post_process_analysis(parent, uri, network_data, parameters):
    """
    🔬 12단계: post_process_results를 아주 세밀하게 분석
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
            pass

    try:
        debug_print("🔬 [DETAIL-1] 세밀한 후처리 분석 시작...")

        # 🔬 단계 A: NetworkContainer.register_network 분석
        debug_print("🔬 [DETAIL-A] NetworkContainer.register_network 테스트...")
        try:
            debug_print(f"   - URI: {uri}")
            debug_print(f"   - network_data 키들: {list(network_data.keys())}")
            debug_print(f"   - 현재 NetworkContainer에 등록된 URI 개수: {len(NetworkContainer._networks)}")

            # 🚨 여기서 크래시가 발생할 수 있음!
            debug_print("   🚨 NetworkContainer.register_network 호출 직전...")
            NetworkContainer.register_network(uri, network_data)
            debug_print("   ✅ NetworkContainer.register_network 성공!")

        except Exception as container_error:
            debug_print(f"   ❌ NetworkContainer.register_network 실패: {str(container_error)}")
            debug_print("   📊 상세 오류:")
            import traceback
            debug_print(f"   {traceback.format_exc()}")
            raise  # 오류를 상위로 전파

        # 🔬 단계 B: 렌더러 업데이트 테스트 (parameters에 따라)
        if parameters.get('update_renderer', False):
            debug_print("🔬 [DETAIL-B] 렌더러 업데이트 테스트...")
            try:
                debug_print("   - 렌더러 업데이트 요청됨")

                # 🚨 여기서도 크래시가 발생할 수 있음!
                debug_print("   🚨 safe_renderer_update 호출 직전...")
                safe_renderer_update_test(uri, debug_print)
                debug_print("   ✅ 렌더러 업데이트 테스트 성공!")

            except Exception as renderer_error:
                debug_print(f"   ❌ 렌더러 업데이트 실패: {str(renderer_error)}")
                debug_print("   📊 상세 오류:")
                import traceback
                debug_print(f"   {traceback.format_exc()}")
                # 렌더러 실패는 전체를 중단하지 않음
                debug_print("   ⚠️ 렌더러 실패는 무시하고 계속 진행")
        else:
            debug_print("🔬 [DETAIL-B] 렌더러 업데이트 건너뜀 (사용자 설정)")

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


def safe_renderer_update_test(uri, debug_print):
    """
    🛡️ 안전한 렌더러 업데이트 테스트
    """
    try:
        debug_print("   🔍 레이어 검색 시작...")

        from qgis.core import QgsProject
        layers = QgsProject.instance().mapLayers()
        target_layers = []

        for layer_id, layer in layers.items():
            if (hasattr(layer, 'dataProvider') and
                    layer.dataProvider().name() == "PandapowerProvider" and
                    layer.source() == uri):
                target_layers.append(layer)
                debug_print(f"   ✅ 대상 레이어 발견: {layer.name()}")

        if not target_layers:
            debug_print("   ℹ️ 업데이트할 레이어가 없음")
            return

        debug_print(f"   🎨 {len(target_layers)}개 레이어 렌더러 테스트...")

        for i, layer in enumerate(target_layers):
            debug_print(f"   🎨-{i + 1} {layer.name()} 처리 중...")

            # 🚨 가장 위험한 부분!
            debug_print(f"   🚨 레이어 데이터 새로고침 직전...")
            layer.dataProvider().dataChanged.emit()
            debug_print(f"   ✅ 레이어 데이터 새로고침 성공")

            debug_print(f"   🚨 레이어 다시 그리기 직전...")
            layer.triggerRepaint()
            debug_print(f"   ✅ 레이어 다시 그리기 성공")

        debug_print("   🎉 모든 레이어 렌더러 테스트 완료!")

    except Exception as e:
        debug_print(f"   ❌ 렌더러 테스트 실패: {str(e)}")
        raise


def validate_network_before_calculation(net):
    """계산 실행 전 네트워크 상태 검증"""
    try:
        print(f"🔍 네트워크 기본 정보:")
        print(f"   - Bus 개수: {len(net.bus)}")
        print(f"   - Line 개수: {len(net.line)}")

        # 기본 데이터 타입 확인
        for table_name in ['bus', 'line', 'load', 'gen']:
            if hasattr(net, table_name):
                table = getattr(net, table_name)
                if not table.empty:
                    print(f"   - {table_name}: {len(table)}개 행, {len(table.columns)}개 컬럼")

                    # NaN 값 확인
                    nan_count = table.isnull().sum().sum()
                    if nan_count > 0:
                        print(f"     ⚠️ {table_name}에 {nan_count}개의 NaN 값 발견")

        print("✅ 계산 전 네트워크 상태 확인 완료")

    except Exception as e:
        print(f"⚠️ 네트워크 상태 확인 중 오류: {str(e)}")


def validate_calculation_results(net):
    """
    runpp 계산 결과를 검증하여 QGIS가 처리할 수 없는 값들을 찾습니다
    """
    issues = []

    try:
        import numpy as np
        import pandas as pd

        print("🔍 계산 결과 상세 검증 중...")

        # 검증할 결과 테이블들
        result_tables = []
        if hasattr(net, 'res_bus') and not net.res_bus.empty:
            result_tables.append(('res_bus', net.res_bus))
        if hasattr(net, 'res_line') and not net.res_line.empty:
            result_tables.append(('res_line', net.res_line))

        for table_name, table in result_tables:
            print(f"🔍 {table_name} 테이블 검증 중...")
            print(f"   - 크기: {table.shape}")
            print(f"   - 컬럼: {list(table.columns)}")

            # 1. NaN 값 검사
            nan_mask = table.isnull()
            nan_count = nan_mask.sum().sum()
            if nan_count > 0:
                issues.append(f"{table_name}에 {nan_count}개의 NaN 값 발견")
                nan_columns = nan_mask.sum()
                for col, count in nan_columns.items():
                    if count > 0:
                        print(f"     ⚠️ {col} 컬럼: {count}개 NaN")

            # 2. 무한대 값 검사
            numeric_columns = table.select_dtypes(include=[np.number]).columns
            for col in numeric_columns:
                inf_count = np.isinf(table[col]).sum()
                if inf_count > 0:
                    issues.append(f"{table_name}.{col}에 {inf_count}개의 무한대 값 발견")
                    print(f"     ⚠️ {col} 컬럼: {inf_count}개 무한대 값")

            # 3. 매우 큰 값 검사 (QGIS 렌더링 문제 가능성)
            for col in numeric_columns:
                max_val = table[col].max()
                min_val = table[col].min()
                if abs(max_val) > 1e10 or abs(min_val) > 1e10:
                    issues.append(f"{table_name}.{col}에 매우 큰 값 발견 (max:{max_val}, min:{min_val})")
                    print(f"     ⚠️ {col} 컬럼: 매우 큰 값 (max:{max_val}, min:{min_val})")

            # 4. 데이터 타입 확인
            for col in table.columns:
                dtype = table[col].dtype
                if dtype == 'object':
                    print(f"     ℹ️ {col} 컬럼: object 타입 (QGIS 호환성 주의)")
                    # object 타입 컬럼의 실제 값들 확인
                    unique_types = set(type(x).__name__ for x in table[col].dropna().values[:5])
                    print(f"        실제 값 타입들: {unique_types}")

            # 5. 간단한 통계 정보 출력
            print(f"   📊 {table_name} 간단 통계:")
            for col in numeric_columns[:3]:  # 처음 3개 숫자 컬럼만
                try:
                    mean_val = table[col].mean()
                    std_val = table[col].std()
                    print(f"     - {col}: 평균={mean_val:.3f}, 표준편차={std_val:.3f}")
                except:
                    print(f"     - {col}: 통계 계산 실패")

        # 검증 결과 요약
        if issues:
            print(f"❌ 총 {len(issues)}개의 데이터 문제 발견:")
            for i, issue in enumerate(issues, 1):
                print(f"   {i}. {issue}")
        else:
            print("✅ 계산 결과 데이터 검증 통과!")

        return {
            'is_valid': len(issues) == 0,
            'issues': issues
        }

    except Exception as e:
        print(f"❌ 데이터 검증 중 오류: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'is_valid': False,
            'issues': [f"데이터 검증 중 오류 발생: {str(e)}"]
        }


def fix_problematic_data(net):
    """
    문제가 있는 데이터를 수정합니다
    """
    try:
        import numpy as np

        print("🔧 데이터 수정 시작...")

        # 결과 테이블들 수정
        result_tables = []
        if hasattr(net, 'res_bus'):
            result_tables.append(('res_bus', net.res_bus))
        if hasattr(net, 'res_line'):
            result_tables.append(('res_line', net.res_line))

        for table_name, table in result_tables:
            print(f"🔧 {table_name} 수정 중...")

            numeric_columns = table.select_dtypes(include=[np.number]).columns

            for col in numeric_columns:
                original_count = len(table)

                # NaN 값을 0 또는 적절한 기본값으로 교체
                nan_count = table[col].isnull().sum()
                if nan_count > 0:
                    # 컬럼별 적절한 기본값 설정
                    if 'vm_pu' in col:  # 전압은 1.0으로
                        table[col].fillna(1.0, inplace=True)
                    elif 'loading_percent' in col:  # 부하율은 0으로
                        table[col].fillna(0.0, inplace=True)
                    else:  # 기타는 0으로
                        table[col].fillna(0.0, inplace=True)
                    print(f"   ✅ {col}: {nan_count}개 NaN 값을 기본값으로 교체")

                # 무한대 값을 매우 큰 값으로 교체
                inf_mask = np.isinf(table[col])
                inf_count = inf_mask.sum()
                if inf_count > 0:
                    # 양의 무한대는 큰 양수로, 음의 무한대는 큰 음수로
                    table.loc[table[col] == np.inf, col] = 1e6
                    table.loc[table[col] == -np.inf, col] = -1e6
                    print(f"   ✅ {col}: {inf_count}개 무한대 값을 유한값으로 교체")

                # 매우 큰 값들을 적절한 범위로 제한
                max_val = table[col].max()
                min_val = table[col].min()
                if abs(max_val) > 1e6 or abs(min_val) > 1e6:
                    table[col] = np.clip(table[col], -1e6, 1e6)
                    print(f"   ✅ {col}: 매우 큰 값들을 [-1e6, 1e6] 범위로 제한")

        print("✅ 데이터 수정 완료!")

    except Exception as e:
        print(f"❌ 데이터 수정 중 오류: {str(e)}")
        import traceback
        traceback.print_exc()






def execute_pipes_calculation(net, function_name, kwargs_dict):
    """
    파이프 네트워크 계산을 실행합니다.

    Args:
        net: pandapipes 네트워크 객체
        function_name (str): 실행할 함수명
        kwargs_dict (dict): 매개변수 딕셔너리

    Returns:
        tuple: (성공여부, 결과메시지)
    """
    try:
        import pandapipes as pp

        # 파이프 네트워크 함수 매핑
        function_map = {
            'run': pp.runpp,          # 기본 유체 계산
            'runpp': pp.runpp,        # 기본 유체 계산
            # 다른 파이프 함수들은 필요시 추가
        }

        # 선택된 함수 가져오기
        if function_name not in function_map:
            available_functions = list(function_map.keys())
            return False, f"지원하지 않는 파이프 함수: {function_name}. 사용 가능한 함수: {available_functions}"

        run_function = function_map[function_name]

        print(f"🔧 파이프 네트워크 함수 실행: {function_name}")
        print(f"🔧 매개변수: {kwargs_dict}")

        # 실제 계산 실행
        result = run_function(net, **kwargs_dict)

        # 결과 정보 생성
        result_message = generate_pipes_result_message(net, function_name)

        return True, result_message, result

    except ImportError:
        return False, "pandapipes 라이브러리를 가져올 수 없습니다. 라이브러리가 설치되어 있는지 확인해주세요."
    except Exception as e:
        return False, f"파이프 네트워크 계산 오류: {str(e)}"


# def generate_power_result_message(net, function_name):
#     """전력 네트워크 계산 결과 메시지를 생성합니다."""
#     try:
#         message_parts = [
#             f"⚡ 전력 네트워크 계산 완료 ({function_name})",
#             f"📊 Bus 개수: {len(net.bus)}",
#             f"📊 Line 개수: {len(net.line)}",
#         ]
#
#         # 결과 데이터가 있는 경우 추가 정보 표시
#         if hasattr(net, 'res_bus') and not net.res_bus.empty:
#             avg_voltage = net.res_bus['vm_pu'].mean()
#             message_parts.append(f"📈 평균 전압: {avg_voltage:.3f} p.u.")
#
#         if hasattr(net, 'res_line') and not net.res_line.empty:
#             max_loading = net.res_line['loading_percent'].max()
#             message_parts.append(f"📈 최대 부하율: {max_loading:.1f}%")
#
#         return "\n".join(message_parts)
#
#     except Exception as e:
#         return f"계산 완료 (결과 정보 생성 중 오류: {str(e)})"


def generate_pipes_result_message(net, function_name):
    """파이프 네트워크 계산 결과 메시지를 생성합니다."""
    try:
        message_parts = [
            f"🔧 파이프 네트워크 계산 완료 ({function_name})",
            f"📊 Junction 개수: {len(net.junction)}",
            f"📊 Pipe 개수: {len(net.pipe)}",
        ]

        # 결과 데이터가 있는 경우 추가 정보 표시
        if hasattr(net, 'res_junction') and not net.res_junction.empty:
            avg_pressure = net.res_junction['p_bar'].mean()
            message_parts.append(f"📈 평균 압력: {avg_pressure:.3f} bar")

        if hasattr(net, 'res_pipe') and not net.res_pipe.empty:
            max_velocity = net.res_pipe['v_mean_m_per_s'].max()
            message_parts.append(f"📈 최대 유속: {max_velocity:.2f} m/s")

        return "\n".join(message_parts)

    except Exception as e:
        return f"계산 완료 (결과 정보 생성 중 오류: {str(e)})"


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
    # try:
    #     print("🔄 결과 후처리 시작...")
    #
    #     # 1. 네트워크 컨테이너에 업데이트된 결과 저장
    #     # 이때 자동으로 모든 Provider들이 알림을 받아서 업데이트됨
    #     NetworkContainer.register_network(uri, network_data)
    #     print("✅ 네트워크 컨테이너 업데이트 완료 (자동 알림 발송됨)")
    #
    #     # 2. 레이어 색상 업데이트 (사용자가 선택한 경우)
    #     if parameters.get('update_renderer', False):
    #         print("🎨 레이어 색상 업데이트 시작...")
    #         update_layer_colors(uri, network_data)
    #         print("✅ 레이어 색상 업데이트 완료")
    #
    #     # 3. 결과 표시 (필요시)
    #     if parameters.get('show_results', False):
    #         print("📊 상세 결과 표시...")
    #         # 이 부분은 추후 구현 가능
    #         pass
    #
    #     print("🎉 결과 후처리 완료!")
    #
    # except Exception as e:
    #     print(f"⚠️ 결과 후처리 중 오류 발생: {str(e)}")
    #     # 후처리 실패해도 메인 계산은 성공으로 간주

    # version 2
    # try:
    #     print("🔄 결과 후처리 시작...")
    #
    #     # 🆕 URI Decoder를 사용해서 파일 경로 추출
    #     from qgis.core import QgsProviderRegistry
    #
    #     print(f"🔍 URI 분석 중: {uri}")
    #
    #     # 1단계: Provider 메타데이터 가져오기
    #     metadata_provider = QgsProviderRegistry.instance().providerMetadata("PandapowerProvider")
    #
    #     # 2단계: URI를 딕셔너리로 분해하기
    #     uri_parts = metadata_provider.decodeUri(uri)
    #     print(f"🔍 URI 분해 결과: {uri_parts}")
    #
    #     # 3단계: 파일 경로 추출
    #     file_path = uri_parts.get('path')
    #     if not file_path:
    #         print("❌ URI에서 파일 경로를 찾을 수 없습니다.")
    #         print(f"❌ URI 구성 요소: {uri_parts}")
    #         return
    #
    #     print(f"✅ 파일 경로 추출 성공: {file_path}")
    #
    #     print(f"📁 파일 경로: {file_path}")
    #
    #     # 🔍 현재 NetworkContainer에 등록된 모든 URI 확인
    #     all_uris = list(NetworkContainer._networks.keys())
    #     related_uris = []
    #
    #     for existing_uri in all_uris:
    #         # 같은 파일에서 온 URI인지 확인
    #         if f'path="{file_path}"' in existing_uri:
    #             related_uris.append(existing_uri)
    #             print(f"🎯 관련 URI 발견: {existing_uri}")
    #
    #     if not related_uris:
    #         print("⚠️ 관련된 URI를 찾을 수 없습니다.")
    #         return
    #
    #     # 🔄 같은 파일의 모든 URI를 업데이트
    #     print(f"📦 {len(related_uris)}개의 관련 URI 업데이트 시작...")
    #
    #     for related_uri in related_uris:
    #         # 각 URI의 기존 데이터 가져오기
    #         existing_data = NetworkContainer.get_network(related_uri)
    #         if existing_data:
    #             # 네트워크 객체만 업데이트 (다른 정보는 그대로 유지)
    #             updated_data = existing_data.copy()
    #             updated_data['net'] = network_data['net']  # 계산 결과가 포함된 최신 네트워크
    #
    #             # NetworkContainer에 업데이트 (알림 발송됨)
    #             NetworkContainer.register_network(related_uri, updated_data)
    #             print(f"✅ URI 업데이트 완료: {related_uri}")
    #         else:
    #             print(f"⚠️ 기존 데이터를 찾을 수 없음: {related_uri}")
    #
    #     print("🎉 모든 관련 레이어 업데이트 완료!")
    #
    #     # 2. 레이어 색상 업데이트 (사용자가 선택한 경우)
    #     if parameters.get('update_renderer', False):
    #         print("🎨 레이어 색상 업데이트 시작...")
    #         # 모든 관련 URI에 대해 색상 업데이트
    #         for related_uri in related_uris:
    #             update_layer_colors_for_uri(related_uri)
    #         print("✅ 레이어 색상 업데이트 완료")
    #
    #     # 3. 결과 표시 (필요시)
    #     if parameters.get('show_results', False):
    #         print("📊 상세 결과 표시...")
    #         # 이 부분은 추후 구현 가능
    #         pass
    #
    #     print("🎉 결과 후처리 완료!")
    #
    # except Exception as e:
    #     print(f"⚠️ 결과 후처리 중 오류 발생: {str(e)}")
    #     import traceback
    #     traceback.print_exc()

    # version 3
    # ppqgis_runpp.py의 post_process_results 함수를 다음과 같이 단순화

    """
    🔧 단순화된 결과 후처리 - 안전성 우선
    """
    try:
        print("🔄 결과 후처리 시작 (단순화된 방식)...")

        # 🎯 1단계: 단순하게 현재 URI만 업데이트
        print(f"📦 네트워크 컨테이너 업데이트: {uri}")
        NetworkContainer.register_network(uri, network_data)
        print("✅ 네트워크 컨테이너 업데이트 완료 (자동 알림 발송됨)")

        # 🎯 2단계: 렌더러 업데이트는 별도로 안전하게 실행
        if parameters.get('update_renderer', False):
            print("🎨 렌더러 업데이트 요청됨 - 안전 모드로 실행...")
            # 약간의 지연을 두어 데이터 업데이트가 완료되도록 함
            from PyQt5.QtCore import QTimer

            def delayed_renderer_update():
                try:
                    safe_update_renderer(uri)
                except Exception as e:
                    print(f"⚠️ 지연된 렌더러 업데이트 실패: {str(e)}")

            # 100ms 후에 렌더러 업데이트 실행
            QTimer.singleShot(100, delayed_renderer_update)
            print("✅ 렌더러 업데이트가 예약되었습니다 (100ms 후 실행)")
        else:
            print("ℹ️ 렌더러 업데이트 건너뜀 (사용자 설정)")

        print("🎉 결과 후처리 완료!")

    except Exception as e:
        print(f"⚠️ 결과 후처리 중 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()


def safe_update_renderer(uri):
    """
    🛡️ 안전한 렌더러 업데이트 - 오류 발생 시에도 계속 진행
    """
    try:
        print(f"🎨 안전한 렌더러 업데이트 시작: {uri}")

        layers = QgsProject.instance().mapLayers()
        updated_count = 0

        for layer_id, layer in layers.items():
            if (hasattr(layer, 'dataProvider') and
                    layer.dataProvider().name() == "PandapowerProvider" and
                    layer.source() == uri):

                try:
                    # 레이어별로 개별 try-catch
                    update_single_layer_renderer(layer)
                    updated_count += 1
                    print(f"✅ 레이어 렌더러 업데이트 성공: {layer.name()}")

                except Exception as layer_error:
                    print(f"⚠️ 레이어 렌더러 업데이트 실패: {layer.name()}")
                    print(f"   오류: {str(layer_error)}")
                    # 개별 레이어 실패는 전체를 중단하지 않음
                    continue

        print(f"🎨 렌더러 업데이트 완료: {updated_count}개 레이어 성공")

    except Exception as e:
        print(f"❌ 전체 렌더러 업데이트 실패: {str(e)}")


def update_single_layer_renderer(layer):
    """
    🎯 단일 레이어의 렌더러만 안전하게 업데이트
    """
    if not layer or not layer.isValid():
        raise Exception("레이어가 유효하지 않음")

    provider = layer.dataProvider()
    if not provider or not provider.isValid():
        raise Exception("프로바이더가 유효하지 않음")

    # 필드가 준비될 때까지 잠시 대기
    fields = layer.fields()
    if not fields or len(fields) == 0:
        raise Exception("레이어 필드가 준비되지 않음")

    layer_name_lower = layer.name().lower()

    # 렌더러 생성
    from .renderer_utils import create_bus_renderer, create_line_renderer

    if 'bus' in layer_name_lower or 'junction' in layer_name_lower:
        # 버스/정션 레이어
        renderer = create_bus_renderer(render=True)

        # vm_pu 필드가 있는지 확인
        field_names = [field.name() for field in fields]
        if 'vm_pu' not in field_names:
            print(f"⚠️ vm_pu 필드가 없어서 단순 렌더러 사용: {layer.name()}")
            renderer, _ = create_bus_renderer(render=False)

    elif 'line' in layer_name_lower or 'pipe' in layer_name_lower:
        # 라인/파이프 레이어
        renderer = create_line_renderer(render=True)

        # loading_percent 필드가 있는지 확인
        field_names = [field.name() for field in fields]
        if 'loading_percent' not in field_names:
            print(f"⚠️ loading_percent 필드가 없어서 단순 렌더러 사용: {layer.name()}")
            renderer, _ = create_line_renderer(render=False)
    else:
        raise Exception(f"알 수 없는 레이어 타입: {layer.name()}")

    if not renderer:
        raise Exception("렌더러 생성 실패")

    # 🚨 여기가 크래시 발생 지점!
    print(f"🚨 setRenderer 호출 직전: {layer.name()}")
    layer.setRenderer(renderer)
    print(f"✅ setRenderer 성공: {layer.name()}")

    # 레이어 새로고침
    layer.triggerRepaint()

# ppqgis_runpp.py에서 update_layer_colors_for_uri 함수를 다음과 같이 수정해보세요

def update_layer_colors_for_uri(uri):
    """
    안전한 렌더러 설정 - 단계별 검증으로 문제점 찾기
    """
    try:
        print("🔍 1단계: 렌더러 import 시작...")
        from .renderer_utils import create_bus_renderer, create_line_renderer
        print("✅ 1단계 완료: import 성공")

        print("🔍 2단계: 레이어 찾기 시작...")
        layers = QgsProject.instance().mapLayers()
        target_layers = []

        for layer_id, layer in layers.items():
            if (hasattr(layer, 'dataProvider') and
                    layer.dataProvider().name() == "PandapowerProvider" and
                    layer.source() == uri):
                target_layers.append(layer)
                print(f"✅ 타겟 레이어 발견: {layer.name()}")

        if not target_layers:
            print("⚠️ 업데이트할 레이어를 찾을 수 없습니다.")
            return True  # 오류가 아니므로 True 반환

        print(f"🔍 3단계: {len(target_layers)}개 레이어 처리 시작...")

        for i, layer in enumerate(target_layers):
            print(f"🔍 3-{i + 1}단계: {layer.name()} 처리 중...")

            # 3-1. 레이어 유효성 검사
            if not layer.isValid():
                print(f"❌ 레이어가 유효하지 않음: {layer.name()}")
                continue

            # 3-2. 데이터 프로바이더 검사
            provider = layer.dataProvider()
            if not provider or not provider.isValid():
                print(f"❌ 프로바이더가 유효하지 않음: {layer.name()}")
                continue

            # 3-3. 레이어 타입 확인
            layer_name_lower = layer.name().lower()
            renderer = None

            print(f"🔍 3-{i + 1}-1: 렌더러 생성 중...")
            if 'bus' in layer_name_lower or 'junction' in layer_name_lower:
                renderer = create_bus_renderer(render=True)
                print(f"✅ 버스 렌더러 생성: {type(renderer)}")
            elif 'line' in layer_name_lower or 'pipe' in layer_name_lower:
                renderer = create_line_renderer(render=True)
                print(f"✅ 라인 렌더러 생성: {type(renderer)}")
            else:
                print(f"⚠️ 알 수 없는 레이어 타입: {layer.name()}")
                continue

            # 3-4. 렌더러 유효성 검사
            if not renderer:
                print(f"❌ 렌더러 생성 실패: {layer.name()}")
                continue

            print(f"🔍 3-{i + 1}-2: 렌더러 설정 시도 중...")

            # 🚨 핵심: 안전한 렌더러 설정
            try:
                # 렌더러 설정 전 추가 검사
                if hasattr(renderer, 'classAttribute') and hasattr(layer, 'fields'):
                    attr_name = renderer.classAttribute()
                    if attr_name:  # 속성 기반 렌더러인 경우
                        field_names = [field.name() for field in layer.fields()]
                        if attr_name not in field_names:
                            print(f"⚠️ 필드 {attr_name}이 레이어에 없음. 단순 렌더러로 변경")
                            # 단순 렌더러로 대체
                            if 'bus' in layer_name_lower or 'junction' in layer_name_lower:
                                renderer = create_bus_renderer(render=False)[0]
                            else:
                                renderer = create_line_renderer(render=False)[0]

                # 📍 여기가 문제가 되는 부분입니다!
                print(f"🚨 CRITICAL: setRenderer 호출 직전 - {layer.name()}")
                layer.setRenderer(renderer)
                print(f"✅ setRenderer 성공 - {layer.name()}")

                # 레이어 새로고침
                layer.triggerRepaint()
                print(f"✅ 3-{i + 1} 완료: {layer.name()} 업데이트 성공")

            except Exception as renderer_error:
                print(f"❌ 렌더러 설정 실패: {layer.name()}")
                print(f"❌ 오류 내용: {str(renderer_error)}")
                import traceback
                traceback.print_exc()
                continue

        print("✅ 모든 레이어 처리 완료")
        return True

    except Exception as e:
        print(f"❌ update_layer_colors_for_uri 전체 오류: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


# # ppqgis_runpp.py에서 이 코드로 테스트해보세요
# def update_layer_colors_for_uri(uri):
#     try:
#         print("🧪 renderer_utils import 테스트...")
#         from .renderer_utils import create_bus_renderer, create_line_renderer
#         print("✅ import 성공")
#
#         # 렌더러 생성 테스트
#         print("🧪 렌더러 생성 테스트...")
#         bus_renderer = create_bus_renderer(render=True)
#         print(f"✅ 버스 렌더러 생성 성공: {type(bus_renderer)}")
#
#         line_renderer = create_line_renderer(render=True)
#         print(f"✅ 라인 렌더러 생성 성공: {type(line_renderer)}")
#
#     except Exception as e:
#         print(f"❌ 렌더러 생성 오류: {str(e)}")
#         import traceback
#         traceback.print_exc()


# def update_layer_colors_for_uri(uri):
#     """
#     임시 방법: 렌더러 설정을 건너뛰고 데이터만 업데이트
#     """
#     try:
#         print(f"🔄 레이어 데이터 업데이트만 실행 (색상 업데이트 건너뛰기): {uri}")
#
#         layers = QgsProject.instance().mapLayers()
#         updated_count = 0
#
#         for layer_id, layer in layers.items():
#             if (hasattr(layer, 'dataProvider') and
#                     layer.dataProvider().name() == "PandapowerProvider" and
#                     layer.source() == uri):
#                 # 🎯 핵심: 렌더러 설정 없이 데이터만 새로고침
#                 print(f"📊 데이터 새로고침: {layer.name()}")
#
#                 # 레이어에게 "데이터가 바뀌었으니 다시 그려!" 명령하기
#                 layer.dataProvider().dataChanged.emit()
#                 layer.triggerRepaint()
#                 updated_count += 1
#
#         print(f"✅ {updated_count}개 레이어 데이터 업데이트 완료 (렌더러 설정 없음)")
#         return True
#
#     except Exception as e:
#         print(f"❌ 데이터 업데이트 오류 (URI: {uri}): {str(e)}")
#         return False


# def update_layer_colors_for_uri(uri):
#     """
#     특정 URI의 레이어 색상만 업데이트
#     """
#     try:
#         from .renderer_utils import create_bus_renderer, create_line_renderer
#
#         layers = QgsProject.instance().mapLayers()
#
#         for layer_id, layer in layers.items():
#             if (hasattr(layer, 'dataProvider') and
#                     layer.dataProvider().name() == "PandapowerProvider" and
#                     layer.source() == uri):
#
#                 # 레이어 타입에 따라 색상 적용
#                 layer_name_lower = layer.name().lower()
#
#                 if 'bus' in layer_name_lower or 'junction' in layer_name_lower:
#                     renderer = create_bus_renderer(render=True)
#                     layer.setRenderer(renderer)
#                 elif 'line' in layer_name_lower or 'pipe' in layer_name_lower:
#                     renderer = create_line_renderer(render=True)
#                     layer.setRenderer(renderer)
#
#                 layer.triggerRepaint()
#                 print(f"🎨 레이어 색상 업데이트: {layer.name()}")
#
#     except Exception as e:
#         print(f"❌ 색상 업데이트 오류 (URI: {uri}): {str(e)}")


# def update_layer_colors(uri):
#     """
#     순수하게 색상만 담당하는 함수
#     데이터 업데이트는 이미 자동으로 완료된 상태!
#     """
#     try:
#         from .renderer_utils import create_bus_renderer, create_line_renderer
#
#         # 🎯 이제 데이터 업데이트 코드가 필요 없음!
#         # Provider들이 이미 알림을 받아서 스스로 업데이트했음
#
#         layers = QgsProject.instance().mapLayers()
#
#         for layer_id, layer in layers.items():
#             if (hasattr(layer, 'dataProvider') and
#                     layer.dataProvider().name() == "PandapowerProvider" and
#                     layer.source() == uri):
#
#                 # 바로 색상 적용!
#                 layer_name_lower = layer.name().lower()
#
#                 if 'bus' in layer_name_lower:
#                     renderer = create_bus_renderer(render=True)
#                     layer.setRenderer(renderer)
#                 elif 'line' in layer_name_lower:
#                     renderer = create_line_renderer(render=True)
#                     layer.setRenderer(renderer)
#
#                 layer.triggerRepaint()
#
#         print("🎨 모든 레이어 색상 업데이트 완료")
#
#     except Exception as e:
#         print(f"❌ 색상 업데이트 오류: {str(e)}")


# def update_layer_colors(uri, network_data):
#     """
#     계산 결과에 따라 레이어 색상을 업데이트합니다.
#     기존 ppqgis_import.py 방식을 사용합니다.
#     """
#     try:
#         from .renderer_utils import create_bus_renderer, create_line_renderer
#         #from qgis.utils import iface
#
#         #print("🎨 레이어 색상 업데이트 시작 (기존 import 방식 사용)...")
#
#         # 현재 프로젝트의 모든 레이어 찾기
#         layers = QgsProject.instance().mapLayers()
#         related_layers = []
#
#         for layer_id, layer in layers.items():
#             if (hasattr(layer, 'dataProvider') and
#                     layer.dataProvider().name() == "PandapowerProvider" and
#                     layer.source() == uri):
#                 provider = layer.dataProvider()
#
#                 # 🎯 핵심: Provider 강제 초기화
#                 provider.net = network_data['net']
#                 provider.fields_list = None
#                 provider.df = None
#                 provider.fields()  # merge_df() 다시 실행
#
#                 related_layers.append(layer)
#
#         if not related_layers:
#             print("⚠️ 업데이트할 레이어를 찾을 수 없습니다.")
#             return
#
#         # 각 레이어에 기존 import 방식의 렌더러 적용
#         for layer in related_layers:
#             print(f"🎨 레이어 업데이트: {layer.name()}")
#
#             # 기존 ppqgis_import 방식 사용!
#             if 'bus' in layer.name().lower():
#                 renderer = create_bus_renderer(render=True)  # 그라데이션 방식
#                 layer.setRenderer(renderer)
#             elif 'line' in layer.name().lower():
#                 renderer = create_line_renderer(render=True)  # 그라데이션 방식
#                 layer.setRenderer(renderer)
#
#             # 레이어 새로고침
#             layer.dataProvider().dataChanged.emit()
#             layer.triggerRepaint()
#
#         # 전체 캔버스 새로고침
#         if iface:
#             iface.mapCanvas().refreshAllLayers()
#
#         print(f"✅ {len(related_layers)}개 레이어 색상 업데이트 완료")
#
#     except Exception as e:
#         print(f"⚠️ 레이어 색상 업데이트 중 오류: {str(e)}")
#         import traceback
#         traceback.print_exc()


# def update_layer_colors(uri, network_data):
#     """
#     계산 결과에 따라 레이어 색상을 업데이트합니다.
#
#     이 함수는 "색칠하기" 역할을 합니다:
#     - 계산 결과(전압, 부하율 등)에 따라 레이어에 색상 적용
#     - 사용자가 결과를 시각적으로 쉽게 파악할 수 있도록 도움
#
#     Args:
#         uri (str): 네트워크 URI
#         network_data (dict): 업데이트된 네트워크 데이터
#     """
#     try:
#         # 현재 프로젝트의 모든 레이어 가져오기
#         layers = QgsProject.instance().mapLayers()
#
#         # 해당 네트워크와 관련된 레이어 찾기
#         related_layers = []
#         for layer_id, layer in layers.items():
#             if (hasattr(layer, 'dataProvider') and
#                     layer.dataProvider().name() == "PandapowerProvider" and
#                     layer.source() == uri):
#                 related_layers.append(layer)
#
#         if not related_layers:
#             print("⚠️ 업데이트할 레이어를 찾을 수 없습니다.")
#             return
#
#         # 각 레이어에 대해 색상 업데이트
#         for layer in related_layers:
#             print(f"🎨 레이어 업데이트: {layer.name()}")
#
#             # 레이어 갱신 트리거
#             layer.dataProvider().dataChanged.emit()
#             layer.triggerRepaint()
#
#         print(f"✅ {len(related_layers)}개 레이어 색상 업데이트 완료")
#
#     except Exception as e:
#         print(f"⚠️ 레이어 색상 업데이트 중 오류: {str(e)}")


# def update_layer_colors(uri, network_data):
#     """
#     계산 결과에 따라 레이어 색상을 완전히 업데이트합니다.
#
#     🎨 이 함수가 하는 일:
#     1. 새 데이터로 레이어 새로고침 (도화지 준비)
#     2. 계산 결과에 따른 색상 규칙 만들기 (물감과 붓 준비)
#     3. 실제로 색칠하기 (그림 그리기)
#     4. 범례 만들기 (설명서 만들기)
#     """
#     try:
#         from qgis.core import (QgsGraduatedSymbolRenderer, QgsRendererRange,
#                                QgsSymbol, QgsField)
#         from qgis.utils import iface
#         from PyQt5.QtCore import QVariant
#         from PyQt5.QtGui import QColor
#
#         print("🔍 디버깅: NetworkContainer 상태 확인...")
#
#         # 🕵️ 1단계: NetworkContainer에서 실제 데이터 확인
#         container_data = NetworkContainer.get_network(uri)
#         if container_data:
#             container_net = container_data.get('net')
#             print(f"📦 Container에서 가져온 net 타입: {type(container_net)}")
#
#             if hasattr(container_net, 'res_bus'):
#                 print(f"✅ Container의 res_bus 크기: {len(container_net.res_bus)}")
#                 print(f"🔍 Container의 첫 번째 버스 전압: {container_net.res_bus.iloc[0]['vm_pu']:.3f}")
#             else:
#                 print("❌ Container에 res_bus가 없음!")
#
#             if hasattr(container_net, 'res_line'):
#                 print(f"✅ Container의 res_line 크기: {len(container_net.res_line)}")
#             else:
#                 print("❌ Container에 res_line이 없음!")
#         else:
#             print("❌ NetworkContainer에서 데이터를 가져올 수 없음!")
#
#         # 🕵️ 2단계: 전달받은 network_data 확인
#         if network_data:
#             net = network_data.get('net')
#             print(f"📥 전달받은 net 타입: {type(net)}")
#
#             if hasattr(net, 'res_bus'):
#                 print(f"✅ 전달받은 res_bus 크기: {len(net.res_bus)}")
#                 print(f"🔍 전달받은 첫 번째 버스 전압: {net.res_bus.iloc[0]['vm_pu']:.3f}")
#             else:
#                 print("❌ 전달받은 데이터에 res_bus가 없음!")
#
#
#
#         print("🎨 완전한 색상 업데이트 시작...")
#
#         # 1단계: 레이어 찾기 (기존과 동일)
#         layers = QgsProject.instance().mapLayers()
#         related_layers = []
#
#         for layer_id, layer in layers.items():
#             if (hasattr(layer, 'dataProvider') and
#                 layer.dataProvider().name() == "PandapowerProvider" and
#                 layer.source() == uri):
#
#                 provider = layer.dataProvider()
#
#
#                 # 🕵️ 3단계: Provider 초기화 전 상태 확인
#                 print(f"🔍 레이어 {layer.name()} Provider 초기화 전:")
#                 print(f"   - fields_list: {'있음' if provider.fields_list else '없음'}")
#                 print(f"   - df: {'있음' if provider.df is not None else '없음'}")
#
#
#                 # 🎯 핵심: Provider 강제 초기화
#                 provider.net = network_data['net']
#                 provider.fields_list = None  # 필드 캐시 초기화
#                 provider.df = None  # 데이터프레임 캐시 초기화
#
#
#                 # 🕵️ 4단계: Provider의 net 객체 직접 확인
#                 print(f"🔍 Provider의 net 객체:")
#                 if hasattr(provider.net, 'res_bus'):
#                     print(f"   ✅ Provider.net.res_bus 크기: {len(provider.net.res_bus)}")
#                 else:
#                     print(f"   ❌ Provider.net에 res_bus 없음!")
#
#
#                 # 🔄 Provider가 최신 데이터를 다시 로드하도록 강제
#                 provider.fields()  # 이때 merge_df()가 다시 실행됨
#
#
#                 # 🕵️ 5단계: Provider 초기화 후 확인
#                 print(f"🔍 Provider 초기화 후:")
#                 if provider.df is not None:
#                     print(f"   ✅ df 크기: {len(provider.df)}")
#                     print(f"   📋 df 컬럼들: {list(provider.df.columns)}")
#
#                     # vm_pu 컬럼이 있는지 확인
#                     if 'vm_pu' in provider.df.columns:
#                         print(f"   ✅ vm_pu 컬럼 발견!")
#                         print(f"   🔍 첫 번째 vm_pu 값: {provider.df.iloc[0]['vm_pu']}")
#                     else:
#                         print(f"   ❌ vm_pu 컬럼이 없음!")
#                 else:
#                     print(f"   ❌ df가 None!")
#
#
#                 related_layers.append(layer)
#
#         if not related_layers:
#             print("⚠️ 업데이트할 레이어를 찾을 수 없습니다.")
#             return
#
#         # 2단계: 각 레이어별로 완전한 색상 업데이트
#         for layer in related_layers:
#             print(f"🎨 레이어 완전 업데이트 시작: {layer.name()}")
#
#             # 2-1. 강제 데이터 새로고침 (제가 이전에 제안한 부분)
#             layer.dataProvider().dataChanged.emit()
#             layer.reload()
#             layer.dataProvider().reloadData()
#
#             # 2-2. 🌟 여기가 핵심! 실제 색상 규칙 설정
#             if 'bus' in layer.name().lower():
#                 # 버스 레이어: 전압에 따른 색상 설정
#                 apply_voltage_colors(layer, network_data)
#             elif 'line' in layer.name().lower():
#                 # 라인 레이어: 부하율에 따른 색상 설정
#                 apply_loading_colors(layer, network_data)
#
#             # 2-3. 레이어 다시 그리기
#             layer.triggerRepaint()
#
#         # 3단계: 전체 캔버스 새로고침
#         if iface:
#             iface.mapCanvas().refreshAllLayers()
#             iface.layerTreeView().refreshLayerSymbology(layer.id())
#
#         print(f"✅ {len(related_layers)}개 레이어 완전 색상 업데이트 완료")
#
#     except Exception as e:
#         print(f"⚠️ 완전한 색상 업데이트 중 오류: {str(e)}")
#         import traceback
#         traceback.print_exc()
#
#
# def apply_voltage_colors(layer, network_data):
#     """
#     버스 레이어에 전압에 따른 색상을 적용합니다.
#
#     🔋 색상 규칙:
#     - 높은 전압 (1.05 이상): 빨간색 (위험)
#     - 정상 전압 (0.95-1.05): 초록색 (안전)
#     - 낮은 전압 (0.95 이하): 파란색 (주의)
#     """
#     try:
#         from qgis.core import (QgsGraduatedSymbolRenderer, QgsRendererRange,
#                                QgsMarkerSymbol, QgsField)
#         from PyQt5.QtCore import QVariant
#         from PyQt5.QtGui import QColor
#
#         print(f"🔋 {layer.name()}에 전압 색상 적용 중...")
#
#         # 1. 전압 필드가 있는지 확인하고 없으면 추가
#         voltage_field_name = 'vm_pu'  # 전압 필드 이름
#
#         # 필드 존재 확인
#         field_names = [field.name() for field in layer.fields()]
#         if voltage_field_name not in field_names:
#             print(f"⚠️ {voltage_field_name} 필드가 없습니다. 추가 중...")
#             # 필드 추가 로직이 필요할 수 있음
#             return
#
#         # 2. 색상 범위 정의
#         ranges = []
#
#         # 범위 1: 낮은 전압 (0.90 - 0.95) - 파란색
#         symbol1 = QgsMarkerSymbol.createSimple({
#             'name': 'circle',
#             'color': 'blue',
#             'size': '4',
#             'outline_color': 'black'
#         })
#         ranges.append(QgsRendererRange(0.90, 0.95, symbol1, '낮은 전압 (0.90-0.95)'))
#
#         # 범위 2: 정상 전압 (0.95 - 1.05) - 초록색
#         symbol2 = QgsMarkerSymbol.createSimple({
#             'name': 'circle',
#             'color': 'green',
#             'size': '4',
#             'outline_color': 'black'
#         })
#         ranges.append(QgsRendererRange(0.95, 1.05, symbol2, '정상 전압 (0.95-1.05)'))
#
#         # 범위 3: 높은 전압 (1.05 - 1.15) - 빨간색
#         symbol3 = QgsMarkerSymbol.createSimple({
#             'name': 'circle',
#             'color': 'red',
#             'size': '4',
#             'outline_color': 'black'
#         })
#         ranges.append(QgsRendererRange(1.05, 1.15, symbol3, '높은 전압 (1.05-1.15)'))
#
#         # 3. 렌더러 생성 및 적용
#         renderer = QgsGraduatedSymbolRenderer(voltage_field_name, ranges)
#         layer.setRenderer(renderer)
#
#         print(f"✅ {layer.name()} 전압 색상 적용 완료")
#
#     except Exception as e:
#         print(f"⚠️ 전압 색상 적용 오류: {str(e)}")
#
#
# def apply_loading_colors(layer, network_data):
#     """
#     라인 레이어에 부하율에 따른 색상을 적용합니다.
#
#     ⚡ 색상 규칙:
#     - 과부하 (80% 이상): 빨간색 + 굵은 선 (위험)
#     - 정상 부하 (50-80%): 초록색 + 중간 선 (안전)
#     - 여유 부하 (50% 이하): 파란색 + 얇은 선 (여유)
#     """
#     try:
#         from qgis.core import (QgsGraduatedSymbolRenderer, QgsRendererRange,
#                                QgsLineSymbol)
#         from PyQt5.QtGui import QColor
#
#         print(f"⚡ {layer.name()}에 부하율 색상 적용 중...")
#
#         # 1. 부하율 필드 확인
#         loading_field_name = 'loading_percent'  # 부하율 필드 이름
#
#         field_names = [field.name() for field in layer.fields()]
#         if loading_field_name not in field_names:
#             print(f"⚠️ {loading_field_name} 필드가 없습니다.")
#             return
#
#         # 2. 색상 및 선 굵기 범위 정의
#         ranges = []
#
#         # 범위 1: 여유 부하 (0-50%) - 파란색, 얇은 선
#         symbol1 = QgsLineSymbol.createSimple({
#             'color': 'blue',
#             'width': '1',
#             'capstyle': 'round'
#         })
#         ranges.append(QgsRendererRange(0, 50, symbol1, '여유 부하 (0-50%)'))
#
#         # 범위 2: 정상 부하 (50-80%) - 초록색, 중간 선
#         symbol2 = QgsLineSymbol.createSimple({
#             'color': 'green',
#             'width': '2',
#             'capstyle': 'round'
#         })
#         ranges.append(QgsRendererRange(50, 80, symbol2, '정상 부하 (50-80%)'))
#
#         # 범위 3: 과부하 (80-100%) - 빨간색, 굵은 선
#         symbol3 = QgsLineSymbol.createSimple({
#             'color': 'red',
#             'width': '3',
#             'capstyle': 'round'
#         })
#         ranges.append(QgsRendererRange(80, 100, symbol3, '과부하 (80-100%)'))
#
#         # 3. 렌더러 생성 및 적용
#         renderer = QgsGraduatedSymbolRenderer(loading_field_name, ranges)
#         layer.setRenderer(renderer)
#
#         print(f"✅ {layer.name()} 부하율 색상 적용 완료")
#
#     except Exception as e:
#         print(f"⚠️ 부하율 색상 적용 오류: {str(e)}")


def show_success_message(parent, title, message):
    """성공 메시지를 사용자에게 표시합니다."""
    try:
        # QGIS 메시지 바에 표시
        if iface:
            iface.messageBar().pushMessage(
                title,
                message,
                level=Qgis.Success,
                duration=5
            )

        # 로그에도 기록
        QgsMessageLog.logMessage(f"{title}: {message}", level=Qgis.Success)

    except Exception as e:
        print(f"⚠️ 성공 메시지 표시 중 오류: {str(e)}")


def show_error_message(parent, message):
    """오류 메시지를 사용자에게 표시합니다."""
    try:
        # QGIS 메시지 바에 표시
        if iface:
            iface.messageBar().pushMessage(
                "RunPP 오류",
                message,
                level=Qgis.Critical,
                duration=10
            )

        # 로그에도 기록
        QgsMessageLog.logMessage(f"RunPP 오류: {message}", level=Qgis.Critical)

    except Exception as e:
        print(f"⚠️ 오류 메시지 표시 중 오류: {str(e)}")


# 🎯 사용 예시 (테스트용)
if __name__ == "__main__":
    # 이 부분은 테스트용이므로 실제 플러그인에서는 실행되지 않습니다
    print("ppqgis_runpp.py 모듈이 성공적으로 로드되었습니다!")

    # 예시 매개변수 파싱 테스트
    test_string = "algorithm='nr', max_iteration=10, tolerance=0.01"
    result = parse_kwargs_string(test_string)
    print(f"테스트 파싱 결과: {result}")