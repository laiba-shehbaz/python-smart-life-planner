"""Small reusable calculation and formatting helpers."""
import math


def ceil_div(a, b):
    if b <= 0:
        raise ValueError("Divisor must be positive.")
    return -(-a // b)


def rooms_required(travellers, room_capacity):
    """ceiling(travellers / room capacity)."""
    if travellers < 1 or room_capacity < 1:
        raise ValueError("Travellers and room capacity must be at least 1.")
    return ceil_div(travellers, room_capacity)


def round_pkr(value):
    """Round half up to whole rupees."""
    return int(math.floor(value + 0.5))


def money(value):
    return round(float(value) + 0.0, 2)


def percentage(part, whole):
    return 0.0 if whole == 0 else round(part / whole * 100, 2)


def emergency_allowance(subtotal, percent):
    """Emergency allowance, always rounded UP so it is never under-estimated."""
    return math.ceil(round(subtotal * percent / 100, 6))


def format_pkr(amount):
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    if abs(amount - round(amount)) < 0.005:
        return f"{sign}PKR {int(round(amount)):,}"
    return f"{sign}PKR {amount:,.2f}"
