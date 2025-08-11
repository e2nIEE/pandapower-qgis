import ast
import sys
import traceback
from typing import Dict, Any
from time import sleep

from qgis.core import QgsProject, QgsMessageLog, Qgis
from qgis.utils import iface
from qgis.PyQt.QtCore import QThread, pyqtSignal
from qgis.PyQt.QtWidgets import QMessageBox

from .network_container import NetworkContainer

# run_network(): 주방장 (전체 과정 관리)
# execute_calculation(): 요리사 (실제 요리 담당)
# parse_kwargs_string(): 번역기 (주문서를 요리법으로 번역)
    # 사용자가 입력한 텍스트를 파이썬이 이해할 수 있는 형태로 변환
    # 예: "algorithm='nr', max_iteration=10" → {'algorithm': 'nr', 'max_iteration': 10}
# post_process_results(): 서빙 담당 (완성된 요리를 예쁘게 플레이팅)


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
                post_process_results(parent, uri, network_data, parameters)
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
    debug_file_path = f"C:\\Users\\slee\\Documents\\pp_old\\test\\0708_post_process_results{timestamp}.txt"

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
        print("\n")
        print("=" * 50)
        print(f"🚚 여기는 post_process_results!")  # ← 이거 추가
        debug_print("[DEBUG] post_process_results 0608 version")

        debug_print("🔬 [DETAIL-1] 세밀한 후처리 분석 시작...")
        # 🔬 단계 A: NetworkContainer.register_network 분석
        debug_print("🔬 [DETAIL-A] NetworkContainer.register_network 테스트...")
        debug_print(f"   - URI: {uri} 🤩🤩🤩🤩🤩🤩🤩🤩")
        debug_print(f"   - network_data 키들: {list(network_data.keys())}")
        debug_print(f"   - 현재 NetworkContainer에 등록된 URI 개수: {len(NetworkContainer._networks)}")


        #🆕 URI Decoder를 사용해서 파일 경로 추출
        from qgis.core import QgsProviderRegistry

        debug_print(f"🔍 URI 분석 중: {uri}")

        # 1단계: Provider 메타데이터 가져오기
        metadata_provider = QgsProviderRegistry.instance().providerMetadata("PandapowerProvider")

        # 2단계: URI를 딕셔너리로 분해하기
        uri_parts = metadata_provider.decodeUri(uri)
        debug_print(f"🔍 URI 분해 결과: {uri_parts}")

        # 3단계: 파일 경로 추출
        file_path = uri_parts.get('path')
        if not file_path:
            debug_print("❌ URI에서 파일 경로를 찾을 수 없습니다.")
            debug_print(f"❌ URI 구성 요소: {uri_parts}")
            return

        debug_print(f"✅ 파일 경로 추출 성공: {file_path}")
        debug_print(f"📁 파일 경로: {file_path}")

        # 🔍 현재 NetworkContainer에 등록된 모든 URI 확인
        all_uris = list(NetworkContainer._networks.keys())
        related_uris = []

        for existing_uri in all_uris:
            # 같은 파일에서 온 URI인지 확인
            if f'path="{file_path}"' in existing_uri:
                related_uris.append(existing_uri)
                debug_print(f"🎯 관련 URI 발견: {existing_uri}")
        if not related_uris:
            debug_print("⚠️ 관련된 URI를 찾을 수 없습니다.")
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
                debug_print(f"✅ URI 업데이트 완료: {related_uri}")
            else:
                debug_print(f"⚠️ 기존 데이터를 찾을 수 없음: {related_uri}")

        debug_print("🎉 모든 관련 레이어 업데이트 완료!")

        # 2. 레이어 색상 업데이트 (사용자가 선택한 경우)
        if parameters.get('update_renderer', False):
            print("#"*50)
            print("🎨 post_process_results 단계 2. 레이어 색상 업데이트 시작...")
            debug_print("🔬 [DETAIL-B] 렌더러 업데이트 테스트...")
            # 모든 관련 URI에 대해 색상 업데이트
            for related_uri in related_uris:
                debug_print(f"   🚨 {related_uri}에 대해 update_layer_colors_for_uri 호출 중...")
                update_layer_colors_for_uri(related_uri)    # v1+v2
                #safe_renderer_update_test(uri, debug_print)    # detailed_post_process_analysis method
                debug_print("   ✅ 렌더러 업데이트 테스트 성공!")
            print("✅ 전체 레이어 색상 업데이트 완료") # 왜 이건 실행안되지?

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


