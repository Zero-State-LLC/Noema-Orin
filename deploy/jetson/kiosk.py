#!/usr/bin/env python3
"""Full-screen Mission Control kiosk for the Orin's attached monitor (D-077).

Uses the WebKit2GTK already shipped with the L4T Ubuntu desktop image, so no
Chromium/snap install is needed. Retries until the dashboard is reachable and
reloads if the web process dies, so it can run unattended.
"""
import os
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gdk, GLib, Gtk, WebKit2  # noqa: E402

URL = os.environ.get("NOEMA_KIOSK_URL", "http://127.0.0.1:8787/?kiosk=1")
RETRY_S = 5


def main() -> int:
    win = Gtk.Window(title="NOEMA Mission Control")
    win.connect("destroy", Gtk.main_quit)
    view = WebKit2.WebView()
    # Single always-on page: no back/forward or page cache, which keeps WebKit's resident set flat.
    WebKit2.WebContext.get_default().set_cache_model(WebKit2.CacheModel.DOCUMENT_VIEWER)
    settings = view.get_settings()
    settings.set_enable_page_cache(False)
    settings.set_enable_developer_extras(False)
    settings.set_enable_write_console_messages_to_stdout(True)

    def retry():
        view.load_uri(URL)
        return False

    def on_fail(_v, _event, _uri, _err):
        GLib.timeout_add_seconds(RETRY_S, retry)
        return True  # suppress WebKit's error page

    def on_crash(_v, _reason):
        GLib.timeout_add_seconds(RETRY_S, retry)

    view.connect("load-failed", on_fail)
    view.connect("web-process-terminated", on_crash)
    win.add(view)
    # Bare xinit has no window manager, so fullscreen() is ignored: size to the monitor explicitly.
    screen = Gdk.Screen.get_default()
    sw, sh = screen.get_width(), screen.get_height()
    win.set_decorated(False)
    win.move(0, 0)
    win.set_default_size(sw, sh)
    win.resize(sw, sh)
    # The UI is laid out for about 1920 px wide. Scale up on 4K panels so text stays readable.
    zoom = float(os.environ.get("NOEMA_KIOSK_ZOOM", "0") or 0) or max(1.0, round(sw / 1920, 2))
    view.set_zoom_level(zoom)
    win.fullscreen()
    win.show_all()
    gdk_win = win.get_window()
    if gdk_win is not None:  # hide the pointer on the wall display
        gdk_win.set_cursor(Gdk.Cursor.new_for_display(Gdk.Display.get_default(), Gdk.CursorType.BLANK_CURSOR))
    view.load_uri(URL)
    # Periodic reload releases any slow JS/DOM growth from the always-on SSE feed (default 30 min).
    reload_s = int(os.environ.get("NOEMA_KIOSK_RELOAD_S", "1800") or 0)
    if reload_s > 0:
        GLib.timeout_add_seconds(reload_s, lambda: (view.load_uri(URL), True)[1])
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
