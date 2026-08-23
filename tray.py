import threading

_icon = None


def _make_icon():
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((5, 5, 59, 59), fill=(52, 36, 20, 255))
    d.ellipse((9, 9, 55, 55), fill=(86, 56, 28, 255))
    d.pieslice((11, 11, 53, 53), -90, 40, fill=(245, 185, 70, 255))
    d.pieslice((11, 11, 53, 53), 40, 80, fill=(210, 140, 50, 255))
    return img


def launch(ctx):
    import pystray

    menu = pystray.Menu(
        pystray.MenuItem(
            lambda item: "PieMesh node  %s" % ctx["id"](), None, enabled=False
        ),
        pystray.MenuItem(lambda item: ctx["status"](), None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Pause load generation",
            lambda *a: ctx["toggle_pause"](),
            checked=lambda item: ctx["is_paused"](),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Load limit",
            pystray.Menu(
                *[
                    pystray.MenuItem(
                        "%s (%d rps)" % (name, rps),
                        (lambda n: lambda *a: ctx["set_limit"](n))(name),
                        radio=True,
                    )
                    for name, rps in ctx["limits"]().items()
                ]
            ),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Start with Windows",
            lambda *a: ctx["toggle_autostart"](),
            checked=lambda item: ctx["autostart_on"](),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", lambda *a: ctx["exit"]()),
    )
    _icon = pystray.Icon("piemesh", _make_icon(), "PieMesh node", menu)
    threading.Thread(target=_icon.run, daemon=True).start()
    return _icon


def notify(title, msg):
    try:
        if _icon:
            _icon.notify(msg, title)
    except Exception:
        pass


def bye():
    try:
        if _icon:
            _icon.stop()
    except Exception:
        pass
