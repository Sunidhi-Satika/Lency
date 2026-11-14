import sys
import os
import math
import time
import datetime
import threading
from dotenv import dotenv_values
from PyQt5.QtWidgets import (QApplication, QScrollArea, QMainWindow, QPushButton, QWidget, QVBoxLayout, QLabel,
                             QHBoxLayout, QStackedWidget, QShortcut, QSystemTrayIcon, QFrame, QLineEdit, QButtonGroup, QComboBox, QListView)
from PyQt5.QtCore import Qt, QSize, QTimer, QPointF, QRect, QEvent
from PyQt5.QtGui import (QIcon, QPainter, QColor, QFont, QFontMetrics,
                         QKeySequence, QRadialGradient, QPen, QBrush, QPainterPath, QImage, QPixmap)

try:
    from Frontend import Theme as T
    from Frontend.VoiceTyping import DictationTyper
    from Frontend.Tray import Tray
except ImportError:  # launched as `python Frontend/GUI.py`
    import Theme as T
    from VoiceTyping import DictationTyper
    from Tray import Tray
from Backend import State
from Backend.TextToSpeech import list_voices, set_voice, current_voice_key, TextToSpeech

env_vars = dotenv_values(".env")
Assistantname = env_vars.get("Assistantname") or "Lency"
Username = env_vars.get("Username") or "You"
GraphicsDirPath = os.path.join(os.getcwd(), "Frontend", "Graphics")


def GraphicsDirectoryPath(Filename):
    return os.path.join(GraphicsDirPath, Filename)


def AnswerModifier(Answer):
    return '\n'.join(line for line in Answer.split("\n") if line.strip())


def QueryModifier(Query):
    new_query = Query.strip()
    if not new_query:
        return new_query
    lowered = new_query.lower()
    query_words = lowered.split()
    question_words = ["how", "what", "who", "where", "when", "why", "which", "whose", "whom", "can you", "what's", "where's", "how's"]
    ender = "?" if any(word + " " in lowered for word in question_words) else "."
    if query_words[-1][-1] in ['.', '?', '!']:
        new_query = new_query[:-1] + ender
    else:
        new_query += ender
    return new_query[:1].upper() + new_query[1:]      # only the first letter: "C#", names and acronyms stay intact


