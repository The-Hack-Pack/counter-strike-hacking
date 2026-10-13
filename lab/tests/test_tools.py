"""Verify reversible binary edits, refusal paths, and typed process-memory writes."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

LAB=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(LAB/'tools'))
from patch_clip import patch, BEFORE, AFTER, MANIFEST
from memscan import Memory

class BinaryPatchTests(unittest.TestCase):
    def setUp(self):
        self.work=tempfile.TemporaryDirectory(prefix='hackpack-test-')
        self.path=Path(self.work.name)/'client.so';shutil.copy2(LAB/'dist/client_amd64.so',self.path)
        self.original=self.path.read_bytes()
    def tearDown(self):self.work.cleanup()
    def test_exact_edit_and_bit_identical_undo(self):
        record=patch(self.path);changed=self.path.read_bytes();offset=record['offset']
        self.assertEqual(self.original[offset:offset+6],BEFORE)
        self.assertEqual(changed,self.original[:offset]+AFTER+self.original[offset+6:])
        patch(self.path,undo=True);self.assertEqual(self.path.read_bytes(),self.original)
    def test_unknown_build_is_not_written(self):
        tampered=self.original[:-1]+bytes([self.original[-1]^1]);self.path.write_bytes(tampered)
        with self.assertRaisesRegex(ValueError,'hash'):patch(self.path)
        self.assertEqual(self.path.read_bytes(),tampered)
        self.assertFalse(Path(str(self.path)+'.clip-original').exists())
    def test_undo_refuses_unrelated_changes(self):
        patch(self.path);changed=self.path.read_bytes();changed=changed[:-1]+bytes([changed[-1]^1]);self.path.write_bytes(changed)
        with self.assertRaisesRegex(ValueError,'changed'):patch(self.path,undo=True)
        self.assertEqual(self.path.read_bytes(),changed)

class ProcessMemoryTests(unittest.TestCase):
    def setUp(self):self.memory=Memory(os.getpid())
    def tearDown(self):self.memory.close()
    def test_selected_typed_address_only(self):
        values=(ctypes.c_int*2)(27,123456);address=ctypes.addressof(values)
        result=self.memory.write(address,'int','99')
        self.assertEqual(result['before'],27);self.assertEqual(list(values),[99,123456])
    def test_readonly_mapping_is_rejected(self):
        libc=ctypes.CDLL(None);address=ctypes.cast(libc.puts,ctypes.c_void_p).value
        with self.assertRaisesRegex(ValueError,'writable'):self.memory.write(address,'int','0')

if __name__=='__main__':unittest.main()
