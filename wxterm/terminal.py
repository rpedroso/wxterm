# -*- coding: utf-8 -*-

import wx
import wx.lib.newevent
import os
import re
import fcntl
import pty
import select
import termios
import pyte
import pyte.screens
import struct
import threading
from collections import namedtuple
from pyte import graphics as g
from .colors256 import CLUT

use_GC = False
if use_GC:
    GCDC = wx.GCDC
else:
    GCDC = lambda a: a


draw_done = threading.Event()

(ChildExitEvent, EVT_TERM_CHILD_EXIT) = wx.lib.newevent.NewEvent()
(ChildReadyEvent, EVT_TERM_CHILD_READY) = wx.lib.newevent.NewEvent()
(TermReadyEvent, EVT_TERM_READY) = wx.lib.newevent.NewEvent()


wxBOLD = wx.BOLD
wxITALIC = wx.ITALIC
wxNORMAL = wx.NORMAL
_Caret = namedtuple("_Caret", [
    "x",
    "y",
    "prev_x",
    "prev_y",
    "col",
    "line",
    "prev_col",
    "prev_line",
    ])

# ['blue', 'brown', u'default', 'green', 'cyan', 'white', 'magenta', 'red']
colormap_normal = {
    'default': wx.Colour(205, 205, 205),
    'white': wx.Colour(205, 205, 205),
    'black': wx.Colour(0, 0, 0),
    'blue': wx.Colour(0, 0, 205),
    'brown': wx.Colour(139, 105, 20),
    'red': wx.Colour(205, 0, 0),
    'green': wx.Colour(0, 205, 0),
    'cyan': wx.Colour(0, 205, 205),
    'magenta': wx.Colour(205, 0, 205),
    }

colormap_bold = {
    'default': wx.Colour(255, 255, 255),
    'white': wx.Colour(255, 255, 255),
    'black': wx.Colour(60, 60, 60),
    'blue': wx.Colour(72, 72, 205),
    'brown': wx.Colour(139, 105, 20),
    'red': wx.Colour(240, 40, 40),
    'green': wx.Colour(187, 255, 170),
    'cyan': wx.Colour(91, 164, 184),
    'magenta': wx.Colour(245, 0, 245),
    }

colormap_bg = {
    'default': wx.Colour(0, 0, 0),
    'black': wx.Colour(0, 0, 0),
    }


class MyScreen(pyte.Screen):
    def __init__(self, *args, **kwargs):
        super(MyScreen, self).__init__(*args, **kwargs)
        self.bg256 = None

    def select_graphic_rendition(self, *attrs):
        """Set display attributes.

        :param list attrs: a list of display attributes to set.
        """
        replace = {}

        for attr in attrs or [0]:
            if attr == 38 and len(attrs) == 3 and attrs[1] == 5:
                replace["fg"] = CLUT[attrs[2]]
                break
            elif attr == 48 and len(attrs) == 3 and attrs[1] == 5:
                replace["bg"] = CLUT[attrs[2]]
                if self.bg256 is None:
                    self.bg256 = replace["bg"]
                break
            elif attr in g.FG:
                replace["fg"] = g.FG[attr]
            elif attr in g.BG:
                if attr == 49:
                    self.bg256 = None
                replace["bg"] = g.BG[attr]
            elif attr in g.TEXT:
                attr = g.TEXT[attr]
                replace[attr[1:]] = attr.startswith("+")
            elif not attr:
                replace = self.default_char._asdict()

        self.cursor.attrs = self.cursor.attrs._replace(**replace)


class _Terminal(pyte.DiffScreen, MyScreen):
    pass


