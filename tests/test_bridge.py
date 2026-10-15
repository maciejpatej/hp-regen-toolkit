"""Offline checks: every CUPS subprocess is mocked, never run on the host."""

import subprocess
import unittest
from unittest.mock import patch

from hp_regen.bridge import bridge_plan, install_queue, list_queues


URI = "ipp://192.168.1.42/ipp/print"
NORMALIZED_URI = "ipp://192.168.1.42:631/ipp/print"


def completed(args, **_kwargs):
    return subprocess.CompletedProcess(args, 0, "", "")


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.which_patch = patch("hp_regen.bridge.shutil.which", side_effect=lambda name: "/usr/bin/" + name)
        self.run_patch = patch("hp_regen.bridge.subprocess.run", side_effect=completed)
        self.which = self.which_patch.start()
        self.run = self.run_patch.start()
        self.addCleanup(self.which_patch.stop)
        self.addCleanup(self.run_patch.stop)

    def test_plan_is_non_mutating_and_normalizes_uri(self):
        plan = bridge_plan(URI, "HP_regen-1")
        self.assertTrue(plan["supported"])
        self.assertEqual(plan["command"], ["/usr/bin/lpadmin", "-p", "HP_regen-1", "-E", "-v", NORMALIZED_URI, "-m", "everywhere"])
        self.assertTrue(any("IPP Everywhere" in line for line in plan["instructions"]))
        self.run.assert_not_called()

    def test_malformed_uri_rejected_before_any_subprocess(self):
        for uri in ("https://192.168.1.42/", "ipp://8.8.8.8/", "ipp://user:secret@192.168.1.42/", "ipp://192.168.1.42:9100/", "ipp://printer.local/", None):
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                install_queue(uri, "HP_regen", acknowledged=True)
        self.run.assert_not_called()

    def test_unsafe_queue_names_rejected_before_any_subprocess(self):
        for name in ("", "-all", "1printer", "queue;echo", "two queues", "żółw", "A" * 64, "queue\n", None):
            with self.subTest(name=name), self.assertRaises(ValueError):
                bridge_plan(URI, name)
            with self.subTest(name=name), self.assertRaises(ValueError):
                install_queue(URI, name, acknowledged=True)
        self.run.assert_not_called()

    def test_acknowledgement_requires_literal_true(self):
        for ack in (False, None, 1, "true", []):
            with self.subTest(ack=ack):
                result = install_queue(URI, "HP_regen", acknowledged=ack)
                self.assertFalse(result["installed"])
                self.assertIn("potwierdzenie", result["output"])
        self.run.assert_not_called()

    def test_local_queue_inventory_is_bounded(self):
        self.run.return_value = subprocess.CompletedProcess([], 0, "device for HP: usb://HP/model\ndevice for Bridge: ipp://192.168.1.42/ipp/print\n", "")
        self.run.side_effect = None
        result = list_queues()
        self.assertTrue(result["available"])
        self.assertEqual(result["queues"], [{"name": "HP", "uri": "usb://HP/model"}, {"name": "Bridge", "uri": URI}])
        args, kwargs = self.run.call_args
        self.assertEqual(args[0], ["/usr/bin/lpstat", "-v"])
        self.assertEqual(kwargs["timeout"], 5)
        self.assertEqual(kwargs["env"]["CUPS_SERVER"], "localhost")
        self.assertFalse(kwargs.get("shell", False))

    def test_empty_cups_inventory(self):
        self.run.side_effect = None
        self.run.return_value = subprocess.CompletedProcess([], 1, "", "lpstat: No destinations added.")
        self.assertEqual(list_queues(), {"available": True, "queues": [], "warnings": []})

    def test_too_many_queues_refuses_inventory(self):
        self.run.side_effect = None
        self.run.return_value = subprocess.CompletedProcess([], 0, "\n".join(f"device for Q{i}: usb://printer" for i in range(257)), "")
        result = list_queues()
        self.assertFalse(result["available"])
        self.assertEqual(len(result["queues"]), 256)

    def test_existing_queue_and_case_variant_never_overwritten(self):
        self.run.side_effect = None
        self.run.return_value = subprocess.CompletedProcess([], 0, "device for HP_REGEN: usb://printer\n", "")
        result = install_queue(URI, "hp_regen", acknowledged=True)
        self.assertFalse(result["installed"])
        self.assertIn("już istnieje", result["output"])
        self.assertEqual(self.run.call_count, 1)
        self.assertEqual(self.run.call_args.args[0][0], "/usr/bin/lpstat")

    def test_second_collision_check_prevents_late_existing_queue(self):
        self.run.side_effect = [
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 0, "device for HP_regen: usb://printer\n", ""),
        ]
        result = install_queue(URI, "HP_regen", acknowledged=True)
        self.assertFalse(result["installed"])
        self.assertEqual(self.run.call_count, 2)

    def test_missing_tools_show_instructions_without_running_shell(self):
        self.which.side_effect = None
        self.which.return_value = None
        self.assertFalse(list_queues()["available"])
        plan = bridge_plan(URI, "HP_regen")
        self.assertFalse(plan["supported"])
        self.assertEqual(plan["command"], [])
        self.assertTrue(any("Windows" in line for line in plan["instructions"]))
        self.assertFalse(install_queue(URI, "HP_regen", acknowledged=True)["installed"])
        self.run.assert_not_called()

    def test_missing_inventory_tool_fails_closed(self):
        self.which.side_effect = lambda name: "/usr/bin/lpadmin" if name == "lpadmin" else None
        result = install_queue(URI, "HP_regen", acknowledged=True)
        self.assertFalse(result["installed"])
        self.assertIn("sprawdzić", result["output"])
        self.run.assert_not_called()

    def test_inventory_timeout_and_nonzero_fail_closed(self):
        for response in (subprocess.TimeoutExpired(["lpstat"], 5), subprocess.CompletedProcess([], 1, "", "cupsd unreachable"), OSError("missing executable")):
            with self.subTest(response=response):
                self.run.side_effect = response if isinstance(response, Exception) else None
                if not isinstance(response, Exception):
                    self.run.return_value = response
                result = install_queue(URI, "HP_regen", acknowledged=True)
                self.assertFalse(result["installed"])
                self.assertTrue(result["output"])
        self.assertTrue(all(call.args[0][0] == "/usr/bin/lpstat" for call in self.run.call_args_list))

    def test_success_runs_no_sudo_no_shell_after_two_inventory_checks(self):
        result = install_queue(URI, "HP_regen", acknowledged=True)
        self.assertTrue(result["installed"])
        self.assertEqual(result["queue_name"], "HP_regen")
        self.assertEqual(self.run.call_count, 3)
        args, kwargs = self.run.call_args
        self.assertEqual(args[0], bridge_plan(URI, "HP_regen")["command"])
        self.assertNotIn("sudo", args[0])
        self.assertEqual(kwargs["timeout"], 15)
        self.assertFalse(kwargs.get("shell", False))
        self.assertEqual(kwargs["env"]["CUPS_SERVER"], "localhost")

    def test_install_timeout_reports_uncertain_side_effect(self):
        self.run.side_effect = [completed([], timeout=5), completed([], timeout=5), subprocess.TimeoutExpired(["lpadmin"], 15, stderr=b"timeout detail")]
        result = install_queue(URI, "HP_regen", acknowledged=True)
        self.assertFalse(result["installed"])
        self.assertIn("mogło utworzyć", result["output"])
        self.assertIn("timeout detail", result["output"])

    def test_install_nonzero_and_oserror_are_informative_and_bounded(self):
        for last in (subprocess.CompletedProcess([], 1, "", "permission denied" * 1000), OSError("missing executable")):
            with self.subTest(last=last):
                self.run.side_effect = [completed([]), completed([]), last]
                result = install_queue(URI, "HP_regen", acknowledged=True)
                self.assertFalse(result["installed"])
                self.assertTrue(result["output"])
                self.assertLessEqual(len(result["output"]), 4000)

    def test_inventory_warning_is_bounded(self):
        self.run.side_effect = None
        self.run.return_value = subprocess.CompletedProcess([], 1, "", "error " * 1000)
        result = list_queues()
        self.assertFalse(result["available"])
        self.assertLessEqual(len(result["warnings"][0]), 4000)


if __name__ == "__main__":
    unittest.main()
