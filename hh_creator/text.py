import logging
import time
from decimal import Decimal

from PyQt5 import QtCore, QtGui, QtWidgets

from . import config
from .config import RESOURCE_PATH
from .dialog import KODialog, NameDialog, StackDialog
from .util import Image, amount_format, decimal_conversion


class TextItem(QtWidgets.QGraphicsTextItem):
    n_decimals = 1

    _fontstr = None

    def __init__(
        self,
        postfix="",
        prefix="",
        currency="",
        currency_is_after=True,
        hide_if_empty=True,
        content_is_number=False,
        color=config.config["text"].get("global_font_color"),  # noqa
        point_size=config.config["text"].getint("global_font_size"),  # noqa
        weight=config.config["text"].getint("global_font_weight"),  # noqa
        italic=False,
        *a,
        **kwa,
    ) -> None:
        super().__init__(*a, **kwa)
        if self._fontstr is None:
            _load_font()
        # Size the font in *pixels* of the scene, not in points: point sizes
        # depend on the screen's logical DPI, so on a 4K/high-DPI display the
        # text used to come out 1.5-2x larger than the table it sits on.
        # 1 pt = 4/3 px at the 96 DPI the layout was designed for.
        self._point_size = point_size
        font = QtGui.QFont(self._fontstr)
        font.setPixelSize(round(point_size * 4 / 3))
        font.setWeight(weight)
        font.setItalic(italic)
        self.setFont(font)
        self.setDefaultTextColor(QtGui.QColor(color))
        self.set_center(0, 0)
        self.prefix = prefix
        self.postfix = postfix
        self.hide_if_empty = hide_if_empty
        if content_is_number:
            self._content = 0
        else:
            self._content = ""
        self.content_is_number = content_is_number
        self.currency = currency
        self.currency_is_after = currency_is_after

    def point_size(self):
        return self._point_size

    def color(self):
        return self.defaultTextColor()

    def weight(self):
        return self.font().weight()

    def font_kwargs(self):
        return {
            "point_size": self.point_size(),
            "color": self.color(),
            "weight": self.weight(),
        }

    @property
    def content(self):
        return self._content

    @content.setter
    def content(self, value) -> None:
        log.debug(f"Updating content of {self}")
        if self.hide_if_empty and not value:
            log.debug(f"Hiding {self} because empty value")
            self.setVisible(False)
        else:
            self.setVisible(True)
        old_width = self.boundingRect().width()
        self._content = value
        text = self.prefix
        if not self.currency_is_after:
            text += self.currency
        if self.content_is_number:
            text += amount_format(value, self.n_decimals)
        else:
            text += str(value)
        if self.currency_is_after:
            text += self.currency
        text += self.postfix
        self.setPlainText(text)
        new_width = self.boundingRect().width()
        super().moveBy((old_width - new_width) / 2, 0)

    def get_pos_if_content(self, content):
        item = TextItem(
            postfix=self.postfix,
            prefix=self.prefix,
            currency_is_after=self.currency_is_after,
            currency=self.currency,
            **self.font_kwargs(),
            content_is_number=self.content_is_number,
        )
        item.set_center(self.sceneBoundingRect().center())
        item.content = content
        # self.scene().addItem(item)
        return item.scenePos()

    def set_center(
        self,
        pos: QtCore.QPointF | QtCore.QPoint | float,
        y: float | None = None,
        scene=False,
    ) -> None:
        if y is not None:
            pos = QtCore.QPointF(pos, y)
        rect = self.boundingRect()
        rpos = self.scenePos() if scene else self.pos()
        offset = pos - rect.center() - rpos
        super().moveBy(offset.x(), offset.y())


class StackItem(QtWidgets.QGraphicsItemGroup):
    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self.stack_item = TextItem(
            hide_if_empty=False, content_is_number=True, color="yellow"
        )
        self.action_item = TextItem()
        self.addToGroup(self.stack_item)
        self.addToGroup(self.action_item)
        self.timer = QtCore.QTimer()
        self.timer.setSingleShot(True)

    @property
    def stack(self):
        return decimal_conversion(self.stack_item.content)

    @stack.setter
    def stack(self, value) -> None:
        self.timer.timeout.connect(lambda: setattr(self.stack_item, "content", value))
        if not self.timer.isActive():
            self.stack_item.content = value

    @property
    def action(self) -> None:
        return

    @action.setter
    def action(self, value) -> None:
        log.debug(f"Setting timer to briefly display action {value}")
        self.action_item.content = value
        self.stack_item.setVisible(False)
        start = time.time()
        log.debug(f"Timer start:{start}")
        timer = self.timer
        timer.timeout.connect(lambda: self.stack_item.setVisible(True))
        timer.timeout.connect(lambda: self.action_item.setVisible(False))
        timer.timeout.connect(
            lambda: log.debug(f"end:{time.time()} ({time.time() - start})")
        )
        timer.start(config.config["animation"].getint("LAST_ACTION_DURATION"))

    def set_center(self, *a) -> None:
        self.stack_item.set_center(*a)
        self.action_item.set_center(*a)

    def dialog(self) -> None:
        win = self.scene().parent()
        dialog = StackDialog(win, self.stack)
        if dialog.exec():
            self.stack = dialog.get_value()

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        log.debug("Click on stack")
        win = self.scene().parent()
        if win.state != win.State.INIT:
            return
        self.dialog()
        # noinspection PyTypeChecker


