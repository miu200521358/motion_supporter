# -*- coding: utf-8 -*-
#
import os
import wx
import wx.lib.newevent
import sys
import csv
import traceback
import operator

from form.panel.BasePanel import BasePanel
from form.parts.BaseFilePickerCtrl import BaseFilePickerCtrl
from form.parts.HistoryFilePickerCtrl import HistoryFilePickerCtrl
from form.parts.ConsoleCtrl import ConsoleCtrl
from form.worker.LegFKtoIKWorkerThread import LegFKtoIKWorkerThread
from utils import MFormUtils, MFileUtils
from utils.MLogger import MLogger # noqa

logger = MLogger(__name__)
TIMER_ID = wx.NewId()

# イベント定義
(LegFKtoIKThreadEvent, EVT_SMOOTH_THREAD) = wx.lib.newevent.NewEvent()

GROUND_LEGS = ["", "右かかと", "左かかと", "右つま先", "左つま先"]


class LegFKtoIKPanel(BasePanel):
        
    def __init__(self, frame: wx.Frame, leg_fk2ik: wx.Notebook, tab_idx: int):
        super().__init__(frame, leg_fk2ik, tab_idx)
        self.convert_leg_fk2ik_worker = None

        self.header_sizer = wx.BoxSizer(wx.VERTICAL)

        self.description_txt = wx.StaticText(self, wx.ID_ANY, u"足FK（足・ひざ・足首）を足IK（足ＩＫの位置と角度）に変換します" \
                                             + "\nIKonoffもIKonに変換されます。FKは残してあるので、IKoffにしても同じ動きになります。" \
                                             + "\n不要キー削除を行うと、キーが間引きされます。キー間がオリジナルから多少ずれ、やや時間がかかります。", wx.DefaultPosition, wx.DefaultSize, 0)
        self.header_sizer.Add(self.description_txt, 0, wx.ALL, 5)

        self.static_line01 = wx.StaticLine(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        self.header_sizer.Add(self.static_line01, 0, wx.EXPAND | wx.ALL, 5)

        # 対象VMDファイルコントロール
        self.leg_fk2ik_vmd_file_ctrl = HistoryFilePickerCtrl(self.frame, self, u"対象モーションVMD/VPD", u"対象モーションVMDファイルを開く", ("vmd", "vpd"), wx.FLP_DEFAULT_STYLE, \
                                                             u"調整したい対象モーションのVMDパスを指定してください。\nD&Dでの指定、開くボタンからの指定、履歴からの選択ができます。", \
                                                             file_model_spacer=46, title_parts_ctrl=None, title_parts2_ctrl=None, file_histories_key="leg_fk2ik_vmd", is_change_output=True, \
                                                             is_aster=False, is_save=False, set_no=1)
        self.header_sizer.Add(self.leg_fk2ik_vmd_file_ctrl.sizer, 1, wx.EXPAND, 0)

        # 対象PMXファイルコントロール
        self.leg_fk2ik_model_file_ctrl = HistoryFilePickerCtrl(self.frame, self, u"適用モデルPMX", u"適用モデルPMXファイルを開く", ("pmx"), wx.FLP_DEFAULT_STYLE, \
                                                               u"モーションを適用したいモデルのPMXパスを指定してください。\nD&Dでの指定、開くボタンからの指定、履歴からの選択ができます。", \
                                                               file_model_spacer=60, title_parts_ctrl=None, title_parts2_ctrl=None, file_histories_key="leg_fk2ik_pmx", \
                                                               is_change_output=True, is_aster=False, is_save=False, set_no=1)
        self.header_sizer.Add(self.leg_fk2ik_model_file_ctrl.sizer, 1, wx.EXPAND, 0)

        # 出力先VMDファイルコントロール
        self.output_leg_fk2ik_vmd_file_ctrl = BaseFilePickerCtrl(frame, self, u"出力対象VMD", u"出力対象VMDファイルを開く", ("vmd"), wx.FLP_OVERWRITE_PROMPT | wx.FLP_SAVE | wx.FLP_USE_TEXTCTRL, \
                                                                 u"調整結果の対象VMD出力パスを指定してください。\n対象VMDファイル名に基づいて自動生成されますが、任意のパスに変更することも可能です。", \
                                                                 is_aster=False, is_save=True, set_no=1)
        self.header_sizer.Add(self.output_leg_fk2ik_vmd_file_ctrl.sizer, 1, wx.EXPAND, 0)

        self.setting_flg_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.ankle_horizonal_flg_ctrl = wx.CheckBox(self, wx.ID_ANY, u"足首水平化", wx.DefaultPosition, wx.DefaultSize, 0)
        self.ankle_horizonal_flg_ctrl.SetToolTip(u"チェックを入れると、水平に近い足首キーフレを地面と水平になるように角度を調整します。")
        self.ankle_horizonal_flg_ctrl.Bind(wx.EVT_CHECKBOX, self.on_change_file)
        self.setting_flg_sizer.Add(self.ankle_horizonal_flg_ctrl, 0, wx.ALL, 5)

        self.ground_leg_flg_ctrl = wx.CheckBox(self, wx.ID_ANY, u"かかと・つま先Y=0", wx.DefaultPosition, wx.DefaultSize, 0)
        self.ground_leg_flg_ctrl.SetToolTip(u"チェックを入れると、「右かかと、左かかと、右つま先、左つま先」の最も低いY値の全体中央値がY=0になるように合わせます。")
        self.ground_leg_flg_ctrl.Bind(wx.EVT_CHECKBOX, self.on_change_file)
        self.setting_flg_sizer.Add(self.ground_leg_flg_ctrl, 0, wx.ALL, 5)

        self.leg_error_tolerance_txt = wx.StaticText(self, wx.ID_ANY, u"足IKブレ固定", wx.DefaultPosition, wx.DefaultSize, 0)
        self.leg_error_tolerance_txt.Wrap(-1)
        self.setting_flg_sizer.Add(self.leg_error_tolerance_txt, 0, wx.ALL, 5)

        # 足IKブレ固定コントロール
        self.leg_error_tolerance_ctrl = wx.SpinCtrlDouble(self, id=wx.ID_ANY, size=wx.Size(60, -1), value="0.8", min=0, max=10, initial=0.8, inc=0.1)
        self.leg_error_tolerance_ctrl.SetToolTip(u"足IKを固定するブレの許容範囲を指定します。\n" \
                                                 + "指定されたブレ距離範囲内の足IKは同じ位置に固定します。")
        self.leg_error_tolerance_ctrl.Bind(wx.EVT_MOUSEWHEEL, lambda event: self.on_wheel_spin_ctrl(event, 0.1))
        self.setting_flg_sizer.Add(self.leg_error_tolerance_ctrl, 0, wx.ALL, 5)

        # 不要キー削除処理
        self.remove_unnecessary_flg_ctrl = wx.CheckBox(self, wx.ID_ANY, u"不要キー削除処理を追加実行する", wx.DefaultPosition, wx.DefaultSize, 0)
        self.remove_unnecessary_flg_ctrl.SetToolTip(u"チェックを入れると、不要キー削除処理を追加で実行します。キーが減る分、キー間が少しズレる事があります。")
        self.remove_unnecessary_flg_ctrl.Bind(wx.EVT_CHECKBOX, self.on_change_file)
        self.setting_flg_sizer.Add(self.remove_unnecessary_flg_ctrl, 0, wx.ALL, 5)

        self.header_sizer.Add(self.setting_flg_sizer, 0, wx.EXPAND | wx.ALL, 5)

        self.sizer.Add(self.header_sizer, 0, wx.EXPAND | wx.ALL, 5)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # 多段分割変換実行ボタン
        self.leg_fk2ik_btn_ctrl = wx.Button(self, wx.ID_ANY, u"足ＦＫ変換", wx.DefaultPosition, wx.Size(200, 50), 0)
        self.leg_fk2ik_btn_ctrl.SetToolTip(u"足FKを足IKに変換したモーションを再生成します。")
        self.leg_fk2ik_btn_ctrl.Bind(wx.EVT_LEFT_DOWN, self.on_convert_leg_fk2ik)
        self.leg_fk2ik_btn_ctrl.Bind(wx.EVT_LEFT_DCLICK, self.on_doubleclick)
        btn_sizer.Add(self.leg_fk2ik_btn_ctrl, 0, wx.ALL, 5)

        self.sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.SHAPED, 5)

        # コンソール
        self.console_ctrl = ConsoleCtrl(self, self.frame.logging_level, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.Size(-1, 420), \
                                        wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_NONE | wx.HSCROLL | wx.VSCROLL | wx.WANTS_CHARS)
        self.console_ctrl.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DLIGHT))
        self.console_ctrl.Bind(wx.EVT_CHAR, lambda event: MFormUtils.on_select_all(event, self.console_ctrl))
        self.sizer.Add(self.console_ctrl, 1, wx.ALL | wx.EXPAND, 5)

        # ゲージ
        self.gauge_ctrl = wx.Gauge(self, wx.ID_ANY, 100, wx.DefaultPosition, wx.DefaultSize, wx.GA_HORIZONTAL)
        self.gauge_ctrl.SetValue(0)
        self.sizer.Add(self.gauge_ctrl, 0, wx.ALL | wx.EXPAND, 5)

        self.Layout()
        self.fit()

        # フレームに変換完了処理バインド
        self.frame.Bind(EVT_SMOOTH_THREAD, self.on_convert_leg_fk2ik_result)
    
    def on_wheel_spin_ctrl(self, event: wx.Event, inc=1):
        self.frame.on_wheel_spin_ctrl(event, inc)
        self.set_output_vmd_path(event)

    # ファイル変更時の処理
    def on_change_file(self, event: wx.Event):
        self.set_output_vmd_path(event, is_force=True)
    
    def set_output_vmd_path(self, event, is_force=False):
        output_leg_fk2ik_vmd_path = MFileUtils.get_output_leg_fk2ik_vmd_path(
            self.leg_fk2ik_vmd_file_ctrl.file_ctrl.GetPath(),
            self.leg_fk2ik_model_file_ctrl.file_ctrl.GetPath(),
            self.output_leg_fk2ik_vmd_file_ctrl.file_ctrl.GetPath(), is_force)

        self.output_leg_fk2ik_vmd_file_ctrl.file_ctrl.SetPath(output_leg_fk2ik_vmd_path)

        if len(output_leg_fk2ik_vmd_path) >= 255 and os.name == "nt":
            logger.error("生成予定のファイルパスがWindowsの制限を超えています。\n生成予定パス: {0}".format(output_leg_fk2ik_vmd_path), decoration=MLogger.DECORATION_BOX)
        
    # フォーム無効化
    def disable(self):
        self.leg_fk2ik_vmd_file_ctrl.disable()
        self.leg_fk2ik_model_file_ctrl.disable()
        self.output_leg_fk2ik_vmd_file_ctrl.disable()
        self.leg_fk2ik_btn_ctrl.Disable()
        self.ground_leg_flg_ctrl.Disable()
        self.ankle_horizonal_flg_ctrl.Disable()
        self.leg_error_tolerance_ctrl.Disable()
        self.remove_unnecessary_flg_ctrl.Disable()

    # フォーム無効化
    def enable(self):
        self.leg_fk2ik_vmd_file_ctrl.enable()
        self.leg_fk2ik_model_file_ctrl.enable()
        self.output_leg_fk2ik_vmd_file_ctrl.enable()
        self.leg_fk2ik_btn_ctrl.Enable()
        self.ground_leg_flg_ctrl.Enable()
        self.ankle_horizonal_flg_ctrl.Enable()
        self.leg_error_tolerance_ctrl.Enable()
        self.remove_unnecessary_flg_ctrl.Enable()

    def on_doubleclick(self, event: wx.Event):
        self.timer.Stop()
        logger.warning("ダブルクリックされました。", decoration=MLogger.DECORATION_BOX)
        event.Skip(False)
        return False
    
    # 多段分割変換
    def on_convert_leg_fk2ik(self, event: wx.Event):
        self.timer = wx.Timer(self, TIMER_ID)
        self.timer.Start(200)
        self.Bind(wx.EVT_TIMER, self.on_convert, id=TIMER_ID)

    # 多段分割変換
    def on_convert(self, event: wx.Event):
        self.timer.Stop()
        self.Unbind(wx.EVT_TIMER, id=TIMER_ID)
        # フォーム無効化
        self.disable()
        # タブ固定
        self.fix_tab()
        # コンソールクリア
        self.console_ctrl.Clear()
        # 出力先を多段分割パネルのコンソールに変更
        sys.stdout = self.console_ctrl

        self.leg_fk2ik_vmd_file_ctrl.save()
        self.leg_fk2ik_model_file_ctrl.save()

        # JSON出力
        MFileUtils.save_history(self.frame.mydir_path, self.frame.file_hitories)

        self.elapsed_time = 0
        result = True
        result = self.leg_fk2ik_vmd_file_ctrl.is_valid() and self.leg_fk2ik_model_file_ctrl.is_valid() and result

        if not result:
            # 終了音
            self.frame.sound_finish()
            # タブ移動可
            self.release_tab()
            # フォーム有効化
            self.enable()

            return result

        # 足ＦＫ変換変換開始
        if self.leg_fk2ik_btn_ctrl.GetLabel() == "足ＦＫ変換停止" and self.convert_leg_fk2ik_worker:
            # フォーム無効化
            self.disable()
            # 停止状態でボタン押下時、停止
            self.convert_leg_fk2ik_worker.stop()

            # タブ移動可
            self.frame.release_tab()
            # フォーム有効化
            self.frame.enable()
            # ワーカー終了
            self.convert_leg_fk2ik_worker = None
            # プログレス非表示
            self.gauge_ctrl.SetValue(0)

            logger.warning("足ＦＫ変換を中断します。", decoration=MLogger.DECORATION_BOX)
            self.leg_fk2ik_btn_ctrl.SetLabel("足ＦＫ変換")
            
            event.Skip(False)
        elif not self.convert_leg_fk2ik_worker:
            # フォーム無効化
            self.disable()
            # タブ固定
            self.fix_tab()
            # コンソールクリア
            self.console_ctrl.Clear()
            # ラベル変更
            self.leg_fk2ik_btn_ctrl.SetLabel("足ＦＫ変換停止")
            self.leg_fk2ik_btn_ctrl.Enable()

            self.convert_leg_fk2ik_worker = LegFKtoIKWorkerThread(self.frame, LegFKtoIKThreadEvent, self.frame.is_saving, self.frame.is_out_log)
            self.convert_leg_fk2ik_worker.start()
            
            event.Skip()
        else:
            logger.error("まだ処理が実行中です。終了してから再度実行してください。", decoration=MLogger.DECORATION_BOX)
            event.Skip(False)

        return result

    # 多段分割変換完了処理
    def on_convert_leg_fk2ik_result(self, event: wx.Event):
        self.elapsed_time = event.elapsed_time
        logger.info("\n処理時間: %s", self.show_worked_time())

        self.leg_fk2ik_btn_ctrl.SetLabel("足ＦＫ変換")

        # 終了音
        self.frame.sound_finish()

        # タブ移動可
        self.release_tab()
        # フォーム有効化
        self.enable()
        # ワーカー終了
        self.convert_leg_fk2ik_worker = None
        # プログレス非表示
        self.gauge_ctrl.SetValue(0)

    def show_worked_time(self):
        # 経過秒数を時分秒に変換
        td_m, td_s = divmod(self.elapsed_time, 60)

        if td_m == 0:
            worked_time = "{0:02d}秒".format(int(td_s))
        else:
            worked_time = "{0:02d}分{1:02d}秒".format(int(td_m), int(td_s))

        return worked_time
