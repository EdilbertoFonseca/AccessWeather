import wx
import wx.adv


class TrayIcon(wx.adv.TaskBarIcon):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        bitmap = wx.ArtProvider.GetBitmap(wx.ART_GO_FORWARD, wx.ART_OTHER, (16, 16))
        self.SetIcon(wx.Icon(bitmap), "AccessWeather")

    def CreatePopupMenu(self):
        menu = wx.Menu()
        entries = [
            ("Abrir a janela", "show_window"),
            ("Atualizar agora", "refresh_now"),
            ("Adicionar local...", "add_location"),
            ("Trocar de local", "cycle_location"),
            ("Copiar previsão", "copy_current"),
            (None, None),
            ("Gerenciar locais...", "open_locations"),
            ("Gerenciar alertas...", "open_alerts"),
            ("Configurações...", "open_settings"),
            ("Verificar atualizações...", "check_update"),
            (None, None),
            ("Changelog...", "show_changelog"),
            ("Sobre", "about"),
            ("Sair", "quit"),
        ]
        for label, action in entries:
            if label is None:
                menu.AppendSeparator()
                continue
            item = menu.Append(wx.ID_ANY, label)
            self.Bind(
                wx.EVT_MENU,
                lambda event, name=action: self.controller.dispatch(name),
                item,
            )
        return menu