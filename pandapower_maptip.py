from qgis.core import QgsMapLayer, QgsVectorLayer, QgsProject, Qgis
from qgis.utils import iface


class MapTipUtils:
    """
    Pandapower 레이어에 대한 Map Tip 구성 및 관리 기능을 제공하는 유틸리티 클래스
    """

    @staticmethod
    def configure_map_tips(layer, vn_kv=None, network_type=None):
        """
        Pandapower 레이어의 Map Tip 설정을 구성합니다.

        :param layer: Layer to set Map Tip
        :type layer: QgsVectorLayer
        :param vn_kv: Voltage Level (kV)
        :type vn_kv: float
        :param network_type: Network Element Type ('bus', 'line', 'junction', 'pipe')
        :type network_type: str
        :return: 설정 성공 여부
        :rtype: bool
        """
        if not layer or not isinstance(layer, QgsVectorLayer):
            return False

        # 기본 스타일 정의
        css_style = """
        <style>
            .pp-container {
                font-family: 'Arial', sans-serif;
                background-color: #f8f9fa;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px;
                min-width: 200px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .pp-header {
                border-bottom: 1px solid #ddd;
                margin-bottom: 6px;
                padding-bottom: 6px;
            }
            .pp-title {
                font-weight: bold;
                color: #0066cc;
            }
            .pp-id {
                float: right;
                color: #666;
                font-size: 0.9em;
            }
            .pp-table {
                width: 100%;
                border-collapse: collapse;
            }
            .pp-table td {
                padding: 2px 4px;
            }
            .pp-table td:first-child {
                color: #666;
            }
            .pp-table td:last-child {
                text-align: right;
            }
            .pp-footer {
                margin-top: 6px;
                font-size: 0.8em;
                color: #666;
                text-align: center;
            }
            .bus-status {
                background-color: #e6f7e6;
                border-left: 3px solid #009933;
                padding: 4px 6px;
                margin-top: 6px;
                font-size: 0.9em;
            }
            .line-status {
                background-color: #fff0f0;
                border-left: 3px solid #cc3300;
                padding: 4px 6px;
                margin-top: 6px;
                font-size: 0.9em;
            }
            .warning {
                color: #cc3300;
                font-weight: bold;
            }
            .ok {
                color: #009933;
                font-weight: bold;
            }
            .caution {
                color: #ff9900;
                font-weight: bold;
            }
        </style>
        """

        # 네트워크 타입이 명시되지 않았으면 레이어 이름에서 추출 시도
        if not network_type:
            layer_name_parts = layer.name().split('_')
            if len(layer_name_parts) > 0:
                last_part = layer_name_parts[-1].lower()
                if last_part in ['bus', 'line', 'junction', 'pipe']:
                    network_type = last_part

        # HTML 템플릿 시작
        html_template = css_style + """
        <div class="pp-container">
            <div class="pp-header">
                <span class="pp-title">
                    [% 
                    CASE 
                    WHEN "name" IS NOT NULL AND length("name") > 0 THEN "name"
                    ELSE "pp_type" || ' ' || "pp_index" 
                    END
                    %]
                </span>
                <span class="pp-id">Dataframe ID: [% "pp_index" %]</span>
            </div>

            <table class="pp-table">
        """

        # 네트워크 타입별 특화 필드 추가
        if network_type == "bus":
            html_template += """
                <tr><td>vn_kv:</td><td>[% "vn_kv" %] kV</td></tr>
                <tr><td>vm_pu:</td>
                    <td>
                        [% 
                        CASE 
                        WHEN "vm_pu" < 0.95 THEN '<span class="warning">' || "vm_pu" || '</span>'
                        WHEN "vm_pu" > 1.05 THEN '<span class="caution">' || "vm_pu" || '</span>'
                        ELSE '<span class="ok">' || "vm_pu" || '</span>'
                        END
                        %]
                    </td>
                </tr>
                <tr><td>p_mw:</td><td>[% "p_mw" %] MW</td></tr>
                <tr><td>q_mvar:</td><td>[% "q_mvar" %] Mvar</td></tr>
            """

            # 전압 상태 정보 섹션 추가
            html_template += """
                <tr><td colspan="2">
                    <div class="bus-status">
                        <strong style="color: #009933;">Voltage Status:</strong>
                        [% 
                        CASE 
                        WHEN "vm_pu" < 0.95 THEN '<span class="warning">Low Voltage</span>'
                        WHEN "vm_pu" > 1.05 THEN '<span class="caution">Over Voltage</span>'
                        ELSE '<span class="ok">Normal Voltage</span>'
                        END
                        %]
                    </div>
                </td></tr>
            """

        elif network_type == "line":
            html_template += """
                <tr><td>from_bus:</td><td>[% "from_bus" %]</td></tr>
                <tr><td>to_bus:</td><td>[% "to_bus" %]</td></tr>
                <tr><td>length_km:</td><td>[% "length_km" %] km</td></tr>
                <tr><td>loading:</td>
                    <td>
                        [% 
                        CASE 
                        WHEN "loading_percent" > 90 THEN '<span class="warning">' || "loading_percent" || '%</span>'
                        WHEN "loading_percent" > 80 THEN '<span class="caution">' || "loading_percent" || '%</span>'
                        ELSE '<span class="ok">' || "loading_percent" || '%</span>'
                        END
                        %]
                    </td>
                </tr>
                <tr><td>i_ka:</td><td>[% "i_ka" %] kA</td></tr>
            """

            # 부하 상태 정보 섹션 추가
            html_template += """
                <tr><td colspan="2">
                    <div class="line-status">
                        <strong style="color: #cc3300;">Load Status:</strong>
                        [% 
                        CASE 
                        WHEN "loading_percent" > 90 THEN '<span class="warning">Overload</span>'
                        WHEN "loading_percent" > 80 THEN '<span class="caution">Caution</span>'
                        ELSE '<span class="ok">Normal</span>'
                        END
                        %]
                    </div>
                </td></tr>
            """

        elif network_type == "junction":
            html_template += """
                <tr><td>pn_bar:</td><td>[% "pn_bar" %] bar</td></tr>
                <tr><td>tfluid_k:</td><td>[% "tfluid_k" %] K</td></tr>
                <tr><td>type:</td><td>[% "type" %]</td></tr>
            """

        elif network_type == "pipe":
            html_template += """
                <tr><td>from_junction:</td><td>[% "from_junction" %]</td></tr>
                <tr><td>to_junction:</td><td>[% "to_junction" %]</td></tr>
                <tr><td>length_km:</td><td>[% "length_km" %] km</td></tr>
                <tr><td>diameter:</td><td>[% "diameter_m" %] m</td></tr>
                <tr><td>k_mm:</td><td>[% "k_mm" %] mm</td></tr>
            """

        # 그 외 타입이거나 타입을 특정할 수 없는 경우 공통 필드만 표시
        else:
            html_template += """
                <tr><td>type:</td><td>[% "pp_type" %]</td></tr>
                <tr><td>index:</td><td>[% "pp_index" %]</td></tr>
                <tr><td>name:</td><td>[% COALESCE("name", "Unspecified") %]</td></tr>
            """

        # HTML 템플릿 종료
        html_template += """
            </table>

            <div class="pp-footer">
                Pandapower Plugin - [% format_date(now(), 'yyyy-MM-dd HH:mm:ss') %]
            </div>
        </div>
        """

        # Map Tip 설정
        layer.setMapTipTemplate(html_template)

        # DisplayExpression 설정 (식별자 표시 방식 결정)
        layer.setDisplayExpression(
            "CASE " +
            "WHEN \"name\" IS NOT NULL AND length(\"name\") > 0 THEN \"name\" || ' (Dataframe ID: ' || \"pp_index\" || ')' " +
            "ELSE 'ID: ' || \"pp_index\" END"
        )

        # 레이어의 Map Tips 기능 활성화
        layer.setMapTipsEnabled(True)

        # 전역 Map Tips 설정도 활성화
        MapTipUtils.enable_map_tips()

        return True

    @staticmethod
    def enable_map_tips():
        """
        QGIS 전역 Map Tips 기능을 활성화합니다.
        """
        from qgis.PyQt.QtCore import QSettings
        QSettings().setValue("qgis/enableMapTips", True)

        # 또는 액션 트리거를 사용 (UI 버튼을 클릭하는 효과)
        try:
            iface.actionMapTips().trigger()
        except:
            pass  # 액션이 없거나 접근할 수 없는 경우 무시

    @staticmethod
    def disable_map_tips():
        """
        QGIS 전역 Map Tips 기능을 비활성화합니다.
        """
        from qgis.PyQt.QtCore import QSettings
        QSettings().setValue("qgis/enableMapTips", False)

        # 액션이 활성화된 경우 비활성화
        try:
            if iface.actionMapTips().isChecked():
                iface.actionMapTips().trigger()
        except:
            pass  # 액션이 없거나 접근할 수 없는 경우 무시

    @staticmethod
    def configure_all_pandapower_layers():
        """
        프로젝트의 모든 Pandapower 레이어에 Map Tip을 일괄 설정합니다.

        :return: 설정된 레이어 수
        :rtype: int
        """
        count = 0

        # 프로젝트의 모든 레이어 순회
        for layer in QgsProject.instance().mapLayers().values():
            if not isinstance(layer, QgsVectorLayer):
                continue

            # Pandapower 레이어 식별
            is_pp_layer = False

            # 데이터 제공자로 확인
            if layer.dataProvider().name() == "PandapowerProvider":
                is_pp_layer = True

            # 또는 레이어 이름으로 확인 (PandapowerProvider가 아닌 레이어도 처리 가능)
            if not is_pp_layer:
                layer_name = layer.name().lower()
                for network_type in ['bus', 'line', 'junction', 'pipe']:
                    if network_type in layer_name:
                        is_pp_layer = True
                        break

            # Pandapower 레이어이면 Map Tip 설정
            if is_pp_layer:
                # 레이어 이름에서 네트워크 타입 추출
                network_type = None
                for net_type in ['bus', 'line', 'junction', 'pipe']:
                    if net_type in layer.name().lower():
                        network_type = net_type
                        break

                # Map Tip 설정
                if MapTipUtils.configure_map_tips(layer, network_type=network_type):
                    count += 1

        # 설정 완료 후 Map Tips 활성화
        MapTipUtils.enable_map_tips()

        return count