class KOBadge(QtWidgets.QGraphicsItemGroup):
    """KO (bounty) badge shown next to a player: a dark pill with a target icon
    and the bounty amount, in the style of online tournament tables.

    The value is purely informational: nothing in the engine uses it.
    """

    PADDING = 6
    GAP = 4

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        conf = config.config
        self._ko = Decimal(0)
        self._anchor = (0.0, 0.0, "right")

        self.background = QtWidgets.QGraphicsPathItem()
        self.background.setBrush(QtGui.QColor(conf["text"].get("ko_background")))
        self.background.setPen(QtGui.QPen(QtCore.Qt.NoPen))

        self.icon = Image.get("chips/ko")
        self.icon.setScale(conf["look"].getfloat("ko_icon_scale"))

        self.amount_item = TextItem(
            postfix=conf["text"].get("ko_suffix"),
            content_is_number=True,
            hide_if_empty=False,
            point_size=conf["text"].getint("ko_font_size"),
        )

        for item in (self.background, self.icon, self.amount_item):
            self.addToGroup(item)
        self.setZValue(5)
        self._layout()

    @property
    def ko(self) -> Decimal:
        return self._ko

    @ko.setter
    def ko(self, value) -> None:
        self._ko = decimal_conversion(str(value))
        self.amount_item.content = self._ko
        self._layout()

    def set_anchor(self, x: float, y: float, side: str = "right") -> None:
        """Place the badge beside the cards. With side="right" its top-left
        corner sits at (x, y) in the parent's coordinates; with side="left" its
        top-right corner does. Both are shifted by the ko_offset_* config
        values (offset_x is mirrored on the left side)."""
        self._anchor = (x, y, side)
        self._layout()

    def _layout(self) -> None:
        icon_rect = self.icon.boundingRect()
        icon_w = icon_rect.width() * self.icon.scale()
        icon_h = icon_rect.height() * self.icon.scale()
        text_rect = self.amount_item.boundingRect()
        height = max(icon_h, text_rect.height()) + 2 * self.PADDING
        width = self.PADDING + icon_w + self.GAP + text_rect.width() + self.PADDING

        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(0, 0, width, height), height / 2, height / 2)
        self.background.setPath(path)
        self.icon.setPos(self.PADDING, (height - icon_h) / 2)
        self.amount_item.setPos(
            self.PADDING + icon_w + self.GAP, (height - text_rect.height()) / 2
        )

        conf = config.config["position"]
        x, y, side = self._anchor
        offset_x = conf.getfloat("ko_offset_x", 0)
        if side == "left":
            x = x - width - offset_x
        else:
            x = x + offset_x
        self.setPos(x, y + conf.getfloat("ko_offset_y", 0))

    def dialog(self) -> None:
        win = self.scene().parent()
        dialog = KODialog(win, self.ko)
        if dialog.exec():
            self.ko = dialog.get_value()

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        log.debug("Click on KO badge")
        win = self.scene().parent()
        if win.state not in (win.State.INIT, win.State.ACTIONS):
            return
        if event.button() != QtCore.Qt.LeftButton:
            return
        self.dialog()


class NameItem(TextItem):
    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        log.debug(f"Click on {self}")
        win = self.scene().parent()
        # noinspection PyTypeChecker
        dialog = NameDialog(win, self.content)
        if dialog.exec():
            self.content = dialog.widgets["lineEdit"].text()


def _load_font() -> None:
    _id = QtGui.QFontDatabase.addApplicationFont(str(RESOURCE_PATH / "Lato-Black.ttf"))
    _fontstr = QtGui.QFontDatabase.applicationFontFamilies(_id)
    try:
        TextItem._fontstr = _fontstr[0]
    except IndexError:
        log.warning("Could not load Lato font file for some reason")
        TextItem._fontstr = "Lato"


log = logging.getLogger(__name__)