# =========================================================================== living background
class AuroraBackground(QWidget):
    """The 'face' of Lency is the whole window: slow aurora light in One Dark colours plus a
    silk ribbon waveform. No central object; her mood shows in colour, speed and ribbon energy.

    Cheap by design: the aurora is rendered into a tiny 192x108 image and smoothly scaled up
    (soft blobs don't need resolution), at ~24 fps, and only while the window is visible.
    """

    PALETTES = {
        "idle":      (T.BLUE,    T.MAGENTA, T.CYAN),
        "listening": (T.MAGENTA, T.RED,     T.BLUE),
        "thinking":  (T.BLUE,    T.CYAN,    T.MAGENTA),
        "searching": (T.CYAN,    T.GREEN,   T.BLUE),
        "answering": (T.MAGENTA, T.ORANGE,  T.BLUE),
    }
    ENERGY = {"idle": 0.30, "listening": 0.60, "thinking": 0.75, "searching": 0.70, "answering": 1.0}
    RIBBON_AMP = {"idle": 7, "listening": 20, "thinking": 13, "searching": 13, "answering": 40}
    BW, BH = 192, 108

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buf = QImage(self.BW, self.BH, QImage.Format_ARGB32_Premultiplied)
        self._t0 = time.time()
        self._state = "idle"
        self._cur = [list(T.rgb(c)) for c in self.PALETTES["idle"]]
        self._energy = self.ENERGY["idle"]
        self._amp = self.RIBBON_AMP["idle"]
        self._ribbon_y = 0.74
        self._ribbon_target = 0.74
        self._bg = None          # cached aurora + vignette (QPixmap)
        self._bg_t = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(50)      # 20 fps is plenty for a slow silk ribbon
        self._timer.timeout.connect(self._on_tick)

    def showEvent(self, e):
        self._timer.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self._timer.stop()
        super().hideEvent(e)

    def set_ribbon(self, frac):
        self._ribbon_target = frac

    def set_state(self, text):
        t = (text or "").lower()
        if "listen" in t:
            s = "listening"
        elif "search" in t:
            s = "searching"
        elif "think" in t or "translat" in t or "creat" in t:
            s = "thinking"
        elif "answer" in t:
            s = "answering"
        else:
            s = "idle"
        self._state = s

    @staticmethod
    def _c(rgb, alpha=255):
        return QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]), int(alpha))

    def _on_tick(self):
        """Aurora + vignette change slowly: refresh that cached layer ~8x/s and full-repaint.
        The ribbon moves fast, so in between only its thin horizontal band is repainted."""
        now = time.time()
        w, h = self.width(), self.height()
        if w < 10 or h < 10:
            return
        moving = abs(self._ribbon_y - self._ribbon_target) > 0.002
        if moving or self._bg is None or self._bg.size() != self.size() or now - self._bg_t > 0.12:
            self._step_anim()
            self._render_bg(now - self._t0, w, h)
            self._bg_t = now
            self.update()
        else:
            self._step_anim()
            half = int(self.RIBBON_AMP["answering"] * (h / 800.0) + 40)
            self.update(QRect(0, int(h * self._ribbon_y) - half, w, half * 2))

    def _step_anim(self):
        s = self._state
        for i, target in enumerate(self.PALETTES[s]):
            tr = T.rgb(target)
            for k in range(3):
                self._cur[i][k] += (tr[k] - self._cur[i][k]) * 0.03
        self._energy += (self.ENERGY[s] - self._energy) * 0.03
        self._amp += (self.RIBBON_AMP[s] - self._amp) * 0.06
        self._ribbon_y += (self._ribbon_target - self._ribbon_y) * 0.06

    def paintEvent(self, event):
        if self._bg is None:
            return
        t = time.time() - self._t0
        p = QPainter(self)
        p.drawPixmap(0, 0, self._bg)
        self._ribbon(p, t, self.width(), self.height(), self._state)
        p.end()

    def _render_bg(self, t, w, h):
        cols = self._cur

        # ---- aurora into the tiny buffer
        bp = QPainter(self._buf)
        bp.setRenderHint(QPainter.Antialiasing)
        bp.fillRect(0, 0, self.BW, self.BH, QColor(T.BG))
        bp.setPen(Qt.NoPen)
        speed = 0.10 + 0.28 * self._energy
        for i in range(5):
            a = t * speed * (0.70 + 0.23 * i) + i * 1.7
            b = t * speed * (0.55 + 0.19 * i) + i * 2.3
            x = self.BW * (0.5 + 0.44 * math.cos(a))
            y = self.BH * (0.5 + 0.42 * math.sin(b))
            rad = self.BW * (0.36 + 0.08 * math.sin(t * 0.4 + i))
            g = QRadialGradient(QPointF(x, y), rad)
            g.setColorAt(0.0, self._c(cols[i % 3], 50 + 75 * self._energy))
            g.setColorAt(1.0, self._c(cols[i % 3], 0))
            bp.setBrush(QBrush(g))
            bp.drawEllipse(QPointF(x, y), rad, rad)
        bp.end()

        if self._bg is None or self._bg.size() != self.size():
            self._bg = QPixmap(self.size())
        p = QPainter(self._bg)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(QRect(0, 0, w, h), self._buf)

        # ---- soft vignette keeps the edges calm (and the contrast low)
        vg = QRadialGradient(QPointF(w / 2, h / 2), max(w, h) * 0.72)
        vg.setColorAt(0.55, QColor(33, 37, 43, 0))
        vg.setColorAt(1.0, QColor(33, 37, 43, 170))
        p.fillRect(0, 0, w, h, QBrush(vg))
        p.end()

    def _ribbon(self, p, t, w, h, state):
        p.setRenderHint(QPainter.Antialiasing)
        y0 = h * self._ribbon_y
        amp = self._amp * (h / 800.0)
        if state == "answering":                         # speech-like envelope
            amp *= 0.65 + 0.35 * abs(math.sin(t * 4.7) * math.cos(t * 1.3))
        s1 = 0.7 + 1.6 * self._energy
        n = max(40, w // 9)
        layers = ((0, 2.6, 215, 0.0, 1.3), (1, 1.8, 130, 1.7, 1.9), (2, 1.2, 90, 3.1, 2.6))
        for ci, width, alpha, phase, freq in layers:
            path = QPainterPath()
            for i in range(n + 1):
                u = i / n
                env = math.sin(math.pi * u) ** 1.6       # flat at the edges = silk look
                v = (0.6 * math.sin(u * freq * 2 * math.pi + t * s1 + phase)
                     + 0.4 * math.sin(u * freq * 3.7 * math.pi - t * s1 * 0.8 + phase * 1.3))
                x, y = w * u, y0 + amp * env * v
                path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
            if ci == 0:  # one soft glow under the main strand (the wide strokes were the costly part)
                glow = QPen(self._c(self._cur[ci], 30), width * 4)
                glow.setCapStyle(Qt.RoundCap)
                p.setPen(glow)
                p.drawPath(path)
            pen = QPen(self._c(self._cur[ci], alpha), width)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawPath(path)


# =========================================================================== input bar
class InputBar(QFrame):
    """Text box + mic button. Typing and talking go through the same pipeline."""

    def __init__(self, on_mic, parent=None):
        super().__init__(parent)
        self.setObjectName("inputbar")
        self.setFixedHeight(58)
        self.setMinimumWidth(620)
        self.setMaximumWidth(760)
        self.icon_off = QIcon(GraphicsDirectoryPath('Mic_off.png'))
        self.icon_on = QIcon(GraphicsDirectoryPath('Mic_on.png'))

        self.edit = QLineEdit()
        self.edit.setPlaceholderText(f"Type to {Assistantname}, or tap the mic and just talk...")
        self.edit.setFrame(False)
        self.edit.setStyleSheet(f"background: transparent; color: {T.FG_BRIGHT}; font-size: 16px;"
                                f" selection-background-color: {T.GUTTER};")
        self.edit.installEventFilter(self)
        self.edit.returnPressed.connect(self.submit)

        self.mic = QPushButton()
        self.mic.setFixedSize(46, 46)
        self.mic.setIconSize(QSize(38, 38))
        self.mic.setCursor(Qt.PointingHandCursor)
        self.mic.setStyleSheet("QPushButton { border: none; background: transparent; }")
        self.mic.clicked.connect(on_mic)

        self.send = QPushButton()
        self.send.setIcon(QIcon(GraphicsDirectoryPath('Send.png')))
        self.send.setFixedSize(46, 46)
        self.send.setIconSize(QSize(34, 34))
        self.send.setCursor(Qt.PointingHandCursor)
        self.send.setStyleSheet("QPushButton { border: none; background: transparent; }")
        self.send.clicked.connect(self.submit)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(22, 6, 8, 6)
        lay.setSpacing(4)
        lay.addWidget(self.edit, 1)
        lay.addWidget(self.mic)
        lay.addWidget(self.send)

        self.setStyleSheet(f"""
            QFrame#inputbar {{ background: rgba(33,37,43,225); border: 1px solid {T.BORDER}; border-radius: 29px; }}
            QFrame#inputbar[focused="true"] {{ border: 1px solid {T.BLUE}; }}
        """)
        self.set_mic(False)

    def eventFilter(self, obj, ev):
        if obj is self.edit and ev.type() in (QEvent.FocusIn, QEvent.FocusOut):
            self.setProperty("focused", ev.type() == QEvent.FocusIn)
            self.style().unpolish(self)
            self.style().polish(self)
        return super().eventFilter(obj, ev)

    def submit(self):
        text = self.edit.text().strip()
        if text:
            self.edit.clear()
            State.set_status("Thinking...")
            State.submit_text(text)

    def set_mic(self, on):
        self.mic.setIcon(self.icon_on if on else self.icon_off)
        self.mic.setToolTip("Listening (speech goes to Windows speech recognition). Tap to stop" if on else "Tap to talk")


# =========================================================================== screens
ACCENT = {"idle": T.BLUE, "listening": T.MAGENTA, "thinking": T.BLUE, "searching": T.CYAN, "answering": T.MAGENTA}


def status_html(text, state):
    return (f"<span style='color:{ACCENT.get(state, T.BLUE)}'>&#9679;</span>&nbsp;&nbsp;"
            f"<span style='color:{T.FG}'>{text}</span>")


class HomeScreen(QWidget):
    """Text-first home: greeting, the latest words as large type with a typewriter reveal,
    a status line, and the input bar. The living background is the visual."""

    def __init__(self, on_mic):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 10, 40, 34)
        lay.setSpacing(10)

        self.greet = QLabel("")
        self.greet.setAlignment(Qt.AlignCenter)
        self.greet.setStyleSheet(f"color: {T.FG}; font-family: '{T.UI_DISPLAY}'; font-size: 13px; letter-spacing: 6px;")

        self.user_line = QLabel("")
        self.user_line.setAlignment(Qt.AlignCenter)
        self.user_line.setWordWrap(True)
        self.user_line.setMaximumWidth(960)
        self.user_line.setStyleSheet(f"color: {T.BLUE}; font-family: '{T.DISPLAY}'; font-size: 19px; font-style: italic;")

        self.reply = QLabel("")
        self.reply.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.reply.setWordWrap(True)
        self.reply.setMaximumWidth(960)

        self.status = QLabel("")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet("font-size: 16px; letter-spacing: 2px;")

        self.bar = InputBar(on_mic)

        lay.addStretch(3)
        lay.addWidget(self.greet, alignment=Qt.AlignCenter)
        lay.addSpacing(6)
        lay.addWidget(self.user_line, alignment=Qt.AlignCenter)
        lay.addWidget(self.reply, alignment=Qt.AlignCenter)
        lay.addSpacing(8)
        lay.addWidget(self.status, alignment=Qt.AlignCenter)
        lay.addStretch(4)
        lay.addWidget(self.bar, alignment=Qt.AlignCenter)

        self._target = ""
        self._shown = 0
        self._last_status = None
        self.set_reply("How can I help you today?", animate=False)
        self.update_greeting()

        self._type_timer = QTimer(self)
        self._type_timer.setInterval(28)
        self._type_timer.timeout.connect(self._typewriter)

    def showEvent(self, e):
        self._type_timer.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self._type_timer.stop()
        super().hideEvent(e)

    def update_greeting(self):
        hr = datetime.datetime.now().hour
        part = "morning" if 5 <= hr < 12 else "afternoon" if 12 <= hr < 17 else "evening" if 17 <= hr < 22 else "night"
        self.greet.setText(f"GOOD {part.upper()}, {Username.upper()}")

    def set_reply(self, text, animate=True):
        text = text.strip()
        if len(text) > 320:
            text = text[:300].rsplit(" ", 1)[0] + "...  (more in Chat)"
        size = 38 if len(text) < 80 else 30 if len(text) < 170 else 23
        font = QFont(T.DISPLAY, size)
        self.reply.setFont(font)
        self.reply.setStyleSheet(f"color: {T.FG_BRIGHT};")
        width = max(300, min(960, self.width() - 120))
        rect = QFontMetrics(font).boundingRect(QRect(0, 0, width, 5000), Qt.TextWordWrap | Qt.AlignHCenter, text)
        self.reply.setFixedHeight(rect.height() + 14)   # reserve the final height: no jumping while typing
        self._target = text
        self._shown = 0 if animate else len(text)
        self.reply.setText(text[:self._shown])

    def _typewriter(self):
        if self._shown < len(self._target):
            self._shown = min(len(self._target), self._shown + 2)
            self.reply.setText(self._target[:self._shown])

    def on_message(self, text):
        t = text.strip()
        if t.startswith(f"{Username}:") or t.startswith(f"{Username} :"):
            self.user_line.setText(t.split(":", 1)[1].strip())
            self.set_reply("...", animate=False)
        elif t.startswith(f"{Assistantname}:") or t.startswith(f"{Assistantname} :"):
            self.set_reply(t.split(":", 1)[1])

    def set_status(self, text, state):
        if (text, state) != self._last_status:
            self._last_status = (text, state)
            self.status.setText(status_html(text, state))


