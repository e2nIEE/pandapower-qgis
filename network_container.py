import sys
from typing import Dict

if 'network_container' not in sys.modules:
    class NetworkContainer:
        _networks = {}  # network data
        _listeners = {}
        _initialized = False

        @classmethod
        def register_network(cls, uri, network_data):
            """
            Register network data for a URI and notify all listeners.
            Args:
                uri: Unique identifier for the network
                network_data: Dictionary containing network information
            """
            if not cls._initialized:
                cls._initialized = True
            # Save data
            cls._networks[uri] = dict(network_data)
            cls._notify_all_listeners(uri, network_data)


        @classmethod
        def get_network(cls, uri):
            """
            Retrieve the registered network data for a given URI.
            Args:
                uri: Unique identifier for the network
            Returns:
                dict or None: Network data if found, None otherwise
            """
            if uri in cls._networks:
                return cls._networks[uri]
            return None


        @classmethod
        def add_listener(cls, uri, listener):
            """
            Add a listener for network updates on a specific URI.
            Args:
                uri: Unique identifier for the network
                listener: Object that will receive network update notifications
            """
            if uri not in cls._listeners:
                cls._listeners[uri] = []
            cls._listeners[uri].append(listener)


        @classmethod
        def remove_listener(cls, uri, listener):
            """
            Remove a listener from a specific URI.
            Args:
                uri: Unique identifier for the network
                listener: Object to remove from notifications
            """
            if uri in cls._listeners:
                if listener in cls._listeners[uri]:
                    cls._listeners[uri].remove(listener)


        @classmethod
        def _notify_all_listeners(cls, uri, network_data):
            """
            Notify all listeners for a URI about network data changes
            to avoid concurrency issues.
            Args:
                uri: Unique identifier for the network
                network_data: Dictionary containing updated network information
            """
            if uri in cls._listeners:
                listeners_count = len(cls._listeners[uri])

                # Copy the listener list to prevent modifications during iteration
                listeners_copy = cls._listeners[uri].copy()

                success_count = 0
                for i, listener in enumerate(listeners_copy):
                    try:
                        if hasattr(listener, 'isValid') and not listener.isValid():
                            print(f"Skip invalid listeners: {listener.__class__.__name__}")
                            continue

                        # Call the actual update
                        listener.on_update_changed_network(network_data)
                        success_count += 1

                    except Exception as e:
                        print(f"❌ Failed to deliver notification to the listener {listener.__class__.__name__}: {str(e)}")
                        # Individual listener failures do not stop the entire process
                        continue
            else:
                print(f"NetworkContainer: No registered listeners for {uri}.")


        @classmethod
        def cleanup_invalid_listeners(cls):
            """
            Remove invalid listeners from all URIs and clean up empty listener lists.
            """
            for uri in list(cls._listeners.keys()):
                if uri in cls._listeners:
                    valid_listeners = []
                    for listener in cls._listeners[uri]:
                        if hasattr(listener, 'isValid') and listener.isValid():
                            valid_listeners.append(listener)
                        else:
                            print(f"Clean up invalid listeners: {listener.__class__.__name__}")

                    cls._listeners[uri] = valid_listeners
                    if not valid_listeners:
                        print(f"Remove empty listener lists: {uri}")
                        del cls._listeners[uri]


        @classmethod
        def clear(cls):
            """Remove all registered network data from the container."""
            cls._networks.clear()

        @classmethod
        def is_initialized(cls):
            """Check if the container has been initialized."""
            return cls._initialized

    # Register in the module registry
    sys.modules['network_container'] = NetworkContainer
else:
    # Use an existing class
    NetworkContainer = sys.modules['network_container']