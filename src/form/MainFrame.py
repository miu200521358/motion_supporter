# -*- coding: utf-8 -*-
#
import os
import sys
import wx

from form.panel.ParentPanel import ParentPanel
from form.panel.NoisePanel import NoisePanel
from form.panel.MultiSplitPanel import MultiSplitPanel
from form.panel.MultiJoinPanel import MultiJoinPanel
from form.panel.ArmIKtoFKPanel import ArmIKtoFKPanel
from form.panel.ArmTwistOffPanel import ArmTwistOffPanel
from form.panel.LegFKtoIKPanel import LegFKtoIKPanel
from form.panel.BlendPanel import BlendPanel
from form.panel.BezierPanel import BezierPanel
from form.panel.SmoothPanel import SmoothPanel
from module.MMath import MRect, MVector3D, MVector4D, MQuaternion, MMatrix4x4 # noqa
from utils import MFormUtils, MFileUtils # noqa
from utils.MLogger import MLogger # noqa

if os.name == "nt":
    import winsound     # Windows版のみインポート

logger = MLogger(__name__)


# イベント
(SizingThreadEvent, EVT_SIZING_THREAD) = wx.lib.newevent.NewEvent()
(LoadThreadEvent, EVT_LOAD_THREAD) = wx.lib.newevent.NewEvent()


