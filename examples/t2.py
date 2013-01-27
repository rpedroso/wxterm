import sys
sys.path.insert(0, '..')

import wx
import wxterm


class Terminal(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        term = wxterm.TerminalWindow(self, allow_bold=False)
        term.ForkCommand('bash', ['bash'])
        term.Bind(wxterm.EVT_TERM_CHILD_EXIT, self.OnExit)
        self.term = term

        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(term, 1, wx.EXPAND, 0)
        self.SetSizer(s)

    def OnExit(self, event):
        self.GetParent().Close()


if __name__ == '__main__':
    app = wx.App(0)
    f = wx.Frame(None, size=(800, 500))
    t = Terminal(f)
    font = wx.Font(9, wx.MODERN, wx.NORMAL, wx.NORMAL)
    t.term.SetFont(font)
    t.SetFocus()
    f.Show()
    app.MainLoop()