class TerminalWindow(wx.ScrolledWindow):
    def __init__(self, parent, id=wx.ID_ANY,
                 pos=wx.DefaultPosition, size=wx.DefaultSize, style=0,
                 allow_underline=True, allow_bold=True, allow_italic=True):

        wx.ScrolledWindow.__init__(self, parent, id, pos, size,
                                   style | wx.WANTS_CHARS)

        self.__allow_underline = allow_underline
        self.__allow_bold = allow_bold
        self.__allow_italic = allow_italic

        self.__caret = _Caret(0, 0, 0, 0, 1, 1, 1, 1)
        self.__io = None
        self.__screen = None
        self.__buffer = None

        self.__select_begin = None
        self.__select_end = None
        self.__selection = {}

        self.__motion_prev_col = None
        self.__motion_prev_line = None
        self.__motion_prev_sels = {}

        self.__has_focus = False
        self.__update_timer = None

        self.__font = wx.Font(10, wx.TELETYPE, wx.NORMAL, wx.NORMAL)

        self.SetBackgroundStyle(wx.BG_STYLE_CUSTOM)
        self.SetBackgroundColour(wx.BLACK)

        self.SetFont(self.__font)

        # create one of the stock (built-in) cursors
        cursor = wx.StockCursor(wx.CURSOR_IBEAM)

        # set the cursor for the window
        self.SetCursor(cursor)

        #self.Bind(wx.EVT_WINDOW_CREATE, self.__terminal)
        wx.CallAfter(self.__terminal, None)

    def __terminal(self, evt):
        w, h = self.GetSize()

        self.__buffer = wx.EmptyBitmap(w, h)
        self.__clear_buffer()

        self.__stream = pyte.Stream()
        self.__screen = _Terminal(w / self.__col_width, h / self.__line_height)
        self.__stream.attach(self.__screen)
        self.__reset()

        #self.__resize(w, h)
        self.Bind(wx.EVT_PAINT, self.__on_paint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda e: None)
        self.Bind(wx.EVT_SIZE, self.__on_size)
        self.Bind(wx.EVT_CHAR, self.__on_char)
        self.Bind(wx.EVT_KILL_FOCUS, self.__on_kill_focus)
        self.Bind(wx.EVT_SET_FOCUS, self.__on_set_focus)
        self.Bind(wx.EVT_LEFT_DOWN, self.__on_leftdown)
        self.Bind(wx.EVT_LEFT_UP, self.__on_leftup)
        self.Bind(wx.EVT_MIDDLE_DOWN, self.__on_middledown)
        self.Bind(wx.EVT_LEFT_DCLICK, self.__on_leftdclick)
        self.Bind(wx.EVT_MOTION, self.__on_motion)

        #print [a for a in dir(self) if 'focus' in a.lower()]
        self.__has_focus = self.FindFocus() is self

    def __update(self, clear=False):
        dc = GCDC(wx.BufferedDC(wx.ClientDC(self), self.__buffer))
        if clear:
            self.__clear_buffer(dc)
        self.__draw(dc)

    def __on_kill_focus(self, event):
        self.__has_focus = False
        self.__update()

    def __on_set_focus(self, event):
        self.__has_focus = True
        self.__update()

    def __text_from_selection(self):
        text_selected = []
        for l, sels in sorted(self.__selection.iteritems()):
            if sels:
                text_selected.append(
                        (''.join([c.data for c in
                            self.__screen[l][sels[0]:sels[-1] + 1]])
                        ).rstrip()
                            )
        return '\n'.join(text_selected)

    def __clipboard_put(self, text_selected, use_primary=False):
        self.do = wx.TextDataObject()
        self.do.SetText(text_selected)
        wx.TheClipboard.UsePrimarySelection(use_primary)
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(self.do)
            wx.TheClipboard.Close()
        # Fail silently
        #else:
        #    wx.MessageBox("Unable to open the clipboard", "Error")

    def __clipboard_get(self, use_primary=False):
        success = False
        do = wx.TextDataObject()
        wx.TheClipboard.UsePrimarySelection(use_primary)
        if wx.TheClipboard.Open():
            success = wx.TheClipboard.GetData(do)
            wx.TheClipboard.Close()

        if success:
            return do.GetText()
        return None

    def __on_char(self, event):
        keycode = event.GetUnicodeKey() or event.GetKeyCode()
        # On my box arrows with modifiers works ok inside vim when TERM=xterm
        # With TERM=linux inside vim does not work without a map ex:
        # :map <ESC>[1;5C <C-Right>
        #print keycode
        if event.ControlDown() and event.ShiftDown():
            if keycode == 3:  # SHIFT-CTRL-C
                text_selected = self.__text_from_selection()
                self.__clipboard_put(text_selected)

            elif keycode == 22:  # SHIFT-CTRL-V
                text = self.__clipboard_get()
                if text:
                    os.write(self.__io, text.encode('utf-8'))
            event.Skip()
            return

        char = None
        #print keycode
        if keycode == wx.WXK_UP:
            if event.ControlDown():
                char = "\033[1;5A"
            elif event.AltDown():
                char = "\033[1;3A"
            else:
                char = "\033[A"
        elif keycode == wx.WXK_DOWN:
            if event.ControlDown():
                char = "\033[1;5B"
            elif event.AltDown():
                char = "\033[1;3B"
            else:
                char = "\033[B"
        elif keycode == wx.WXK_RIGHT:
            if event.ControlDown():
                char = "\033[1;5C"
            elif event.AltDown():
                char = "\033[1;3C"
            else:
                char = "\033[C"
        elif keycode == wx.WXK_LEFT:
            if event.ControlDown():
                char = "\033[1;5D"
            elif event.AltDown():
                char = "\033[1;3D"
            else:
                char = "\033[D"
        elif keycode == wx.WXK_PAGEUP:
            char = "\033[5~"
        elif keycode == wx.WXK_PAGEDOWN:
            char = "\033[6~"
        elif keycode == wx.WXK_END:
            char = "\033[4~"
        elif keycode == wx.WXK_HOME:
            char = "\033[1~"
        elif keycode == wx.WXK_INSERT:
            char = "\033[2~"
        elif keycode == wx.WXK_DELETE:
            char = "\033[3~"
        elif keycode < 256:
            char = unichr(keycode)

        if char:
            os.write(self.__io, char.encode('utf-8'))

        if keycode == wx.WXK_TAB:
            return
        event.Skip()

    def __on_size(self, event):
        self.__resize(*event.GetSize())
        #event.Skip()

    def __reset(self):
        self.__screen.reset()
        # to have accented chars displayed correctly
        self.__screen.set_charset('B', '(')
        #self.__clear_buffer()
        self.__update(clear=True)

    def __clear_buffer(self, dc=None):
        if dc is None:
            dc = GCDC(wx.BufferedDC(wx.ClientDC(self), self.__buffer))
        dc.SetBackgroundMode(wx.SOLID)
        dc.SetBackground(wx.BLACK_BRUSH)
        dc.Clear()

    def IsShown(self):
        return wx.ScrolledWindow.IsShown(self)

    def __resize(self, w, h):
        if not self.IsShown():
            return
        if self.__io and self.__screen:
            cw, lh = self.__col_width, self.__line_height
            new_w = w / cw
            new_h = h / lh

            def __update():
                self.__buffer = wx.EmptyBitmap(w, h)
                fcntl.ioctl(self.__io, termios.TIOCSWINSZ,
                        struct.pack("hhhh", new_h, new_w, 0, 0))
                self.__screen.resize(new_h, new_w)
                #self.__clear_buffer()
                self.__update(clear=True)
                self.__update_timer = None

            if self.__update_timer:
                self.__update_timer.Stop()
            self.__update_timer = wx.FutureCall(10, __update)
            #__update()

    def __on_paint(self, event):
        dc = GCDC(wx.BufferedPaintDC(self, self.__buffer))

    def __draw_line(self, dc, y, lineno, linedata):
        prev_style = None
        start = 0
        text = ''

        col_width = self.__col_width
        font = self.__font
        colormap_bg_get = colormap_bg.get
        screen_force_bg = self.__screen.bg256
        selection = self.__selection

        for current, char in enumerate(linedata):
            colormap = colormap_bold if char[3] else colormap_normal

            bg = colormap_bg_get(char[2], None)
            if screen_force_bg:  # 256 colours
                bg = char[2] if bg is None else screen_force_bg
            else:
                bg = colormap_bg_get(char[2], char[2])

            style = [colormap.get(char[1], char[1]),  # fg
                     bg,
                     char[7],  # reverse
                     char[5],  # underline
                     char[3],  # bold
                     char[4],  # italics
                     ]

            if selection and lineno in selection:
                if current in selection[lineno]:
                    style[2] = True  # reverse

            if style == prev_style:
                text += char[0]
            else:
                if prev_style is None:
                    prev_style = style

                if prev_style[2]:  # reverse
                    dc.SetTextForeground(prev_style[1])
                    dc.SetTextBackground(prev_style[0])
                else:
                    dc.SetTextForeground(prev_style[0])
                    dc.SetTextBackground(prev_style[1])

                if self.__allow_underline:
                    font.SetUnderlined(prev_style[3])
                if self.__allow_bold:
                    font.SetWeight(wxBOLD if prev_style[4] else wxNORMAL)
                if self.__allow_italic:
                    font.SetStyle(wxITALIC if prev_style[5] else wxNORMAL)
                dc.SetFont(font)
                dc.DrawText(text, start * col_width, y)

                text = char[0]
                start = current
                prev_style = style

        if start <= current:
            if self.__allow_underline:
                font.SetUnderlined(style[3])
            if self.__allow_bold:
                font.SetWeight(wxBOLD if style[4] else wxNORMAL)
            if self.__allow_italic:
                font.SetStyle(wxITALIC if style[5] else wxNORMAL)
            dc.SetFont(font)
            if style[2]:  # reverse
                dc.SetTextForeground(style[1])
                dc.SetTextBackground(style[0])
            else:
                dc.SetTextForeground(style[0])
                dc.SetTextBackground(style[1])

            dc.DrawText(text, start * col_width, y)

    def __draw(self, dc):
        dc.SetBackgroundMode(wx.SOLID)

        lnh = self.__line_height

        # Always set the current and previous cursor lines as dirty
        self.__screen.dirty.add(self.__caret.line)
        self.__screen.dirty.add(self.__caret.prev_line)

        for lineno, linedata in enumerate(self.__screen):
            if lineno in self.__screen.dirty or lineno in self.__selection:
                self.__draw_line(dc, lineno * lnh, lineno, linedata)

        # DrawCaret
        dc.SetLogicalFunction(wx.XOR)
        if self.__has_focus:
            dc.SetPen(wx.TRANSPARENT_PEN)
            dc.SetBrush(wx.GREEN_BRUSH)
        else:
            dc.SetPen(wx.GREEN_PEN)
            dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.DrawRectangle(self.__caret.x, self.__caret.y, self.__col_width, lnh)
        draw_done.set()

    def __record_cursor_position(self):
        # previous positions
        px = self.__caret.x
        py = self.__caret.y
        pc = self.__caret.col
        pl = self.__caret.line

        # current positions
        xx, yy = self.__screen.cursor.x, self.__screen.cursor.y
        x = xx * self.__col_width
        y = yy * self.__line_height

        self.__caret = _Caret(x, y, px, py, xx, yy, pc, pl)

    def __update_display(self, data):
        #if self.__screen:
        self.__screen.dirty.clear()
        self.__stream.feed(data)
        self.__record_cursor_position()
        self.__update()
        #self.Refresh(False)

    def __on_leftdown(self, event):
        col = event.GetX() / self.__col_width
        line = event.GetY() / self.__line_height
        self.__select_begin = (col, line)
        self.__select_end = None

        self.__screen.dirty = set(self.__selection.keys())
        self.__selection = {}
        self.__update()
        self.CaptureMouse()
        event.Skip()

    def __on_leftup(self, event):
        if not self.HasCapture():
            return
        self.ReleaseMouse()
        text_selected = self.__text_from_selection()
        self.__clipboard_put(text_selected, True)
        event.Skip()

    def __on_middledown(self, event):
        text = self.__clipboard_get(True)
        if text:
            os.write(self.__io, text.encode('utf-8'))
        event.Skip()

    def __on_leftdclick(self, event):
        col = event.GetX() / self.__col_width
        line = event.GetY() / self.__line_height
        start, end, text_selected = self.__get_word(col, line)
        if text_selected:
            self.__selection = {line: xrange(start, end)}
            self.__screen.dirty.add(line)
            self.__clipboard_put(text_selected, True)
            self.__update()
        event.Skip()

    def __on_motion(self, event):
        if event.LeftIsDown() and self.HasCapture():
            col = event.GetX() / self.__col_width
            line = event.GetY() / self.__line_height

            if (self.__motion_prev_line == line
                    and self.__motion_prev_col == col):
                return

            self.__motion_prev_line = line
            self.__motion_prev_col = col

            self.__select_end = (col, line)

            self.__screen.dirty.update(self.__motion_prev_sels.keys())

            w = self.GetSize()[0]
            sels = selection(self.__select_begin, self.__select_end,
                                 w / self.__col_width)

            self.__motion_prev_sels = sels
            self.__screen.dirty.update(sels.keys())
            self.__selection = sels

            self.__update()

    def __process_input(self, io):
        inp_ = [io]

        evt = TermReadyEvent()
        evt.SetEventObject(self)
        wx.PostEvent(self, evt)

        start_up = True
        while True:
            inp, out, err = select.select(inp_, [], [], None)
            if io in inp:
                if start_up:
                    start_up = False
                    evt = ChildReadyEvent()
                    evt.SetEventObject(self)
                    wx.PostEvent(self, evt)

                try:
                    data = os.read(io, 4096)
                except OSError:
                    break

                wx.CallAfter(self.__update_display,
                                data.decode('utf-8', 'replace'))
                draw_done.clear()
                draw_done.wait()

        wx.CallAfter(self.__exit)

    def __exit(self):
        os.waitpid(self.__pid, 0)
        self.t.join()
        evt = ChildExitEvent()
        evt.SetEventObject(self)
        wx.PostEvent(self, evt)

    def __get_word(self, col, line):
        linetext = self.__screen.display[line]
        for m in re.finditer(r"\b([a-zA-Z0-9@#%&_\-\.]+)\b", linetext):
            if m.start() <= col <= m.end():
                return m.start(), m.end(), m.group(0)
        return -1, -1, None

    def SetReadOnly(self, flag):
        if flag:
            self.Unbind(wx.EVT_CHAR)
        else:
            self.Bind(wx.EVT_CHAR, self.__on_char)

    def ForkCommand(self, command, argv, directory=None):
        if not directory:
            directory = os.getcwd()
        _pid, self.__io = pty.fork()
        if _pid == 0:
            os.chdir(directory)
            os.putenv('TERM', 'linux')
            os.execlp(command, *argv)

        self.t = t = threading.Thread(
                            target=self.__process_input, args=(self.__io,))
        t.daemon = True
        t.start()
        self.__thread = t
        self.__pid = _pid
        return _pid
    fork_command = ForkCommand

    def FeedChild(self, command):
        if self.__io:
            if isinstance(command, unicode):
                command = command.encode('utf-8')
            os.write(self.__io, command.encode('utf-8'))
    feed_child = FeedChild

    def SetFont(self, font):
        def _f():
            self.__font = font
            #wx.ScrolledWindow.SetFont(self, font)
            dc = GCDC(wx.ClientDC(self))
            dc.SetFont(font)
            self.__col_width,  self.__line_height = dc.GetTextExtent("W")
            self.__resize(*self.GetSize())
        wx.CallAfter(_f)


def selection(begin, end, width):
    if end is None or begin is None:
        return {}

    bcol, brow = begin
    ecol, erow = end

    if erow < brow:
        _, brow = end
        _, erow = begin

    if ecol < bcol:
        ecol, _ = begin
        bcol, _ = end

    if brow == erow:
        return {brow: xrange(bcol, ecol)}

    n = brow
    ret = {n: xrange(bcol, width)}
    for n in xrange(brow + 1, erow):
        ret[n] = xrange(0, width)
    ret[n + 1] = xrange(0, ecol)
    return ret
