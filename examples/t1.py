import sys
sys.path.insert(0, '..')
import wx
import wxterm


class Terminal(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        term = wxterm.TerminalWindow(self)
        term.ForkCommand('bash', ['bash'])
        term.Bind(wxterm.EVT_TERM_CHILD_EXIT, self.OnExit)

        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(term, 1, wx.EXPAND, 0)
        self.SetSizer(s)

    def OnExit(self, event):
        self.GetParent().Close()


if __name__ == '__main__':
    app = wx.App(0)
    f = wx.Frame(None, size=(800, 400))
    Terminal(f).SetFocus()
    f.Show()
    app.MainLoop()
