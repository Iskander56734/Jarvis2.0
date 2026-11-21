"""
Jarvis — ПРИЛОЖЕНИЕ ДЛЯ ТЕЛЕФОНА (Android, сборка через Buildozer).
ИИ на телефоне не запускается: все вопросы уходят на твой компьютер
(jarvis_server.py), а ответ приходит обратно потоком.
"""
import os
import json
import base64
import re
import socket
import ssl
import threading
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from kivy.utils import platform
from kivy.config import Config
Config.set("input", "mouse", "mouse,disable_multitouch")
if platform != "android":                      # размер окна только для теста на ПК
    Config.set("graphics", "width", "420")
    Config.set("graphics", "height", "820")
    Config.set("kivy", "exit_on_escape", "0")

from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.properties import StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

# =====================================================================
MAX_HISTORY_MESSAGES = 8
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
DEFAULT_PORT = 8765

BG = (0.129, 0.129, 0.129, 1)
SURFACE = (0.184, 0.184, 0.184, 1)
SURFACE_HOVER = (0.25, 0.25, 0.25, 1)
TEXT = (0.93, 0.93, 0.93, 1)
MUTED = (0.62, 0.62, 0.62, 1)
ACCENT = (0.063, 0.639, 0.498, 1)
WARN = (0.95, 0.70, 0.2, 1)
ERR = (0.95, 0.38, 0.38, 1)


def measure_width(text, font_size):
    try:
        cl = CoreLabel(text=text or " ", font_size=font_size)
        cl.refresh()
        return cl.texture.width if cl.texture else 0
    except Exception:
        return 0


def bind_wrap(label):
    label.bind(size=lambda inst, val: setattr(inst, "text_size", val))


# =====================================================================
# ВИДЖЕТЫ
# =====================================================================
class IconButton(ButtonBehavior, Widget):
    kind = StringProperty("send")   # send | stop | plus | close | new | menu

    def __init__(self, **kw):
        super().__init__(**kw)
        self.bind(pos=self._draw, size=self._draw, state=self._draw,
                  disabled=self._draw, kind=self._draw)
        self._draw()

    def _draw(self, *args):
        self.canvas.clear()
        cx, cy = self.center
        r = min(self.width, self.height) / 2
        down = self.state == "down"
        lw = dp(1.8)
        with self.canvas:
            if self.kind in ("send", "stop"):
                if self.disabled:
                    Color(0.30, 0.30, 0.30, 1)
                else:
                    Color(1, 1, 1, 0.8 if down else 1)
                Ellipse(pos=(cx - r, cy - r), size=(2 * r, 2 * r))
                Color(0.13, 0.13, 0.13, 1) if not self.disabled else Color(0.5, 0.5, 0.5, 1)
                s = r * 0.42
                if self.kind == "send":
                    Line(points=[cx, cy - s, cx, cy + s], width=lw, cap="round")
                    Line(points=[cx - s * 0.85, cy + s * 0.1, cx, cy + s, cx + s * 0.85, cy + s * 0.1],
                         width=lw, cap="round", joint="round")
                else:
                    RoundedRectangle(pos=(cx - s * 0.8, cy - s * 0.8),
                                     size=(s * 1.6, s * 1.6), radius=[dp(2)])
            else:
                if down and not self.disabled:
                    Color(1, 1, 1, 0.12)
                    Ellipse(pos=(cx - r, cy - r), size=(2 * r, 2 * r))
                Color(1, 1, 1, 0.3 if self.disabled else 0.85)
                if self.kind == "plus":
                    s = r * 0.45
                    Line(points=[cx - s, cy, cx + s, cy], width=lw, cap="round")
                    Line(points=[cx, cy - s, cx, cy + s], width=lw, cap="round")
                elif self.kind == "close":
                    s = r * 0.35
                    Line(points=[cx - s, cy - s, cx + s, cy + s], width=lw, cap="round")
                    Line(points=[cx - s, cy + s, cx + s, cy - s], width=lw, cap="round")
                elif self.kind == "menu":
                    s = r * 0.5
                    for dy in (-s * 0.7, 0, s * 0.7):
                        Line(points=[cx - s, cy + dy, cx + s, cy + dy], width=lw, cap="round")
                elif self.kind == "new":
                    s = r * 0.5
                    Line(rounded_rectangle=(cx - s, cy - s, 2 * s, 2 * s, dp(5)), width=lw)
                    p = s * 0.5
                    Line(points=[cx - p, cy, cx + p, cy], width=lw, cap="round")
                    Line(points=[cx, cy - p, cx, cy + p], width=lw, cap="round")


