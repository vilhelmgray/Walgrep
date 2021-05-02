#!/usr/bin/env python3
# Copyright (C) 2021 William Breathitt Gray
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango
import io
import os.path
import queue
import re
import threading
import zipfile

class Walgrep(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="Walgrep - ZIP file search utility", default_height=480, default_width=640)
        self.set_border_width(10)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(vbox)

        searchBox = Gtk.Box(spacing=6)
        vbox.pack_start(searchBox, False, False, 0)
        pathLabel = Gtk.Label(label="Path:")
        self.zipEntry = Gtk.Entry()
        selectFileButton = Gtk.Button(label="File")
        selectFileButton.connect("clicked", self.select_zip, Gtk.FileChooserAction.OPEN)
        selectFolderButton = Gtk.Button(label="Folder")
        selectFolderButton.connect("clicked", self.select_zip, Gtk.FileChooserAction.SELECT_FOLDER)
        searchBox.pack_start(pathLabel, False, False, 0)
        searchBox.pack_start(self.zipEntry, True, True, 0)
        searchBox.pack_start(selectFileButton, False, False, 0)
        searchBox.pack_start(selectFolderButton, False, False, 0)

        self.recurseButton = Gtk.CheckButton(label="Recurse into subdirectories")
        vbox.pack_start(self.recurseButton, False, False, 0)

        patternBox = Gtk.Box(spacing=6)
        vbox.pack_start(patternBox, False, False, 0)
        patternLabel = Gtk.Label(label="Pattern:")
        self.patternEntry = Gtk.Entry()
        self.resultsQueue = queue.SimpleQueue()
        self.searching = 0
        self.searchButton = Gtk.Button(label="Search")
        self.searchButton.connect("clicked", self.search_toggle)
        patternBox.pack_start(patternLabel, False, False, 0)
        patternBox.pack_start(self.patternEntry, True, True, 0)
        patternBox.pack_start(self.searchButton, False, False, 0)

        self.filenameButton = Gtk.CheckButton(label="Toggle filename only search")
        vbox.pack_start(self.filenameButton, False, False, 0)

        progressBox = Gtk.Box(spacing=6)
        vbox.pack_start(progressBox, False, False, 0)
        progressLabel = Gtk.Label(label="Progress:")
        self.progress = Gtk.ProgressBar(ellipsize=Pango.EllipsizeMode.MIDDLE, text="", show_text=True)
        self.status = ""
        self.statusLock = threading.Lock()
        self.matches = 0
        self.progress.set_text(self.status)
        self.progress.set_show_text(True)
        progressBox.pack_start(progressLabel, False, False, 0)
        progressBox.pack_start(self.progress, True, True, 0)

        scrolledWindow = Gtk.ScrolledWindow()
        vbox.pack_start(scrolledWindow, True, True, 0)

        self.results = Gtk.TreeStore(str, str, str, str)
        resultsTree = Gtk.TreeView(model=Gtk.TreeModelSort(model=self.results))

        iconRenderer = Gtk.CellRendererPixbuf()
        textRenderer = Gtk.CellRendererText()
        fileColumn = Gtk.TreeViewColumn("File")
        fileColumn.pack_start(iconRenderer, False)
        fileColumn.pack_start(textRenderer, False)
        fileColumn.add_attribute(iconRenderer, "icon_name", 0)
        fileColumn.add_attribute(textRenderer, "markup", 1)
        fileColumn.set_sort_column_id(1)
        fileColumn.set_resizable(True)
        fileColumn.set_sort_indicator(True)
        lineColumn = Gtk.TreeViewColumn("Line", textRenderer, text=2)
        lineColumn.set_sort_column_id(2)
        lineColumn.set_sort_indicator(True)
        stringColumn = Gtk.TreeViewColumn("String", textRenderer, markup=3)
        resultsTree.append_column(fileColumn)
        resultsTree.append_column(lineColumn)
        resultsTree.append_column(stringColumn)
        scrolledWindow.add(resultsTree)

    def handle_invalid_zip(self, e, path):
        dialog = Gtk.MessageDialog(message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.CLOSE, text=f'{type(e).__name__}', secondary_text=f'{e}: {path}')
        dialog.run()
        dialog.destroy()

    def parse_zip(self, root, relpath, pattern, search_by_name):
        path = os.path.join(root, relpath)
        with zipfile.ZipFile(path, 'r') as z:
            archive = GLib.markup_escape_text(relpath);

            for member in z.infolist():
                if not self.searching:
                    break;

                if member.is_dir():
                    continue

                if search_by_name:
                    basename = os.path.basename(member.filename)
                    matches = re.finditer(pattern, basename)
                    filename = ""
                    pos = 0
                    for m in matches:
                        prefix = GLib.markup_escape_text(basename[pos:m.start()])
                        match = f"<span foreground='red'>{GLib.markup_escape_text(m[0])}</span>"
                        pos = m.end()
                        filename += f'{prefix}{match}'
                    if filename:
                        prefix = os.path.dirname(member.filename)
                        suffix = GLib.markup_escape_text(basename[pos:])
                        if archive:
                            self.resultsQueue.put(("a", archive))
                            archive = None
                        self.resultsQueue.put(("m", f'{prefix}{filename}{suffix}'))
                    continue

                with z.open(member) as f:
                    lines = io.TextIOWrapper(f, encoding="utf-8")
                    try:
                        for i, line in enumerate(lines):
                            if not self.searching:
                                break;
                            matches = re.finditer(pattern, line)
                            for m in matches:
                                if archive:
                                    self.resultsQueue.put(("a", archive))
                                    archive = None
                                if member.filename:
                                    self.resultsQueue.put(("m", GLib.markup_escape_text(member.filename)))
                                    member.filename = None
                                prefix = GLib.markup_escape_text(line[:m.start()])
                                match = f"<span foreground='red'>{GLib.markup_escape_text(m[0])}</span>"
                                suffix = GLib.markup_escape_text(line[m.end():])
                                self.resultsQueue.put((f'{i}', f'{prefix}{match}{suffix}'))
                    except UnicodeError:
                        break

    def process_queue(self, search_by_name):
        global zipIter, memberIter;
        while not self.resultsQueue.empty():
            line, string = self.resultsQueue.get_nowait()
            if line == "a":
                zipIter = self.results.append(None, ["folder", string, "", ""])
            elif line == "m":
                memberIter = self.results.append(zipIter, ["text-x-generic", string, "", ""])
                if search_by_name:
                    self.matches += 1
            else:
                self.results.append(memberIter, ["", "", line, string])
                self.matches += 1

    def search_stop(self, thread):
        self.searching = 0
        thread.join()
        self.searchButton.set_label("Search")

    def search_toggle(self, widget):
        global thread;
        if self.searching:
            self.search_stop(thread)
        else:
            path = self.zipEntry.get_text()
            pattern = self.patternEntry.get_text()
            recurse = self.recurseButton.get_active()
            search_by_name = self.filenameButton.get_active()
            self.results.clear()
            self.searchButton.set_label("Stop")
            self.searching = 1
            thread = threading.Thread(target=self.search_zip, args=(path, pattern, recurse, search_by_name,))
            thread.start()
            GLib.timeout_add(50, self.update_progress, search_by_name)

    def search_zip(self, path, pattern, recurse, search_by_name):
        zip_path = path
        try:
            if os.path.isdir(path):
                for root, dirs, files in os.walk(path):
                    for name in files:
                        if not self.searching:
                            break;
                        zip_path = os.path.join(root, name)
                        if zipfile.is_zipfile(zip_path):
                            with self.statusLock:
                                self.status = f'Searching {zip_path}'
                            self.parse_zip(path, os.path.relpath(zip_path, path), pattern, search_by_name)
                    if not recurse or not self.searching:
                        break;
            else:
                with self.statusLock:
                    self.status = f'Searching {zip_path}'
                self.parse_zip(os.path.dirname(path), os.path.basename(path), pattern, search_by_name)
        except Exception as e:
            GLib.idle_add(self.handle_invalid_zip, e, zip_path)
        GLib.idle_add(self.search_stop, threading.current_thread())

    def select_zip(self, widget, action):
        chooser = Gtk.FileChooserNative()
        chooser.set_transient_for(self)
        chooser.set_action(action)

        if action == Gtk.FileChooserAction.OPEN:
            zipFilter = Gtk.FileFilter()
            zipFilter.set_name("ZIP files")
            zipFilter.add_mime_type("application/zip")
            allFilter = Gtk.FileFilter()
            allFilter.set_name("All files")
            allFilter.add_pattern("*")
            chooser.add_filter(zipFilter)
            chooser.add_filter(allFilter)

        if chooser.run() == Gtk.ResponseType.ACCEPT:
            self.zipEntry.set_text(chooser.get_filename())
        chooser.destroy()

    def update_progress(self, search_by_name):
        self.process_queue(search_by_name)
        if self.searching:
            self.progress.pulse()
        else:
            with self.statusLock:
                self.status = f'Found {self.matches} matches.'
            self.matches = 0
            self.progress.set_fraction(0.0)
        with self.statusLock:
            status = self.status
        self.progress.set_text(status)
        return self.searching

win = Walgrep()
win.connect("destroy", Gtk.main_quit)
win.show_all()
Gtk.main()
