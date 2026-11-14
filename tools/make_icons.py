"""Regenerates every PNG in Frontend/Graphics in one coherent One Dark style.

Run from the project root:   python tools/make_icons.py
All icons are drawn as 4x supersampled vectors: rounded 7px strokes on a 128px canvas.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "Frontend"))

from PyQt5.QtGui import (QGuiApplication, QImage, QPainter, QPen, QColor, QPainterPath,
                         QLinearGradient, QRadialGradient, QBrush)
from PyQt5.QtCore import Qt, QPointF, QRectF
import Theme as T

app = QGuiApplication([])
OUT = os.path.join(ROOT, "Frontend", "Graphics")
S = 128


def canvas():
    img = QImage(S * 2, S * 2, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    p.scale(2, 2)
    return img, p


def stroke(p, color, w=7):
    pen = QPen(QColor(color), w)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)


def save(name, img, p):
    p.end()
    img = img.scaled(S, S, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    img.save(os.path.join(OUT, name))
    print("wrote", name)


def poly(pts, close=False):
    path = QPainterPath(QPointF(*pts[0]))
    for pt in pts[1:]:
        path.lineTo(QPointF(*pt))
    if close:
        path.closeSubpath()
    return path


# ------------------------------------------------------------------ nav + window icons
def home():
    img, p = canvas(); stroke(p, T.FG)
    p.drawPath(poly([(22, 66), (64, 28), (106, 66)]))
    p.drawPath(poly([(34, 58), (34, 100), (94, 100), (94, 58)]))
    p.drawPath(poly([(54, 100), (54, 76), (74, 76), (74, 100)]))
    save("Home.png", img, p)


def chats():
    img, p = canvas(); stroke(p, T.FG)
    p.drawRoundedRect(QRectF(20, 26, 88, 62), 18, 18)
    p.drawPath(poly([(46, 90), (46, 108), (68, 88)]))
    p.setPen(Qt.NoPen); p.setBrush(QColor(T.FG))
    for x in (44, 64, 84):
        p.drawEllipse(QPointF(x, 57), 5, 5)
    save("Chats.png", img, p)


def close():
    img, p = canvas(); stroke(p, T.FG)
    p.drawLine(QPointF(36, 36), QPointF(92, 92))
    p.drawLine(QPointF(92, 36), QPointF(36, 92))
    save("Close.png", img, p)


def maximize():
    img, p = canvas(); stroke(p, T.FG)
    p.drawRoundedRect(QRectF(32, 32, 64, 64), 10, 10)
    save("Maximize.png", img, p)


def restore():  # shown when the window is maximized ("Minimize.png" in the original set)
    img, p = canvas(); stroke(p, T.FG)
    p.drawRoundedRect(QRectF(26, 44, 54, 54), 10, 10)
    p.drawPath(poly([(46, 44), (46, 36), (54, 28), (92, 28), (100, 36), (100, 74), (92, 82), (80, 82)]))
    save("Minimize.png", img, p)


def minimize():
    img, p = canvas(); stroke(p, T.FG)
    p.drawLine(QPointF(32, 70), QPointF(96, 70))
    save("Minimize2.png", img, p)


# ------------------------------------------------------------------ microphone badges
def mic_glyph(p, color, w=7):
    stroke(p, color, w)
    p.drawRoundedRect(QRectF(51, 26, 26, 46), 13, 13)
    p.drawArc(QRectF(38, 44, 52, 46), 180 * 16, 180 * 16)
    p.drawLine(QPointF(64, 90), QPointF(64, 102))
    p.drawLine(QPointF(50, 102), QPointF(78, 102))


def mic_on():  # listening: glowing magenta -> blue badge
    img, p = canvas()
    glow = QRadialGradient(QPointF(64, 64), 64)
    g = QColor(T.MAGENTA); g.setAlpha(90); glow.setColorAt(0.78, g)
    g0 = QColor(T.MAGENTA); g0.setAlpha(0); glow.setColorAt(1.0, g0)
    p.setPen(Qt.NoPen); p.setBrush(QBrush(glow)); p.drawEllipse(QPointF(64, 64), 64, 64)
    grad = QLinearGradient(14, 14, 114, 114)
    grad.setColorAt(0, QColor(T.MAGENTA)); grad.setColorAt(1, QColor(T.BLUE))
    p.setBrush(QBrush(grad)); p.drawEllipse(QPointF(64, 64), 52, 52)
    mic_glyph(p, T.BG_DARK, 7)
    save("Mic_on.png", img, p)


def mic_off():  # idle: quiet dark badge with slashed mic
    img, p = canvas()
    p.setPen(QPen(QColor(T.GUTTER), 3)); p.setBrush(QColor(T.BG_LIGHT))
    p.drawEllipse(QPointF(64, 64), 51, 51)
    mic_glyph(p, T.FG, 6)
    stroke(p, T.RED, 7)
    p.drawLine(QPointF(34, 34), QPointF(94, 94))
    save("Mic_off.png", img, p)


def chevron():  # dropdown arrow for the voice picker
    img, p = canvas(); stroke(p, T.FG, 9)
    p.drawPath(poly([(30, 48), (64, 82), (98, 48)]))
    save("Chevron.png", img, p)


def tray():  # app / tray icon: aurora badge with three voice bars
    img, p = canvas()
    glow = QRadialGradient(QPointF(64, 64), 64)
    g = QColor(T.MAGENTA); g.setAlpha(110); glow.setColorAt(0.8, g)
    g0 = QColor(T.MAGENTA); g0.setAlpha(0); glow.setColorAt(1.0, g0)
    p.setPen(Qt.NoPen); p.setBrush(QBrush(glow)); p.drawEllipse(QPointF(64, 64), 64, 64)
    grad = QLinearGradient(10, 10, 118, 118)
    grad.setColorAt(0, QColor(T.MAGENTA)); grad.setColorAt(1, QColor(T.BLUE))
    p.setBrush(QBrush(grad)); p.drawEllipse(QPointF(64, 64), 56, 56)
    stroke(p, T.BG_DARK, 12)
    for x, h in ((42, 14), (64, 30), (86, 20)):
        p.drawLine(QPointF(x, 64 - h), QPointF(x, 64 + h))
    save("Tray.png", img, p)


def send():  # arrow-up in a blue -> cyan badge (the text input's send button)
    img, p = canvas()
    grad = QLinearGradient(14, 14, 114, 114)
    grad.setColorAt(0, QColor(T.BLUE)); grad.setColorAt(1, QColor(T.CYAN))
    p.setPen(Qt.NoPen); p.setBrush(QBrush(grad)); p.drawEllipse(QPointF(64, 64), 52, 52)
    stroke(p, T.BG_DARK, 9)
    p.drawLine(QPointF(64, 92), QPointF(64, 38))
    p.drawLine(QPointF(64, 38), QPointF(42, 60))
    p.drawLine(QPointF(64, 38), QPointF(86, 60))
    save("Send.png", img, p)


for fn in (home, chats, close, maximize, restore, minimize, mic_on, mic_off, send, chevron, tray):
    fn()
