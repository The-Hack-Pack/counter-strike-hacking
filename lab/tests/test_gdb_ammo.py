"""Exercise actual GDB continue/SIGINT/input behavior on a controlled inferior."""
import fcntl
import json
import os
from pathlib import Path
import pty
import re
import select
import shutil
import signal
import subprocess
import tempfile
import termios
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "tools/gdb_ammo.py"
FIXTURE = r'''
#include <signal.h>
#include <unistd.h>
volatile int fixture_clip = 20;
volatile int fixture_mirror = 20;
volatile int fixture_static = 20;
volatile int fixture_decoy = 20;
volatile int fixture_bss[32768];
static void shot(int unused) {
    --fixture_clip;
    fixture_mirror = fixture_clip;
    fixture_bss[16384] = fixture_clip;
    fixture_decoy = fixture_clip == 18 ? 19 : 0;
    write(1, "FIXTURE_SHOT\n", 13);
}
void fixture_ready(void) {}
int main(void) {
    signal(SIGUSR1, shot);
    fixture_bss[16384] = 20;
    fixture_bss[16385] = 20;
    fixture_ready();
    write(1, "FIXTURE_RUNNING\n", 16);
    for (;;) pause();
}
'''


def controlling_terminal():
    os.setsid()
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)


@unittest.skipUnless(os.name == "posix" and shutil.which("gdb") and shutil.which("gcc"),
                     "Requires Linux, GDB with Python, and GCC")
class GDBAmmoTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="hackpack-gdb-test-")
        self.root = Path(self.work.name)
        source = self.root / "fixture.c"
        source.write_text(FIXTURE)
        self.fixture = self.root / "ammo-fixture"
        subprocess.run(["gcc", "-g", "-O0", str(source), "-o", str(self.fixture)], check=True)
        self.master, slave = pty.openpty()
        options = ["-q"] if os.getenv("HACKPACK_TEST_GEF") else ["-nx", "-q"]
        self.process = subprocess.Popen(["gdb", *options, str(self.fixture)],
                                        stdin=slave, stdout=slave, stderr=slave,
                                        preexec_fn=controlling_terminal)
        os.close(slave)
        self.pending = ""
        self.transcript = ""
        self.pid = 0
        self.expect(r"\(gdb\) |gef.*?➤")
        self.command("set pagination off")
        self.command("set confirm off")
        self.command("handle SIGUSR1 nostop noprint pass")
        self.command("break fixture_ready")
        self.command("run")
        self.send('python print("FIXTURE_PID:%d" % gdb.selected_inferior().pid)')
        self.pid = int(self.expect(r"FIXTURE_PID:(\d+)").group(1))
        self.expect(r"\(gdb\) |gef.*?➤")
        self.command("source " + str(SCRIPT))
        self.addresses = {}
        for name in ("fixture_clip", "fixture_mirror", "fixture_static", "fixture_decoy", "fixture_bss[16384]"):
            self.send('python print("FIXTURE_ADDRESS:0x%x" % int(gdb.parse_and_eval("&' + name + '")))')
            self.addresses[name] = self.expect(r"FIXTURE_ADDRESS:(0x[0-9a-f]+)").group(1)
            self.expect(r"\(gdb\) |gef.*?➤")

    def tearDown(self):
        if hasattr(self, "process"):
            if self.process.poll() is None:
                os.write(self.master, b"\x03q\nquit\n")
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            if self.pid and Path(f"/proc/{self.pid}/exe").resolve() == self.fixture:
                os.kill(self.pid, signal.SIGKILL)
            os.close(self.master)
        if hasattr(self, "work"):
            self.work.cleanup()

    def send(self, text):
        os.write(self.master, (text + "\n").encode())

    def expect(self, pattern, timeout=12):
        deadline = time.monotonic() + timeout
        while True:
            match = re.search(pattern, self.pending)
            if match:
                self.pending = self.pending[match.end():]
                return match
            if time.monotonic() >= deadline:
                self.fail("GDB did not emit " + pattern + "\n" + self.transcript[-6000:])
            if select.select([self.master], [], [], .1)[0]:
                try:
                    chunk = os.read(self.master, 65536).decode(errors="replace")
                except OSError:
                    self.fail("GDB closed its terminal\n" + self.transcript[-6000:])
                self.pending += chunk
                self.transcript += chunk

    def command(self, text):
        self.send(text)
        self.expect(r"\(gdb\) |gef.*?➤")

    def fire(self, count=1):
        for _ in range(count):
            os.kill(self.pid, signal.SIGUSR1)
            self.expect(r"(?m)^FIXTURE_SHOT\r?$")

    def finish_and_save(self):
        self.send("q")
        self.expect(r"\(gdb\) |gef.*?➤")
        record = self.root / "search.json"
        self.command("ammo-save " + str(record))
        result = json.loads(record.read_text())
        self.command("ammo-list 0")
        self.command("source " + str(SCRIPT))  # Reloading must retain the session.
        return result

    def test_continue_refine_and_quit(self):
        self.send("ammo-scan 20")
        self.expect("Running. Fire one shot")
        self.expect(r"(?m)^FIXTURE_RUNNING\r?$")
        for value in (19, 18):
            self.fire()
            os.write(self.master, b"\x03")
            self.expect(f"Value {value}: ")
            self.expect("number = retry count: ")
            if value == 19:
                self.send("")
                self.expect("Running. Fire one shot")
        result = self.finish_and_save()
        self.assertEqual([r["value"] for r in result["history"]], [20, 19, 18])
        self.assertEqual(result["value"], 18)
        self.assertIn(self.addresses["fixture_static"], result["history"][0]["addresses"])
        self.assertNotIn(self.addresses["fixture_static"], result["addresses"])
        for name in ("fixture_clip", "fixture_mirror", "fixture_bss[16384]"):
            self.assertIn(self.addresses[name], result["addresses"])
        self.assertLess(len(result["addresses"]), result["history"][0]["count"])

    def test_extra_shots_can_retry_without_losing_candidates(self):
        self.send("ammo-scan 20 ammo-fixture")
        self.expect("Running. Fire one shot")
        self.expect(r"(?m)^FIXTURE_RUNNING\r?$")
        self.fire(2)
        os.write(self.master, b"\x03")
        self.expect("Value 19: ")
        self.expect("number = retry count: ")
        self.send("18")
        self.expect("Value 18: ")
        self.expect("number = retry count: ")
        result = self.finish_and_save()
        self.assertEqual(result["value"], 18)
        self.assertTrue(result["history"][1]["accepted"])
        self.assertIn(self.addresses["fixture_decoy"], result["history"][1]["addresses"])
        self.assertNotIn(self.addresses["fixture_decoy"], result["addresses"])
        self.assertEqual(result["module"], "ammo-fixture")
        self.assertIn(self.addresses["fixture_clip"], result["addresses"])
        self.assertIn(self.addresses["fixture_bss[16384]"], result["addresses"])

    def test_no_shot_preserves_candidates(self):
        self.send("ammo-scan 20 ammo-fixture")
        self.expect("Running. Fire one shot")
        self.expect(r"(?m)^FIXTURE_RUNNING\r?$")
        os.write(self.master, b"\x03")
        self.expect("No candidates contain 19; kept the previous")
        self.expect("number = retry count: ")
        result = self.finish_and_save()
        self.assertEqual(result["value"], 20)
        self.assertFalse(result["history"][1]["accepted"])
        self.assertEqual(result["addresses"], result["history"][0]["addresses"])


if __name__ == "__main__":
    unittest.main()
