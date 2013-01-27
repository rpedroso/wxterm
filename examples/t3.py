import sys
sys.path.insert(0, '..')

import wx
import wxterm


class ColourButton(wx.Button):
    def __init__(self, parent, size, name, colour, pallete):
        wx.Button.__init__(self, parent, size=size, label=name)
        self.SetBackgroundColour(colour)
        self.SetHelpText(name)

        self.name = name
        self.colour = colour
        self.pallete = pallete

class Pallete(wx.Panel):
    def __init__(self, parent, pallete):
        wx.Panel.__init__(self, parent)

        s = wx.BoxSizer(wx.HORIZONTAL)
        for name, colour in sorted(pallete.iteritems()):
            button = ColourButton(self, (50,-1), name, colour, pallete)
            s.Add(button, 0, 0, 0)
            self.SetSizer(s)


class Terminal(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        term = wxterm.TerminalWindow(self)
        term.ForkCommand('bash', ['bash'])
        term.Bind(wxterm.EVT_TERM_CHILD_EXIT, self.OnExit)
        self.term = term

        p1 = Pallete(self, wxterm.terminal.colormap_normal)
        p1.Bind(wx.EVT_BUTTON, self.OnButton)

        p2 = Pallete(self, wxterm.terminal.colormap_bold)
        p2.Bind(wx.EVT_BUTTON, self.OnButton)

        p3 = Pallete(self, wxterm.terminal.colormap_bg)
        p3.Bind(wx.EVT_BUTTON, self.OnButton)

        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(term, 1, wx.EXPAND, 0)
        s.Add(p1, 0, 0, 0)
        s.Add(p2, 0, 0, 0)
        s.Add(p3, 0, 0, 0)
        self.SetSizer(s)

    def OnExit(self, event):
        self.GetParent().Close()

    def OnButton(self, event):
        btn = event.GetEventObject()
        data = wx.ColourData()
        data.SetColour(btn.GetBackgroundColour())
        dlg = wx.ColourDialog(self, data=data)
        dlg.GetColourData().SetChooseFull(True)
        if dlg.ShowModal() == wx.ID_OK:
            data = dlg.GetColourData()
            btn.pallete[btn.name] = data.GetColour()
            btn.SetBackgroundColour(data.GetColour())
        dlg.Destroy()

if __name__ == '__main__':
    app = wx.App(0)
    f = wx.Frame(None, size=(800, 500))
    t = Terminal(f)
    font = wx.Font(10, wx.MODERN, wx.NORMAL, wx.NORMAL)
    t.term.SetFont(font)
    t.SetFocus()
    f.Show()
    app.MainLoop()
