"""Let the timed event choice expire without sending battle clicks through it."""
from functools import lru_cache
import time
import cv2
from app.utils.common import get_resource_path
from app.utils.logger import setup_logger

logger = setup_logger('BattleRewards')


@lru_cache(maxsize=1)
def _header():
    return cv2.imread(str(get_resource_path('templates/events/reward_header.png')), 0)


def reward_visible(frame):
    if frame is None:
        return False
    art = _header()
    if art is None:
        return False
    h, w = frame.shape[:2]
    scale = h / 1440
    art = cv2.resize(art, (max(1, round(art.shape[1]*scale)), max(1, round(art.shape[0]*scale))))
    roi = cv2.cvtColor(frame[round(h*.04):round(h*.32), round(w*.15):round(w*.85)], cv2.COLOR_BGR2GRAY)
    if roi.shape[0] < art.shape[0] or roi.shape[1] < art.shape[1]:
        return False
    return cv2.minMaxLoc(cv2.matchTemplate(roi, art, cv2.TM_CCOEFF_NORMED))[1] >= .84


class BattleRewards:
    def __init__(self, window, input_service, stop_event):
        self.window, self.input, self.stop_event = window, input_service, stop_event

    def handle(self, frame):
        if self.stop_event.is_set():
            raise InterruptedError('Bot stopped by user')
        if not reward_visible(frame):
            return False
        self.input.mouse_up(0, 0)
        logger.info('Event reward: waiting for automatic selection')
        deadline = time.monotonic() + 40
        clear = 0
        while time.monotonic() < deadline:
            if self.stop_event.wait(.15):
                raise InterruptedError('Bot stopped by user')
            fresh = self.window.screenshot()
            clear = clear + 1 if fresh is not None and not reward_visible(fresh) else 0
            if clear >= 2:
                logger.info('Event reward closed; resuming battle')
                return True
        raise RuntimeError('Event reward remained open for 40 seconds')
