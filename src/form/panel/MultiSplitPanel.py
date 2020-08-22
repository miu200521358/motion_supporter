# -*- coding: utf-8 -*-
#
import os
import wx
import wx.lib.newevent
import sys

from form.panel.BasePanel import BasePanel
from form.parts.BaseFilePickerCtrl import BaseFilePickerCtrl
from form.parts.HistoryFilePickerCtrl import HistoryFilePickerCtrl
from form.parts.ConsoleCtrl import ConsoleCtrl
from form.parts.TargetBoneDialog import TargetBoneDialog
from form.worker.MultiSplitWorkerThread import MultiSplitWorkerThread
from utils import MFormUtils, MFileUtils
from utils.MLogger import MLogger # noqa

logger = MLogger(__name__)
TIMER_ID = wx.NewId()

# イベント定義
(MultiSplitThreadEvent, EVT_SMOOTH_THREAD) = wx.lib.newevent.NewEvent()


class MultiSplitPanel(BasePanel):
        
    def __init__(self, frame: wx.Frame, multi_split: wx.Notebook, tab_idx: int):
        super().__init__(frame, multi_split, tab_idx)
        self.timer = wx.Timer(self, TIMER_ID)
        self.convert_multi_split_worker = None

        self.header_sizer = wx.BoxSizer(wx.VERTICAL)

        self.description_txt = wx.StaticText(self, wx.ID_ANY, u"モーションの指定ボーンの移動量と回転量をXYZに分割します。分割するボーンは「ボーン指定」ボタンから定義できます。" \
                                             + "\n回転ボーンは、YXZの順番で多段化したボーンを適用すると、回転結果がオリジナルと一致します。" \
                                             + "\n不要キー削除を行うと、キーが間引きされます。キー間がオリジナルから多少ずれ、またかなり時間がかかります。", wx.DefaultPosition, wx.DefaultSize, 0)
        self.header_sizer.Add(self.description_txt, 0, wx.ALL, 5)

        self.static_line01 = wx.StaticLine(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        self.header_sizer.Add(self.static_line01, 0, wx.EXPAND | wx.ALL, 5)

        # 対象VMDファイルコントロール
        self.vmd_file_ctrl = HistoryFilePickerCtrl(self.frame, self, u"対象モーションVMD/VPD", u"対象モーションVMDファイルを開く", ("vmd", "vpd"), wx.FLP_DEFAULT_STYLE, \
                                                   u"調整したい対象モーションのVMDパスを指定してください。\nD&Dでの指定、開くボタンからの指定、履歴からの選択ができます。", \
                                                   file_model_spacer=46, title_parts_ctrl=None, title_parts2_ctrl=None, file_histories_key="multi_split_vmd", is_change_output=True, \
                                                   is_aster=False, is_save=False, set_no=1)
        self.vmd_file_ctrl.file_ctrl.Bind(wx.EVT_FILEPICKER_CHANGED, self.on_change_file)
        self.header_sizer.Add(self.vmd_file_ctrl.sizer, 1, wx.EXPAND, 0)

        # 対象PMXファイルコントロール
        self.model_file_ctrl = HistoryFilePickerCtrl(self.frame, self, u"多段化済みモデルPMX", u"多段化済みモデルPMXファイルを開く", ("pmx"), wx.FLP_DEFAULT_STYLE, \
                                                     u"モーションを適用したいモデルのPMXパスを指定してください。\n人体モデル以外にも適用可能です。\nD&Dでの指定、開くボタンからの指定、履歴からの選択ができます。", \
                                                     file_model_spacer=49, title_parts_ctrl=None, title_parts2_ctrl=None, file_histories_key="multi_split_pmx", \
                                                     is_change_output=True, is_aster=False, is_save=False, set_no=1)
        self.model_file_ctrl.file_ctrl.Bind(wx.EVT_FILEPICKER_CHANGED, self.on_change_file)
        self.header_sizer.Add(self.model_file_ctrl.sizer, 1, wx.EXPAND, 0)

        # 出力先VMDファイルコントロール
        self.output_vmd_file_ctrl = BaseFilePickerCtrl(frame, self, u"出力対象VMD", u"出力対象VMDファイルを開く", ("vmd"), wx.FLP_OVERWRITE_PROMPT | wx.FLP_SAVE | wx.FLP_USE_TEXTCTRL, \
                                                       u"調整結果の対象VMD出力パスを指定してください。\n対象VMDファイル名に基づいて自動生成されますが、任意のパスに変更することも可能です。", \
                                                       is_aster=False, is_save=True, set_no=1)
        self.header_sizer.Add(self.output_vmd_file_ctrl.sizer, 1, wx.EXPAND, 0)

        self.sizer.Add(self.header_sizer, 0, wx.EXPAND | wx.ALL, 5)

        self.setting_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # ボーン名指定
        self.bone_target_txt_ctrl = wx.TextCtrl(self, wx.ID_ANY, "", wx.DefaultPosition, (450, 50), wx.HSCROLL | wx.VSCROLL | wx.TE_MULTILINE | wx.TE_READONLY)
        self.bone_target_txt_ctrl.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DLIGHT))
        self.setting_sizer.Add(self.bone_target_txt_ctrl, 1, wx.EXPAND | wx.ALL, 5)

        self.bone_target_btn_ctrl = wx.Button(self, wx.ID_ANY, u"ボーン指定", wx.DefaultPosition, wx.DefaultSize, 0)
        self.bone_target_btn_ctrl.SetToolTip(u"モーションに登録されているボーンから、分割したいボーンを指定できます")
        self.bone_target_btn_ctrl.Bind(wx.EVT_BUTTON, self.on_click_bone_target)
        self.setting_sizer.Add(self.bone_target_btn_ctrl, 0, wx.ALIGN_BOTTOM | wx.ALL, 5)

        self.sizer.Add(self.setting_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # 不要キー削除処理
        self.flg_sizer = wx.BoxSizer(wx.VERTICAL)
        self.remove_unnecessary_flg_ctrl = wx.CheckBox(self, wx.ID_ANY, u"不要キー削除処理を追加実行する", wx.DefaultPosition, wx.DefaultSize, 0)
        self.remove_unnecessary_flg_ctrl.SetToolTip(u"チェックを入れると、不要キー削除処理を追加で実行します。キーが減る分、キー間が少しズレる事があります。")
        self.flg_sizer.Add(self.remove_unnecessary_flg_ctrl, 0, wx.ALL, 5)
        self.sizer.Add(self.flg_sizer, 0, wx.EXPAND | wx.ALL, 5)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # 実行ボタン
        self.multi_split_btn_ctrl = wx.Button(self, wx.ID_ANY, u"多段分割", wx.DefaultPosition, wx.Size(200, 50), 0)
        self.multi_split_btn_ctrl.SetToolTip(u"キーフレを多段用に分割したモーションを生成します")
        self.multi_split_btn_ctrl.Bind(wx.EVT_LEFT_DOWN, self.on_convert_multi_split)
        self.multi_split_btn_ctrl.Bind(wx.EVT_LEFT_DCLICK, self.on_doubleclick)
        btn_sizer.Add(self.multi_split_btn_ctrl, 0, wx.ALL, 5)

        self.sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.SHAPED, 5)

        # コンソール
        self.console_ctrl = ConsoleCtrl(self, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.Size(-1, 420), \
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

        # ボーン選択用ダイアログ
        self.bone_dialog = TargetBoneDialog(self.frame, self, "→")

        # フレームに変換完了処理バインド
        self.frame.Bind(EVT_SMOOTH_THREAD, self.on_convert_multi_split_result)
    
    def on_click_bone_target(self, event: wx.Event):
        self.disable()

        sys.stdout = self.console_ctrl
        # VMD読み込み
        self.vmd_file_ctrl.load()
        # PMX読み込み
        self.model_file_ctrl.load()

        if (self.vmd_file_ctrl.data and self.model_file_ctrl.data and \
                (self.vmd_file_ctrl.data.digest != self.bone_dialog.vmd_digest or self.model_file_ctrl.data.digest != self.bone_dialog.pmx_digest)):

            # データが揃ってたら押下可能
            self.bone_target_btn_ctrl.Enable()
            # リストクリア
            self.bone_target_txt_ctrl.SetValue("")
            # ボーン選択用ダイアログ
            self.bone_dialog.Destroy()
            self.bone_dialog = TargetBoneDialog(self.frame, self, "→")
            self.bone_dialog.initialize()
        else:
            if not self.vmd_file_ctrl.data or not self.model_file_ctrl.data:
                logger.error("対象モーションVMD/VPDもしくは多段化済みモデルPMXが未指定です。", decoration=MLogger.DECORATION_BOX)
                self.enable()
                return

        self.enable()

        if self.bone_dialog.ShowModal() == wx.ID_CANCEL:
            return     # the user changed their mind

        # 選択されたボーンリストを入力欄に設定
        bone_list = self.bone_dialog.get_bone_list()

        selections = ["{0} {7} 【回転X: {1}】【回転Y: {2}】【回転Z: {3}】【移動X: {4}】【移動Y: {5}】【移動Z: {6}】" \
                      .format(bset[0], bset[1], bset[2], bset[3], bset[4], bset[5], bset[6], "→") for bset in bone_list]
        self.bone_target_txt_ctrl.SetValue('\n'.join(selections))

        self.bone_dialog.Hide()

    # ファイル変更時の処理
    def on_change_file(self, event: wx.Event):
        self.set_output_vmd_path(event, is_force=True)
    
    def set_output_vmd_path(self, event: wx.Event, is_force=False):
        output_multi_split_vmd_path = MFileUtils.get_output_multi_split_vmd_path(
            self.vmd_file_ctrl.file_ctrl.GetPath(),
            self.model_file_ctrl.file_ctrl.GetPath(),
            self.output_vmd_file_ctrl.file_ctrl.GetPath(), is_force)

        self.output_vmd_file_ctrl.file_ctrl.SetPath(output_multi_split_vmd_path)

        if len(output_multi_split_vmd_path) >= 255 and os.name == "nt":
            logger.error("生成予定のファイルパスがWindowsの制限を超えています。\n生成予定パス: {0}".format(output_multi_split_vmd_path), decoration=MLogger.DECORATION_BOX)

    # フォーム無効化
    def disable(self):
        self.vmd_file_ctrl.disable()
        self.model_file_ctrl.disable()
        self.output_vmd_file_ctrl.disable()
        self.bone_target_btn_ctrl.Disable()
        self.multi_split_btn_ctrl.Disable()

    # フォーム無効化
    def enable(self):
        self.vmd_file_ctrl.enable()
        self.model_file_ctrl.enable()
        self.output_vmd_file_ctrl.enable()
        self.bone_target_btn_ctrl.Enable()
        self.multi_split_btn_ctrl.Enable()

    def on_doubleclick(self, event: wx.Event):
        self.timer.Stop()
        logger.warning("ダブルクリックされました。", decoration=MLogger.DECORATION_BOX)
        event.Skip(False)
        return False
    
    def on_convert_multi_split(self, event: wx.Event):
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

        self.vmd_file_ctrl.save()
        self.model_file_ctrl.save()

        # JSON出力
        MFileUtils.save_history(self.frame.mydir_path, self.frame.file_hitories)

        self.elapsed_time = 0
        result = True
        result = self.vmd_file_ctrl.is_valid() and result
        result = self.model_file_ctrl.is_valid() and result

        if len(self.bone_target_txt_ctrl.GetValue()) == 0:
            logger.error("分割対象ボーンが指定されていません。", decoration=MLogger.DECORATION_BOX)
            result = False

        if not result:
            # 終了音
            self.frame.sound_finish()
            # タブ移動可
            self.release_tab()
            # フォーム有効化
            self.enable()

            return result

        # 多段分割変換開始
        if self.multi_split_btn_ctrl.GetLabel() == "多段分割停止" and self.convert_multi_split_worker:
            # フォーム無効化
            self.disable()
            # 停止状態でボタン押下時、停止
            self.convert_multi_split_worker.stop()

            # タブ移動可
            self.frame.release_tab()
            # フォーム有効化
            self.frame.enable()
            # ワーカー終了
            self.convert_multi_split_worker = None
            # プログレス非表示
            self.gauge_ctrl.SetValue(0)

            logger.warning("多段分割を中断します。", decoration=MLogger.DECORATION_BOX)
            self.multi_split_btn_ctrl.SetLabel("多段分割")
            
            event.Skip(False)
        elif not self.convert_multi_split_worker:
            # フォーム無効化
            self.disable()
            # タブ固定
            self.fix_tab()
            # コンソールクリア
            self.console_ctrl.Clear()
            # ラベル変更
            self.multi_split_btn_ctrl.SetLabel("多段分割停止")
            self.multi_split_btn_ctrl.Enable()

            self.convert_multi_split_worker = MultiSplitWorkerThread(self.frame, MultiSplitThreadEvent, self.frame.is_saving, self.frame.is_out_log)
            self.convert_multi_split_worker.start()
            
            event.Skip()
        else:
            logger.error("まだ処理が実行中です。終了してから再度実行してください。", decoration=MLogger.DECORATION_BOX)
            event.Skip(False)

        return result

    # 多段分割変換完了処理
    def on_convert_multi_split_result(self, event: wx.Event):
        self.elapsed_time = event.elapsed_time
        logger.info("\n処理時間: %s", self.show_worked_time())

        # 終了音
        self.frame.sound_finish()

        # タブ移動可
        self.release_tab()
        # フォーム有効化
        self.enable()
        # ワーカー終了
        self.convert_multi_split_worker = None
        # プログレス非表示
        self.gauge_ctrl.SetValue(0)
        # ラベル変更
        self.multi_split_btn_ctrl.SetLabel("多段分割")
        self.multi_split_btn_ctrl.Enable()

    def show_worked_time(self):
        # 経過秒数を時分秒に変換
        td_m, td_s = divmod(self.elapsed_time, 60)

        if td_m == 0:
            worked_time = "{0:02d}秒".format(int(td_s))
        else:
            worked_time = "{0:02d}分{1:02d}秒".format(int(td_m), int(td_s))

        return worked_time


