import unittest
from unittest.mock import Mock, patch
import numpy as np
from app.core.battle_rewards import BattleRewards
from app.core.bot import Bot
from app.core.strategies import AttackStrategy


class EventTests(unittest.TestCase):
    def setUp(self):
        self.window, self.input, self.stop = Mock(), Mock(), Mock()
        self.stop.is_set.return_value = False
        self.stop.wait.return_value = False
        self.event = BattleRewards(self.window, self.input, self.stop)

    @patch('app.core.battle_rewards.reward_visible')
    def test_expiry_is_success_without_card_click(self, visible):
        visible.side_effect = [True, True, False, False]
        self.assertTrue(self.event.handle(object()))
        self.input.click.assert_not_called()
        self.input.mouse_up.assert_called_once()

    @patch('app.core.battle_rewards.reward_visible')
    def test_already_expired_screen_continues(self, visible):
        visible.return_value = False
        self.assertFalse(self.event.handle(object()))
        self.input.mouse_up.assert_not_called()

    @patch('app.core.battle_rewards.reward_visible')
    def test_stop_interrupts_countdown(self, visible):
        visible.return_value = True
        self.stop.wait.return_value = True
        with self.assertRaises(InterruptedError):
            self.event.handle(object())
        self.input.click.assert_not_called()

    @patch('app.core.battle_rewards.reward_visible')
    def test_missing_capture_is_not_dismissal(self, visible):
        visible.side_effect = [True, False, False]
        self.window.screenshot.side_effect = [None, object(), object()]
        self.assertTrue(self.event.handle(object()))
        self.assertEqual(self.window.screenshot.call_count, 3)

    @patch('app.core.battle_rewards.reward_visible')
    def test_all_milestones_are_repeatable(self, visible):
        for _ in (33, 66, 100):
            visible.side_effect = [True, False, False]
            self.assertTrue(self.event.handle(object()))
        self.input.click.assert_not_called()

    def test_ability_clicks_do_not_redetect_undeployed_templates(self):
        frame = np.zeros((731, 1299, 3), dtype=np.uint8)
        vision, config = Mock(), Mock()
        positions = {'queen.png': (450, 660), 'king.png': (550, 660)}
        vision.find_template.side_effect = lambda frame, name, **kw: positions.get(name, (None, None))
        strategy = AttackStrategy(self.input, vision, config, self.stop)
        strategy._get_hero_deploy_point = Mock(return_value=(800, 300))
        strategy.deploy_heroes(frame)
        ability_clicks = [c.args for c in self.input.click.call_args_list[-2:]]
        self.assertCountEqual(ability_clicks, list(positions.values()))
        self.assertEqual(sum(c.args[1]=='queen.png' for c in vision.find_template.call_args_list), 1)

    def test_exit_immediately_after_reward_clears(self):
        bot = Bot.__new__(Bot)
        bot.stop_event, bot.input, bot.window = self.stop, self.input, self.window
        bot.vision = Mock()
        bot.vision.find_template.return_value = (40, 570)
        bot._update_config_size = Mock()
        bot._search_region_for_template = Mock(return_value=None)
        bot._battle_rewards = Mock()
        bot._battle_rewards.handle.side_effect = [True, False]
        bot._wait_for_battle_end(False)
        self.input.click.assert_called_once_with(40, 570, pause=.1)
        bot.vision.find_template.assert_called_once()

    def test_shifted_ability_uses_live_portrait(self):
        frame = np.zeros((731, 1299, 3), dtype=np.uint8)
        tile = np.random.default_rng(7).integers(0, 255, (36, 36, 3), dtype=np.uint8)
        frame[640:676, 500:536] = tile
        strategy = AttackStrategy(self.input, Mock(), Mock(), self.stop)
        relocated = strategy._relocate_abilities([(450, 658, tile)], frame)
        self.assertEqual(relocated[0][:2], (518, 658))

    def test_unavailable_ability_after_reward_does_not_crash(self):
        frame = np.zeros((731, 1299, 3), dtype=np.uint8)
        vision = Mock()
        vision.find_template.side_effect = lambda f, name, **kw: (450, 660) if name=='queen.png' else (None,None)
        strategy = AttackStrategy(self.input, vision, Mock(), self.stop)
        strategy._get_hero_deploy_point = Mock(return_value=(800,300))
        strategy._reward_checkpoint = Mock(side_effect=[(frame,False)]*7+[(frame,True)])
        strategy._relocate_abilities = Mock(return_value=[])
        strategy.deploy_heroes(frame)
        self.assertEqual(self.input.click.call_count, 2)


if __name__ == '__main__':
    unittest.main()
