from qgis.core import QgsMapLayer, QgsVectorLayer, QgsProject, Qgis
from qgis.utils import iface


class MapTipUtils:
    """
    A utility class that provides map tip configuration
    and management functions for the Pandapower layer.
    """

    @staticmethod
    def configure_map_tips(layer, vn_kv=None, network_type=None):
        """
        Configure HTML map tip template for a pandapower layer with network-specific information display.
        Creates styled tooltips showing relevant attributes based on network element type (bus, line, junction, pipe).
        Args:
            layer: QgsVectorLayer to configure map tips for
            vn_kv: Nominal voltage level (optional, currently unused in implementation)
            network_type: Type of network element ('bus', 'line', 'junction', 'pipe').
                         If None, attempts to extract from layer name
        Returns:
            bool: True if configuration successful, False if layer is invalid
        """
        if not layer or not isinstance(layer, QgsVectorLayer):
            return False

        # Default style definition
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
            .no-calc {
                background: #fffacd;
                border-left: 3px solid #ffa500;
                padding: 5px;
                margin-top: 8px;
                font-size: 0.9em;
            }
        </style>
        """

        # If the network type is not specified, attempt to extract it from the layer name
        if not network_type:
            layer_name_parts = layer.name().split('_')
            if len(layer_name_parts) > 0:
                last_part = layer_name_parts[-1].lower()
                if last_part in ['bus', 'line', 'junction', 'pipe']:
                    network_type = last_part

        # Start of HTML template
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

        # Include conditional rendering in the template for each network type
        if network_type == "bus":
            html_template += """
                <tr><td>vn_kv:</td><td>[% "vn_kv" %] kV</td></tr>
                [% 
                CASE 
                WHEN "vm_pu" IS NOT NULL THEN
                    '<tr><td>vm_pu:</td><td>' ||
                    CASE 
                        WHEN "vm_pu" < 0.95 THEN '<span class="warning">' || "vm_pu" || '</span>'
                        WHEN "vm_pu" > 1.05 THEN '<span class="caution">' || "vm_pu" || '</span>'
                        ELSE '<span class="ok">' || "vm_pu" || '</span>'
                    END || 
                    '</td></tr>' ||
                    '<tr><td>p_mw:</td><td>' || "p_mw" || ' MW</td></tr>' ||
                    '<tr><td>q_mvar:</td><td>' || "q_mvar" || ' Mvar</td></tr>'
                ELSE
                    '<tr><td colspan="2"><div class="no-calc">⚠️ No calculation results — RunPP must be run</div></td></tr>'
                END
                %]
            """

        elif network_type == "line":
            html_template += """
                <tr><td>from_bus:</td><td>[% "from_bus" %]</td></tr>
                <tr><td>to_bus:</td><td>[% "to_bus" %]</td></tr>
                <tr><td>length_km:</td><td>[% "length_km" %] km</td></tr>
                [% 
                CASE 
                WHEN "loading_percent" IS NOT NULL THEN
                    '<tr><td>loading:</td><td>' ||
                    CASE 
                        WHEN "loading_percent" > 90 THEN '<span class="warning">' || "loading_percent" || '%</span>'
                        WHEN "loading_percent" > 80 THEN '<span class="caution">' || "loading_percent" || '%</span>'
                        ELSE '<span class="ok">' || "loading_percent" || '%</span>'
                    END || 
                    '</td></tr>' ||
                    '<tr><td>i_ka:</td><td>' || "i_ka" || ' kA</td></tr>'
                ELSE
                    '<tr><td colspan="2"><div class="no-calc">⚠️ No calculation results — RunPP must be run</div></td></tr>'
                END
                %]
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

        else:
            html_template += """
                <tr><td>type:</td><td>[% "pp_type" %]</td></tr>
                <tr><td>index:</td><td>[% "pp_index" %]</td></tr>
                <tr><td>name:</td><td>[% COALESCE("name", "Unspecified") %]</td></tr>
            """

        # End of HTML template
        html_template += """
            </table>

            <div class="pp-footer">
                Pandapower Plugin - [% format_date(now(), 'yyyy-MM-dd HH:mm:ss') %]
            </div>
        </div>
        """

        layer.setMapTipTemplate(html_template)
        layer.setDisplayExpression(
            "CASE " +
            "WHEN \"name\" IS NOT NULL AND length(\"name\") > 0 THEN \"name\" || ' (Dataframe ID: ' || \"pp_index\" || ')' " +
            "ELSE 'ID: ' || \"pp_index\" END"
        )
        layer.setMapTipsEnabled(True)
        MapTipUtils.enable_map_tips()
        return True


    @staticmethod
    def enable_map_tips():
        """
        Enables the global Map Tips feature in QGIS.
        """
        from qgis.PyQt.QtCore import QSettings
        QSettings().setValue("qgis/enableMapTips", True)

        # Or use an action trigger (simulates clicking a UI button)
        try:
            iface.actionMapTips().trigger()
        except:
            pass  # Ignore if the action is missing or inaccessible


    @staticmethod
    def disable_map_tips():
        """
        Disables the global Map Tips feature in QGIS.
        """
        from qgis.PyQt.QtCore import QSettings
        QSettings().setValue("qgis/enableMapTips", False)

        # Disable if the action is enabled
        try:
            if iface.actionMapTips().isChecked():
                iface.actionMapTips().trigger()
        except:
            pass  # Ignore if the action is missing or inaccessible