"""Check decision telemetry and the read-only live map's HTTP lifecycle."""
import copy
import json
from pathlib import Path
import random
import socket
import sys
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))
from bot import Brain, Navigation
from bot_viewer import BotViewer, load_overview


class DecisionTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        path = Path(self.work.name) / 'graph.json'
        nodes = [{'id': i, 'flags': 16 if i == 2 else 0, 'origin': [i * 200, 0, 0],
                  'links': [{'to': i + 1}] if i < 2 else []} for i in range(3)]
        path.write_text(json.dumps({'nodes': nodes}))
        self.brain = Brain(Navigation(path), rng=random.Random(7))
        self.state = {'local': {'alive': True, 'team': 1, 'slot': 1, 'origin': [0, 0, 0],
                               'view': [0, 0, 0], 'eye': [0, 0, 17], 'punch': [0, 0, 0],
                               'velocity': [0, 0, 0], 'clip_hud': 30, 'ground': True},
                      'players': [{'slot': 2, 'team': 2, 'dead': False, 'age': 0,
                                   'fresh': True, 'visible': False, 'origin': [400, 0, 0],
                                   'head': [400, 0, 28]}], 'probes': [1] * 8}

    def tearDown(self):
        self.work.cleanup()

    def test_pursuit_target_persists_between_plans(self):
        self.brain.step(self.state, now=10)
        first_route = list(self.brain.route)
        self.brain.step(self.state, now=10.1)
        self.assertEqual((self.brain.mode, self.brain.target, self.brain.goal), ('pursue', 2, 2))
        self.assertEqual(self.brain.route, first_route)

    def test_leaving_engagement_restores_route_decision(self):
        self.brain.step(self.state, now=10)
        self.state['players'][0]['visible'] = True
        self.brain.step(self.state, now=10.1)
        self.assertEqual(self.brain.mode, 'engage')
        self.state['players'][0]['visible'] = False
        self.brain.step(self.state, now=10.2)
        self.assertEqual((self.brain.mode, self.brain.target), ('pursue', 2))

    def test_dead_bot_clears_route_and_target(self):
        self.brain.step(self.state, now=10)
        self.state['local']['alive'] = False
        self.assertEqual(self.brain.step(self.state, now=10.1)[2:], (0, 0, 0))
        self.assertEqual((self.brain.mode, self.brain.route, self.brain.goal, self.brain.target),
                         ('waiting', [], None, None))

    def test_stalled_navigation_jumps_and_sidesteps_then_releases_jump(self):
        self.brain.step(self.state, now=10)
        self.assertFalse(self.brain.step(self.state, now=11)[4] & 2)
        action = self.brain.step(self.state, now=11.3)
        self.assertTrue(action[4] & 2)
        self.assertNotEqual(action[3], 0)
        self.assertEqual(self.brain.mode, 'unstick')
        self.assertFalse(self.brain.step(self.state, now=11.4)[4] & 2)
        self.assertFalse(self.brain.step(self.state, now=11.9)[4] & 2)
        self.assertTrue(self.brain.step(self.state, now=12.8)[4] & 2)

    def test_vertical_bobbing_and_small_jitter_do_not_hide_a_stall(self):
        self.brain.step(self.state, now=10)
        self.state['local']['origin'] = [2, -2, 24]
        self.brain.step(self.state, now=10.5)
        self.state['local']['origin'] = [0, 0, 0]
        self.assertTrue(self.brain.step(self.state, now=11.3)[4] & 2)

    def test_progress_delays_recovery(self):
        self.brain.step(self.state, now=10)
        self.state['local']['origin'] = [80, 0, 0]
        self.brain.step(self.state, now=11)
        self.assertFalse(self.brain.step(self.state, now=11.3)[4] & 2)
        self.assertEqual(self.brain.mode, 'pursue')

    def test_airborne_bot_waits_for_landing_before_recovery_jump(self):
        self.brain.step(self.state, now=10)
        self.state['local']['ground'] = False
        self.assertFalse(self.brain.step(self.state, now=11.3)[4] & 2)
        self.state['local']['ground'] = True
        self.assertTrue(self.brain.step(self.state, now=11.4)[4] & 2)

    def test_recovery_chooses_the_open_side(self):
        self.state['probes'][2] = 1
        self.state['probes'][6] = 0
        self.brain.step(self.state, now=10)
        self.assertLess(self.brain.step(self.state, now=11.3)[3], 0)

    def test_engagement_and_death_reset_stuck_tracking(self):
        for pause in ('engage', 'dead'):
            with self.subTest(pause=pause):
                self.brain.step(self.state, now=10)
                if pause == 'engage':
                    self.state['players'][0]['visible'] = True
                else:
                    self.state['local']['alive'] = False
                self.brain.step(self.state, now=15)
                self.state['players'][0]['visible'] = False
                self.state['local']['alive'] = True
                self.assertFalse(self.brain.step(self.state, now=20)[4] & 2)

    def test_changed_waypoint_starts_a_new_progress_timer(self):
        self.brain.step(self.state, now=10)
        self.state['local']['origin'] = [200, 0, 0]
        self.assertFalse(self.brain.step(self.state, now=11.3)[4] & 2)
        self.assertEqual(self.brain.route, [2])


class LiveMapTests(unittest.TestCase):
    def test_state_and_graph_share_the_controllers_snapshot(self):
        nodes = [{'id': 0, 'origin': [0, 0, 0], 'links': []}]
        viewer = BotViewer(nodes, 'mahaloz-bot', 0)
        try:
            with urlopen(viewer.url + 'state') as response:
                initial = json.load(response)
                self.assertEqual(initial, {'name': 'mahaloz-bot', 'snapshot': None, 'age': None})
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
            snapshot = {'name': 'mahaloz-bot', 'route': [0], 'goal': 0, 'target': 2,
                        'state': {'local': {'origin': [1, 2, 3]}}}
            viewer.update(copy.deepcopy(snapshot))
            with urlopen(viewer.url + 'state') as response:
                result = json.load(response)
            self.assertEqual(result['snapshot'], snapshot)
            self.assertGreaterEqual(result['age'], 0)
            with urlopen(viewer.url + 'graph') as response:
                self.assertEqual(json.load(response), {'nodes': nodes, 'overview': None})
            with urlopen(viewer.url) as response:
                self.assertIn(b'Waiting for bot telemetry', response.read())
            with self.assertRaises(HTTPError) as error:
                urlopen(viewer.url + 'missing')
            self.assertEqual(error.exception.code, 404)
            port = viewer._server.server_port
            self.assertEqual(viewer._server.server_address[0], '127.0.0.1')
        finally:
            viewer.close()
        with socket.socket() as client:
            self.assertNotEqual(client.connect_ex(('127.0.0.1', port)), 0)

    def test_missing_overview_falls_back_to_waypoint_graph(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(load_overview(directory), (None, None))
        self.assertEqual(load_overview(None), (None, None))

    def test_overview_reads_world_coordinates_and_bitmap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'cstrike' / 'overviews'
            root.mkdir(parents=True)
            (root / 'de_dust2.txt').write_text('// ZOOM 99\nglobal { ZOOM 1.5 ORIGIN -223 1097 -192 ROTATED 0 }')
            (root / 'de_dust2.bmp').write_bytes(b'BMtest')
            overview, bitmap = load_overview(directory)
            self.assertEqual(overview, {'zoom': 1.5, 'origin': [-223, 1097], 'rotated': False})
            self.assertEqual(bitmap, b'BMtest')


if __name__ == '__main__':
    unittest.main()
