import ast
import sys
import traceback
from typing import Dict, Any
from time import sleep

from qgis.core import QgsProject, QgsMessageLog, Qgis, QgsGraduatedSymbolRenderer, QgsSingleSymbolRenderer, QgsProviderRegistry
from qgis.utils import iface
from qgis.PyQt.QtCore import QThread, pyqtSignal
from qgis.PyQt.QtWidgets import QMessageBox

from .renderer_utils import create_power_renderer
from .network_session import NetworkSession


def run_session(parent, session, parameters):
    """
    Run a power flow on an open network, from calculation to post-processing.
    Args:
        parent: Parent interface object
        session (NetworkSession): The open network to calculate
        parameters (dict): Calculation settings
    Returns:
        tuple: (success, message) - overall workflow status
    """
    try:
        if session is None:
            message = "No pandapower network is open."
            show_error_message(parent, message)
            return False, message

        net = session.net
        if net is None:
            message = "Network object is not valid."
            show_error_message(parent, message)
            return False, message

        # Execute calculation. pandapower mutates the network in place, so the
        # results land directly on the object every layer of this file shares.
        success, result_message, updated_net = execute_calculation(net, parameters)
        if not success:
            show_error_message(parent, f"Calculation failed: {result_message}")
            return False, result_message

        try:
            # Keep the session pointing at the calculated network. This is
            # normally the very same object, but an implementation that
            # returns a new one is handled correctly too.
            if updated_net is not None:
                session.net = updated_net
            session.mark_dirty()
            # Post-process calculation (update results and colors)
            post_process_results(parent, session, parameters)
        except Exception:
            import traceback
            traceback.print_exc()
            # Treat as successful calculation even if post-processing fails

        show_success_message(parent, "Calculation completed successfully!",
                             result_message)
        return True, ""

    except Exception as e:
        message = f"Unexpected error occurred: {str(e)}"
        import traceback
        traceback.print_exc()
        show_error_message(parent, message)
        return False, message


def run_network(parent, uri, parameters):
    """
    Deprecated: run a power flow addressed by layer URI.
    Kept so any external caller keeps working; prefer run_session().
    Args:
        parent: Parent interface object
        uri: Network identifier
        parameters (dict): Calculation settings
    Returns:
        tuple: (success, message) - overall workflow status
    """
    metadata_provider = QgsProviderRegistry.instance().providerMetadata(
        "PandapowerProvider")
    file_path = metadata_provider.decodeUri(uri).get('path')
    return run_session(parent, NetworkSession.get(file_path), parameters)


def execute_calculation(net, parameters):
    """
    Parse parameters and route calculation to appropriate network type.
    Args:
        net: Network object (pandapower or pandapipes)
        parameters (dict): Raw calculation settings
    Returns:
        tuple: (success, message, updated_network) - calculation results
    """
    try:
        # Get the user-selected execution function
        run_function_name = parameters.get('run_function', 'run')

        # Process user-entered parameter string
        kwargs_string = parameters.get('kwargs_string', '').strip()
        kwargs_dict = {}
        if kwargs_string:
            kwargs_dict = parse_kwargs_string(kwargs_string)

        # Add default parameters if needed
        if 'init' in parameters and parameters['init'] != 'auto':
            kwargs_dict['init'] = parameters['init']

        # Select the appropriate library based on the network type
        network_type = parameters.get('network_type', 'power')
        if network_type == 'power':
            return execute_power_calculation(net, run_function_name, kwargs_dict)
        elif network_type == 'pipes':
            return execute_pipes_calculation(net, run_function_name, kwargs_dict)
        else:
            return False, f"Unsupported network type: {network_type}"

    except Exception as e:
        error_message = f"Error during computation: {str(e)}"
        traceback.print_exc()
        return False, error_message


def execute_power_calculation(net, function_name, kwargs_dict):
    """
    Execute pandapower calculation and validate results.
    Args:
        net: pandapower network object
        function_name (str): Calculation function ('runpp', 'runopp', etc.)
        kwargs_dict (dict): Parsed calculation parameters
    Returns:
        tuple: (success, message, network) - calculation outcome with safety checks
    """
    try:
        import pandapower as pp
        import numpy as np
        import pandas as pd

        function_map = {
            'run': pp.runpp,
            'runpp': pp.runpp,
            'rundcpp': pp.rundcpp,
            'runopp': pp.runopp,
        }

        if function_name not in function_map:
            available_functions = list(function_map.keys())
            return False, f"Unsupported function: {function_name}", None

        run_function = function_map[function_name]

        # Execute calculation
        try:
            result = run_function(net, **kwargs_dict)
        except Exception as e:
            return False, f"pandapower calculation error: {e}", None

        # Check if calculation results exist
        try:
            has_res_bus = hasattr(net, 'res_bus') and not net.res_bus.empty
            has_res_line = hasattr(net, 'res_line') and not net.res_line.empty
        except Exception as e:
            return False, f"Calculation result verification error: {e}", None

        result_message = generate_power_result_message(net, function_name)
        return True, result_message, net

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, f"Power network calculation error: {str(e)}", None


