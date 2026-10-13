"""Source this file in GDB/GEF, then run `ammo-scan 20`.

Find aligned 32-bit integers in writable memory, continue the game, and refine
the saved addresses after each Ctrl-C. Enter resumes; q ends the loop with the
game stopped. A numeric response retries the last candidates at that value.
Uses GDB's memory API; it never writes to the inferior or installs breakpoints.
"""
import json
from pathlib import Path
import struct

import gdb


def say(message):
    gdb.write("[ammo] " + message + "\n")


def number(text):
    value = int(text, 0)
    if not 0 <= value <= 0x7fffffff:
        raise ValueError("Use an integer between 0 and 2147483647.")
    return value


def stopped_inferior():
    inferior = gdb.selected_inferior()
    if not inferior.is_valid() or not inferior.pid:
        raise gdb.GdbError("Attach to the game and pause it first.")
    if inferior.connection is None or inferior.connection.type != "native":
        raise gdb.GdbError("This scanner requires a local Linux process.")
    if gdb.parameter("non-stop") or any(t.is_running() for t in inferior.threads()):
        raise gdb.GdbError("Pause the game in GDB's normal all-stop mode first.")
    return inferior


def writable_regions(pid, module=None):
    previous_end, previous_selected = 0, False
    for line in Path(f"/proc/{pid}/maps").read_text().splitlines():
        fields = line.split(maxsplit=5)
        start, end = (int(x, 16) for x in fields[0].split("-"))
        name = fields[5] if len(fields) > 5 else "[anonymous]"
        selected = (not module or module in name or
                    (previous_selected and start == previous_end and name == "[anonymous]"))
        previous_end, previous_selected = end, selected
        if selected and "r" in fields[1] and "w" in fields[1]:
            yield start, end, name


class AmmoScanner:
    def __init__(self):
        self.inferior = None
        self.pid = 0
        self.module = None
        self.fmt = "<i"
        self.value = None
        self.candidates = []
        self.regions = []
        self.history = []
        self.last_stop = None

    def require_session(self):
        if self.value is None:
            raise gdb.GdbError("Start a search with ammo-scan VALUE first.")
        target = stopped_inferior()
        if target != self.inferior or target.pid != self.pid:
            raise gdb.GdbError("The inferior changed. Start a new ammo-scan search.")
        return target

    def record(self, value, addresses, accepted=True, **details):
        self.history.append(dict(value=value, count=len(addresses),
                                 addresses=[hex(a) for a in addresses],
                                 accepted=accepted, **details))

    def start(self, value, module=None):
        target = stopped_inferior()
        endian = gdb.execute("show endian", to_string=True)
        fmt = "<i" if "little endian" in endian else ">i"
        packed = struct.pack(fmt, value)
        regions = list(writable_regions(target.pid, module))
        if not regions:
            raise gdb.GdbError("No readable/writable mappings match that module.")
        found, scanned, skipped = [], 0, 0
        say(f"Scanning writable memory for {value}; Ctrl-C cancels the initial scan.")
        for low, high, _ in regions:
            for start in range(low, high, 4 * 1024 * 1024):
                size = min(4 * 1024 * 1024, high - start)
                try:
                    data = bytes(target.read_memory(start, size))
                except gdb.MemoryError:
                    skipped += size
                    continue
                scanned += len(data)
                offset = data.find(packed)
                while offset != -1:
                    if (start + offset) % 4 == 0:
                        found.append(start + offset)
                    offset = data.find(packed, offset + 1)
        # Commit the complete result; an interrupted scan leaves old results intact.
        self.inferior, self.pid, self.module = target, target.pid, module
        self.fmt, self.regions, self.value = fmt, regions, value
        self.candidates, self.history = found, []
        self.record(value, found, scanned_bytes=scanned, skipped_bytes=skipped)
        say(f"Value {value}: {len(found)} candidates; scanned {scanned / 1048576:.1f} MiB.")
        if skipped:
            say(f"Skipped {skipped / 1048576:.1f} MiB that GDB could not read.")
        self.show()

    def refine(self, value, candidates=None):
        target = self.require_session()
        baseline = self.candidates if candidates is None else candidates
        packed = struct.pack(self.fmt, value)
        found = []
        for address in baseline:
            try:
                if bytes(target.read_memory(address, 4)) == packed:
                    found.append(address)
            except gdb.MemoryError:
                pass
        self.record(value, found, accepted=bool(found))
        if not found:
            say(f"No candidates contain {value}; kept the previous {len(self.candidates)} addresses.")
            say("Enter the actual clip count to retry, or q to inspect in GDB.")
            return False
        previous = len(baseline)
        self.candidates, self.value = found, value
        say(f"Value {value}: {previous} -> {len(found)} candidates.")
        self.show()
        return True

    def show(self, limit=20):
        visible = self.candidates if limit == 0 else self.candidates[:limit]
        for address in visible:
            region = next((r for r in self.regions if r[0] <= address < r[1]), None)
            label = f"{region[2]}+0x{address - region[0]:x}" if region else "[mapping changed]"
            say(f"0x{address:x}  {label}")
        if len(visible) < len(self.candidates):
            say(f"Showing {len(visible)} of {len(self.candidates)}; ammo-list 0 prints all.")

    def on_stop(self, event):
        self.last_stop = event

    def run(self):
        self.require_session()
        gdb.events.stop.connect(self.on_stop)
        try:
            with gdb.with_parameter("pagination", False):
                while self.candidates and self.value > 0:
                    self.last_stop = None
                    say(f"Running. Fire one shot, then Ctrl-C in GDB to filter for {self.value - 1}.")
                    try:
                        gdb.execute("continue", from_tty=True)
                    except KeyboardInterrupt:
                        # GDB versions differ in whether Ctrl-C also raises here.
                        pass
                    if not self.inferior.is_valid() or self.inferior.pid != self.pid:
                        say("Game exited or detached; saved results are retained.")
                        return
                    if not isinstance(self.last_stop, gdb.SignalEvent) or self.last_stop.stop_signal != "SIGINT":
                        say("Stopped at another breakpoint/signal. Results retained; returning to GDB.")
                        return
                    baseline = self.candidates
                    self.refine(self.value - 1, baseline)
                    while True:
                        answer = input("[ammo] Enter = resume; q = finish; number = retry count: ").strip()
                        if answer.lower() in ("q", "quit", "stop"):
                            say("Search finished; game stays paused. Use ammo-list or ammo-save FILE.")
                            return
                        if not answer:
                            break
                        try:
                            # Retry the pre-filter addresses, including candidates
                            # discarded by an incorrect expected clip count.
                            self.refine(number(answer), baseline)
                        except ValueError as error:
                            say(str(error))
                say("Search reached zero or has no candidates; game stays paused.")
        except (KeyboardInterrupt, EOFError):
            say("Search finished; results retained and game stays paused.")
        finally:
            gdb.events.stop.disconnect(self.on_stop)