class Bubble(QFrame):
    """One chat message: soft rounded card, blue-tinted for the user, violet for Lency."""

    def __init__(self, who, text, mine):
        super().__init__()
        self.mine = mine
        self.setObjectName("bubble")
        tint, edge = ((97, 175, 239), T.BLUE) if mine else ((198, 120, 221), T.MAGENTA)
        self.setStyleSheet(
            f"QFrame#bubble {{ background: rgba({tint[0]},{tint[1]},{tint[2]},34);"
            f" border: 1px solid rgba({tint[0]},{tint[1]},{tint[2]},95); border-radius: 20px;"
            f" border-{'bottom-right' if mine else 'bottom-left'}-radius: 6px; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 11, 18, 13)
        lay.setSpacing(3)
        name = QLabel(f"{who.upper()}  ·  {datetime.datetime.now().strftime('%H:%M')}")
        name.setStyleSheet(f"color: {edge}; font-family: '{T.UI_DISPLAY}'; font-size: 10px; letter-spacing: 3px;"
                           " background: transparent; border: none;")
        self.body = QLabel(text)
        self.body.setWordWrap(True)
        self.body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.body.setStyleSheet(f"color: {T.FG_BRIGHT}; font-family: '{T.DISPLAY}'; font-size: 17px;"
                                " background: transparent; border: none;")
        lay.addWidget(name, alignment=Qt.AlignRight if mine else Qt.AlignLeft)
        lay.addWidget(self.body)

    def fit(self, limit):
        """Grow to the text's natural width, up to `limit`, so short lines stay compact and long ones wrap."""
        want = QFontMetrics(self.body.font()).boundingRect(QRect(0, 0, 4000, 100), 0, self.body.text()).width()
        self.setMaximumWidth(limit)
        self.body.setMinimumWidth(min(want + 8, limit - 40))

    def add(self, more):
        self.body.setText(self.body.text() + "\n" + more)


class ChatScreen(QWidget):
    """Conversation as soft bubbles: you on the right in blue, her on the left in violet."""

    def __init__(self, on_mic):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 14, 28, 24)
        lay.setSpacing(14)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; } QWidget#feed { background: transparent; }")
        self.feed = QWidget()
        self.feed.setObjectName("feed")
        self.col = QVBoxLayout(self.feed)
        self.col.setContentsMargins(max(0, 20), 10, 20, 10)
        self.col.setSpacing(10)
        self.col.addStretch(1)
        self.scroll.setWidget(self.feed)
        lay.addWidget(self.scroll, 1)

        self.bar = InputBar(on_mic)
        lay.addWidget(self.bar, alignment=Qt.AlignCenter)
        self._last = None
        self._bubbles = []
        self.scroll.verticalScrollBar().rangeChanged.connect(self._stick)

    def clear(self):
        while self.col.count() > 1:                     # everything except the trailing stretch
            item = self.col.takeAt(0)
            lay = item.layout()
            if lay is not None:
                while lay.count():
                    w = lay.takeAt(0).widget()
                    if w is not None:
                        w.deleteLater()
        self._last = None
        self._bubbles = []

    def _stick(self, lo, hi):
        self.scroll.verticalScrollBar().setValue(hi)

    def _limit(self):
        return max(280, int(self.width() * 0.62))

    def resizeEvent(self, e):
        for b in self._bubbles:
            b.fit(self._limit())
        super().resizeEvent(e)

    def add_message(self, message):
        for line in message.split("\n"):
            line = line.strip()
            if not line:
                continue
            who = None
            for name in (Username, Assistantname):
                for sep in (f"{name}:", f"{name} :"):
                    if line.startswith(sep):
                        who, line = name, line[len(sep):].strip()
                        break
                if who:
                    break
            if who is None and self._last is not None:
                self._last.add(line)                # continuation of the previous speaker
                self._last.fit(self._limit())
                continue
            who = who or Assistantname
            mine = who == Username
            bubble = Bubble(who, line, mine)
            bubble.fit(self._limit())
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            if mine:
                row.addStretch(1)
                row.addWidget(bubble)
            else:
                row.addWidget(bubble)
                row.addStretch(1)
            self.col.insertLayout(self.col.count() - 1, row)
            self._last = bubble
            self._bubbles.append(bubble)


