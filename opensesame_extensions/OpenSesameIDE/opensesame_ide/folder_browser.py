# coding=utf-8

"""
This file is part of OpenSesame.

OpenSesame is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

OpenSesame is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with OpenSesame.  If not, see <http://www.gnu.org/licenses/>.
"""

from libopensesame.py3compat import *
import os
import time
import multiprocessing
from pyqode.core.widgets import (
    FileSystemTreeView,
    FileSystemContextMenu
)
from qtpy.QtWidgets import (
    QDockWidget,
    QPushButton,
    QWidget,
    QVBoxLayout,
    QApplication
)
from qtpy.QtCore import QFileSystemWatcher, QTimer
from libopensesame.oslogging import oslogger
from libqtopensesame.misc.translate import translation_context
_ = translation_context(u'OpenSesameIDE', category=u'extension')


class FolderBrowserDockWidget(QDockWidget):

    def __init__(self, parent, ide, path):

        super(FolderBrowserDockWidget, self).__init__(parent)
        self.main_window = parent
        self._ide = ide
        self.path = path
        self._folder_browser = FolderBrowser(parent, ide, path)
        self._container_layout = QVBoxLayout(self)
        self._container_layout.setContentsMargins(6, 6, 6, 6)
        self._container_layout.addWidget(self._folder_browser)
        self._container_widget = QWidget(self)
        self._container_widget.setLayout(self._container_layout)
        self.setWidget(self._container_widget)
        self.setWindowTitle(os.path.basename(path))
        self.setObjectName(os.path.basename(path))

    def select_path(self, path):

        self._folder_browser.select_path(path)

    def closeEvent(self, e):

        self._ide.remove_folder_browser_dock_widget(self)
        self.close()

    @property
    def file_list(self):

        return self._folder_browser.file_list


class FolderBrowser(FileSystemTreeView):

    def __init__(self, parent, ide, path):

        super(FolderBrowser, self).__init__(parent)
        self.main_window = parent
        self._path = path
        self._ide = ide
        self.clear_ignore_patterns()
        self.add_ignore_patterns(ide.ignore_patterns)
        self.set_root_path(os.path.normpath(path))
        self.set_context_menu(FileSystemContextMenu())
        self._watcher = QFileSystemWatcher()
        self._watcher.addPath(path)
        self._watcher.fileChanged.connect(self._index_files)
        self._watcher.directoryChanged.connect(self._index_files)
        self._indexing = False
        self._file_list = []
        self._index_files()

    def mouseDoubleClickEvent(self, event):

        path = self.fileInfo(self.indexAt(event.pos())).filePath()
        self.open_file(path)

    def open_file(self, path):

        if not os.path.exists(path) or os.path.isdir(path):
            return
        self._ide.open_document(path)

    @property
    def file_list(self):

        while self._indexing:
            oslogger.debug(u'still indexing {}'.format(self._path))
            time.sleep(.1)
            QApplication.processEvents()
        return self._file_list

    def _index_files(self, _=None):

        if self._indexing:
            oslogger.debug(u'indexing in progress for {}'.format(self._path))
            return
        self._indexing = True
        self._queue = multiprocessing.Queue()
        self._file_indexer = multiprocessing.Process(
            target=file_indexer,
            args=(self._queue, self._path, self._ide.ignore_patterns)
        )
        self._file_indexer.start()
        oslogger.debug(u'indexing {}'.format(self._path))
        QTimer.singleShot(1000, self._check_file_indexer)

    def _check_file_indexer(self):

        if self._queue.empty():
            oslogger.debug(u'queue still empty for {}'.format(self._path))
            QTimer.singleShot(1000, self._check_file_indexer)
            return
        self._file_list = self._queue.get()
        self._indexing = False
        oslogger.debug(u'{} files indexed for {}'.format(
            len(self._file_list),
            self._path)
        )
        QTimer.singleShot(300000, self._index_files)


def file_indexer(queue, path, ignore_patterns):

    import fnmatch

    def _list_files(dirname, ignore_patterns):

        files = []
        ignore_patterns = ignore_patterns[:]
        gitignore = os.path.join(dirname, u'.gitignore')
        if os.path.exists(gitignore):
            oslogger.debug('excluding patterns from {}'.format(gitignore))
            with open(gitignore) as fd:
                ignore_patterns += [p.strip() for p in fd.read().split(u'\n')]
        ignore_patterns = [p for p in ignore_patterns if p]
        for basename in os.listdir(dirname):
            path = os.path.join(dirname, basename)
            if any(
                (
                    ignore_pattern in path or
                    fnmatch.fnmatch(basename, ignore_pattern)
                )
                for ignore_pattern in ignore_patterns
            ):
                continue
            if os.path.isdir(path):
                files += _list_files(path, ignore_patterns)
            else:
                files.append(path)
        return files

    queue.put(_list_files(path, ignore_patterns))
