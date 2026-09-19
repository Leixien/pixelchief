'''New buildings from the shop: buy what the Town Hall unlocked and let the game place it.

A new village unlocks buildings faster than it upgrades them, and the builder popup that
:mod:`app.core.upgrader` reads only lists what already stands. :class:`ShopBuilder` opens
*Shop → Buildings & Traps*, walks its sections, buys the first card it may, and confirms
the spot the game picked (green check). No layout logic: the game chooses the spot.

Card choice is colour only, no OCR: a buildable card is blue; its price band must show a
gold or elixir icon, no gem, and no red digits (red = cannot afford, the gem-spend path).
Free cards (the tutorial Walls) show no resource icon and are skipped with the gem ones.
Nothing happens unless a builder above the reserve is free — buying with every builder
busy opens a finish-with-gems dialog.
'''
import cv2
import numpy as np
from app.core.upgrade_menu import parse_builder_chip
from app.services.vision import VisionService
from app.utils.logger import setup_logger

logger = setup_logger('Shop')

_CARD_BLUE = ((95, 120, 150), (110, 255, 255))  # HSV fill of a buildable card
_CARD_AREA_Y = (0.28, 0.92)  # frame fraction between the section tabs and the resource bar
_PRICE_BAND = (0.80, 0.97)  # card-height fraction holding the price and its icon
_MIN_SHARE = 0.01  # band pixel share that counts as "this colour is there"
_MAX_PLACEMENTS_PER_PASS = 3
_SECTION_SETTLE_SECONDS = 1.0
_PLACE_SETTLE_SECONDS = 1.0


def _price_colours(hsv):
    (h, s, v) = (hsv[..., i].astype(int) for i in range(3))
    return {
        'gold': (h >= 18) & (h <= 30) & (s > 150) & (v > 150),
        'elixir': (h >= 140) & (h <= 170) & (s > 100) & (v > 120),
        'gem': (h >= 33) & (h <= 85) & (s > 90) & (v > 150),
        'red': ((h <= 8) | (h >= 172)) & (s > 80) & (v > 150),
    }


