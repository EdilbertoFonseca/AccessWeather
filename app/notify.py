from __future__ import annotations

from .config import APP_AUMID, APP_NAME, tools_dir

try:
    from windows_toasts import (
        InteractableWindowsToaster,
        Toast,
        ToastDisplayImage,
        ToastDuration,
        WindowsToaster,
    )

    TOASTS_AVAILABLE = True
except Exception:  # pragma: no cover - depends on the host system
    InteractableWindowsToaster = None
    Toast = None
    ToastDisplayImage = None
    ToastDuration = None
    WindowsToaster = None
    TOASTS_AVAILABLE = False


TOAST_ICON_NAMES = ("toast.png", "toast.ico")


def toast_icon_path():
    for name in TOAST_ICON_NAMES:
        candidate = tools_dir() / name
        if candidate.is_file():
            return candidate
    return None


class Notifier:
    """Toasts do Windows; falha em silêncio e continua opcional."""

    def __init__(self, settings=None, app_name=APP_NAME, aumid=APP_AUMID):
        self.settings = settings
        self.app_name = app_name
        self.aumid = aumid
        self._toaster = None
        self._failed = False
        self._last_error = ""

    @property
    def available(self) -> bool:
        return TOASTS_AVAILABLE and not self._failed

    @property
    def last_error(self) -> str:
        return self._last_error

    def _allowed(self, category) -> bool:
        settings = self.settings
        if settings is None or category is None:
            return True
        try:
            group = settings["notifications"]
        except Exception:
            return True
        if not isinstance(group, dict):
            return True
        return bool(group.get(category, True))

    def _ensure(self):
        if self._toaster is not None or self._failed:
            return self._toaster
        if not TOASTS_AVAILABLE:
            self._last_error = "A biblioteca windows_toasts não está instalada."
            self._failed = True
            return None
        # WindowsToaster funciona em app portátil (não instalado); o toaster com
        # AUMID customizado só aparece quando o AUMID está registrado no Windows.
        for factory in (
            lambda: WindowsToaster(self.app_name),
            lambda: InteractableWindowsToaster(self.app_name, notifierAUMID=self.aumid),
        ):
            try:
                self._toaster = factory()
                break
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
                self._toaster = None
        if self._toaster is None:
            self._failed = True
        return self._toaster

    def send(
        self,
        title,
        body="",
        category="forecast",
        icon=None,
        on_activated=None,
        force=False,
    ) -> bool:
        if not force and not self._allowed(category):
            self._last_error = (
                f"As notificações de {category} estão desligadas nas configurações."
            )
            return False
        toaster = self._ensure()
        if toaster is None:
            return False
        fields = [str(title)]
        if body:
            fields.append(str(body))
        try:
            toast = Toast(text_fields=fields, on_activated=on_activated)
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            return False
        image = icon or toast_icon_path()
        if image:
            try:
                toast.AddImage(ToastDisplayImage.fromPath(str(image)))
            except Exception:
                pass
        try:
            toaster.show_toast(toast)
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            self._failed = True
            return False
        return True

    def alert(self, location_label, message, force=False) -> bool:
        if location_label:
            title = f"Alerta meteorológico: {location_label}"
        else:
            title = "Alerta meteorológico"
        return self.send(title, message, category="alerts", force=force)

    def forecast(self, location_label, message, force=False) -> bool:
        return self.send(
            location_label or APP_NAME, message, category="forecast", force=force
        )

    def update(self, version, message="") -> bool:
        title = f"Atualização do {self.app_name} disponível"
        body = message or f"Versão {version} pronta para instalar."
        return self.send(title, body, category="update")

    def clear(self) -> bool:
        toaster = self._ensure()
        if toaster is None:
            return False
        try:
            toaster.clear_toasts()
        except Exception:
            return False
        return True
