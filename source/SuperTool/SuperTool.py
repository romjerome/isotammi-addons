#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2021      Kari Kujansuu
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#


import csv
import json
import os
import sys
import time
import traceback
from types import GeneratorType
from gramps.gen.filters._genericfilter import GenericFilterFactory
from gramps.gen.filters._filterlist import FilterList
from gramps.gen.filters import reload_custom_filters
from gramps.gen.lib.person import Person
import types
from gramps.gen.lib.family import Family
from gramps.gen.lib.event import Event
from gramps.gen.lib.place import Place
from pprint import pprint
from gramps.gui.display import display_url
from gramps.gui.utils import ProgressMeter
from contextlib import contextmanager

try:
    from typing import Any
    from typing import Callable
    from typing import Dict
    from typing import Generator
    from typing import Iterator
    from typing import List
    from typing import Optional
    from typing import Tuple
    from typing import Type
    from typing import Union
except:
    pass

from gi.repository import Gtk, Gdk, GObject, Gio

from gramps.gui.glade import Glade
from gramps.gui.managedwindow import ManagedWindow
from gramps.gui.plug import tool

from gramps.gen.config import config as configman

from gramps.gen.const import GRAMPS_LOCALE as glocale, CUSTOM_FILTERS

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext

from gramps.gen.db.txn import DbTxn

from gramps.gui.dialog import OkDialog

_ = glocale.translation.gettext


config = configman.register_manager("supertool")
config.register("defaults.encoding", "utf-8")
config.register("defaults.delimiter", "comma")
config.register("defaults.font", "")
config.register("defaults.last_filename", "")

SCRIPTFILE_EXTENSION = ".script"


def get_text(textview):
    buf = textview.get_buffer()
    text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
    return text


def set_text(textview, text):
    textview.get_buffer().set_text(text)


def importfile(fname):
    dirname = os.path.split(__file__)[0]
    fullname = os.path.join(dirname, fname)
    from types import SimpleNamespace

    code = open(fullname).read()
    globals_dict = {}
    exec(code, globals_dict)
    return SimpleNamespace(**globals_dict)


# Regular import would put "supertool_engine" in the global module namespace (sys.modules).
# This could clash with other addons.
# engine = importfile("supertool_engine.py")
import supertool_engine as engine


class ScriptOpenFileChooserDialog(Gtk.FileChooserDialog):
    def __init__(self, uistate):
        Gtk.FileChooserDialog.__init__(
            self,
            title="Load query from a .script file",
            transient_for=uistate.window,
            action=Gtk.FileChooserAction.OPEN,
        )

        self.add_buttons(
            _("_Cancel"), Gtk.ResponseType.CANCEL, _("Load"), Gtk.ResponseType.OK
        )

        filter_scriptfile = Gtk.FileFilter()
        filter_scriptfile.set_name("Script files")
        filter_scriptfile.add_pattern("*" + SCRIPTFILE_EXTENSION)
        self.add_filter(filter_scriptfile)

        filter_json = Gtk.FileFilter()
        filter_json.set_name("JSON files")
        filter_json.add_pattern("*.json")
        self.add_filter(filter_json)

        filter_all = Gtk.FileFilter()
        filter_all.set_name("All files")
        filter_all.add_pattern("*.*")
        self.add_filter(filter_all)


class ScriptSaveFileChooserDialog(Gtk.FileChooserDialog):
    def __init__(self, uistate):
        Gtk.FileChooserDialog.__init__(
            self,
            title="Save query to a .script file",
            transient_for=uistate.window,
            action=Gtk.FileChooserAction.SAVE,
        )

        self.add_buttons(
            _("_Cancel"), Gtk.ResponseType.CANCEL, _("Save"), Gtk.ResponseType.OK
        )

        filter_scriptfile = Gtk.FileFilter()
        filter_scriptfile.set_name("Script files")
        filter_scriptfile.add_pattern("*" + SCRIPTFILE_EXTENSION)
        self.add_filter(filter_scriptfile)


