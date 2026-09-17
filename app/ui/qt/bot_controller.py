'''Bot orchestration for the Qt UI.'''
from __future__ import annotations
import random
import threading
import time
from PySide6.QtCore import QObject, Signal
from app.core.bot import Bot
from app.utils.logger import setup_logger
from app.utils.profile_settings_store import REPEAT_MAX_CONSECUTIVE_FAILURES, load_profile_settings
logger = setup_logger('BotController')

class BotController(QObject):
    statusChanged = Signal(str, bool)
    botStarted = Signal()
    botFinished = Signal(object)
    runningChanged = Signal(bool)
    # Live village state from the bot thread: dict with any of
    # state/builders/lab/storages/note (missing keys = unchanged/unknown).
    stateChanged = Signal(dict)
    # Session loot totals: gold, elixir, dark elixir, elapsed seconds.
    lootChanged = Signal(int, int, int, float)

    def __init__(self, bot_version):
        super().__init__()
        self._bot_version = bot_version
        self._bot = Bot()
        self._bot_thread = None
        # Set by stop(). Distinct from the bot's own stop_event because it also has to
        # break the pause between sessions, when no bot run is in flight to signal.
        self._stop_requested = threading.Event()


    def is_running(self):
        return self._bot_thread is not None and self._bot_thread.is_alive()


    def start(self, *, method, minutes, star_bonus, ranked_fill, upgrade_walls, multi_run_players, builder_base = False, loot_prioritise = 'both', auto_upgrade = 'off'):
        '''``minutes <= 0`` = unlimited ("run until maxed") — single Home Village runs only.'''
        if self.is_running():
            return None
        self._stop_requested.clear()

        def worker():
            error_msg = None

            def on_status(msg):
                self.statusChanged.emit(msg, 'not found' in msg.lower())

            def on_state(payload):
                self.stateChanged.emit(dict(payload))

            def on_loot(gold, elixir, dark, elapsed):
                self.lootChanged.emit(int(gold), int(elixir), int(dark), float(elapsed))


            failures = 0
            session = 0
            # Bound before the loop so the post-run check below can never hit an
            # unbound name if a later reload raises; re-read each cycle so a settings
            # change applies without restarting the bot.
            profile = load_profile_settings()
            while not self._stop_requested.is_set():
                session += 1
                cycle_failed = False
                try:
                    profile = load_profile_settings()
                    run_minutes = minutes
                    # Random session length: re-rolled every cycle, so no two sessions
                    # are the same length. Only for timed runs — an explicit "run until
                    # maxed" (minutes <= 0) is the user's choice and is left alone.
                    if run_minutes > 0 and profile.random_minutes_min > 0:
                        run_minutes = random.randint(profile.random_minutes_min, profile.random_minutes_max)
                        on_status(f'Random session length: {run_minutes} min (range {profile.random_minutes_min}-{profile.random_minutes_max})')
                        logger.info('Session %d: random length %d min (range %d-%d)', session, run_minutes, profile.random_minutes_min, profile.random_minutes_max)
                    self._bot.start(method, run_minutes, star_bonus = star_bonus, status_callback = on_status, loot_callback = on_loot, state_callback = on_state, multi_run_players = multi_run_players, ranked_fill = ranked_fill, upgrade_walls = upgrade_walls, earthquake_method = profile.earthquake_method, builder_base = builder_base, loot_prioritise = loot_prioritise, wall_upgrade_threshold = profile.wall_upgrade_threshold_m * 1000000, auto_upgrade = auto_upgrade, reserve_builders = profile.reserve_builders, upgrade_order = profile.upgrade_order)
                    error_msg = None
                except InterruptedError:
                    logger.info('Bot thread stopped by user')
                    break
                except Exception as exc:
                    error_msg = str(exc)
                    cycle_failed = True
                    logger.exception('Session %d failed', session)

                # Auto-restart: pause, then run again. Needs a timed run (nothing to
                # repeat when the session has no end) and a pause above 0.
                if self._stop_requested.is_set() or minutes <= 0 or profile.repeat_pause_min <= 0:
                    break
                failures = failures + 1 if cycle_failed else 0
                if failures >= REPEAT_MAX_CONSECUTIVE_FAILURES:
                    error_msg = f'Stopped after {failures} failed sessions in a row: {error_msg}'
                    logger.error(error_msg)
                    break
                pause = random.randint(profile.repeat_pause_min, profile.repeat_pause_max)
                resume = time.strftime('%H:%M', time.localtime(time.time() + pause * 60))
                note = ' after a failure' if cycle_failed else ''
                on_status(f'Paused{note} — next session at {resume} ({pause} min)')
                logger.info('Session %d over%s; pausing %d min, resuming at %s', session, note, pause, resume)
                if self._stop_requested.wait(pause * 60):
                    break
            self.botFinished.emit(error_msg)

        self._bot_thread = threading.Thread(target = worker, daemon = True, name = 'BotThread')
        self.runningChanged.emit(True)
        self.botStarted.emit()
        self._bot_thread.start()


    def stop(self):
        self._stop_requested.set()
        self._bot.stop()
        self.statusChanged.emit('Stopping...', False)


    def on_bot_finished(self):
        self.runningChanged.emit(False)
