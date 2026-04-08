import unittest

from os_simulator.main import Simulator


class SimulatorCommandTests(unittest.TestCase):
    def test_medium_style_fix_flow(self) -> None:
        sim = Simulator()

        status_before = sim.execute("status nginx")
        restart_before = sim.execute("restart nginx")
        edit_result = sim.execute("edit /etc/nginx/nginx.conf")
        restart_after = sim.execute("restart nginx")
        status_after = sim.execute("status nginx")

        self.assertIn("failed", status_before)
        self.assertIn("invalid config", restart_before)
        self.assertIn("Edited /etc/nginx/nginx.conf", edit_result)
        self.assertIn("restarted", restart_after)
        self.assertEqual("nginx is running", status_after)

    def test_kill_reduces_process_list(self) -> None:
        sim = Simulator()
        ps_before = sim.execute("ps")
        kill_result = sim.execute("kill 202")
        ps_after = sim.execute("ps")

        self.assertIn("202", ps_before)
        self.assertIn("Process 202 terminated", kill_result)
        self.assertNotIn("202", ps_after)

    def test_rm_reduces_disk_usage(self) -> None:
        sim = Simulator()
        before = sim.get_state().resources.disk
        rm_result = sim.execute("rm /var/log/nginx/error.log")
        after = sim.get_state().resources.disk

        self.assertIn("Removed /var/log/nginx/error.log", rm_result)
        self.assertLess(after, before)

    def test_restart_blocked_when_disk_too_high(self) -> None:
        sim = Simulator()

        # Fill disk by editing mysql config repeatedly until >95%.
        for _ in range(600):
            if sim.get_state().resources.disk > 95.0:
                break
            sim.execute("edit /etc/mysql/my.cnf")

        result = sim.execute("restart mysql")
        self.assertIn("disk usage too high", result)


if __name__ == "__main__":
    unittest.main()
