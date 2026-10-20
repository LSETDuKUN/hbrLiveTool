import gc
import tkinter as tk
import unittest

from hbr_live_app.components import RoundedEntry, RoundedSelect


class RoundedInputTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('400x150')

    def tearDown(self):
        self.root.update()
        self.root.destroy()
        gc.collect()

    def test_entry_survives_initial_focus_and_resize_repaints(self):
        value = tk.StringVar(self.root, value='15')
        field = RoundedEntry(self.root, textvariable=value)
        field.pack(fill='x')
        self.root.update()
        for width in (320, 390, 260):
            self.root.geometry(f'{width}x150')
            field._focus_in()
            field._focus_out()
            self.root.update()
            self.assertEqual(field.type(field._slot), 'window')
            self.assertTrue(field.entry.winfo_ismapped())
            self.assertGreater(field.entry.winfo_width(), 20)
            self.assertEqual(len(field.find_all()), 2)  # Background + entry.
        field.entry.delete(0, 'end')
        field.entry.insert(0, '65')
        self.assertEqual(value.get(), '65')
        value.set('100')
        self.assertEqual(field.entry.get(), '100')

    def test_select_current_and_user_selection_feed_bound_value(self):
        value = tk.StringVar(self.root, value='自动')
        field = RoundedSelect(self.root, textvariable=value, values=['自动', '启用', '禁用'])
        field.pack()
        selected = []
        field.bind('<<ComboboxSelected>>', lambda _: selected.append(field.current()))
        field.current(1)
        self.assertEqual(value.get(), '启用')
        self.assertEqual(selected, [])
        field._choose('禁用')
        self.assertEqual(value.get(), '禁用')
        self.assertEqual(selected, [2])