class PillButton(ButtonBehavior, Label):
    def __init__(self, **kw):
        kw.setdefault("color", TEXT)
        kw.setdefault("font_size", sp(14))
        super().__init__(**kw)
        with self.canvas.before:
            self._c = Color(*SURFACE_HOVER)
            self._r = RoundedRectangle(radius=[dp(17)])
        self.bind(pos=self._upd, size=self._upd, state=self._upd, disabled=self._upd)
        self._upd()

    def _upd(self, *args):
        self._r.pos = self.pos
        self._r.size = self.size
        self._c.rgba = (0.33, 0.33, 0.33, 1) if self.state == "down" else SURFACE_HOVER
        self.opacity = 0.4 if self.disabled else 1


class StatusDot(Widget):
    def __init__(self, **kw):
        super().__init__(size_hint=(None, None), size=(dp(10), dp(10)), **kw)
        with self.canvas:
            self._c = Color(*WARN)
            self._e = Ellipse()
        self.bind(pos=self._upd, size=self._upd)

    def _upd(self, *args):
        self._e.pos = self.pos
        self._e.size = self.size

    def set_color(self, rgba):
        self._c.rgba = rgba


class Avatar(Label):
    def __init__(self, **kw):
        super().__init__(text="J", bold=True, font_size=sp(15), color=(1, 1, 1, 1),
                         size_hint=(None, None), size=(dp(32), dp(32)), **kw)
        with self.canvas.before:
            Color(*ACCENT)
            self._e = Ellipse()
        self.bind(pos=self._upd, size=self._upd)

    def _upd(self, *args):
        self._e.pos = self.pos
        self._e.size = self.size


class ChatInput(TextInput):
    """На ПК: Enter — отправить, Shift+Enter — новая строка. На телефоне — кнопка отправки."""

    def __init__(self, on_submit=None, **kw):
        super().__init__(**kw)
        self.on_submit = on_submit

    def keyboard_on_key_down(self, window, keycode, text, modifiers):
        if (platform != "android" and keycode[1] in ("enter", "numpadenter")
                and "shift" not in modifiers):
            if self.on_submit:
                self.on_submit()
            return True
        return super().keyboard_on_key_down(window, keycode, text, modifiers)


class Message(BoxLayout):
    def __init__(self, role, text="", style="normal", **kw):
        super().__init__(orientation="horizontal", size_hint_y=None,
                         spacing=dp(12), height=dp(60), **kw)
        self.role = role
        self._text = ""

        if role == "user":
            self.add_widget(Widget())
            self.bubble = BoxLayout(size_hint=(None, None), padding=[dp(16), dp(10)],
                                    pos_hint={"top": 1})
            with self.bubble.canvas.before:
                Color(*SURFACE)
                self._bg = RoundedRectangle(radius=[dp(20)])
            self.bubble.bind(pos=self._upd_bg, size=self._upd_bg)
            self.label = Label(size_hint=(None, None), halign="left", valign="top",
                               color=TEXT, font_size=sp(16))
            self.bubble.add_widget(self.label)
            self.add_widget(self.bubble)
        else:
            self.add_widget(Avatar(pos_hint={"top": 1}))
            self.label = Label(size_hint_y=None, halign="left", valign="top",
                               color=TEXT, font_size=sp(16))
            self.add_widget(self.label)

        self.label.bind(texture_size=self._relayout)
        self.bind(width=self._relayout)
        if role != "user":
            self.label.bind(width=self._relayout)
        self.set_text(text, style)

    def _upd_bg(self, *args):
        self._bg.pos = self.bubble.pos
        self._bg.size = self.bubble.size

    def set_text(self, text, style="normal"):
        self._text = text
        self.label.text = text
        self.label.color = {"normal": TEXT, "muted": MUTED, "error": ERR}.get(style, TEXT)
        self._relayout()

    def _relayout(self, *args):
        side = max(dp(14), (self.width - dp(780)) / 2)
        vpad = dp(10)
        self.padding = [side, vpad, side, vpad]
        inner = max(dp(120), self.width - 2 * side)
        line_h = sp(16) * 1.3

        if self.role == "user":
            max_text = inner * 0.82 - dp(32)
            natural = measure_width(self._text, sp(16))
            tw = max(dp(10), min(natural + dp(2), max_text))
            self.label.text_size = (tw, None)
            self.label.size = (tw, max(self.label.texture_size[1], line_h))
            self.bubble.size = (tw + dp(32), self.label.height + dp(20))
            self.height = self.bubble.height + 2 * vpad
        else:
            if self.label.width > dp(10):
                self.label.text_size = (self.label.width, None)
            self.label.height = max(self.label.texture_size[1], dp(32))
            self.height = self.label.height + 2 * vpad