# =========================================================================== window chrome
class CustomTopBar(QWidget):

    def __init__(self, parent, stacked_widget):
        super().__init__(parent)
        self.stacked_widget = stacked_widget
        self.draggable = True
        self.offset = None
        self.initUI()

    def _btn(self, icon, name, size=(36, 32), icon_px=16, text=None):
        b = QPushButton(text or "")
        b.setIcon(QIcon(GraphicsDirectoryPath(icon)))
        b.setIconSize(QSize(icon_px, icon_px))
        b.setObjectName(name)
        b.setCursor(Qt.PointingHandCursor)
        if text is None:
            b.setFixedSize(*size)
        return b

    def initUI(self):
        self.setFixedHeight(50)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 12, 0)
        layout.setSpacing(6)

        title = QLabel(f"<span style='color:{T.MAGENTA}'>&#9679;</span>&nbsp;&nbsp;"
                       f"<span style='color:{T.FG_BRIGHT}; font-weight:600'>{str(Assistantname).capitalize()}</span>")
        title.setStyleSheet("font-size: 17px; letter-spacing: 1px;")

        self.home_button = self._btn("Home.png", "nav", icon_px=18, text="  Home")
        self.message_button = self._btn("Chats.png", "nav", icon_px=18, text="  Chat")
        group = QButtonGroup(self)
        group.setExclusive(True)
        for b in (self.home_button, self.message_button):
            b.setCheckable(True)
            group.addButton(b)
        self.home_button.setChecked(True)
        self.home_button.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        self.message_button.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(1))
        self.stacked_widget.currentChanged.connect(
            lambda i: (self.home_button, self.message_button)[i].setChecked(True))

        minimize_button = self._btn("Minimize2.png", "win")
        minimize_button.clicked.connect(lambda: self.parent().showMinimized())
        self.maximize_button = self._btn("Maximize.png", "win")
        self.maximize_icon = QIcon(GraphicsDirectoryPath('Maximize.png'))
        self.restore_icon = QIcon(GraphicsDirectoryPath('Minimize.png'))
        self.maximize_button.clicked.connect(self.maximizeWindow)
        close_button = self._btn("Close.png", "close")
        close_button.clicked.connect(lambda: self.parent().close())

        self.voice_box = QComboBox()
        self.voice_box.setObjectName("voice")
        self.voice_box.setCursor(Qt.PointingHandCursor)
        self.voice_box.setToolTip(f"Change {Assistantname}'s voice")
        for key, label, female in list_voices():
            self.voice_box.addItem(label, key)
        self.sync_voice()
        self.voice_box.activated.connect(self._voice_chosen)

        layout.addWidget(title)
        layout.addStretch(1)
        layout.addWidget(self.home_button)
        layout.addWidget(self.message_button)
        layout.addStretch(1)
        self.stop_button = QPushButton("■  Stop")
        self.stop_button.setObjectName("chip")
        self.stop_button.setCursor(Qt.PointingHandCursor)
        self.stop_button.setToolTip(f"Make {Assistantname} stop talking (Esc)")
        self.stop_button.clicked.connect(lambda: self.parent().stop_talking())
        self.clear_button = QPushButton("Clear chat")
        self.clear_button.setObjectName("chip")
        self.clear_button.setCursor(Qt.PointingHandCursor)
        self.clear_button.setToolTip("Erase the conversation history")
        self.clear_button.clicked.connect(lambda: self.parent().clear_history())

        layout.addWidget(self.stop_button)
        layout.addWidget(self.clear_button)
        layout.addWidget(self.voice_box)
        layout.addSpacing(8)
        layout.addWidget(minimize_button)
        layout.addWidget(self.maximize_button)
        layout.addWidget(close_button)

        self.setStyleSheet(f"""
            QPushButton#nav {{ color: {T.FG}; background: transparent; border: none; border-radius: 9px;
                               padding: 6px 16px; font-size: 14px; }}
            QPushButton#nav:hover {{ background: {T.BG_LIGHT}; color: {T.FG_BRIGHT}; }}
            QPushButton#nav:checked {{ background: {T.BG_LIGHT}; color: {T.BLUE}; }}
            QPushButton#win, QPushButton#close {{ background: transparent; border: none; border-radius: 8px; }}
            QPushButton#win:hover {{ background: {T.BG_LIGHT}; }}
            QPushButton#close:hover {{ background: {T.RED}; }}
            QPushButton#chip {{ background: transparent; color: {T.FG}; border: 1px solid {T.BORDER};
                                border-radius: 9px; padding: 5px 12px; font-size: 13px; }}
            QPushButton#chip:hover {{ border: 1px solid {T.BLUE}; color: {T.FG_BRIGHT}; }}
            QComboBox#voice {{ background: {T.BG_LIGHT}; color: {T.FG}; border: 1px solid {T.BORDER};
                               border-radius: 9px; padding: 5px 12px; min-width: 120px; font-size: 13px; }}
            QComboBox#voice:hover {{ border: 1px solid {T.BLUE}; color: {T.FG_BRIGHT}; }}
            QComboBox#voice::drop-down {{ border: none; width: 24px; }}
            QComboBox#voice::down-arrow {{ image: url({GraphicsDirectoryPath("Chevron.png").replace(chr(92), "/")});
                               width: 12px; height: 12px; }}
        """)
        # the popup is its own top-level window, so it must be styled directly (not via the combo's stylesheet)
        self.voice_box.setView(QListView())
        self.voice_box.view().setStyleSheet(f"""
            QListView {{ background: {T.BG_DARK}; color: {T.FG}; border: 1px solid {T.BORDER};
                         border-radius: 8px; outline: none; padding: 4px; font-size: 13px; }}
            QListView::item {{ padding: 7px 12px; border-radius: 6px; min-height: 20px; }}
            QListView::item:hover, QListView::item:selected {{ background: {T.BG_LIGHT}; color: {T.BLUE}; }}
        """)

    def sync_voice(self):
        """Keep the picker showing the active voice (it can also change by voice command)."""
        i = self.voice_box.findData(current_voice_key())
        if i >= 0 and i != self.voice_box.currentIndex() and not self.voice_box.view().isVisible():
            self.voice_box.setCurrentIndex(i)

    def _voice_chosen(self, index):
        if set_voice(self.voice_box.itemData(index)):
            threading.Thread(target=TextToSpeech, args=("Hi! This is how I sound now. Do you like it?",),
                             daemon=True).start()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(T.BG_DARK))
        p.setPen(QColor(T.BORDER))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        p.end()

    def maximizeWindow(self):
        if self.parent().isMaximized():
            self.parent().showNormal()
            self.maximize_button.setIcon(self.maximize_icon)
        else:
            self.parent().showMaximized()
            self.maximize_button.setIcon(self.restore_icon)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.offset = event.globalPos() - self.parent().frameGeometry().topLeft()

    def mouseReleaseEvent(self, event):
        self.offset = None

    def mouseMoveEvent(self, event):
        if self.draggable and self.offset and not self.parent().isMaximized():
            self.parent().move(event.globalPos() - self.offset)


