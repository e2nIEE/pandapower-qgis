import os

from pandapower import runpm_tnep
from qgis.PyQt import QtWidgets, QtCore
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
                                 QLabel, QLineEdit, QSpinBox, QDoubleSpinBox,
                                 QCheckBox, QDialogButtonBox, QGroupBox,
                                 QProgressBar, QTextEdit, QPushButton, QFrame, QComboBox)
from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal
from qgis.core import QgsProviderRegistry
from .network_container import NetworkContainer


class ppRunDialog(QDialog):
    def __init__(self, parent=None):
        """생성자 - RunPP 다이얼로그를 초기화합니다."""
        super(ppRunDialog, self).__init__(parent)

        # 다이얼로그 기본 설정
        self.setWindowTitle(self.tr("Run Pandapower Network"))
        self.setMinimumWidth(450)
        self.setMinimumHeight(600)

        # 네트워크 정보 저장
        self.uri = None
        self.network_data = None
        self.network_type = None  # 'power' or 'pipes'

        # UI 구성
        self.setup_ui()

        # 기본값 설정
        #self.set_default_values()

    def setup_ui(self):
        """UI 레이아웃을 구성합니다."""
        # 메인 레이아웃
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # 1. 네트워크 정보 그룹
        self.create_network_info_group()
        main_layout.addWidget(self.network_info_group)

        # 2. RunPP 옵션 그룹
        self.create_runpp_options_group()
        main_layout.addWidget(self.runpp_options_group)

        # 3. 고급 옵션 그룹
        self.create_advanced_options_group()
        main_layout.addWidget(self.advanced_options_group)

        # 4. 진행상황 그룹
        self.create_progress_group()
        main_layout.addWidget(self.progress_group)

        # 5. 버튼
        self.create_buttons()
        main_layout.addWidget(self.button_box)

    def create_network_info_group(self):
        """네트워크 정보를 표시하는 그룹박스를 생성합니다."""
        self.network_info_group = QGroupBox(self.tr("Network Information"))
        layout = QGridLayout()

        # 네트워크 타입 라벨
        self.network_type_label = QLabel(self.tr("Network Type: "))
        self.network_type_value = QLabel(self.tr("Not loaded"))
        layout.addWidget(self.network_type_label, 0, 0)
        layout.addWidget(self.network_type_value, 0, 1)

        # Bus/Junction 개수 라벨
        self.bus_label = QLabel(self.tr("Buses/Junctions: "))
        self.bus_count = QLabel("0")
        layout.addWidget(self.bus_label, 1, 0)
        layout.addWidget(self.bus_count, 1, 1)

        # Line/Pipe 개수 라벨
        self.line_label = QLabel(self.tr("Lines/Pipes: "))
        self.line_count = QLabel("0")
        layout.addWidget(self.line_label, 2, 0)
        layout.addWidget(self.line_count, 2, 1)

        # 파일 경로 라벨
        self.file_path_label = QLabel(self.tr("File: "))
        self.file_path_value = QLabel(self.tr("Not loaded"))
        self.file_path_value.setWordWrap(True)  # 긴 경로를 줄바꿈
        layout.addWidget(self.file_path_label, 3, 0)
        layout.addWidget(self.file_path_value, 3, 1)

        self.network_info_group.setLayout(layout)

    def create_runpp_options_group(self):
        """RunPP 옵션을 설정하는 그룹박스를 생성합니다."""
        self.runpp_options_group = QGroupBox(self.tr("RunPP Options"))
        layout = QGridLayout()

        # run 함수 선택
        layout.addWidget(QLabel(self.tr("Function:")), 0, 0)
        self.run_function = QComboBox()
        self.run_function.addItems(['run', 'rundcopp', 'rundcpp', 'runopp', 'runpm', 'runpm_ac_opf', 'runpm_dc_opf',
                                    'runpm_loading', 'runpm_multi_qflex', 'runpm_multi_vstab', 'runpm_ots', 'runpm_pf',
                                    'runpm_ploss', 'runpm_qflex', 'runpm_storage_opf', 'runpm_tnep', 'runpm_vstab',
                                    'runpp', 'runpp_3ph', 'runpp_pgm'])
        self.run_function.setCurrentText('run')  # 기본값
        layout.addWidget(self.run_function, 0, 1)

        # 파라미터 선택
        layout.addWidget(QLabel(self.tr("Parameter(**kwargs):")), 1, 0)
        self.parameter_dict = QLineEdit()
        #self.parameter_dict.addItems(['nr', 'iwamoto_nr', 'bfsw', 'gs', 'fdpf'])
        #self.parameter_dict.setCurrentText('nr')  # 기본값
        layout.addWidget(self.parameter_dict, 1, 1)

        """
        # 최대 반복 횟수
        layout.addWidget(QLabel(self.tr("Max Iteration:")), 2, 0)
        self.max_iteration_spin = QSpinBox()
        self.max_iteration_spin.setRange(1, 1000)
        self.max_iteration_spin.setValue(10)  # 기본값
        layout.addWidget(self.max_iteration_spin, 2, 1)

        # 허용 오차 (MVA)
        layout.addWidget(QLabel(self.tr("Tolerance (MVA):")), 3, 0)
        self.tolerance_spin = QDoubleSpinBox()
        self.tolerance_spin.setRange(0.0001, 1.0)
        self.tolerance_spin.setDecimals(6)
        self.tolerance_spin.setSingleStep(0.0001)
        self.tolerance_spin.setValue(0.01)  # 기본값
        layout.addWidget(self.tolerance_spin, 3, 1)
        """

        # 초기화 방법
        layout.addWidget(QLabel(self.tr("Initialization:")), 4, 0)
        self.init_combo = QComboBox()
        self.init_combo.addItems(['auto', 'flat', 'results'])
        self.init_combo.setCurrentText('auto')  # 기본값
        layout.addWidget(self.init_combo, 4, 1)

        self.runpp_options_group.setLayout(layout)

    def create_advanced_options_group(self):
        """고급 옵션을 설정하는 그룹박스를 생성합니다."""
        self.advanced_options_group = QGroupBox(self.tr("Advanced Options"))
        layout = QVBoxLayout()

        '''
        # 체크박스 옵션들
        self.calc_voltage_angles_cb = QCheckBox(self.tr("Calculate voltage angles"))
        self.calc_voltage_angles_cb.setChecked(True)  # 기본값
        layout.addWidget(self.calc_voltage_angles_cb)

        self.voltage_dependent_loads_cb = QCheckBox(self.tr("Voltage dependent loads"))
        self.voltage_dependent_loads_cb.setChecked(True)  # 기본값
        layout.addWidget(self.voltage_dependent_loads_cb)

        self.consider_line_temp_cb = QCheckBox(self.tr("Consider line temperature"))
        self.consider_line_temp_cb.setChecked(False)  # 기본값
        layout.addWidget(self.consider_line_temp_cb)

        self.distributed_slack_cb = QCheckBox(self.tr("Distributed slack"))
        self.distributed_slack_cb.setChecked(False)  # 기본값
        layout.addWidget(self.distributed_slack_cb)
        '''

        #separator = QFrame()
        #separator.setFrameStyle(QFrame.HLine | QFrame.Sunken)
        #layout.addWidget(separator)

        # 결과 시각화 옵션
        layout.addWidget(QLabel(self.tr("Visualization Options:")))
        self.update_renderer_cb = QCheckBox(self.tr("Update layer colors after calculation"))
        self.update_renderer_cb.setChecked(True)  # 기본값
        layout.addWidget(self.update_renderer_cb)

        self.show_results_cb = QCheckBox(self.tr("Show detailed results in dialog"))
        self.show_results_cb.setChecked(False)  # 기본값
        layout.addWidget(self.show_results_cb)

        self.advanced_options_group.setLayout(layout)

    def create_progress_group(self):
        """진행상황을 표시하는 그룹박스를 생성합니다."""
        self.progress_group = QGroupBox(self.tr("Progress"))
        layout = QVBoxLayout()

        # 진행바
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)  # 처음에는 숨김
        layout.addWidget(self.progress_bar)

        # 결과 텍스트
        self.result_text = QTextEdit()
        self.result_text.setMaximumHeight(100)
        self.result_text.setVisible(False)  # 처음에는 숨김
        layout.addWidget(self.result_text)

        self.progress_group.setLayout(layout)

    def create_buttons(self):
        """버튼들을 생성합니다."""
        self.button_box = QDialogButtonBox()

        # Run 버튼
        self.run_button = QPushButton(self.tr("Run Calculation"))
        self.run_button.setDefault(True)
        self.button_box.addButton(self.run_button, QDialogButtonBox.AcceptRole)

        # Cancel 버튼
        self.cancel_button = QPushButton(self.tr("Cancel"))
        self.button_box.addButton(self.cancel_button, QDialogButtonBox.RejectRole)

        # 신호 연결
        #self.button_box.accepted.connect(self.accept)
        self.button_box.accepted.connect(self.start_calculation)
        self.button_box.rejected.connect(self.reject)

    def setup_network(self, uri):
        """
        네트워크 정보를 설정합니다.

        Args:
            uri (str): 네트워크 URI
        """
        print(f"[DEBUG] Setting up network with URI: {uri}")

        self.uri = uri

        try:
            # URI 파싱
            provider_metadata = QgsProviderRegistry.instance().providerMetadata("PandapowerProvider")
            uri_parts = provider_metadata.decodeUri(uri)

            # 네트워크 데이터 가져오기
            self.network_data = NetworkContainer.get_network(uri)

            if not self.network_data:
                self.show_error("Failed to load network data from container")
                return

            # 네트워크 타입 결정
            network_type = uri_parts.get('network_type', '')
            if network_type in ['bus', 'line']:
                self.network_type = 'power'
                self.update_power_network_info()
            elif network_type in ['junction', 'pipe']:
                self.network_type = 'pipes'
                self.update_pipes_network_info()
            else:
                self.show_error(f"Unknown network type: {network_type}")
                return

            # 파일 경로 표시
            file_path = uri_parts.get('path', 'Unknown')
            self.file_path_value.setText(os.path.basename(file_path))
            self.file_path_value.setToolTip(file_path)  # 전체 경로는 툴팁으로

            print(f"[DEBUG] Network setup completed. Type: {self.network_type}")

        except Exception as e:
            print(f"[ERROR] Failed to setup network: {str(e)}")
            self.show_error(f"Failed to setup network: {str(e)}")

    def update_power_network_info(self):
        """전력 네트워크 정보를 업데이트합니다."""
        net = self.network_data['net']

        self.network_type_value.setText("Pandapower Network")
        self.bus_label.setText(self.tr("Buses: "))
        self.line_label.setText(self.tr("Lines: "))

        try:
            bus_count = len(net.bus) if hasattr(net, 'bus') else 0
            line_count = len(net.line) if hasattr(net, 'line') else 0

            self.bus_count.setText(str(bus_count))
            self.line_count.setText(str(line_count))

        except Exception as e:
            print(f"[ERROR] Error reading power network info: {str(e)}")
            self.bus_count.setText("Error")
            self.line_count.setText("Error")

    def update_pipes_network_info(self):
        """파이프 네트워크 정보를 업데이트합니다."""
        net = self.network_data['net']

        self.network_type_value.setText("Pandapipes Network")
        self.bus_label.setText(self.tr("Junctions: "))
        self.line_label.setText(self.tr("Pipes: "))

        try:
            junction_count = len(net.junction) if hasattr(net, 'junction') else 0
            pipe_count = len(net.pipe) if hasattr(net, 'pipe') else 0

            self.bus_count.setText(str(junction_count))
            self.line_count.setText(str(pipe_count))

        except Exception as e:
            print(f"[ERROR] Error reading pipes network info: {str(e)}")
            self.bus_count.setText("Error")
            self.line_count.setText("Error")

    def get_parameters(self):
        """
        사용자가 설정한 RunPP 파라미터들을 반환합니다.

        Returns:
            dict: RunPP 파라미터 딕셔너리
        """
        parameters = {
            'kwargs_string': self.parameter_dict.text(),
            # 기본 RunPP 파라미터
            #'algorithm': self.algorithm_combo.text(),
            #'max_iteration': self.max_iteration_spin.value(),
            #'tolerance_mva': self.tolerance_spin.value(),
            'init': self.init_combo.currentText(),
            #'calculate_voltage_angles': self.calc_voltage_angles_cb.isChecked(),
            #'voltage_dependent_loads': self.voltage_dependent_loads_cb.isChecked(),
            #'consider_line_temperature': self.consider_line_temp_cb.isChecked(),
            #'distributed_slack': self.distributed_slack_cb.isChecked(),

            # 시각화 옵션
            'update_renderer': self.update_renderer_cb.isChecked(),
            'show_results': self.show_results_cb.isChecked(),

            # 네트워크 정보
            'network_type': self.network_type
        }

        print(f"[DEBUG] Parameters collected: {parameters}")
        return parameters


    def start_calculation(self):
        """완벽하게 개선된 계산 시작 함수"""
        try:
            print("🛡️ 완벽한 계산 시작!")

            # 1. 네트워크 확인
            if not self.uri:
                self.show_error("먼저 네트워크를 선택해주세요!")
                return

            # 2. 설정 수집
            parameters = self.get_parameters()

            # 3. 계산 시작 모드로 UI 변경
            self.enter_calculation_mode()

            # 4. 진행 메시지들 차례대로 표시
            self.add_progress_message("⚡ Starting calculation...")
            QtCore.QCoreApplication.processEvents()

            import time
            time.sleep(0.5)

            self.add_progress_message("⚡ Executing power grid calculation...")
            QtCore.QCoreApplication.processEvents()

            # 5. 실제 계산 실행
            from .ppqgis_runpp import run_network
            success = run_network(None, self.uri, parameters)

            # 6. 결과에 따른 처리
            if success:
                self.add_progress_message("✅ Calculation completed!")
                QtCore.QCoreApplication.processEvents()

                # 색상 업데이트
                if parameters.get('update_renderer', False):
                    self.add_progress_message("🎨 Displaying results on the map...")
                    QtCore.QCoreApplication.processEvents()
                    self.update_map_colors()
                    self.add_progress_message("🎨 Map color update completed!")
                    QtCore.QCoreApplication.processEvents()

                time.sleep(2)  # 결과를 보여주는 시간
                self.calculation_success()  # 성공 처리

            else:
                self.add_progress_message("❌ Calculation failed!")
                self.show_error("계산 실패!")
                self.calculation_failed()  # 실패 처리

        except Exception as e:
            error_msg = f"Calculation error: {str(e)}"
            print(f"❌ {error_msg}")
            self.add_progress_message(f"❌ {error_msg}")
            self.show_error(error_msg)
            self.calculation_failed()  # 실패 처리


    def enter_calculation_mode(self):
        """계산 시작할 때 UI를 준비하는 함수"""
        try:
            # 버튼을 "계산 중..." 상태로 바꾸기
            self.run_button.setEnabled(False)  # 버튼 비활성화 (중복 클릭 방지)
            self.run_button.setText("계산 중...")  # 버튼 텍스트 변경

            # 진행바 시작하기
            self.progress_bar.setVisible(True)  # 진행바 보이게 하기
            self.progress_bar.setRange(0, 0)  # 무한 진행바로 설정

            # 결과 텍스트 영역 준비하기
            if hasattr(self, 'result_text'):
                self.result_text.setVisible(True)  # 텍스트 영역 보이게 하기
                self.result_text.clear()  # 이전 내용 지우기

            print("🎬 계산 모드 시작")

        except Exception as e:
            print(f"⚠️ 계산 모드 진입 오류: {str(e)}")

    def add_progress_message(self, message):
        """진행 상황을 사용자에게 알려주는 함수"""
        try:
            print(f"📝 진행: {message}")

            # 화면의 텍스트 영역에 메시지 추가하기
            if hasattr(self, 'result_text'):
                # 기존에 있던 텍스트 가져오기
                current_text = self.result_text.toPlainText()

                # 새 메시지를 기존 텍스트에 추가하기
                if current_text:
                    new_text = current_text + f"\n{message}"  # 줄바꿈 후 추가
                else:
                    new_text = message  # 첫 번째 메시지면 그냥 추가

                # 화면에 표시하기
                self.result_text.setText(new_text)

                # 자동으로 맨 아래로 스크롤하기 (새 메시지가 보이도록)
                scrollbar = self.result_text.verticalScrollBar()
                if scrollbar:
                    scrollbar.setValue(scrollbar.maximum())

        except Exception as e:
            print(f"⚠️ 메시지 추가 오류: {str(e)}")

    def update_map_colors(self):
        """계산 결과를 지도에 색깔로 표시하는 함수"""
        try:
            print("🎨 지도 색상 업데이트 시작...")

            # QGIS에서 현재 열려있는 모든 지도 레이어들 가져오기
            from qgis.core import QgsProject
            layers = QgsProject.instance().mapLayers()

            updated_count = 0  # 업데이트된 레이어 개수 세기

            # 각 레이어를 하나씩 확인해보기
            for layer_id, layer in layers.items():
                try:
                    # 우리가 만든 전력망 레이어인지 확인하기
                    if (hasattr(layer, 'dataProvider') and
                            layer.dataProvider().name() == "PandapowerProvider" and
                            layer.source() == self.uri):
                        print(f"🎨 레이어 업데이트: {layer.name()}")

                        # 레이어에게 "데이터가 바뀌었으니 다시 그려!" 명령하기
                        layer.dataProvider().dataChanged.emit()
                        layer.triggerRepaint()
                        updated_count += 1

                except Exception as e:
                    print(f"⚠️ 레이어 {layer_id} 업데이트 오류: {str(e)}")
                    continue  # 이 레이어는 건너뛰고 다음 레이어로

            # 업데이트 결과 확인
            if updated_count > 0:
                print(f"✅ {updated_count}개 레이어 색상 업데이트 완료")

                # 전체 지도 화면도 새로고침하기
                from qgis.utils import iface
                if iface:
                    iface.mapCanvas().refresh()
                    print("✅ 지도 캔버스 새로고침 완료")
            else:
                print("⚠️ 업데이트할 레이어를 찾을 수 없습니다")

        except Exception as e:
            print(f"⚠️ 지도 색상 업데이트 오류: {str(e)}")

    def calculation_success(self):
        """계산이 성공했을 때 마무리 처리"""
        try:
            print("🎉 계산 성공 처리 시작")

            # 모든 UI를 원래 상태로 되돌리기
            self.reset_ui()

            # 3초 후에 다이얼로그 자동으로 닫기
            QtCore.QTimer.singleShot(3000, self.accept)

            print("🎉 계산 성공 처리 완료")

        except Exception as e:
            print(f"⚠️ 성공 처리 오류: {str(e)}")

    def calculation_failed(self):
        """계산이 실패했을 때 마무리 처리"""
        try:
            print("💥 계산 실패 처리 시작")

            # 모든 UI를 원래 상태로 되돌리기
            self.reset_ui()

            print("💥 계산 실패 처리 완료")

        except Exception as e:
            print(f"⚠️ 실패 처리 오류: {str(e)}")

    def reset_ui(self):
        """UI를 완전히 원래 상태로 되돌리는 함수 (핵심!)"""
        try:
            print("🔄 UI 완전 복원 시작...")

            # 1. 버튼을 원래 상태로 되돌리기
            if hasattr(self, 'run_button'):
                self.run_button.setEnabled(True)  # 버튼 활성화
                self.run_button.setText(self.tr("Run Calculation"))  # 원래 텍스트로
                print("   ✅ 버튼 상태 복원")

            # 2. 진행바 완전히 정리하기
            if hasattr(self, 'progress_bar'):
                self.progress_bar.setVisible(False)  # 진행바 숨기기
                self.progress_bar.setRange(0, 100)  # 범위를 정상으로 되돌리기
                print("   ✅ 진행바 중지 및 숨김")

            # 3. 결과 텍스트는 그대로 두기 (사용자가 결과를 확인할 수 있도록)
            # self.result_text.setVisible(False)  # 이 줄은 주석처리!

            print("🔄 UI 완전 복원 완료!")

        except Exception as e:
            print(f"⚠️ UI 복원 오류: {str(e)}")


    def closeEvent(self, event):
        """다이얼로그가 닫힐 때 자동으로 정리하는 함수"""
        try:
            print("🚪 다이얼로그 닫기 준비...")
            self.reset_ui()  # 완전 정리
            event.accept()  # 닫기 허용
            print("🚪 다이얼로그 정리 완료")
        except Exception as e:
            print(f"⚠️ 다이얼로그 닫기 오류: {str(e)}")
            event.accept()  # 에러가 나도 일단 닫기

    def showEvent(self, event):
        """다이얼로그가 열릴 때 자동으로 준비하는 함수"""
        try:
            print("👁️ 다이얼로그 열기 준비...")
            self.reset_ui()  # 깨끗한 상태로 시작

            # 결과 텍스트도 완전히 비우기 (새로 시작할 때는 깨끗하게)
            if hasattr(self, 'result_text'):
                self.result_text.clear()
                self.result_text.setVisible(False)

            event.accept()  # 열기 허용
            print("👁️ 다이얼로그 초기화 완료")
        except Exception as e:
            print(f"⚠️ 다이얼로그 열기 오류: {str(e)}")
            event.accept()


    def show_error(self, message):
        """에러 메시지를 표시합니다."""
        from qgis.PyQt.QtWidgets import QMessageBox
        QMessageBox.critical(self, self.tr("Error"), message)


    def show_progress(self, visible=True):
        """진행바를 표시하거나 숨깁니다."""
        self.progress_bar.setVisible(visible)
        if visible:
            self.progress_bar.setRange(0, 0)  # 무한 진행바


    def show_results(self, results_text):
        """결과를 텍스트로 표시합니다."""
        if self.show_results_cb.isChecked():
            self.result_text.setVisible(True)
            self.result_text.setText(results_text)


    def tr(self, message):
        """번역을 위한 헬퍼 메서드"""
        return QtCore.QCoreApplication.translate('ppRunDialog', message)