class AmmoCommand(gdb.Command):
    """Base for the Hack Pack ammo commands."""
    def __init__(self, name, scanner):
        super().__init__(name, gdb.COMMAND_USER)
        self.scanner = scanner

    def invoke(self, argument, from_tty):
        self.dont_repeat()
        try:
            self.perform(gdb.string_to_argv(argument))
        except (ValueError, OSError) as error:
            raise gdb.GdbError(str(error))
        except KeyboardInterrupt:
            say("Scan cancelled; completed results are retained.")


class AmmoScan(AmmoCommand):
    """ammo-scan [VALUE=20] [MODULE]: initial scan, then interactive continue/refine loop."""
    def perform(self, arguments):
        if len(arguments) > 2:
            raise ValueError("Usage: ammo-scan [VALUE=20] [MODULE]")
        self.scanner.start(number(arguments[0]) if arguments else 20,
                           arguments[1] if len(arguments) == 2 else None)
        if self.scanner.candidates:
            self.scanner.run()
        else:
            say("No candidates; game stays paused. Check the displayed count and module.")


class AmmoRun(AmmoCommand):
    """ammo-run: resume the continue/refine loop using saved candidates."""
    def perform(self, arguments):
        if arguments:
            raise ValueError("Usage: ammo-run")
        self.scanner.run()


class AmmoRefine(AmmoCommand):
    """ammo-refine VALUE: filter saved candidates once, leaving the game paused."""
    def perform(self, arguments):
        if len(arguments) != 1:
            raise ValueError("Usage: ammo-refine VALUE")
        self.scanner.refine(number(arguments[0]))


class AmmoList(AmmoCommand):
    """ammo-list [LIMIT=20]: list retained addresses; LIMIT=0 prints all."""
    def perform(self, arguments):
        if len(arguments) > 1:
            raise ValueError("Usage: ammo-list [LIMIT=20]")
        if self.scanner.value is None:
            raise ValueError("Start a search with ammo-scan VALUE first.")
        say(f"Last accepted value {self.scanner.value}: {len(self.scanner.candidates)} addresses.")
        self.scanner.show(number(arguments[0]) if arguments else 20)


class AmmoSave(AmmoCommand):
    """ammo-save FILE: export search history and retained candidate addresses as JSON."""
    def perform(self, arguments):
        if len(arguments) != 1 or self.scanner.value is None:
            raise ValueError("Start a search, then use ammo-save FILE.")
        scanner = self.scanner
        result = dict(pid=scanner.pid, type="int32", alignment=4,
                      endian="little" if scanner.fmt == "<i" else "big",
                      module=scanner.module, value=scanner.value,
                      addresses=[hex(a) for a in scanner.candidates], history=scanner.history)
        Path(arguments[0]).expanduser().write_text(json.dumps(result, indent=2) + "\n")
        say("Saved " + arguments[0])


if not hasattr(gdb, "_hackpack_ammo_scanner"):
    gdb._hackpack_ammo_scanner = AmmoScanner()
    for name, command in (("ammo-scan", AmmoScan), ("ammo-run", AmmoRun),
                          ("ammo-refine", AmmoRefine), ("ammo-list", AmmoList),
                          ("ammo-save", AmmoSave)):
        command(name, gdb._hackpack_ammo_scanner)
say("Loaded. Pause the game, then ammo-scan 20. Help: help ammo-scan")