def _parse_call_kwargs(kwargs_string):
    """
    Parse a "key1='value1', key2=2" argument list into a dictionary.

    The string is parsed as the keyword arguments of a call expression and each
    value is read with ast.literal_eval, so only literals are accepted. No user
    input is ever evaluated as code.

    Args:
        kwargs_string (str): Argument list without the surrounding parentheses.
    Returns:
        dict: Parsed parameter dictionary.
    Raises:
        ValueError: If the string is not a plain list of keyword arguments with
            literal values.
    """
    call = ast.parse(f"f({kwargs_string})", mode='eval').body
    if not isinstance(call, ast.Call) or call.args:
        raise ValueError("only keyword arguments with literal values are supported")

    parsed = {}
    for keyword in call.keywords:
        if keyword.arg is None:  # **kwargs unpacking
            raise ValueError("** unpacking is not supported")
        parsed[keyword.arg] = ast.literal_eval(keyword.value)
    return parsed


def parse_kwargs_string(kwargs_string):
    """
    Parse the parameter string entered by the user.
    Example: "algorithm='nr', max_iteration=10" -> {'algorithm': 'nr', 'max_iteration': 10}
    Args:
        kwargs_string (str): User input string
    Returns:
        dict: Parsed parameter dictionary
    """
    kwargs_dict = {}
    if not kwargs_string:
        return kwargs_dict
    try:
        # Method 1: Simple parsing (key=value format)
        if '=' in kwargs_string and not kwargs_string.startswith('{'):
            # Handle "key1=value1, key2=value2" format string
            pairs = kwargs_string.split(',')
            for pair in pairs:
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    key = key.strip()
                    value = value.strip()

                    # Auto-detect value type
                    try:
                        # Remove string quotes
                        if (value.startswith('"') and value.endswith('"')) or \
                                (value.startswith("'") and value.endswith("'")):
                            kwargs_dict[key] = value[1:-1]
                        # Try number conversion
                        elif value.isdigit():
                            kwargs_dict[key] = int(value)
                        elif value.replace('.', '', 1).isdigit():
                            kwargs_dict[key] = float(value)
                        # Handle boolean values
                        elif value.lower() in ['true', 'false']:
                            kwargs_dict[key] = value.lower() == 'true'
                        else:
                            kwargs_dict[key] = value
                    except (ValueError, TypeError):
                        kwargs_dict[key] = value

        # Method 2: Dictionary format parsing
        elif kwargs_string.startswith('{') and kwargs_string.endswith('}'):
            # Handle "{'key1': 'value1', 'key2': value2}" format string
            kwargs_dict = ast.literal_eval(kwargs_string)

        # Method 3: Python expression parsing
        else:
            # Convert "key1='value1', key2=value2" format to dictionary.
            # Parsed as a literal-only AST -- no evaluation of user input.
            kwargs_dict = _parse_call_kwargs(kwargs_string)

        return kwargs_dict

    except Exception as e:
        QgsMessageLog.logMessage(
            f"Parameter parsing failed: {str(e)} | Original: {kwargs_string}",
            "Pandapower",
            Qgis.Warning
        )
        return {}   #todo: don't run calculation if parsing failed


def generate_power_result_message(net, function_name):
    """Generate result message"""
    try:
        message_parts = [
            f"⚡ Power network calculation completed ({function_name})",
            f"📊 Bus count: {len(net.bus)}",
            f"📊 Line count: {len(net.line)}",
        ]
        # Show additional information only when result data exists
        if hasattr(net, 'res_bus') and not net.res_bus.empty:
            # Safely calculate average
            if 'vm_pu' in net.res_bus.columns:
                valid_voltage = net.res_bus['vm_pu'].dropna()
                if len(valid_voltage) > 0:
                    avg_voltage = valid_voltage.mean()
                    message_parts.append(f"📈 Average voltage: {avg_voltage:.3f} p.u.")
        result_message = "\n".join(message_parts)
        return result_message
    except Exception as e:
        return f"Calculation completed (message generation error: {str(e)})"