def update_layer_colors_for_uri(uri):
    """
    안전한 렌더러 설정 - 단계별 검증으로 문제점 찾기
    """
    try:
        print("현재 update_layer_colors_for_uri이에요!")
        print("🔍 1단계: 렌더러 import 시작...")
        from .renderer_utils import create_bus_renderer, create_line_renderer
        print("✅ 1단계 완료: import 성공")

        print("🔍 2단계: 레이어 찾기 시작...")
        layers = QgsProject.instance().mapLayers()
        target_layers = []
        renderer = None

        for layer_id, layer in layers.items():
            if (hasattr(layer, 'dataProvider') and
                    layer.dataProvider().name() == "PandapowerProvider" and
                    layer.source() == uri):
                target_layers.append(layer)
                renderer = layer.renderer()
                print(f"✅ 타겟 레이어 발견: {layer.name()}")
                print(f"✅ 렌더러 발견: {renderer}")

        if not target_layers:
            print("⚠️ 업데이트할 레이어를 찾을 수 없습니다.")
            return True  # 오류가 아니므로 True 반환
        if not renderer:
            print("⚠️ 기존 렌더러를 발견할 수 없습니다.")

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
            #renderer = None
            field_names = [field.name() for field in layer.fields()]
            print(f"🔍 레이어 {layer.name()} 필드들: {field_names}")

            # print(f"🔍 3-{i + 1}-1: 렌더러 생성 중...")
            # if 'bus' in layer_name_lower or 'junction' in layer_name_lower:
            #     if "vm_pu" in field_names:
            #         renderer = create_bus_renderer(render=True)
            #         print(f"✅ 새로운 그라데이션 버스 렌더러 생성 for {layer.name()}")
            #     else:
            #         renderer = create_bus_renderer(render=False)[0]  # return값 다 안 쓸거면 왜 두 개 만든겨?
            #         print(f"✅ 새로운 단순 버스 렌더러 생성 for {layer.name()}")
            #     print(f"✅ 버스 렌더러 생성: {type(renderer)}")
            # elif 'line' in layer_name_lower or 'pipe' in layer_name_lower:
            #     if "loading_percent" in field_names:
            #         #renderer = create_line_renderer(render=True)
            #         print(f"⚠️ 라인 렌더러 생성 시도 중... (크래시 위험 구간)")
            #         try:
            #             renderer = create_line_renderer(render=True)
            #             print(f"✅ 새로운 그라데이션 라인 렌더러 생성 for {layer.name()}")
            #         except Exception as line_renderer_error:
            #             print(f"❌ 그라데이션 라인 렌더러 생성 실패: {line_renderer_error}")
            #             print("⚠️ 단순 렌더러로 대체...")
            #             renderer, _ = create_line_renderer(render=False)
            #             print(f"✅ 단순 라인 렌더러로 대체 완료 for {layer.name()}")
            #     else:
            #         renderer = create_line_renderer(render=False)[0]
            #         print("✅ 단순 렌더러 for line 생성")
            #     print(f"✅ 라인 렌더러 생성: {type(renderer)}")
            # else:
            #     print(f"⚠️ 알 수 없는 레이어 타입: {layer.name()}")
            #     continue

            # 3-4. 렌더러 유효성 검사
            print(f"   - 메모리 주소: {id(renderer)}🔍🔍🔍🔍🔍🔍🔍🔍")  # 각 레이어마다 다른 주소여야 함!
            if not renderer:
                print(f"❌ 렌더러 생성 실패: {layer.name()}")
                continue

            print(f"🔍 3-{i + 1}-2: 렌더러 설정 시도 중...")

            # # 🚨 핵심: 안전한 렌더러 설정
            try:
            #     # 렌더러 설정 전 추가 검사
            #     if hasattr(renderer, 'classAttribute') and hasattr(layer, 'fields'):
            #         #attr_name = renderer.classAttribute()
            #
            #         if attr_name:  # 속성 기반 렌더러인 경우
            #             field_names = [field.name() for field in layer.fields()]
            #             if attr_name not in field_names:
            #                 print(f"⚠️ 필드 {attr_name}이 레이어에 없음. 단순 렌더러로 변경")
            #                 # 단순 렌더러로 대체
            #                 if 'bus' in layer_name_lower or 'junction' in layer_name_lower:
            #                     renderer = create_bus_renderer(render=False)[0]
            #                 else:
            #                     renderer = create_line_renderer(render=False)[0]

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