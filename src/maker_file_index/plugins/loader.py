from __future__ import annotations

from importlib.metadata import entry_points
from typing import List

from maker_file_index.plugins.base import FilePlugin


def load_plugins() -> List[FilePlugin]:
    eps = entry_points().select(group="maker_file_index.plugins")
    plugins: List[FilePlugin] = []
    for ep in eps:
        plugin_cls = ep.load()
        plugins.append(plugin_cls())
    return plugins