def post_process_results(parent, session, parameters):
    """
    Perform post-calculation cleanup tasks.
    - Refresh every layer of the calculated network
    - Update layer colors if needed
    - Handle result display options
    Args:
        parent: Parent object
        session (NetworkSession): Session holding the calculated network
        parameters (dict): User setting parameters
    """
    try:
        # Every layer of this file shares the session's network object, so the
        # results are already visible to them. They only need to rebuild their
        # cached dataframes and repaint.
        session.notify_changed()

        # Find the layers backed by this session among the open QGIS layers
        layers = QgsProject.instance().mapLayers()
        target_layers = []
        current_renderers = []

        for layer_id, layer in layers.items():
            if (hasattr(layer, 'dataProvider') and
                    layer.dataProvider().name() == "PandapowerProvider"):
                if getattr(layer.dataProvider(), 'session', None) is session:
                    target_layers.append(layer)
                    current_renderers.append(layer.renderer())

        if not target_layers:
            print("⚠️ No layers found for the calculated network.")
            return

        # First assume same renderer
        if isinstance(current_renderers[0], QgsGraduatedSymbolRenderer):
            for i, layer in enumerate(target_layers):
                layer.triggerRepaint()

        # If it was single renderer originally, apply new graduated renderer
        elif isinstance(current_renderers[0], QgsSingleSymbolRenderer):
            for layer in target_layers:
                # Build a fresh renderer per layer: a renderer instance must not
                # be shared between layers, since each layer takes ownership.
                bus_renderer, line_renderer = create_power_renderer()
                network_type = layer.dataProvider().network_type
                if network_type == 'bus':
                    layer.setRenderer(bus_renderer)
                elif network_type == 'line':
                    layer.setRenderer(line_renderer)
                layer.triggerRepaint()

        # 3. Display results (if needed)
        if parameters.get('show_results', False):
            #print("📊 Display detailed results...")
            # This part can be implemented later
            pass

        # Other post-processing tasks
        try:
            # Memory cleanup
            import gc
            gc.collect()
        except Exception as misc_error:
            print(f"   ❌ Other post-processing failed: {str(misc_error)}")
            # This also doesn't halt the entire process

    except Exception as e:
        import traceback
        raise  # Propagate error to upper level


def execute_pipes_calculation(net, function_name, kwargs_dict):
    """
    Execute pipes network calculation.
    Args:
        net: pandapipes network object
        function_name (str): Function name to execute
        kwargs_dict (dict): Parameters dictionary
    Returns:
        tuple: (success, result_message)
    """
    try:
        import pandapipes as pp

        function_map = {
            'run': pp.runpp,          # Basic fluid calculation
            'runpp': pp.runpp,        # Basic fluid calculation
            # Add other pipe functions as needed
        }
        if function_name not in function_map:
            available_functions = list(function_map.keys())
            return False, f"Unsupported pipe function: {function_name}. Available functions: {available_functions}"

        run_function = function_map[function_name]

        # Execute actual calculation
        result = run_function(net, **kwargs_dict)
        result_message = generate_pipes_result_message(net, function_name)

        return True, result_message, result

    except ImportError:
        return False, "Cannot import pandapipes library. Please check if the library is installed."
    except Exception as e:
        return False, f"Pipe network calculation error: {str(e)}"


def generate_pipes_result_message(net, function_name):
    """Generate result message for pipes network calculation."""
    try:
        message_parts = [
            f"🔧 Pipes network calculation completed ({function_name})",
            f"📊 Junction count: {len(net.junction)}",
            f"📊 Pipe count: {len(net.pipe)}",
        ]

        # Show additional information when result data exists
        if hasattr(net, 'res_junction') and not net.res_junction.empty:
            avg_pressure = net.res_junction['p_bar'].mean()
            message_parts.append(f"📈 Average pressure: {avg_pressure:.3f} bar")

        if hasattr(net, 'res_pipe') and not net.res_pipe.empty:
            max_velocity = net.res_pipe['v_mean_m_per_s'].max()
            message_parts.append(f"📈 Maximum velocity: {max_velocity:.2f} m/s")

        return "\n".join(message_parts)

    except Exception as e:
        return f"Calculation completed (error while generating result info: {str(e)})"


def show_success_message(parent, title, message):
    """Display the success message to the user."""
    try:
        if iface:
            iface.messageBar().pushMessage(
                title,
                message,
                level=Qgis.Success,
                duration=5
            )
        QgsMessageLog.logMessage(f"{title}: {message}", level=Qgis.Success)

    except Exception as e:
        print(f"⚠️ Error displaying the success message: {str(e)}")


def show_error_message(parent, message):
    """Display the error message to the user."""
    try:
        if iface:
            iface.messageBar().pushMessage(
                "RunPP error",
                message,
                level=Qgis.Critical,
                duration=10
            )
        QgsMessageLog.logMessage(f"RunPP error: {message}", level=Qgis.Critical)
    except Exception as e:
        print(f"⚠️ Error displaying the error message: {str(e)}")