class MainWindow(QMainWindow):

    def __init__(self, enable_voice=True):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setWindowTitle(str(Assistantname))
        screen = QApplication.primaryScreen()
        self.setGeometry(0, 0, screen.size().width(), screen.size().height())

        self.stage = AuroraBackground()
        self.home = HomeScreen(self.toggle_mic)
        self.chat_screen = ChatScreen(self.toggle_mic)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.home)
        self.stack.addWidget(self.chat_screen)
        box = QVBoxLayout(self.stage)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(self.stack)

        self.setStyleSheet(f"""
            QMainWindow {{ background: {T.BG}; }}
            QScrollBar:vertical {{ border: none; background: transparent; width: 10px; margin: 4px 2px; }}
            QScrollBar::handle:vertical {{ background: {T.GUTTER}; min-height: 28px; border-radius: 3px; }}
            QScrollBar::handle:vertical:hover {{ background: {T.COMMENT}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
        """)
        self.top_bar = CustomTopBar(self, self.stack)
        self.setMenuWidget(self.top_bar)
        self.setCentralWidget(self.stage)
        self.stack.currentChanged.connect(lambda i: self.stage.set_ribbon((0.74, 0.945)[i]))
        QShortcut(QKeySequence("Esc"), self, activated=self.stop_talking)

        self.voice = DictationTyper(self, lambda: (self.home, self.chat_screen)[self.stack.currentIndex()].bar.edit) \
            if enable_voice else None

        self._quitting = False
        self._told_tray = False
        icon_path = GraphicsDirectoryPath("Tray.png")
        self.setWindowIcon(QIcon(icon_path))
        self.tray = Tray(self, icon_path, str(Assistantname), self.quit_app)             if QSystemTrayIcon.isSystemTrayAvailable() else None

        self._tick = QTimer(self)
        self._tick.timeout.connect(self.refresh)
        self._tick.start(60)      # pure in-memory reads now: no file polling

    def toggle_mic(self):
        State.set_mic(not State.mic_on())

    def stop_talking(self):
        State.request_stop()
        State.set_status("Available...")

    def clear_history(self):
        try:
            with open(r"Data/ChatLog.json", "w", encoding="utf-8") as f:
                f.write("[]")
        except OSError:
            pass
        self.chat_screen.clear()
        self.home.set_reply("Fresh start! What shall we talk about?", animate=False)
        self.home.user_line.setText("")

    def refresh(self):
        now = time.time()
        if now - getattr(self, "_voice_sync_t", 0) > 1.0:
            self._voice_sync_t = now
            self.top_bar.sync_voice()
            self.home.update_greeting()           # "Good morning" must not stay on screen all day
        for title, message in State.drain_notes():       # reminders, timers, alarms
            if self.tray:
                self.tray.toast(title, message)
        for kind, text in State.drain():
            self.chat_screen.add_message(text)
            if kind == "live":
                self.home.on_message(text)

        status = State.get_status()
        listening = State.mic_on() and self.voice is not None and self.voice.active and status.startswith("Available")
        shown = "Listening..." if listening else status
        self.stage.set_state(shown)
        state = self.stage._state
        self.home.set_status(shown, state)
        on = State.mic_on()
        self.home.bar.set_mic(on)
        self.chat_screen.bar.set_mic(on)

    def closeEvent(self, e):
        if self.tray and not self._quitting:             # the X hides to the tray; reminders keep running
            e.ignore()
            self.hide()
            if not self._told_tray:
                self._told_tray = True
                self.tray.toast(f"{Assistantname} is still here",
                                "I'm in the tray so your reminders keep working. Right-click the icon to quit.", 5)
            return
        if self.voice:
            self.voice.shutdown()
        super().closeEvent(e)

    def quit_app(self):
        self._quitting = True
        if self.tray:
            self.tray.hide()
        self.close()
        QApplication.quit()


def GraphicalUserInterface(start_hidden=False):
    app = QApplication(sys.argv)
    app.setFont(QFont(T.UI, 10))
    app.setQuitOnLastWindowClosed(False)                 # closing the window must not end the process
    window = MainWindow()
    if start_hidden and window.tray:                     # launched at Windows start-up: tray only
        window.tray.toast(f"{Assistantname} is ready", "Click the tray icon to open me.", 4)
    else:
        window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    GraphicalUserInterface()
