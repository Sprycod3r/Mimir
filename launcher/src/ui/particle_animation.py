"""
particle_animation.py — Mimir Particle Field Background

A slow-moving network of particles and connecting lines.
Designed to be layered behind the intro screen — subtle, not distracting.

Specs:
  - 60 particles moving at 0.15–0.35 px/frame
  - Particles bounce off edges with slight randomization
  - Lines drawn between particles closer than CONNECT_THRESHOLD px
  - Line opacity fades with distance (closer = more opaque)
  - Particle opacity pulses slowly and independently
  - Colors from the active theme (uses accent_primary)
  - 24fps via QTimer
  - CPU-light: pure QPainter, no GPU required
"""

import math
import random
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush


PARTICLE_COUNT = 58
CONNECT_THRESHOLD = 140       # px — max distance to draw a connection line
FRAME_INTERVAL_MS = 42        # ~24fps
MIN_SPEED = 0.12
MAX_SPEED = 0.32
PARTICLE_RADIUS_MIN = 1.5
PARTICLE_RADIUS_MAX = 3.5


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "radius", "opacity", "pulse_speed", "pulse_phase")

    def __init__(self, width: int, height: int):
        self.x = random.uniform(0, width)
        self.y = random.uniform(0, height)
        speed = random.uniform(MIN_SPEED, MAX_SPEED)
        angle = random.uniform(0, 2 * math.pi)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.radius = random.uniform(PARTICLE_RADIUS_MIN, PARTICLE_RADIUS_MAX)
        self.opacity = random.uniform(0.35, 0.75)
        self.pulse_speed = random.uniform(0.005, 0.018)
        self.pulse_phase = random.uniform(0, 2 * math.pi)

    def update(self, width: int, height: int, frame: int):
        self.x += self.vx
        self.y += self.vy

        # Bounce off edges with a tiny velocity nudge to prevent looping patterns
        if self.x <= 0 or self.x >= width:
            self.vx = -self.vx + random.uniform(-0.02, 0.02)
            self.x = max(0.0, min(float(width), self.x))
        if self.y <= 0 or self.y >= height:
            self.vy = -self.vy + random.uniform(-0.02, 0.02)
            self.y = max(0.0, min(float(height), self.y))

        # Clamp speed so particles don't accelerate indefinitely
        speed = math.sqrt(self.vx ** 2 + self.vy ** 2)
        if speed > MAX_SPEED * 1.5:
            scale = (MAX_SPEED * 1.5) / speed
            self.vx *= scale
            self.vy *= scale

        # Pulse opacity
        self.pulse_phase += self.pulse_speed
        pulse = math.sin(self.pulse_phase) * 0.18
        self.opacity = max(0.2, min(0.85, 0.55 + pulse))


class ParticleField(QWidget):
    """
    Background widget that renders an animated particle field.
    Place this as the bottom layer in a stacked or layered layout.
    Call set_colors() after theme changes.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

        self._particles: list = []
        self._frame = 0
        self._initialized = False

        # Default colors — call set_colors() to apply the active theme
        self._particle_color = QColor("#8B5CF6")  # Mimir Dark accent_primary
        self._line_color = QColor("#8B5CF6")
        self._bg_color = QColor("#0E0E14")         # Mimir Dark bg_primary

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(FRAME_INTERVAL_MS)

    def set_colors(self, bg_color: str, particle_color: str, line_color: str = None):
        """Apply theme colors. Call after theme is loaded."""
        self._bg_color = QColor(bg_color)
        self._particle_color = QColor(particle_color)
        self._line_color = QColor(line_color or particle_color)
        self.update()

    def start(self):
        self._timer.start(FRAME_INTERVAL_MS)

    def stop(self):
        self._timer.stop()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._initialize_particles()

    def _initialize_particles(self):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        self._particles = [Particle(w, h) for _ in range(PARTICLE_COUNT)]
        self._initialized = True

    def _tick(self):
        if not self._initialized:
            self._initialize_particles()
            return
        w, h = self.width(), self.height()
        for p in self._particles:
            p.update(w, h, self._frame)
        self._frame += 1
        self.update()

    def paintEvent(self, event):
        if not self._initialized or not self._particles:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        painter.fillRect(self.rect(), self._bg_color)

        particles = self._particles
        n = len(particles)

        # Draw connection lines
        line_r = self._line_color.red()
        line_g = self._line_color.green()
        line_b = self._line_color.blue()

        for i in range(n):
            pi = particles[i]
            for j in range(i + 1, n):
                pj = particles[j]
                dx = pi.x - pj.x
                dy = pi.y - pj.y
                dist = math.sqrt(dx * dx + dy * dy)
                if dist >= CONNECT_THRESHOLD:
                    continue

                # Opacity: full at 0px, zero at CONNECT_THRESHOLD
                t = 1.0 - (dist / CONNECT_THRESHOLD)
                alpha = int(t * t * 80)  # Squared falloff — subtle near edges
                if alpha < 4:
                    continue

                line_color = QColor(line_r, line_g, line_b, alpha)
                pen = QPen(line_color)
                pen.setWidthF(0.8)
                painter.setPen(pen)
                painter.drawLine(int(pi.x), int(pi.y), int(pj.x), int(pj.y))

        # Draw particles
        p_r = self._particle_color.red()
        p_g = self._particle_color.green()
        p_b = self._particle_color.blue()

        painter.setPen(Qt.PenStyle.NoPen)
        for p in particles:
            alpha = int(p.opacity * 220)
            color = QColor(p_r, p_g, p_b, alpha)
            painter.setBrush(QBrush(color))
            painter.drawEllipse(
                QRectF(p.x - p.radius, p.y - p.radius,
                       p.radius * 2, p.radius * 2)
            )

        painter.end()