class CsvFileChooserDialog(Gtk.FileChooserDialog):
    def __init__(self, uistate):
        Gtk.FileChooserDialog.__init__(
            self,
            title="Download results as a CSV file",
            transient_for=uistate.window,
            action=Gtk.FileChooserAction.SAVE,
        )

        self.add_buttons(
            _("_Cancel"), Gtk.ResponseType.CANCEL, _("Save"), Gtk.ResponseType.OK
        )

        box = Gtk.VBox()
        box1 = Gtk.HBox()
        box2 = Gtk.HBox()

        config.load()
        encoding = config.get("defaults.encoding")
        delimiter = config.get("defaults.delimiter")

        self.cb_utf8 = Gtk.RadioButton.new_with_label_from_widget(None, "UTF-8")
        self.cb_iso8859_1 = Gtk.RadioButton.new_with_label_from_widget(
            self.cb_utf8, "ISO8859-1"
        )
        if encoding == "iso8859-1":
            self.cb_iso8859_1.set_active(True)

        box1.add(Gtk.Label("Encoding:"))
        box1.add(self.cb_utf8)
        box1.add(self.cb_iso8859_1)
        frame1 = Gtk.Frame()
        frame1.add(box1)

        self.cb_comma = Gtk.RadioButton.new_with_label_from_widget(None, "comma")
        self.cb_semicolon = Gtk.RadioButton.new_with_label_from_widget(
            self.cb_comma, "semicolon"
        )
        if delimiter == ";":
            self.cb_semicolon.set_active(True)

        box2.add(Gtk.Label("Delimiter:"))
        box2.add(self.cb_comma)
        box2.add(self.cb_semicolon)
        frame2 = Gtk.Frame()
        frame2.add(box2)
        box.set_spacing(5)
        box.add(frame1)
        box.add(frame2)
        box.show_all()
        self.set_extra_widget(box)
        self.set_do_overwrite_confirmation(True)

        filter_csv = Gtk.FileFilter()
        filter_csv.set_name("CSV files")
        filter_csv.add_pattern("*.csv")
        self.add_filter(filter_csv)


class GrampsEngine:
    def __init__(
        self,
        dbstate,
        uistate,
        category,
        selected_handles,
        initial_statements,
        statements,
        filter,
        expressions,
        unwind_lists,
        commit_changes,
        summary_only,
        step=None,
    ):
        self.dbstate = dbstate
        self.db = dbstate.db
        self.uistate = uistate
        self.category = category
        self.selected_handles = selected_handles
        self.initial_statements = initial_statements
        self.statements = statements
        self.filter = filter
        self.expressions = expressions
        self.unwind_lists = unwind_lists
        self.commit_changes = commit_changes
        self.summary_only = summary_only
        self.step = step

    def generate_rows(self, res):
        # type: (Tuple[Any,...]) -> Iterator[List[Any]]
        def cast(value):
            if type(value) in {int, str, float}:
                return value
            else:
                return str(value)

        if not res:
            yield []
            return
        value = res[0]
        for values in self.generate_rows(res[1:]):
            if type(value) is GeneratorType:
                value = list(value)
            if self.unwind_lists and type(value) is list:
                for v in value:
                    yield [cast(v)] + values
            else:
                yield [cast(value)] + values

    def evaluate_condition(self, obj, cond, env):
        # type: (Any,str,Dict[str,Any]) -> Tuple[bool, Dict[str,Any]]
        return self.category.execute_func(self.dbstate, obj, cond, env)

    def generate_values(self, init_env):
        # type: (Dict[str,Any]) -> Iterator[Tuple[Any,Dict[str,Any],List[Any]]]
        self.total_objects = len(self.selected_handles)
        for handle in self.selected_handles:
            if self.step:
                if self.step():
                    raise StopIteration()
            env = {}
            env.update(init_env)
            obj = self.category.getfunc(handle)
            obj.commit_ok = True
            if self.statements:
                value, env = self.category.execute_func(
                    self.dbstate, obj, self.statements, env, "exec"
                )

            if self.filter:
                ok, env = self.evaluate_condition(obj, self.filter, env)
                if not ok:
                    continue

            if self.commit_changes and obj.commit_ok:
                self.category.commitfunc(obj, self.trans)

            self.object_count += 1
            if self.expressions:
                res, env = self.category.execute_func(
                    self.dbstate, obj, self.expressions, env
                )
                if type(res) != tuple:
                    res = (res,)
                for values in self.generate_rows(res):
                    values.append(handle)
                    yield obj, env, [obj.gramps_id] + values

    def get_values(self, trans):
        # type: () -> None
        print("executing")
        self.trans = trans

        #         if not self.category.execute_func:
        #             return
        self.object_count = 0
        init_env = {}  # type: Dict[str,Any]
        init_env["trans"] = trans
        init_env["uistate"] = self.uistate
        if self.initial_statements:
            value, init_env = self.category.execute_func(
                self.dbstate, None, self.initial_statements, init_env, "exec"
            )

        for obj, env, values in self.generate_values(init_env):
            if not self.summary_only:
                yield values

        if self.summary_only:
            if self.expressions:
                res, env = self.category.execute_func(
                    self.dbstate, None, self.expressions, init_env
                )
                if type(res) != tuple:
                    res = (res,)
                for values in self.generate_rows(res):
                    yield [None] + values + [None]


class Query:
    def __init__(self):
        self.category = ""
        self.title = ""
        self.initial_statements = ""
        self.statements = ""
        self.filter = ""
        self.expressions = ""
        self.scope = "selected"
        self.unwind_lists = False
        self.commit_changes = False
        self.summary_only = False


