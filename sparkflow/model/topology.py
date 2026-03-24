from __future__ import annotations

from .connectivity import ConnectivityBuildOptions, build_connectivity, connected_components

TopologyBuildOptions = ConnectivityBuildOptions
build_topology = build_connectivity

__all__ = ['ConnectivityBuildOptions', 'TopologyBuildOptions', 'build_connectivity', 'build_topology', 'connected_components']