def find_buyable_cards(frame):
    '''Shop "Buildings & Traps" page → ``[(x, y, resource)]`` of the cards the bot may buy,
    row by row, left to right. Partial cards at the scroll edge are ignored.'''
    (fh, fw) = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    top = int(fh * _CARD_AREA_Y[0])
    mask = cv2.inRange(hsv[top:int(fh * _CARD_AREA_Y[1])], *_CARD_BLUE)
    k = max(3, round(15 * fh / 1080))  # close the building art and "i" button holes
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    stats = cv2.connectedComponentsWithStats(mask)[2]
    cards = []
    for (x, y, w, h, _area) in stats[1:]:
        if w < fw * 0.09 or h < fh * 0.2:
            continue
        y += top
        band = hsv[y + int(h * _PRICE_BAND[0]):y + int(h * _PRICE_BAND[1]), x:x + w]
        share = {name: float(m.mean()) for name, m in _price_colours(band).items()}
        resource = max(('gold', 'elixir'), key = share.get)
        if share[resource] < _MIN_SHARE or share['gem'] >= _MIN_SHARE or share['red'] >= _MIN_SHARE:
            continue
        cards.append((int(x + w // 2), int(y + h * 0.45), resource))
    row = fh * 0.1
    return sorted(cards, key = lambda c: (round(c[1] / row), c[0]))


class ShopBuilder:
    '''Buys and places new buildings from the home screen. One instance per bot session.'''

    def __init__(self, window, input_service, vision, config, stop_event):
        self.window = window
        self.input = input_service
        self.vision = vision
        self.config = config
        self.stop_event = stop_event

    def _frame(self):
        frame = self.window.screenshot()
        if frame is None or frame.size == 0:
            return None
        self.config.set_target_size_from_frame(frame)
        return frame

    def _wait_for(self, template, timeout = 3.0):
        '''Poll until ``template`` shows; returns its (x, y) or (None, None).'''
        for _ in range(max(1, int(timeout / 0.3))):
            frame = self._frame()
            if frame is not None:
                (x, y) = self.vision.find_template(frame, template)
                if x:
                    return (x, y)
            if self.stop_event.wait(0.3):
                break
        return (None, None)

    def _click_if_found(self, template):
        frame = self._frame()
        (x, y) = self.vision.find_template(frame, template) if frame is not None else (None, None)
        if x:
            self.input.click(x, y, pause = 0.5)
        return bool(x)

    def _back_out(self):
        '''Cancel a placement or close the shop. Never Okay: an unknown dialog's Okay can
        confirm a gem spend.'''
        for name in ('placecancel.png', 'shopclose.png', 'exit.png'):
            if self._click_if_found(name):
                return
        self.input.click(pause = 0.3, *self.config.get_point('empty'))

    def run(self, dry, reserve_builders = 1):
        '''Buy and place while a builder above the reserve is free. Returns how many were placed.'''
        if not self.config.data.get('shop_sections'):
            return 0  # no shop layout measured for this aspect
        placed = 0
        for _ in range(_MAX_PLACEMENTS_PER_PASS):
            frame = self._frame()
            if frame is None:
                break
            if not self.vision.find_template(frame, 'attack.png', region = VisionService.bottom_half_region(frame))[0]:
                logger.info('Shop: not on the home screen — skipping')
                break
            chip = parse_builder_chip(frame)
            if chip is None or chip[0] <= reserve_builders:
                logger.info('Shop: no builder free above the reserve (builders=%s) — not buying', chip)
                break
            card = self._open_and_pick()
            if card is None:
                break
            if dry:
                logger.info('Shop (dry): WOULD BUY the %s card at (%d, %d)', card[2], card[0], card[1])
                self._back_out()
                break
            if not self._place(card):
                break
            placed += 1
        return placed

    def _open_and_pick(self):
        '''Open the Buildings & Traps page and return the first buyable card, or None
        (shop closed again).'''
        if not self._click_if_found('shopbtn.png'):
            logger.info('Shop: shop button not found — skipping')
            return None
        if not self._wait_for('shopclose.png')[0]:
            logger.info('Shop: shop did not open')
            return None
        # Other tabs sell gems for real money: section clicks only once the page is confirmed.
        self.input.click(pause = 0.5, *self.config.get_point('shop_tab_buildings'))
        if not self._wait_for('shopbuildings.png')[0]:
            logger.warning('Shop: Buildings & Traps page not confirmed — closing')
            self._back_out()
            return None
        for section in self.config.data['shop_sections']:
            self.input.click(pause = 0.3, *self.config.scale_point(section))
            if self.stop_event.wait(_SECTION_SETTLE_SECONDS):
                return None
            frame = self._frame()
            cards = find_buyable_cards(frame) if frame is not None else []
            if cards:
                return cards[0]
        logger.info('Shop: nothing new to build')
        self._back_out()
        return None

    def _place(self, card):
        '''Buy ``card`` and confirm the spot the game chose. True once the check is gone.'''
        (x, y, resource) = card
        logger.info('Shop: buying the %s card at (%d, %d)', resource, x, y)
        self.input.click(x, y, pause = 0.5)
        (ox, oy) = self._wait_for('placeok.png', timeout = 5.0)
        if not ox:
            logger.warning('Shop: no placement check after buying — backing out')
            self._back_out()
            return False
        self.input.click(ox, oy, pause = 0.5)
        if self.stop_event.wait(_PLACE_SETTLE_SECONDS):
            return False
        frame = self._frame()
        if frame is not None and self.vision.find_template(frame, 'placeok.png')[0]:
            logger.warning('Shop: placement not accepted — cancelling')
            self._back_out()
            return False
        logger.info('Shop: placed a new %s building', resource)
        return True