class ScriptFile:
    def load(self, filename, loadtitle=True):
        # type: (str, bool) -> Query
        query = Query()
        if filename.endswith(".json"):
            data = self.__readdata_json(filename)
        else:
            data = self.__readdata(filename)
        query.category = data.get("category", "")
        title = data.get("title", "")
        if not title and loadtitle:
            name = os.path.split(filename)[1]
            title = name.replace(SCRIPTFILE_EXTENSION, "")
        query.title = title

        query.initial_statements = data.get("initial_statements", "")
        query.statements = data.get("statements", "")
        query.filter = data.get("filter", "")
        query.expressions = data.get("expressions", "")
        query.scope = data.get("scope", "selected")

        unwind_lists = data.get("unwind_lists", "")
        commit_changes = data.get("commit_changes", "")
        summary_only = data.get("summary_only", "")
        query.unwind_lists = unwind_lists == "True"
        query.commit_changes = commit_changes == "True"
        query.summary_only = summary_only == "True"
        return query

    def save(self, filename, query):
        # type: (str, Query) -> None
        data = {}
        data["title"] = query.title
        data["category"] = query.category
        data["initial_statements"] = query.initial_statements
        data["statements"] = query.statements
        data["filter"] = query.filter
        data["expressions"] = query.expressions

        data["scope"] = query.scope

        data["unwind_lists"] = str(query.unwind_lists)
        data["commit_changes"] = str(query.commit_changes)
        data["summary_only"] = str(query.summary_only)

        self.__writedata(filename, data)

    def __writedata(self, filename, data):
        # type: (str, Dict[str,str]) -> None
        # open(filename, "w").write(json.dumps(data, indent=4))
        with open(filename, "w") as f:
            for key, value in data.items():
                print("[" + key + "]", file=f)
                print(value, file=f)
                if value:
                    print(file=f)  # empty line

    def __readdata(self, filename):
        try:
            data = {}
            key = None
            value = ""
            for line in open(filename):
                if line.startswith("["):
                    if key:
                        data[key] = value.rstrip()
                    key = line.strip()[1:-1]
                    value = ""
                else:
                    value += line
            if key:
                data[key] = value.rstrip()
            return data
        except:
            return {}

    def __readdata_json(self, filename):
        # type: (str) -> Dict[str,str]
        try:
            data = open(filename).read()
            return json.loads(data)
        except FileNotFoundError:
            return {}
        except:
            traceback.print_exc()
            return {}


class HelpWindow(Gtk.Window):
    def __init__(self, uistate, help_notebook):
        Gtk.Window.__init__(self, title="Help Window")
        self.set_keep_above(True)
        self.box = Gtk.VBox(spacing=6)
        self.add(self.box)

        readme_url = "https://github.com/Taapeli/isotammi-addons/blob/master/source/SuperTool/README.md"

        label = Gtk.Label()
        markup = '<a href="{url}">{title}</a>'.format(
            url=readme_url, title="Open README in a browser"
        )
        label.set_markup(markup)
        self.box.pack_start(label, True, True, 0)

        self.box.pack_start(Gtk.Label("Available properties"), True, True, 0)
        self.box.pack_start(help_notebook, True, True, 0)


