"""Small dependency-free SVG chart helpers.

Pure functions: take plain numbers/labels in, hand back render-ready
coordinates and path strings for the templates. No Flask or DB imports here.
"""

import calendar as _calendar
import math

PIE_COLORS = ["#4F63F6", "#16A34A", "#DB2777", "#D97706", "#8B5CF6"]


def month_grid(year: int, month: int):
    """Weeks of the given month (Monday-first). Each day is a dict with
    day=0 for the leading/trailing cells that fall outside the month."""
    weeks = []
    for week in _calendar.monthcalendar(year, month):
        weeks.append([{"day": day} for day in week])
    return weeks


def bar_chart(values, labels, width=320, height=160, pad_left=8, pad_bottom=24, pad_top=10):
    plot_w = width - pad_left - 8
    plot_h = height - pad_bottom - pad_top
    max_val = max(values) if values and max(values) > 0 else 1
    n = len(values)
    gap = 8
    bar_w = (plot_w - gap * (n - 1)) / n if n else 0

    bars = []
    for i, v in enumerate(values):
        bar_h = (v / max_val) * plot_h
        x = pad_left + i * (bar_w + gap)
        y = pad_top + (plot_h - bar_h)
        bars.append({
            "x": round(x, 1),
            "y": round(y, 1),
            "width": round(bar_w, 1),
            "height": round(max(bar_h, 1), 1),
            "label": labels[i],
            "value": v,
            "label_x": round(x + bar_w / 2, 1),
        })
    return {
        "width": width,
        "height": height,
        "bars": bars,
        "baseline_y": pad_top + plot_h,
    }


def line_chart(values, width=320, height=160, pad=12):
    plot_w = width - pad * 2
    plot_h = height - pad * 2
    max_val = max(values) if values else 0
    min_val = min(values) if values else 0
    span = max(max_val - min_val, 1)
    n = len(values)
    step = plot_w / (n - 1) if n > 1 else 0

    points = []
    for i, v in enumerate(values):
        x = pad + i * step
        y = pad + plot_h - ((v - min_val) / span) * plot_h
        points.append((round(x, 1), round(y, 1)))

    points_str = " ".join(f"{x},{y}" for x, y in points)
    area_str = f"{pad},{pad + plot_h} {points_str} {pad + plot_w},{pad + plot_h}"
    return {
        "width": width,
        "height": height,
        "points": points_str,
        "area_points": area_str,
        "start_value": values[0] if values else 0,
        "end_value": values[-1] if values else 0,
    }


def pie_chart(counts: dict, radius=70, cx=80, cy=80):
    """counts: {label: value}. Returns a list of slice dicts, skipping zero values."""
    total = sum(counts.values())
    slices = []
    if total == 0:
        return slices

    start_angle = -90.0
    for i, (label, value) in enumerate(counts.items()):
        if value == 0:
            continue
        fraction = value / total
        angle = 359.99 if fraction >= 0.9999 else fraction * 360
        end_angle = start_angle + angle
        large_arc = 1 if angle > 180 else 0

        x1 = cx + radius * math.cos(math.radians(start_angle))
        y1 = cy + radius * math.sin(math.radians(start_angle))
        x2 = cx + radius * math.cos(math.radians(end_angle))
        y2 = cy + radius * math.sin(math.radians(end_angle))

        path = f"M{cx},{cy} L{x1:.2f},{y1:.2f} A{radius},{radius} 0 {large_arc} 1 {x2:.2f},{y2:.2f} Z"
        slices.append({
            "path": path,
            "color": PIE_COLORS[i % len(PIE_COLORS)],
            "label": label,
            "value": value,
            "percent": round(fraction * 100),
        })
        start_angle = end_angle

    return slices
