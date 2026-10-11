from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge"))
import summon


class SummonTest(unittest.TestCase):
    def test_return_to_named_workspace(self):
        monitor = {"name": "DP-4", "activeWorkspace": {"id": -1337, "name": "tv"}}
        with patch.object(summon, "dispatch") as dispatch:
            summon.return_to(monitor)
        self.assertEqual(dispatch.call_args_list[0].args[0],
                         'hl.dsp.focus({ monitor = "DP-4" })')
        self.assertEqual(dispatch.call_args_list[1].args[0],
                         'hl.dsp.focus({ workspace = "name:tv" })')

    def test_restore_returns_to_original_tab_and_window(self):
        with tempfile.TemporaryDirectory() as runtime:
            state_file = Path(runtime) / "state.json"
            state_file.write_text("{}")
            origin = {"address": "0xapp", "workspace": {"name": "1"}}
            chrome = {"address": "0xchrome", "workspace": {"name": summon.LOCKER}}
            placeholder = {"address": "0xslot", "workspace": {"name": "2"}}
            current = {"name": "DP-1", "focused": True,
                       "activeWorkspace": {"id": 3, "name": "3"},
                       "specialWorkspace": {"name": ""}}
            state = {"address": "0xchrome", "windowId": 7, "workspace": "2",
                     "tiled": True, "previousTabId": 42, "originAddress": "0xapp",
                     "originMonitor": {"name": "DP-1",
                                       "activeWorkspace": {"id": 1, "name": "1"}}}
            with patch.object(summon, "STATE", state_file), \
                 patch.object(summon, "snapshot", return_value=[current]), \
                 patch.object(summon, "window", side_effect=lambda addr: origin if addr == "0xapp" else chrome), \
                 patch.object(summon, "slot", return_value=placeholder), \
                 patch.object(summon, "geometry", side_effect=[{"0xslot": [[0, 0], [100, 100]]},
                                                              {"0xchrome": [[0, 0], [100, 100]]}]), \
                 patch.object(summon, "dispatch") as dispatch, \
                 patch.object(summon, "plugin"), \
                 patch.object(summon, "call", side_effect=[[{"id": 42, "windowId": 7}], True]) as call:
                summon.restore(state)
            call.assert_any_call("activate", tabId=42)
            self.assertEqual(dispatch.call_args_list[-1].args[0],
                             'hl.dsp.focus({ window = "address:0xapp" })')
            self.assertFalse(state_file.exists())

    def test_restore_with_no_summoned_window_is_a_noop(self):
        with tempfile.TemporaryDirectory() as runtime:
            with patch.object(summon, "STATE", Path(runtime) / "missing"), \
                 patch.object(summon, "dispatch") as dispatch:
                summon.restore_current()
            dispatch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