class SuperTool(ManagedWindow):
    def __init__(self, user, dbstate):
        ManagedWindow.__init__(self, user.uistate, [], self.__class__, modal=False)
        self.user = user
        self.uistate = user.uistate
        self.dbstate = dbstate
        self.db = dbstate.db
        self.csv_filename = None
        self.last_filename = None
        self.getfunc = None
        self.execute_func = None
        self.editfunc = None
        self.init()

    def init(self):
        # type: () -> None
        window = self.__create_gui()
        self.select_category()
        self.loadconfig()
        # self.load_attributes()
        self.dbstate.connect("no-database", self.db_closed)
        self.dbstate.connect("database-changed", self.db_changed)
        self.uistate.viewmanager.notebook.connect("switch-page", self.pageswitch)
        print(self.uistate.viewmanager.active_page)
        self.set_window(window, None, _("SuperTool"))
        # self.window.set_sensitive(self.category.objclass is not None)
        # self.btn_help.set_sensitive(True)
        self.help_loaded = False

        config.load()
        font = config.get("defaults.font")
        if font:
            self.btn_font.set_font(font)
            font_description = self.btn_font.get_font_desc()
            self.window.modify_font(font_description)
        self.last_filename = config.get("defaults.last_filename")
        self.show()
        self.check_category()

    def db_closed(self):
        # type: () -> None
        print("db_closed")
        if self.listview:
            self.output_window.remove(self.listview)
        self.listview = None  # type: Optional[Gtk.TreeView]
        self.btn_execute.set_sensitive(False)

    def db_changed(self, db):
        # type: (Any) -> None
        self.db = self.dbstate.db
        print("db_changed", db, db.db_is_open)
        print("db:", self.dbstate.db)
        print("db is_open:", self.dbstate.db.db_is_open)
        if db.db_is_open:
            self.btn_execute.set_sensitive(True)
        self.statusmsg.set_text("")
        self.select_category()

    def get_configfile(self):
        # type: () -> str
        return __file__[:-3] + "-" + self.category_name + SCRIPTFILE_EXTENSION

    def get_attributes(self, objclass, proxyclass):
        obj = objclass()
        for name in dir(obj):
            if name.startswith("_"):
                continue
            attr = getattr(obj, name)
            #             if type(attr) == types.FunctionType: continue
            if type(attr) == types.MethodType:
                continue
            # print(name, type(attr))
            # self.attributes_list.append_text(name)
        from unittest import mock

        db = mock.Mock()
        obj = mock.Mock()
        p = proxyclass(db, obj.handle, obj)

        for name in dir(proxyclass) + list(
            p.__dict__.keys()
        ):  # this contains the @property methods
            if name.startswith("_"):
                continue
            # print(">>",name)
            # print(name, type(attr))
            yield name

    def set_error(self, msg):
        # type: (str) -> None
        self.errormsg.set_markup(
            "<span font_family='monospace' color='red' size='larger'>{}</span>".format(
                msg.replace("<", "&lt;")
            )
        )

    def check_category(self):
        # type: () -> None
        category_ok = self.category.objclass is not None
        if category_ok:
            self.label_filter.show()
            self.label_statements.show()
            self.statements.show()
            self.filter.show()
        else:
            # self.set_error("This category ({}) is not supported".format(self.category_name))
            self.label_filter.hide()
            self.label_statements.hide()
            self.statements.hide()
            self.filter.hide()
            self.summary_checkbox.set_active(True)

        #         set_text(self.filter, "disabled")
        #         set_text(self.statements, "disabled")
        #         self.filter.set_sensitive(category_ok)
        #         self.statements.set_sensitive(category_ok)

        self.btn_save_as_filter.set_sensitive(category_ok)

        self.all_objects.set_sensitive(category_ok)
        self.filtered_objects.set_sensitive(category_ok)
        self.selected_objects.set_sensitive(category_ok)

        self.summary_checkbox.set_sensitive(category_ok)

    def pageswitch(self, *args):
        # type: (Any) -> None
        self.saveconfig()
        self.select_category()
        self.loadconfig()
        if self.listview:
            self.output_window.remove(self.listview)
            self.btn_csv.hide()
            self.btn_copy.hide()
        self.statusmsg.set_text("")
        self.check_category()

    def savestate(self, filename):
        # type: (str) -> None
        query = Query()
        query.category = self.category_name
        query.title = self.title.get_text()
        if self.selected_objects.get_active():
            scope = "selected"
        elif self.all_objects.get_active():
            scope = "all"
        elif self.filtered_objects.get_active():
            scope = "filtered"
        query.scope = scope
        query.expressions = get_text(self.expressions)
        query.filter = get_text(self.filter)
        query.statements = get_text(self.statements)
        query.initial_statements = get_text(self.initial_statements)

        query.unwind_lists = self.unwind_lists.get_active()
        query.commit_changes = self.commit_checkbox.get_active()
        query.summary_only = self.summary_checkbox.get_active()

        scriptfile = ScriptFile()
        scriptfile.save(filename, query)
        # self.writedata(filename, data)

    def loadstate(self, filename, loadtitle=True):
        # type: (str) -> None
        scriptfile = ScriptFile()
        query = scriptfile.load(filename)
        if query.category and query.category != self.category_name:
            msg = "Warning: saved query is for category '{}'. Current category is '{}'."
            msg = msg.format(query.category, self.category_name)
            OkDialog(
                _("Warning"),
                msg,
                parent=self.uistate.window,
            )

        if not query.title and loadtitle:
            name = os.path.split(filename)[1]
            query.title = name.replace(SCRIPTFILE_EXTENSION, "")
        self.title.set_text(query.title)

        set_text(self.expressions, query.expressions)
        set_text(self.filter, query.filter)
        set_text(self.statements, query.statements)
        set_text(self.initial_statements, query.initial_statements)
        scope = query.scope
        self.all_objects.set_active(scope == "all")
        self.filtered_objects.set_active(scope == "filtered_")
        self.selected_objects.set_active(scope == "selected")

        self.unwind_lists.set_active(query.unwind_lists)
        self.commit_checkbox.set_active(query.commit_changes)
        self.summary_checkbox.set_active(query.summary_only)

    def saveconfig(self):
        # type: () -> None
        self.savestate(self.get_configfile())

    def loadconfig(self):
        # type: () -> None
        self.loadstate(self.get_configfile(), loadtitle=False)

    def download(self, obj):
        # type: (Gtk.Widget) -> None
        choose_file_dialog = CsvFileChooserDialog(self.uistate)
        title = self.title.get_text().strip()
        if title:
            fname = title + ".csv"
        else:
            fname = self.category_name + ".csv"

        choose_file_dialog.set_current_name(fname)
        if self.csv_filename:
            if self.title.get_text():
                dirname = os.path.split(self.csv_filename)[0]
                self.csv_filename = os.path.join(dirname, fname)
            choose_file_dialog.set_filename(self.csv_filename)

        while True:
            response = choose_file_dialog.run()
            if response == Gtk.ResponseType.CANCEL:
                break
            elif response == Gtk.ResponseType.DELETE_EVENT:
                break
            elif response == Gtk.ResponseType.OK:
                self.csv_filename = choose_file_dialog.get_filename()
                print(self.csv_filename)
                delimiter = ","
                if choose_file_dialog.cb_comma.get_active():
                    delimiter = ","
                if choose_file_dialog.cb_semicolon.get_active():
                    delimiter = ";"
                encoding = "utf-8"
                if choose_file_dialog.cb_utf8.get_active():
                    encoding = "utf-8"
                if choose_file_dialog.cb_iso8859_1.get_active():
                    encoding = "iso8859-1"

                config.set("defaults.encoding", encoding)
                config.set("defaults.delimiter", delimiter)
                config.save()

                writer = csv.writer(
                    open(self.csv_filename, "w", encoding=encoding, newline=""),
                    delimiter=delimiter,
                )
                for row in self.store:
                    for col in row:
                        print("- col", col)
                    writer.writerow(row)
                break

        choose_file_dialog.destroy()

    def copy(self, obj):
        # type: (Gtk.Widget) -> None
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)

        import io

        stringio = io.StringIO()
        writer = csv.writer(stringio)
        for row in self.store:
            writer.writerow(row)
        clipboard.set_text(stringio.getvalue(), -1)
        OkDialog("Info", "Result list copied to clipboard")

    def save(self, obj):
        # type: (Gtk.Widget) -> None
        choose_file_dialog = ScriptSaveFileChooserDialog(self.uistate)
        title = self.title.get_text().strip()
        if title:
            fname = title + SCRIPTFILE_EXTENSION
        else:
            fname = self.category_name + "-query" + SCRIPTFILE_EXTENSION
        choose_file_dialog.set_current_name(fname)
        choose_file_dialog.set_do_overwrite_confirmation(True)
        if self.last_filename:
            if self.title.get_text():
                dirname = os.path.split(self.last_filename)[0]
                self.last_filename = os.path.join(dirname, fname)
            choose_file_dialog.set_filename(self.last_filename)

        while True:
            response = choose_file_dialog.run()
            if response == Gtk.ResponseType.CANCEL:
                break
            elif response == Gtk.ResponseType.DELETE_EVENT:
                break
            elif response == Gtk.ResponseType.OK:
                filename = choose_file_dialog.get_filename()
                print(filename)
                self.savestate(filename)
                self.last_filename = filename
                config.set("defaults.last_filename", filename)
                config.save()
                break

        choose_file_dialog.destroy()

    def load(self, obj):
        # type: (Gtk.Widget) -> None
        print("load")
        choose_file_dialog = ScriptOpenFileChooserDialog(self.uistate)
        choose_file_dialog.set_current_name(
            self.category_name + "-query" + SCRIPTFILE_EXTENSION
        )
        if self.last_filename:
            choose_file_dialog.set_filename(self.last_filename)

        while True:
            response = choose_file_dialog.run()
            if response == Gtk.ResponseType.CANCEL:
                break
            elif response == Gtk.ResponseType.DELETE_EVENT:
                break
            elif response == Gtk.ResponseType.OK:
                filename = choose_file_dialog.get_filename()
                print(filename)
                self.loadstate(filename)
                self.last_filename = filename
                config.set("defaults.last_filename", filename)
                config.save()
                break

        choose_file_dialog.destroy()

    def main(self):
        # type: () -> None
        if self.uistate.viewmanager.active_page:
            self.category_name = self.uistate.viewmanager.active_page.get_category()
            self.loadconfig()

    def clear(self, obj):
        # type: (Any) -> None
        self.title.set_text("")
        set_text(self.initial_statements, "")
        set_text(self.statements, "")
        set_text(self.filter, "")
        set_text(self.expressions, "")
        self.selected_objects.set_active(True)
        self.unwind_lists.set_active(False)
        self.commit_checkbox.set_active(False)
        self.summary_checkbox.set_active(False)

    def __close(self, obj):
        self.saveconfig()
        if self.help_win:
            self.help_win.close()
        self.close()

    def build_help(self):  # temporary helper; not used
        self.help_notebook = Gtk.Notebook()
        page = 0
        data = {}
        for cat_name in engine.get_categories():
            print(cat_name)
            data[cat_name] = []
            info = engine.get_category_info(self.db, cat_name)
            if not info.objclass:
                continue
            box = Gtk.VBox()
            box.set_border_width(10)
            # box.add(Gtk.Label(label=objclass.__name__))
            # self.help_notebook.append_page(box, Gtk.Label(label=info.objclass))
            grid = Gtk.Grid()
            row = 0
            col = 0
            for name in sorted(self.get_attributes(info.objcls, info.proxyclass)):
                print("-", name)
                label = Gtk.Label(label=name)
                label.set_halign(Gtk.Align.START)
                # box.add(label)
                grid.attach(label, col, row, 1, 1)

                label = Gtk.Label(label="description")
                label.set_halign(Gtk.Align.START)
                # box.add(label)
                grid.attach(label, col + 1, row, 1, 1)
                data[cat_name].append((name, ""))
                row += 1
            self.help_notebook.append_page(grid, Gtk.Label(label=info.objclass))
            grid.show()
            if cat_name == self.category_name:
                self.help_notebook.set_current_page(page)
            page += 1
        self.help_loaded = True
        print(json.dumps(data, indent=4))

    def load_help(self):
        dirname = os.path.split(__file__)[0]
        fname = os.path.join(dirname, "helptext.txt")
        data = json.loads(open(fname).read())
        self.help_notebook = Gtk.Notebook()
        page = 0
        for cat_name in ["global"] + engine.get_categories():
            grid = Gtk.Grid()
            grid.set_column_spacing(10)
            row = 0
            col = 0
            for name, desc in sorted(data[cat_name]):
                label = Gtk.Label(label=name)
                label.set_halign(Gtk.Align.START)
                # box.add(label)
                grid.attach(label, col, row, 1, 1)

                label = Gtk.Label(label=desc)
                label.set_halign(Gtk.Align.START)
                # box.add(label)
                grid.attach(label, col + 1, row, 1, 1)
                row += 1
            self.help_notebook.append_page(grid, Gtk.Label(label=cat_name))
            grid.show()
            if cat_name == self.category_name:
                self.help_notebook.set_current_page(page)
            page += 1

    def help(self, obj):
        self.load_help()
        self.help_win = HelpWindow(self.uistate, self.help_notebook)
        font_description = self.btn_font.get_font_desc()
        self.help_win.modify_font(font_description)
        self.help_win.show_all()

    def __create_gui(self):
        # type: () -> Gtk.Widget
        glade = Glade(toplevel="main", also_load=["help_window", "adjustment1"])
        glade.set_translation_domain(None)

        self.title = glade.get_child_object("title")

        self.label_filter = glade.get_child_object("label_filter")
        self.label_statements = glade.get_child_object("label_statements")

        self.initial_statements = glade.get_child_object("initial_statements")
        self.statements = glade.get_child_object("statements")
        self.filter = glade.get_child_object("filter")
        self.expressions = glade.get_child_object("expressions")

        self.all_objects = glade.get_child_object("all_objects")
        self.filtered_objects = glade.get_child_object("filtered_objects")
        self.selected_objects = glade.get_child_object("selected_objects")

        self.unwind_lists = glade.get_child_object("unwind_lists")
        self.commit_checkbox = glade.get_child_object("commit_checkbox")
        self.summary_checkbox = glade.get_child_object("summary_checkbox")

        self.btn_execute = glade.get_child_object("btn_execute")
        self.btn_csv = glade.get_child_object("btn_csv")
        self.btn_copy = glade.get_child_object("btn_copy")
        self.btn_close = glade.get_child_object("btn_close")
        self.btn_load = glade.get_child_object("btn_load")
        self.btn_save = glade.get_child_object("btn_save")
        self.btn_save_as_filter = glade.get_child_object("btn_save_as_filter")
        self.btn_clear = glade.get_child_object("btn_clear")
        self.btn_help = glade.get_child_object("btn_help")

        self.btn_font = glade.get_child_object("btn_font")
        self.btn_font.set_label("Select font")

        self.attributes_list = glade.get_child_object("attributes_list")

        self.statusmsg = glade.get_child_object("statusmsg")
        self.errormsg = self.statusmsg

        self.output_window = glade.get_child_object("output_window")
        self.help_window = glade.get_object("help_window")
        self.help_notebook = glade.get_object("help_notebook")
        self.help_win = None

        self.selected_objects.set_active(True)
        self.btn_execute.connect("clicked", self.__execute)
        self.btn_csv.connect("clicked", self.download)
        self.btn_copy.connect("clicked", self.copy)
        self.btn_close.connect("clicked", self.__close)
        self.btn_load.connect("clicked", self.load)
        self.btn_save.connect("clicked", self.save)
        self.btn_save_as_filter.connect("clicked", self.save_as_filter)
        self.btn_clear.connect("clicked", self.clear)
        self.btn_help.connect("clicked", self.help)
        self.btn_font.connect("font-set", self.set_font)

        self.btn_csv.hide()
        self.listview = None

        ver = (Gtk.get_major_version(),Gtk.get_minor_version())
        if ver >= (3, 22):
            self.initial_statements_window = glade.get_child_object("initial_statements_window")
            self.statements_window = glade.get_child_object("statements_window")
            self.initial_statements_window.set_max_content_height(200)             
            self.initial_statements_window.set_propagate_natural_height(True)             
            self.statements_window.set_propagate_natural_height(True)             
            self.statements_window.set_max_content_height(200)             

        return glade.toplevel

    def set_font(self, widget):
        font = widget.get_font()
        font_description = widget.get_font_desc()
        self.window.modify_font(font_description)
        config.set("defaults.font", font)
        config.save()

    def select_category(self):
        # type: () -> None
        self.execute_func = None
        self.category_name = self.uistate.viewmanager.active_page.get_category()
        self.category = engine.get_category_info(self.db, self.category_name)

    def __execute(self, obj):
        # type: (Gtk.Widget) -> None
        self.statusmsg.set_text("")
        self.output_window.hide()
        self.btn_csv.hide()
        self.btn_copy.hide()
        self.trans = None
        try:
            self.commit_changes = self.commit_checkbox.get_active()
            txtitle = "Executing SuperTool".format(self.title.get_text())
            if self.title.get_text():
                txtitle += " ({})".format(self.title.get_text())

            if self.commit_changes:
                with DbTxn(txtitle, self.dbstate.db) as self.trans:
                    self.__execute1()
            else:  # no need for a transaction
                self.__execute1()
        except Exception as e:
            traceback.print_exc()
            if isinstance(e, engine.SupertoolException):
                self.set_error(str(e))
                return
            lines = traceback.format_exc().splitlines()
            lastline = lines[-1]
            if lastline.startswith("SyntaxError:"):
                msglines = lines[-3:]
            elif lastline.startswith("NameError:"):
                msglines = lines[-1:]
            else:
                msglines = [str(e)]
            errortext = "\n".join(msglines)
            self.set_error(errortext)

    def __execute1(self):
        # type: () -> None
        print("executing")
        self.errormsg.set_text("")
        t1 = time.time()

        if not self.uistate.viewmanager.active_page:
            return
        self.saveconfig()
        #         if not self.category.execute_func:
        #             return
        if self.listview:
            self.output_window.remove(self.listview)
        self.listview = None
        n = 0
        LIMIT = 1000

        if self.category.objclass:
            if self.selected_objects.get_active():
                selected_handles = (
                    self.uistate.viewmanager.active_page.selected_handles()
                )
            elif self.all_objects.get_active():
                selected_handles = self.category.get_all_objects_func()
            elif self.filtered_objects.get_active():
                selected_handles = []  # ???
                store = self.uistate.viewmanager.active_page.model
                for row in store:
                    handle = store.get_handle_from_iter(row.iter)
                    selected_handles.append(handle)
        else:
            selected_handles = []

        unwind_lists = self.unwind_lists.get_active()
        summary_only = self.summary_checkbox.get_active()
        commit_changes = self.commit_checkbox.get_active()
        initial_statements = get_text(self.initial_statements).strip()
        statements = get_text(self.statements).strip()
        filtertext = get_text(self.filter).strip()
        expressions = get_text(self.expressions).strip()
        with self.progress(
            "SuperTool", "Executing " + self.title.get_text(), len(selected_handles)
        ) as step:
            gramps_engine = GrampsEngine(
                self.dbstate,
                self.uistate,
                self.category,
                selected_handles,
                initial_statements,
                statements,
                filtertext,
                expressions,
                unwind_lists,
                commit_changes,
                summary_only,
                step,
            )
            for values in gramps_engine.get_values(self.trans):
                if not self.listview:
                    # can build this only after the column types are known
                    # (we assume the types are the same for all rows)
                    self.build_listview(values)

                self.store.append(None, values)
                n += 1
                if n >= LIMIT:
                    OkDialog(
                        _("Warning"),
                        "Limit of {} rows reached".format(LIMIT),
                        parent=self.uistate.window,
                    )
                    break
        t2 = time.time()

        msg = "Objects: {}/{}; rows: {} ({:.2f}s)".format(
            gramps_engine.object_count, gramps_engine.total_objects, n, t2 - t1
        )
        print(msg)
        self.statusmsg.set_text(msg)
        if n > 0:
            self.btn_csv.show()
            self.btn_copy.show()
        else:
            self.btn_csv.hide()
            self.btn_copy.hide()
        self.output_window.show()

    @contextmanager
    def progress(self, title1, title2, count):
        self._progress = ProgressMeter(title1, can_cancel=True)
        self._progress.set_pass(title2, count, ProgressMeter.MODE_FRACTION)
        try:
            yield self._progress.step
        finally:
            self._progress.close()

    def build_listview(self, res):
        # type: (Tuple[Union[int,str,float],...]) -> None
        self.listview = Gtk.TreeView()
        numcols = len(res)
        renderer = Gtk.CellRendererText()
        coltypes = []  # type: List[Union[Type[int],Type[str],Type[float]]]
        for colnum in range(numcols - 1):
            if colnum == 0:
                title = "ID"
                coltypes.append(str)
            else:
                title = "Value %s" % colnum
                coltype = type(res[colnum])
                if coltype in {int, str, float}:
                    coltypes.append(coltype)
                else:
                    coltypes.append(str)
            col = Gtk.TreeViewColumn(title, renderer, text=colnum, weight_set=True)
            col.set_clickable(True)
            col.set_resizable(True)
            col.set_sort_column_id(colnum)
            self.listview.append_column(col)
        coltypes.append(str)  # for handle

        self.output_window.set_size_request(600, 400)
        self.output_window.add(self.listview)

        # self.store = Gtk.TreeStore(*([str]*(numcols)))
        self.store = Gtk.TreeStore(*coltypes)
        self.listview.set_model(self.store)
        self.listview.connect("button-press-event", self.__button_press)
        self.listview.show()

    def __button_press(self, treeview, event):
        if not self.db.db_is_open:
            return True
        try:  # may fail if clicked too frequently
            if event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS and event.button == 1:
                model, treeiter = self.listview.get_selection().get_selected()
                row = list(model[treeiter])
                handle = row[-1]
                obj = self.category.getfunc(handle)
                self.category.editfunc(self.dbstate, self.uistate, [], obj)
                return True
        except:
            traceback.print_exc()
        return False

    def save_as_filter(self, obj):
        filtername = self.title.get_text().strip()
        filtertext = get_text(self.filter).strip()
        initial_statements = get_text(self.initial_statements).strip()
        statements = get_text(self.statements).strip()
        initial_statements = initial_statements.replace("\n", "<br>")
        statements = statements.replace("\n", "<br>")
        self.makefilter(
            self.category, filtername, filtertext, initial_statements, statements
        )

    def makefilter(
        self, category, filtername, filtertext, initial_statements, statements
    ):
        the_filter = GenericFilterFactory(category.objclass)()
        rule = category.filterrule([filtertext, initial_statements, statements])
        if not filtername:
            OkDialog(
                _("Error"), "Please supply a title/name", parent=self.uistate.window
            )
            return
        if not filtertext:
            OkDialog(
                _("Error"),
                "Please supply a filtering condition",
                parent=self.uistate.window,
            )
            return
        the_filter.add_rule(rule)
        the_filter.set_name(filtername)
        filterdb = FilterList(CUSTOM_FILTERS)
        filterdb.load()
        filters = filterdb.get_filters_dict(category.objclass)
        if filtername in filters:
            msg = "Filter '{}' already exists; choose another name".format(filtername)
            OkDialog(_("Error"), msg, parent=self.uistate.window)
            return
        filterdb.add(category.objclass, the_filter)
        print("added filter", the_filter)
        filterdb.save()
        reload_custom_filters()
        self.uistate.emit("filters-changed", (category.objclass,))

        msg = "Created filter {0}".format(filtername)
        OkDialog(_("Done"), msg, parent=self.uistate.window)