class Welcome(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", size_hint_y=None, height=dp(260),
                         padding=[dp(20), dp(80), dp(20), 0], spacing=dp(10), **kw)
        self.add_widget(Label(text="Чем могу помочь?", bold=True, font_size=sp(26),
                              color=TEXT, size_hint_y=None, height=dp(46)))
        sub = Label(text="Отвечает ИИ на твоём компьютере.\nМожно прикрепить фото.",
                    font_size=sp(14), color=MUTED, halign="center", valign="top")
        bind_wrap(sub)
        self.add_widget(sub)


# =====================================================================
# ПРИЛОЖЕНИЕ
# =====================================================================
class JarvisApp(App):
    def build(self):
        self.title = "Jarvis"
        Window.clearcolor = BG
        if platform == "android":
            Window.softinput_mode = "resize"     # клавиатура не перекрывает поле ввода
            try:
                from android.permissions import request_permissions
                request_permissions(["android.permission.READ_EXTERNAL_STORAGE",
                                     "android.permission.READ_MEDIA_IMAGES"])
            except Exception as e:
                print("permissions:", e)

        self.cfg_path = os.path.join(self.user_data_dir, "config.json")
        self.cfg = self._load_cfg()

        self.generating = False
        self.image_path = None
        self.history = []
        self.welcome = None
        self._sheet = None
        self._pinging = False
        self._gen_started = 0.0
        self._first_chunk_at = None
        self.stop_event = threading.Event()
        self._latest = (None, "")
        self._flush = Clock.create_trigger(self._do_flush)

        root = BoxLayout(orientation="vertical")
        root.add_widget(self._make_header())

        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(4),
                                 bar_color=(1, 1, 1, 0.25), bar_inactive_color=(1, 1, 1, 0.08),
                                 scroll_type=["bars", "content"])
        self.msgs = BoxLayout(orientation="vertical", size_hint_y=None,
                              padding=[0, dp(8), 0, dp(8)])
        self.msgs.bind(minimum_height=self.msgs.setter("height"))
        self.scroll.add_widget(self.msgs)
        root.add_widget(self.scroll)
        root.add_widget(self._make_input_area())

        Window.bind(on_drop_file=self._on_drop, on_keyboard=self._on_keyboard)
        self.show_welcome()
        self.refresh_send()

        Clock.schedule_interval(lambda dt: self.check_server(), 20)
        Clock.schedule_once(self._first_start, 0.5)
        return root

    def on_pause(self):
        return True       # Android: не убивать приложение при сворачивании

    def _first_start(self, dt):
        if not self.base_url():
            self.open_settings()
        else:
            self.check_server()

    def _on_keyboard(self, window, key, *args):
        if key == 27 and self._sheet is not None:     # кнопка «назад» закрывает окно настроек
            self._sheet.dismiss()
            return True
        return False

    # ------------------------------------------------------ настройки
    def _load_cfg(self):
        try:
            with open(self.cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {"host": str(data.get("host", "")), "token": str(data.get("token", ""))}
        except Exception:
            return {"host": "", "token": ""}

    def _save_cfg(self):
        try:
            os.makedirs(self.user_data_dir, exist_ok=True)
            with open(self.cfg_path, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f)
        except Exception as e:
            print("save cfg:", e)

    def base_url(self):
        """IP:порт -> http (домашняя сеть), любое имя/ссылка -> https (интернет)."""
        host = self.cfg.get("host", "").strip().strip("/")
        if not host:
            return None
        low = host.lower()
        if low.startswith(("http://", "https://")):
            return host
        if re.match(r"^[\d.]+(:\d+)?$", host) or low.startswith("localhost"):
            if ":" not in host:
                host += f":{DEFAULT_PORT}"
            return "http://" + host
        return "https://" + host

    def _make_sheet(self, size_hint, height=None):
        sheet = ModalView(size_hint=size_hint, auto_dismiss=True, background="",
                          background_color=(0, 0, 0, 0), overlay_color=(0, 0, 0, 0.6))
        if height is not None:
            sheet.height = height
        content = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(8))
        with content.canvas.before:
            Color(*SURFACE)
            bg = RoundedRectangle(radius=[dp(20)])
        content.bind(pos=lambda i, v: setattr(bg, "pos", v),
                     size=lambda i, v: setattr(bg, "size", v))
        sheet.add_widget(content)
        sheet.bind(on_dismiss=lambda *a: setattr(self, "_sheet", None))
        self._sheet = sheet
        return sheet, content

    def _field_style(self):
        return dict(
            multiline=False, background_normal="", background_active="",
            background_color=(0.13, 0.13, 0.13, 1), foreground_color=TEXT,
            hint_text_color=(1, 1, 1, 0.35), cursor_color=(1, 1, 1, 1),
            selection_color=(0.063, 0.639, 0.498, 0.4),
            padding=[dp(12), dp(12), dp(12), dp(12)], font_size=sp(16),
            size_hint_y=None, height=dp(46), write_tab=False,
            use_bubble=False, use_handles=False)

    def _small_label(self, text):
        lb = Label(text=text, font_size=sp(13), color=MUTED, halign="left", valign="bottom",
                   size_hint_y=None, height=dp(24))
        bind_wrap(lb)
        return lb

    def open_settings(self, *a):
        if self._sheet is not None:
            return
        sheet, box = self._make_sheet(size_hint=(0.94, None), height=dp(360))
        title = Label(text="Подключение к компьютеру", bold=True, font_size=sp(18), color=TEXT,
                      size_hint_y=None, height=dp(34), halign="left", valign="middle")
        bind_wrap(title)
        box.add_widget(title)
        box.add_widget(self._small_label("Адрес ПК (IP:порт или https-ссылка)"))
        host = TextInput(text=self.cfg.get("host", ""), hint_text="192.168.0.10:8765",
                         **self._field_style())
        box.add_widget(host)
        box.add_widget(self._small_label("Токен (тоже покажет сервер)"))
        token = TextInput(text=self.cfg.get("token", ""), hint_text="например a1b2c3d4",
                          **self._field_style())
        box.add_widget(token)
        box.add_widget(Widget())

        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
        cancel = PillButton(text="Отмена")
        save = PillButton(text="Сохранить", bold=True)
        row.add_widget(cancel)
        row.add_widget(save)
        box.add_widget(row)

        def do_save(*_):
            self.cfg["host"] = host.text.strip()
            self.cfg["token"] = token.text.strip()
            self._save_cfg()
            sheet.dismiss()
            self.refresh_send()
            self.check_server()

        cancel.bind(on_release=lambda *_: sheet.dismiss())
        save.bind(on_release=do_save)
        sheet.open()

    # ------------------------------------------------------------ UI
    def _make_header(self):
        header = BoxLayout(size_hint_y=None, height=dp(56), padding=[dp(14), dp(8)], spacing=dp(8))
        with header.canvas.before:
            Color(*BG)
            bg = Rectangle()
            Color(1, 1, 1, 0.08)
            line = Rectangle()

        def upd(*a):
            bg.pos, bg.size = header.pos, header.size
            line.pos, line.size = header.pos, (header.width, 1)
        header.bind(pos=upd, size=upd)

        header.add_widget(Label(text="Jarvis", bold=True, font_size=sp(18), color=TEXT,
                                size_hint_x=None, width=dp(64)))
        self.status_dot = StatusDot(pos_hint={"center_y": 0.5})
        header.add_widget(self.status_dot)
        self.status_label = Label(text="Нет подключения", font_size=sp(12), color=MUTED,
                                  halign="left", valign="middle",
                                  shorten=True, shorten_from="right")
        bind_wrap(self.status_label)
        header.add_widget(self.status_label)

        self.btn_new = IconButton(kind="new", size_hint=(None, None), size=(dp(38), dp(38)),
                                  pos_hint={"center_y": 0.5})
        self.btn_new.bind(on_release=lambda *a: self.new_chat())
        header.add_widget(self.btn_new)
        btn_menu = IconButton(kind="menu", size_hint=(None, None), size=(dp(38), dp(38)),
                              pos_hint={"center_y": 0.5})
        btn_menu.bind(on_release=self.open_settings)
        header.add_widget(btn_menu)
        return header

    def _make_input_area(self):
        self.input_wrap = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4),
                                    padding=[dp(10), dp(6), dp(10), dp(10)])
        self.pill = BoxLayout(orientation="vertical", size_hint_y=None, padding=[dp(8), dp(6)])
        with self.pill.canvas.before:
            Color(*SURFACE)
            self._pill_bg = RoundedRectangle(radius=[dp(24)])
        self.pill.bind(pos=self._upd_pill, size=self._upd_pill)

        self.chip = BoxLayout(size_hint_y=None, height=0, opacity=0, spacing=dp(6),
                              padding=[dp(8), 0])
        self.chip_label = Label(text="", font_size=sp(14), color=MUTED, halign="left",
                                valign="middle", shorten=True, shorten_from="right")
        bind_wrap(self.chip_label)
        self.chip.add_widget(self.chip_label)
        chip_close = IconButton(kind="close", size_hint=(None, None), size=(dp(24), dp(24)),
                                pos_hint={"center_y": 0.5})
        chip_close.bind(on_release=lambda *a: self.clear_attachment())
        self.chip.add_widget(chip_close)
        self.chip.bind(height=self._relayout_input)

        self.row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        self.btn_attach = IconButton(kind="plus", size_hint=(None, None), size=(dp(36), dp(36)))
        self.btn_attach.bind(on_release=self.open_file_dialog)
        self.input = ChatInput(
            on_submit=self.submit, multiline=True,
            hint_text="Сообщение Джарвису…",
            background_normal="", background_active="", background_disabled_normal="",
            background_color=(0, 0, 0, 0), foreground_color=TEXT,
            hint_text_color=(1, 1, 1, 0.4), cursor_color=(1, 1, 1, 1),
            selection_color=(0.063, 0.639, 0.498, 0.4),
            padding=[dp(8), dp(10), dp(8), dp(10)], font_size=sp(16),
            size_hint_y=None, height=dp(40), write_tab=False,
            use_bubble=False, use_handles=False,
        )
        self.input.bind(minimum_height=self._on_input_min_h,
                        text=lambda *a: self.refresh_send(), height=self._relayout_input)
        self.btn_send = IconButton(kind="send", size_hint=(None, None), size=(dp(36), dp(36)))
        self.btn_send.bind(on_release=self.on_send_pressed)

        self.row.add_widget(self.btn_attach)
        self.row.add_widget(self.input)
        self.row.add_widget(self.btn_send)
        self.pill.add_widget(self.chip)
        self.pill.add_widget(self.row)
        self.input_wrap.add_widget(self.pill)
        self._relayout_input()
        return self.input_wrap

    def _upd_pill(self, *a):
        self._pill_bg.pos = self.pill.pos
        self._pill_bg.size = self.pill.size

    def _on_input_min_h(self, inst, val):
        inst.height = max(dp(40), min(val, dp(130)))

    def _relayout_input(self, *a):
        self.row.height = self.input.height
        self.pill.height = self.chip.height + self.row.height + dp(12)
        self.input_wrap.height = self.pill.height + dp(16)

    def show_welcome(self):
        self.welcome = Welcome()
        self.msgs.add_widget(self.welcome)

    def refresh_send(self):
        self.btn_send.kind = "stop" if self.generating else "send"
        has_content = bool(self.input.text.strip()) or bool(self.image_path)
        configured = bool(self.base_url())
        self.btn_send.disabled = not (self.generating or (configured and has_content))
        self.btn_attach.disabled = self.generating
        self.btn_new.disabled = self.generating

    # ------------------------------------------------------- вложения
    def open_file_dialog(self, *a):
        if self._sheet is not None:
            return
        start = os.path.expanduser("~")
        if platform == "android":
            for p in ("/storage/emulated/0/DCIM/Camera", "/storage/emulated/0/DCIM",
                      "/storage/emulated/0/Pictures", "/storage/emulated/0"):
                if os.path.isdir(p):
                    start = p
                    break
        sheet, box = self._make_sheet(size_hint=(0.96, 0.88))
        chooser = FileChooserListView(
            path=start, size_hint=(1, 1),
            filters=[lambda folder, name: name.lower().endswith(IMAGE_EXT)])
        box.add_widget(chooser)
        hint = Label(text="Список пуст? Разреши приложению доступ к фото в настройках телефона.",
                     font_size=sp(12), color=MUTED, size_hint_y=None, height=dp(30),
                     halign="center", valign="middle")
        bind_wrap(hint)
        box.add_widget(hint)

        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
        cancel = PillButton(text="Отмена")
        choose = PillButton(text="Выбрать", bold=True)
        row.add_widget(cancel)
        row.add_widget(choose)
        box.add_widget(row)

        def pick(selection):
            if selection:
                path = selection[0]
                if os.path.isfile(path) and path.lower().endswith(IMAGE_EXT):
                    sheet.dismiss()
                    self.attach(path)

        cancel.bind(on_release=lambda *_: sheet.dismiss())
        choose.bind(on_release=lambda *_: pick(chooser.selection))
        chooser.bind(on_submit=lambda inst, sel, touch: pick(sel))
        sheet.open()

    def _on_drop(self, window, filename, *args):
        if isinstance(filename, bytes):
            filename = filename.decode("utf-8", errors="ignore")
        if not self.generating and filename.lower().endswith(IMAGE_EXT):
            self.attach(filename)

    def attach(self, path):
        if not os.path.isfile(path):
            return
        self.image_path = path
        self.chip_label.text = "Фото: " + os.path.basename(path)
        self.chip.height = dp(30)
        self.chip.opacity = 1
        self.refresh_send()

    def clear_attachment(self):
        self.image_path = None
        self.chip_label.text = ""
        self.chip.height = 0
        self.chip.opacity = 0
        self.refresh_send()

    # --------------------------------------------------------- чат
    def new_chat(self):
        if self.generating:
            return
        self.history = []
        self.msgs.clear_widgets()
        self.show_welcome()
        self.clear_attachment()

    def _to_bottom(self, *a):
        self.scroll.scroll_y = 0

    def _add_message(self, role, text, style="normal"):
        if self.welcome is not None and self.welcome.parent is not None:
            self.msgs.remove_widget(self.welcome)
            self.welcome = None
        msg = Message(role, text, style)
        self.msgs.add_widget(msg)
        Clock.schedule_once(self._to_bottom, 0.05)
        Clock.schedule_once(self._to_bottom, 0.25)
        return msg

    def on_send_pressed(self, *a):
        if self.generating:
            now = time.time()
            first = self._first_chunk_at
            # Игнорируем случайные касания сразу после отправки и после первого куска ответа
            if now - self._gen_started < 2.0 or (first is not None and now - first < 2.0):
                return
            self.stop_event.set()
            return
        self.submit()

    def submit(self):
        if self.generating:
            return
        if not self.base_url():
            self.open_settings()
            return
        text = self.input.text.strip()
        image_path = self.image_path
        if not text and not image_path:
            return
        if not text:
            text = "Опиши это изображение."

        shown = text
        if image_path:
            shown += "\n[Фото: " + os.path.basename(image_path) + "]"
        self.input.text = ""
        self.clear_attachment()

        self._add_message("user", shown)
        bubble = self._add_message("assistant", "Думаю…", "muted")

        self.stop_event.clear()
        self._first_chunk_at = None
        self._gen_started = time.time()
        self.generating = True
        self.refresh_send()
        threading.Thread(target=self._worker, args=(text, image_path, bubble), daemon=True).start()

    # ------------------------------------------------------- сеть
    def _request(self, path, payload=None, timeout=15):
        url = self.base_url() + path
        headers = {"X-Token": self.cfg.get("token", "")}
        if payload is not None:
            headers["Content-Type"] = "application/json"
            req = Request(url, data=json.dumps(payload).encode("utf-8"),
                          headers=headers, method="POST")
        else:
            req = Request(url, headers=headers)
        ctx = self._ssl_context() if url.startswith("https://") else None
        return urlopen(req, timeout=timeout, context=ctx)

    def _ssl_context(self):
        try:
            import certifi                    # на Android нужен свой набор сертификатов
            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            return ssl.create_default_context()

    def _set_status(self, text, color):
        def _do(dt):
            self.status_label.text = text
            self.status_dot.set_color(color)
        Clock.schedule_once(_do, 0)

    def check_server(self, *a):
        if self.generating or self._pinging:
            return
        if not self.base_url():
            self._set_status("Укажи адрес ПК в настройках", WARN)
            return
        self._pinging = True
        threading.Thread(target=self._ping_worker, daemon=True).start()

    def _ping_worker(self):
        try:
            with self._request("/ping", timeout=4) as r:
                info = json.loads(r.read().decode("utf-8"))
            self._set_status("ПК подключён · " + str(info.get("device", "")), ACCENT)
        except HTTPError as e:
            if e.code == 401:
                self._set_status("Неверный токен", ERR)
            else:
                self._set_status(f"Ошибка сервера ({e.code})", ERR)
        except Exception:
            self._set_status("Нет связи с ПК", ERR)
        finally:
            self._pinging = False

    def _do_flush(self, dt):
        bubble, reply = self._latest
        if bubble is None:
            return
        stick = self.scroll.scroll_y <= 0.05
        bubble.set_text(reply if reply else "Думаю…", "normal" if reply else "muted")
        if stick:
            Clock.schedule_once(self._to_bottom, 0.02)

    def _worker(self, text, image_path, bubble):
        reply = ""
        error = None
        resp = None
        try:
            payload = {"history": self.history[-MAX_HISTORY_MESSAGES:], "text": text, "image": None}
            if image_path:
                with open(image_path, "rb") as f:
                    payload["image"] = base64.b64encode(f.read()).decode("ascii")
            resp = self._request("/chat", payload, timeout=120)
            for raw in resp:
                if self.stop_event.is_set():
                    break
                line = raw.decode("utf-8").strip()
                if not line:
                    continue
                obj = json.loads(line)
                if "error" in obj:
                    raise RuntimeError(obj["error"])
                if "t" in obj:
                    if self._first_chunk_at is None:
                        self._first_chunk_at = time.time()
                    reply += obj["t"]
                    self._latest = (bubble, reply)
                    self._flush()
                if obj.get("done"):
                    break
        except HTTPError as e:
            if e.code == 401:
                error = "Неверный токен. Проверь настройки (≡)."
            elif e.code == 503:
                error = "ПК сейчас занят другим запросом. Попробуй через пару секунд."
            elif e.code == 413:
                error = "Фото слишком большое."
            else:
                error = f"Ошибка сервера ({e.code})."
        except (socket.timeout, OSError) as e:
            error = (f"Нет связи с ПК ({type(e).__name__}). "
                     "Проверь Wi-Fi, адрес и что jarvis_server.py запущен.")
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
        finally:
            if resp is not None:
                try:
                    resp.close()
                except Exception:
                    pass

        reply = reply.strip()
        if not error:
            if not reply:
                reply = "(пустой ответ)"
            user_hist = text + (" (к сообщению было приложено фото)" if image_path else "")
            self.history.append({"role": "user", "content": user_hist})
            self.history.append({"role": "assistant", "content": reply})
            self.history = self.history[-MAX_HISTORY_MESSAGES:]
        shown = reply
        if self.stop_event.is_set() and not error:
            shown = (reply + "\n\n" if reply else "") + "[остановлено]"
        Clock.schedule_once(lambda dt: self._finish(bubble, shown, error), 0)

    def _finish(self, bubble, reply, error):
        if error:
            bubble.set_text((reply + "\n\n" if reply else "") + error, "error")
        else:
            bubble.set_text(reply)
        self.generating = False
        self.refresh_send()
        Clock.schedule_once(self._to_bottom, 0.05)
        self.check_server()


if __name__ == "__main__":
    JarvisApp().run()
