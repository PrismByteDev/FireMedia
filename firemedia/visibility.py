"""Whether a widget can actually be displayed by its compositor."""


def is_presented(widget):
    window=widget.window();handle=window.windowHandle()
    # Wayland may report WindowNoState for an unexposed, minimized window.
    return widget.isVisible() and not window.isMinimized() and (handle is None or handle.isExposed())