# -------------------------------------------------------------------------
#
# Tool
#
# -------------------------------------------------------------------------
class Tool(tool.Tool):
    def __init__(self, dbstate, user, options_class, name, callback=None):
        # type: (Any, Any, Any, str, Callable) -> None
        self.user = user
        self.uistate = user.uistate
        self.dbstate = dbstate
        self.db = dbstate.db
        tool.Tool.__init__(self, dbstate, options_class, name)
        if not self.uistate:  # CLI mode
            self.run_cli()
            return
        self.run()

    def run_cli(self):
        script_filename = self.options.handler.options_dict["script"]
        if not script_filename:
            print("No script_filename")
            return
        if not os.path.exists(script_filename):
            print("Script file '{}' does not exist".format(script_filename))
            return
        output_filename = self.options.handler.options_dict.get("output")
        print("script_filename:", script_filename)
        scriptfile = ScriptFile()
        print("scriptfile:", scriptfile)
        query = scriptfile.load(script_filename)
        print("query:", query)
        print(self.options.handler.options_dict)
        category_name = self.options.handler.options_dict.get("category")
        print("category_name:", category_name)
        if not category_name:
            category_name = query.category
        if not category_name:
            print("No category name specified")
            return
        category = engine.get_category_info(self.db, category_name)
        selected_handles = category.get_all_objects_func()
        gramps_engine = GrampsEngine(
            self.dbstate,
            self.uistate,
            category,
            selected_handles,
            query.initial_statements,
            query.statements,
            query.filter,
            query.expressions,
            query.unwind_lists,
            query.commit_changes,
            query.summary_only,
        )
        if output_filename:
            f = csv.writer(open(output_filename, "w"))
        with DbTxn("Generating values", self.db) as trans:
            for values in gramps_engine.get_values(trans):
                if output_filename:
                    f.writerow(values)
                else:
                    print(json.dumps(values))

    def run(self):
        # type: () -> None
        m = SuperTool(self.user, self.dbstate)
        print("run")


# ------------------------------------------------------------------------
#
# Options
#
# ------------------------------------------------------------------------
class Options(tool.ToolOptions):
    """
    Define options and provides handling interface.
    """

    def __init__(self, name, person_id=None):
        tool.ToolOptions.__init__(self, name, person_id)
        print("person_id:", person_id)

        self.options_dict = dict(
            script="",
            output="",
            category="",
        )
        self.options_help = dict(
            script=(
                "=str",
                "Script file name",
                "A {} file name".format(SCRIPTFILE_EXTENSION),
            ),
            output=("=str", "Output CSV file name (optional)", "a CSV file name"),
            category=(
                "=str",
                "Object category (optional)",
                [
                    "People",
                    "Families",
                    "Events",
                    "Places",
                    "Citations",
                    "Sources",
                    "Repositories",
                    "Notes",
                ],
                False,
            ),
        )
