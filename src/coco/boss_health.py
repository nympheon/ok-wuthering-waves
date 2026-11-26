"""Detect the tapered fill at the left end of a nearly empty 4C boss bar."""

import cv2

from ok import color_range_to_bound
from src.combat.CombatCheck import boss_health_color


def boss_bar_has_health(task):
    area = task.box_of_screen(1269 / 3840, 58 / 2160, 2533 / 3840, 200 / 2160,
                              hcenter=True, vcenter=True)
    mask = cv2.inRange(area.crop_frame(task.frame)[:, :, :3], *color_range_to_bound(boss_health_color))
    _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    min_height = 9 / 2160 * task.height
    max_height = 40 / 2160 * task.height
    min_area = min_height * 3 / 3840 * task.width
    return any(min_height <= row[cv2.CC_STAT_HEIGHT] <= max_height and row[cv2.CC_STAT_AREA] >= min_area
               for row in stats[1:])
