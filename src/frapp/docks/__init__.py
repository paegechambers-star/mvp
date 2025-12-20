class Dock:
    """Minimal Dock-Interface (Plugins)."""

    name: str = "dummy"

    def load(self):
        return True
