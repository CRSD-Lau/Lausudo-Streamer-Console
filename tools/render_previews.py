"""Render deterministic public preview assets without desktop capture."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

if sys.platform != "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from streamer_console.models import ConnectionState, Platform
from streamer_console.theme import COLORS
from streamer_console.ui import MainWindow, ensure_application_theme


OUTPUT_DIR = PROJECT_ROOT / "docs" / "images"
README_PREVIEW = OUTPUT_DIR / "streamer-console-preview.png"
SOCIAL_PREVIEW = OUTPUT_DIR / "social-preview.png"


def _pump_events(rounds: int = 8) -> None:
    application = ensure_application_theme()
    for _ in range(rounds):
        application.processEvents()


def _build_preview_window() -> MainWindow:
    window = MainWindow(persist_settings=False, restore_geometry=False)
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.set_window_options(borderless=True, always_on_top=False)
    window.resize(1080, 1920)
    window.update_connection(Platform.TWITCH, ConnectionState.CONNECTED, "RECEIVING")
    window.update_connection(Platform.TIKTOK, ConnectionState.CONNECTED, "RECEIVING")
    window.update_live_metrics(
        {
            "tiktok_viewers": 184,
            "tiktok_follows": 12,
            "tiktok_likes": 4_821,
            "twitch_viewers": 63,
        }
    )
    window.update_spotify_status(
        {
            "available": True,
            "playing": True,
            "title": "Raid Night Mix",
            "artist": "Spotify · local playback",
            "position_seconds": 94,
            "duration_seconds": 238,
        }
    )
    window.update_obs_status(
        {
            "connected": True,
            "streaming": True,
            "recording": True,
            "vertical_active": True,
            "main_scene": "WoW Raid",
            "vertical_scene": "WoW Raid TikTok",
            "brb_state": "live",
            "mic_muted": False,
            "mic_monitor_type": "OBS_MONITORING_TYPE_MONITOR_AND_OUTPUT",
            "spotify_muted": False,
            "spotify_monitor_type": "OBS_MONITORING_TYPE_MONITOR_AND_OUTPUT",
        }
    )
    window.update_collector_health(
        {"listener_running": True, "twitch_native": True}
    )
    window.add_messages(
        [
            {
                "sequence": 1,
                "platform": "twitch",
                "username": "PizzaGuy",
                "text": "Clean pull. That transition was perfect.",
            },
            {
                "sequence": 2,
                "platform": "tiktok",
                "username": "Sarah",
                "text": "what server is this?",
            },
            {
                "sequence": 3,
                "platform": "twitch",
                "username": "Ari",
                "text": "Ari followed the channel",
                "kind": "event",
                "event_type": "follow",
            },
            {
                "sequence": 4,
                "platform": "twitch",
                "username": "RaidLead",
                "text": "@Lausudo defensive in 10",
            },
            {
                "sequence": 5,
                "platform": "tiktok",
                "username": "Mika",
                "text": "Mika sent a Rose",
                "kind": "event",
                "event_type": "gift",
            },
            {
                "sequence": 6,
                "platform": "twitch",
                "username": "Bob",
                "text": "LMAO that recovery",
            },
            {
                "sequence": 7,
                "platform": "tiktok",
                "username": "John",
                "text": "what addon is that?",
            },
            {
                "sequence": 8,
                "platform": "twitch",
                "username": "Northstar",
                "text": "Northstar subscribed for 6 months",
                "kind": "event",
                "event_type": "resub",
            },
            {
                "sequence": 9,
                "platform": "tiktok",
                "username": "Luna",
                "text": "the music fits this boss so well",
            },
            {
                "sequence": 10,
                "platform": "twitch",
                "username": "TankerOne",
                "text": "gear check after this?",
            },
            {
                "sequence": 11,
                "platform": "tiktok",
                "username": "Jade",
                "text": "Jade followed the LIVE",
                "kind": "event",
                "event_type": "follow",
            },
            {
                "sequence": 12,
                "platform": "twitch",
                "username": "MagesOnly",
                "text": "big damage on that phase",
            },
            {
                "sequence": 13,
                "platform": "tiktok",
                "username": "Kai",
                "text": "@Lausudo clean positioning",
            },
            {
                "sequence": 14,
                "platform": "twitch",
                "username": "Nova",
                "text": "Nova cheered 500 Bits",
                "kind": "event",
                "event_type": "bits",
            },
            {
                "sequence": 15,
                "platform": "tiktok",
                "username": "Ember",
                "text": "good luck on the next pull!",
            },
        ]
    )
    window.show()
    _pump_events(16)
    return window


def _render_readme_preview() -> QImage:
    window = _build_preview_window()
    try:
        image = window.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
        if image.size().width() != 1080 or image.size().height() != 1920:
            raise RuntimeError(f"Unexpected README preview size: {image.size()}")
        return image
    finally:
        window.close()
        _pump_events()


def _rounded_image(
    painter: QPainter,
    image: QImage,
    target: QRectF,
    radius: float,
) -> None:
    path = QPainterPath()
    path.addRoundedRect(target, radius, radius)
    painter.save()
    painter.setClipPath(path)
    painter.drawImage(target, image)
    painter.restore()


def _draw_social_preview(app_image: QImage) -> QImage:
    canvas = QImage(1280, 640, QImage.Format.Format_ARGB32)
    canvas.fill(QColor(COLORS.ink))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    painter.fillRect(QRect(0, 0, 1280, 640), QColor(COLORS.ink))
    painter.fillRect(QRect(0, 0, 12, 640), QColor(COLORS.teal))

    glow = QImage(1280, 640, QImage.Format.Format_ARGB32)
    glow.fill(Qt.GlobalColor.transparent)
    glow_painter = QPainter(glow)
    for radius, alpha in ((310, 18), (220, 24), (130, 32)):
        glow_painter.setBrush(QColor(47, 183, 176, alpha))
        glow_painter.setPen(Qt.PenStyle.NoPen)
        glow_painter.drawEllipse(QPointF(1100, 120), radius, radius)
    glow_painter.end()
    painter.drawImage(0, 0, glow)

    logo_path = PROJECT_ROOT / "streamer_console" / "assets" / "lausudo-logo-600.png"
    logo = QPixmap(str(logo_path))
    painter.drawPixmap(
        QRect(80, 64, 86, 86),
        logo.scaled(
            86,
            86,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ),
    )

    painter.setPen(QColor(COLORS.teal))
    painter.setFont(QFont("Bahnschrift SemiBold", 18, QFont.Weight.DemiBold))
    painter.drawText(QRect(80, 174, 620, 30), "LAUSUDO · WINDOWS STREAMING")

    painter.setPen(QColor(COLORS.text))
    painter.setFont(QFont("Bahnschrift SemiBold", 48, QFont.Weight.Bold))
    painter.drawText(QRect(76, 208, 690, 122), Qt.TextFlag.TextWordWrap, "STREAMER\nCONSOLE")

    painter.setPen(QColor(COLORS.mist))
    painter.setFont(QFont("Segoe UI Variable Text", 21, QFont.Weight.Normal))
    painter.drawText(
        QRect(82, 354, 590, 78),
        Qt.TextFlag.TextWordWrap,
        "One chronological Twitch + TikTok feed, live status, raid controls, and Spotify.",
    )

    chips = ("NATIVE WINDOWS", "LOW OVERHEAD", "PRIVACY FIRST")
    chip_x = 82
    painter.setFont(QFont("Bahnschrift SemiBold", 12, QFont.Weight.DemiBold))
    for label in chips:
        width = painter.fontMetrics().horizontalAdvance(label) + 28
        rect = QRectF(chip_x, 492, width, 40)
        painter.setPen(QPen(QColor(COLORS.line), 1))
        painter.setBrush(QColor(COLORS.panel))
        painter.drawRoundedRect(rect, 9, 9)
        painter.setPen(QColor(COLORS.muted))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
        chip_x += width + 12

    target = QRectF(830, 40, 338, 600)
    painter.setPen(QPen(QColor(COLORS.teal), 2))
    painter.setBrush(QColor(COLORS.panel))
    painter.drawRoundedRect(target.adjusted(-12, -12, 12, 12), 22, 22)
    scaled = app_image.scaled(
        int(target.width()),
        int(target.height()),
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    crop_x = max(0, (scaled.width() - int(target.width())) // 2)
    crop_y = max(0, (scaled.height() - int(target.height())) // 2)
    cropped = scaled.copy(crop_x, crop_y, int(target.width()), int(target.height()))
    _rounded_image(painter, cropped, target, 13)

    painter.end()
    return canvas


def _validate_image(path: Path, expected_width: int, expected_height: int) -> None:
    image = QImage(str(path))
    if image.isNull():
        raise RuntimeError(f"Preview is unreadable: {path}")
    if image.width() != expected_width or image.height() != expected_height:
        raise RuntimeError(
            f"Preview has size {image.width()}x{image.height()}, expected "
            f"{expected_width}x{expected_height}: {path}"
        )
    if path.stat().st_size >= 1_000_000:
        raise RuntimeError(f"Preview must remain below 1 MB: {path}")


def main(argv: list[str] | None = None) -> int:
    """Render or validate public preview assets.

    Args:
        argv: Optional CLI arguments. Pass ``--check`` to validate existing files.

    Returns:
        Zero when both preview assets are valid.

    Raises:
        RuntimeError: If rendering fails or an asset violates size constraints.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate existing preview files without rendering them.",
    )
    args = parser.parse_args(argv)
    application = ensure_application_theme()
    if not args.check:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        app_image = _render_readme_preview()
        if not app_image.save(str(README_PREVIEW), "PNG"):
            raise RuntimeError(f"Could not write {README_PREVIEW}")
        social = _draw_social_preview(app_image)
        if not social.save(str(SOCIAL_PREVIEW), "PNG"):
            raise RuntimeError(f"Could not write {SOCIAL_PREVIEW}")

    _validate_image(README_PREVIEW, 1080, 1920)
    _validate_image(SOCIAL_PREVIEW, 1280, 640)
    print(f"Verified {README_PREVIEW.relative_to(PROJECT_ROOT)}")
    print(f"Verified {SOCIAL_PREVIEW.relative_to(PROJECT_ROOT)}")
    application.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