class MainFrame(wx.Frame):

    def __init__(self, parent, mydir_path: str, version_name: str, logging_level: int, is_saving: bool, is_out_log: bool):
        self.version_name = version_name
        self.logging_level = logging_level
        self.is_out_log = is_out_log
        self.is_saving = is_saving
        self.mydir_path = mydir_path
        self.elapsed_time = 0
        self.popuped_finger_warning = False
        
        self.worker = None
        self.load_worker = None

        wx.Frame.__init__(self, parent, id=wx.ID_ANY, title=u"モーションサポーター ローカル版 {0}".format(self.version_name), \
                          pos=wx.DefaultPosition, size=wx.Size(600, 650), style=wx.DEFAULT_FRAME_STYLE | wx.TAB_TRAVERSAL)

        # ファイル履歴読み込み
        self.file_hitories = MFileUtils.read_history(self.mydir_path)

        # ---------------------------------------------

        self.SetSizeHints(wx.DefaultSize, wx.DefaultSize)

        bSizer1 = wx.BoxSizer(wx.VERTICAL)

        self.note_ctrl = wx.Notebook(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, 0)
        if self.logging_level == MLogger.FULL or self.logging_level == MLogger.DEBUG_FULL:
            # フルデータの場合
            self.note_ctrl.SetBackgroundColour("RED")
        elif self.logging_level == MLogger.DEBUG:
            # テスト（デバッグ版）の場合
            self.note_ctrl.SetBackgroundColour("CORAL")
        elif self.logging_level == MLogger.TIMER:
            # 時間計測の場合
            self.note_ctrl.SetBackgroundColour("YELLOW")
        elif not is_saving:
            # ログありの場合、色変え
            self.note_ctrl.SetBackgroundColour("BLUE")
        elif is_out_log:
            # ログありの場合、色変え
            self.note_ctrl.SetBackgroundColour("AQUAMARINE")
        else:
            self.note_ctrl.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNSHADOW))

        # ---------------------------------------------

        # 全親タブ
        self.parent_panel_ctrl = ParentPanel(self, self.note_ctrl, 1)
        self.note_ctrl.AddPage(self.parent_panel_ctrl, u"全親移植", False)
        
        # ゆらぎタブ
        self.noise_panel_ctrl = NoisePanel(self, self.note_ctrl, 2)
        self.note_ctrl.AddPage(self.noise_panel_ctrl, u"ゆらぎ複製", False)
        
        # 多段分割タブ
        self.multi_split_panel_ctrl = MultiSplitPanel(self, self.note_ctrl, 3)
        self.note_ctrl.AddPage(self.multi_split_panel_ctrl, u"多段分割", False)
        
        # 多段統合タブ
        self.multi_join_panel_ctrl = MultiJoinPanel(self, self.note_ctrl, 4)
        self.note_ctrl.AddPage(self.multi_join_panel_ctrl, u"多段統合", False)
        
        # 足FK2FKタブ
        self.leg_fk2ik_panel_ctrl = LegFKtoIKPanel(self, self.note_ctrl, 5)
        self.note_ctrl.AddPage(self.leg_fk2ik_panel_ctrl, u"足FKtoIK", False)

        # 腕IKtoFKタブ
        self.arm_ik2fk_panel_ctrl = ArmIKtoFKPanel(self, self.note_ctrl, 6)
        self.note_ctrl.AddPage(self.arm_ik2fk_panel_ctrl, u"腕IKtoFK", False)
        
        # スムーズタブ
        self.smooth_panel_ctrl = SmoothPanel(self, self.note_ctrl, 7)
        self.note_ctrl.AddPage(self.smooth_panel_ctrl, u"スムーズ", False)

        # ブレンドタブ
        self.blend_panel_ctrl = BlendPanel(self, self.note_ctrl, 8)
        self.note_ctrl.AddPage(self.blend_panel_ctrl, u"ブレンド", False)

        # 補間タブ
        self.bezier_panel_ctrl = BezierPanel(self, self.note_ctrl, 9)
        self.note_ctrl.AddPage(self.bezier_panel_ctrl, u"補間", False)
                
        # # 捩りOFFタブ
        # self.arm_twist_off_panel_ctrl = ArmTwistOffPanel(self, self.note_ctrl, 9)
        # self.note_ctrl.AddPage(self.arm_twist_off_panel_ctrl, u"捩りOFF", False)
        
        # ---------------------------------------------

        # タブ押下時の処理
        self.note_ctrl.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_tab_change)

        # ---------------------------------------------

        bSizer1.Add(self.note_ctrl, 1, wx.EXPAND, 5)

        # デフォルトの出力先はファイルタブのコンソール
        sys.stdout = self.parent_panel_ctrl.console_ctrl

        self.SetSizer(bSizer1)
        self.Layout()

        self.Centre(wx.BOTH)
    
    def on_idle(self, event: wx.Event):
        pass

    def on_tab_change(self, event: wx.Event):

        if self.parent_panel_ctrl.is_fix_tab:
            self.note_ctrl.ChangeSelection(self.parent_panel_ctrl.tab_idx)
            event.Skip()
            return

        elif self.smooth_panel_ctrl.is_fix_tab:
            self.note_ctrl.ChangeSelection(self.smooth_panel_ctrl.tab_idx)
            event.Skip()
            return

        elif self.blend_panel_ctrl.is_fix_tab:
            self.note_ctrl.ChangeSelection(self.blend_panel_ctrl.tab_idx)
            event.Skip()
            return

    # タブ移動可
    def release_tab(self):
        pass

    # フォーム入力可
    def enable(self):
        pass

    def show_worked_time(self):
        # 経過秒数を時分秒に変換
        td_m, td_s = divmod(self.elapsed_time, 60)

        if td_m == 0:
            worked_time = "{0:02d}秒".format(int(td_s))
        else:
            worked_time = "{0:02d}分{1:02d}秒".format(int(td_m), int(td_s))

        return worked_time

    def sound_finish(self):
        # 終了音を鳴らす
        if os.name == "nt":
            # Windows
            try:
                winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS)
            except Exception:
                pass

    def on_wheel_spin_ctrl(self, event: wx.Event, inc=0.1):
        # スピンコントロール変更時
        if event.GetWheelRotation() > 0:
            event.GetEventObject().SetValue(event.GetEventObject().GetValue() + inc)
            if event.GetEventObject().GetValue() >= 0:
                event.GetEventObject().SetBackgroundColour("WHITE")
        else:
            event.GetEventObject().SetValue(event.GetEventObject().GetValue() - inc)
            if event.GetEventObject().GetValue() < 0:
                event.GetEventObject().SetBackgroundColour("TURQUOISE")
