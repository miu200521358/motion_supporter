# -*- coding: utf-8 -*-
#
import os
import wx
import wx.lib.newevent
import sys
import csv
import traceback

from form.panel.BasePanel import BasePanel
from form.parts.BaseFilePickerCtrl import BaseFilePickerCtrl
from form.parts.HistoryFilePickerCtrl import HistoryFilePickerCtrl
from form.parts.ConsoleCtrl import ConsoleCtrl
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
                                             + "\n回転ボーンは、YXZの順番で多段化したボーンを適用すると、回転結果がオリジナルと一致します。", wx.DefaultPosition, wx.DefaultSize, 0)
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
        self.model_file_ctrl = HistoryFilePickerCtrl(self.frame, self, u"適用モデルPMX", u"適用モデルPMXファイルを開く", ("pmx"), wx.FLP_DEFAULT_STYLE, \
                                                     u"モーションを適用したいモデルのPMXパスを指定してください。\n人体モデル以外にも適用可能です。\nD&Dでの指定、開くボタンからの指定、履歴からの選択ができます。", \
                                                     file_model_spacer=0, title_parts_ctrl=None, title_parts2_ctrl=None, file_histories_key="multi_split_pmx", \
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
        self.bone_target_txt_ctrl = wx.TextCtrl(self, wx.ID_ANY, "", wx.DefaultPosition, (450, 60), wx.HSCROLL | wx.VSCROLL | wx.TE_MULTILINE | wx.TE_READONLY)
        self.bone_target_txt_ctrl.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DLIGHT))
        self.setting_sizer.Add(self.bone_target_txt_ctrl, 1, wx.EXPAND | wx.ALL, 5)

        self.bone_target_btn_ctrl = wx.Button(self, wx.ID_ANY, u"ボーン指定", wx.DefaultPosition, wx.DefaultSize, 0)
        self.bone_target_btn_ctrl.SetToolTip(u"モーションに登録されているボーンから、分割したいボーンを指定できます")
        self.bone_target_btn_ctrl.Bind(wx.EVT_BUTTON, self.on_click_bone_target)
        self.setting_sizer.Add(self.bone_target_btn_ctrl, 0, wx.ALIGN_BOTTOM | wx.ALL, 5)

        self.static_line03 = wx.StaticLine(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        self.setting_sizer.Add(self.static_line03, 0, wx.EXPAND | wx.ALL, 5)

        self.sizer.Add(self.setting_sizer, 0, wx.EXPAND | wx.ALL, 5)

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
        self.bone_dialog = TargetBoneDialog(self.frame, self)

        # フレームに変換完了処理バインド
        self.frame.Bind(EVT_SMOOTH_THREAD, self.on_convert_multi_split_result)
    
    def on_click_bone_target(self, event: wx.Event):
        self.disable()

        # VMD読み込み
        sys.stdout = self.console_ctrl
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
            self.bone_dialog = TargetBoneDialog(self.frame, self)
            self.bone_dialog.initialize()
        else:
            if not self.vmd_file_ctrl.data or not self.model_file_ctrl.data:
                logger.error("対象モーションVMD/VPDもしくは適用モデルPMXが未指定です。", decoration=MLogger.DECORATION_BOX)
                self.enable()
                return

        self.enable()

        if self.bone_dialog.ShowModal() == wx.ID_CANCEL:
            return     # the user changed their mind

        # 選択されたボーンリストを入力欄に設定
        bone_list = self.bone_dialog.get_bone_list()

        selections = ["{0} → 【回転X: {1}】【回転Y: {2}】【回転Z: {3}】【移動X: {4}】【移動Y: {5}】【移動Z: {6}】" \
                      .format(bset[0], bset[1], bset[2], bset[3], bset[4], bset[5], bset[6]) for bset in bone_list]
        self.bone_target_txt_ctrl.SetValue('\n'.join(selections))

        self.bone_dialog.Hide()

    # ファイル変更時の処理
    def on_change_file(self, event: wx.Event):
        self.set_output_vmd_path(event)
    
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


class TargetBoneDialog(wx.Dialog):

    def __init__(self, frame: wx.Frame, panel: wx.Panel):
        super().__init__(frame, id=wx.ID_ANY, title="分割ボーン指定", pos=(-1, -1), size=(700, 450), style=wx.DEFAULT_DIALOG_STYLE, name="TargetBoneDialog")

        self.frame = frame
        self.panel = panel
        self.vmd_digest = 0 if not self.panel.vmd_file_ctrl.data else self.panel.vmd_file_ctrl.data.digest
        self.pmx_digest = 0 if not self.panel.model_file_ctrl.data else self.panel.model_file_ctrl.data.digest
        self.org_bones = [""]  # 選択肢文言
        self.rep_bones = [""]
        self.org_choices = []   # 選択コントロール
        self.rep_mx_choices = []
        self.rep_my_choices = []
        self.rep_mz_choices = []
        self.rep_rx_choices = []
        self.rep_ry_choices = []
        self.rep_rz_choices = []

        self.sizer = wx.BoxSizer(wx.VERTICAL)

        # 説明文
        self.description_txt = wx.StaticText(self, wx.ID_ANY, u"多段分割したいボーン名を選択してください。", wx.DefaultPosition, wx.DefaultSize, 0)
        self.sizer.Add(self.description_txt, 0, wx.ALL, 5)

        # ボタン
        self.btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.ok_btn = wx.Button(self, wx.ID_OK, "OK")
        self.btn_sizer.Add(self.ok_btn, 0, wx.ALL, 5)

        self.calcel_btn = wx.Button(self, wx.ID_CANCEL, "キャンセル")
        self.btn_sizer.Add(self.calcel_btn, 0, wx.ALL, 5)

        # インポートボタン
        self.import_btn_ctrl = wx.Button(self, wx.ID_ANY, u"インポート ...", wx.DefaultPosition, wx.DefaultSize, 0)
        self.import_btn_ctrl.SetToolTip(u"ボーン分割データをCSVファイルから読み込みます。\nファイル選択ダイアログが開きます。")
        self.import_btn_ctrl.Bind(wx.EVT_BUTTON, self.on_import)
        self.btn_sizer.Add(self.import_btn_ctrl, 0, wx.ALL, 5)

        # エクスポートボタン
        self.export_btn_ctrl = wx.Button(self, wx.ID_ANY, u"エクスポート ...", wx.DefaultPosition, wx.DefaultSize, 0)
        self.export_btn_ctrl.SetToolTip(u"ボーン分割データをCSVファイルに出力します。\n調整対象VMDと同じフォルダに出力します。")
        self.export_btn_ctrl.Bind(wx.EVT_BUTTON, self.on_export)
        self.btn_sizer.Add(self.export_btn_ctrl, 0, wx.ALL, 5)

        # 行追加ボタン
        self.add_line_btn_ctrl = wx.Button(self, wx.ID_ANY, u"行追加", wx.DefaultPosition, wx.DefaultSize, 0)
        self.add_line_btn_ctrl.SetToolTip(u"ボーン分割の組み合わせ行を追加します。\n上限はありません。")
        self.add_line_btn_ctrl.Bind(wx.EVT_BUTTON, self.on_add_line)
        self.btn_sizer.Add(self.add_line_btn_ctrl, 0, wx.ALL, 5)

        self.sizer.Add(self.btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 5)

        self.static_line01 = wx.StaticLine(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        self.sizer.Add(self.static_line01, 0, wx.EXPAND | wx.ALL, 5)

        self.window = wx.ScrolledWindow(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.FULL_REPAINT_ON_RESIZE | wx.HSCROLL | wx.ALWAYS_SHOW_SB)
        self.window.SetScrollRate(5, 5)

        # セット用基本Sizer
        self.set_list_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # タイトル部分
        self.grid_sizer = wx.FlexGridSizer(0, 8, 0, 0)
        self.grid_sizer.SetFlexibleDirection(wx.BOTH)
        self.grid_sizer.SetNonFlexibleGrowMode(wx.FLEX_GROWMODE_SPECIFIED)

        # モデル名 ----------
        self.org_model_name_txt = wx.StaticText(self.window, wx.ID_ANY, "モデルなし", wx.DefaultPosition, wx.DefaultSize, 0)
        self.org_model_name_txt.Wrap(-1)
        self.grid_sizer.Add(self.org_model_name_txt, 0, wx.ALL, 5)

        self.name_arrow_txt = wx.StaticText(self.window, wx.ID_ANY, u"　→　", wx.DefaultPosition, wx.DefaultSize, 0)
        self.name_arrow_txt.Wrap(-1)
        self.grid_sizer.Add(self.name_arrow_txt, 0, wx.CENTER | wx.ALL, 5)

        self.rotate_x_txt = wx.StaticText(self.window, wx.ID_ANY, "回転X", wx.DefaultPosition, wx.DefaultSize, 0)
        self.rotate_x_txt.Wrap(-1)
        self.grid_sizer.Add(self.rotate_x_txt, 0, wx.ALL, 5)

        self.rotate_y_txt = wx.StaticText(self.window, wx.ID_ANY, "回転Y", wx.DefaultPosition, wx.DefaultSize, 0)
        self.rotate_y_txt.Wrap(-1)
        self.grid_sizer.Add(self.rotate_y_txt, 0, wx.ALL, 5)

        self.rotate_z_txt = wx.StaticText(self.window, wx.ID_ANY, "回転Z", wx.DefaultPosition, wx.DefaultSize, 0)
        self.rotate_z_txt.Wrap(-1)
        self.grid_sizer.Add(self.rotate_z_txt, 0, wx.ALL, 5)

        self.move_x_txt = wx.StaticText(self.window, wx.ID_ANY, "移動X", wx.DefaultPosition, wx.DefaultSize, 0)
        self.move_x_txt.Wrap(-1)
        self.grid_sizer.Add(self.move_x_txt, 0, wx.ALL, 5)

        self.move_y_txt = wx.StaticText(self.window, wx.ID_ANY, "移動Y", wx.DefaultPosition, wx.DefaultSize, 0)
        self.move_y_txt.Wrap(-1)
        self.grid_sizer.Add(self.move_y_txt, 0, wx.ALL, 5)

        self.move_z_txt = wx.StaticText(self.window, wx.ID_ANY, "移動Z", wx.DefaultPosition, wx.DefaultSize, 0)
        self.move_z_txt.Wrap(-1)
        self.grid_sizer.Add(self.move_z_txt, 0, wx.ALL, 5)

        self.set_list_sizer.Add(self.grid_sizer, 0, wx.ALL, 5)

        # スクロールバーの表示のためにサイズ調整
        self.window.SetSizer(self.set_list_sizer)
        self.window.Layout()
        self.sizer.Add(self.window, 1, wx.ALL | wx.EXPAND, 5)
        self.SetSizer(self.sizer)
        self.sizer.Layout()
        
        # 画面中央に表示
        self.CentreOnScreen()
        
        # 最初は隠しておく
        self.Hide()
    
    def initialize(self):
        if self.panel.vmd_file_ctrl.data and self.panel.model_file_ctrl.data:
            self.org_model_name_txt.SetLabel(self.panel.vmd_file_ctrl.data.model_name[:10])

            for bone_name in self.panel.vmd_file_ctrl.data.bones.keys():
                # 処理対象ボーン：有効なボーン
                self.org_bones.append(bone_name)
        
            for bone_name, bone_data in self.panel.model_file_ctrl.data.bones.items():
                if bone_data.getVisibleFlag():
                    # 処理対象ボーン：有効なボーン
                    self.rep_bones.append(bone_name)

            # 一行追加
            self.add_line()

    def on_import(self, event: wx.Event):
        input_bone_path = MFileUtils.get_output_split_bone_path(
            self.panel.vmd_file_ctrl.file_ctrl.GetPath(),
            self.panel.model_file_ctrl.file_ctrl.GetPath()
        )

        with wx.FileDialog(self.frame, "ボーン組み合わせCSVを読み込む", wildcard=u"CSVファイル (*.csv)|*.csv|すべてのファイル (*.*)|*.*",
                           defaultDir=os.path.dirname(input_bone_path),
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:

            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return     # the user changed their mind

            # Proceed loading the file chosen by the user
            target_bone_path = fileDialog.GetPath()
            try:
                with open(target_bone_path, 'r') as f:
                    cr = csv.reader(f, delimiter=",", quotechar='"')
                    bone_lines = [row for row in cr]

                    if len(bone_lines) == 0:
                        return

                    org_choice_values = bone_lines[0]
                    rep_rx_choice_values = bone_lines[1]
                    rep_ry_choice_values = bone_lines[2]
                    rep_rz_choice_values = bone_lines[3]
                    rep_mx_choice_values = bone_lines[4]
                    rep_my_choice_values = bone_lines[5]
                    rep_mz_choice_values = bone_lines[6]

                    for (ov, rmxv, rmyv, rmzv, rrxv, rryv, rrzv) in zip(org_choice_values, rep_mx_choice_values, rep_my_choice_values, rep_mz_choice_values, \
                                                                        rep_rx_choice_values, rep_ry_choice_values, rep_rz_choice_values):
                        oc = self.org_choices[-1]
                        rrxc = self.rep_rx_choices[-1]
                        rryc = self.rep_ry_choices[-1]
                        rrzc = self.rep_rz_choices[-1]
                        rmxc = self.rep_mx_choices[-1]
                        rmyc = self.rep_my_choices[-1]
                        rmzc = self.rep_mz_choices[-1]

                        is_seted = False
                        for v, c in [(ov, oc), (rmxv, rmxc), (rmyv, rmyc), (rmzv, rmzc), (rrxv, rrxc), (rryv, rryc), (rrzv, rrzc)]:
                            logger.debug("v: %s, c: %s", v, c)
                            for n in range(c.GetCount()):
                                if c.GetString(n).strip() == v:
                                    c.SetSelection(n)
                                    is_seted = True
                            
                        if is_seted:
                            # 行追加
                            self.add_line()
                        else:
                            # ひとつも追加がなかった場合、終了
                            break

                # パス変更
                self.panel.set_output_vmd_path(event)

            except Exception:
                dialog = wx.MessageDialog(self.frame, "CSVファイルが読み込めませんでした '%s'\n\n%s." % (target_bone_path, traceback.format_exc()), style=wx.OK)
                dialog.ShowModal()
                dialog.Destroy()

    def on_export(self, event: wx.Event):
        org_choice_values = []
        rep_rx_choice_values = []
        rep_ry_choice_values = []
        rep_rz_choice_values = []
        rep_mx_choice_values = []
        rep_my_choice_values = []
        rep_mz_choice_values = []

        for m in self.get_bone_list():
            org_choice_values.append(m[0])
            rep_rx_choice_values.append(m[1])
            rep_ry_choice_values.append(m[2])
            rep_rz_choice_values.append(m[3])
            rep_mx_choice_values.append(m[4])
            rep_my_choice_values.append(m[5])
            rep_mz_choice_values.append(m[6])

        output_bone_path = MFileUtils.get_output_split_bone_path(
            self.panel.vmd_file_ctrl.file_ctrl.GetPath(),
            self.panel.model_file_ctrl.file_ctrl.GetPath()
        )

        try:
            with open(output_bone_path, encoding='cp932', mode='w', newline='') as f:
                cw = csv.writer(f, delimiter=",", quotechar='"', quoting=csv.QUOTE_ALL)

                cw.writerow(org_choice_values)
                cw.writerow(rep_rx_choice_values)
                cw.writerow(rep_ry_choice_values)
                cw.writerow(rep_rz_choice_values)
                cw.writerow(rep_mx_choice_values)
                cw.writerow(rep_my_choice_values)
                cw.writerow(rep_mz_choice_values)

            logger.info("出力成功: %s" % output_bone_path)

            dialog = wx.MessageDialog(self.frame, "多段ボーンデータのエクスポートに成功しました \n'%s'" % (output_bone_path), style=wx.OK)
            dialog.ShowModal()
            dialog.Destroy()

        except Exception:
            dialog = wx.MessageDialog(self.frame, "多段ボーンデータのエクスポートに失敗しました \n'%s'\n\n%s." % (output_bone_path, traceback.format_exc()), style=wx.OK)
            dialog.ShowModal()
            dialog.Destroy()

    def on_add_line(self, event: wx.Event):
        # 行追加
        self.add_line()

    def get_bone_list(self):
        bone_list = []

        for midx, (oc, rmxc, rmyc, rmzc, rrxc, rryc, rrzc) in \
                enumerate(zip(self.org_choices, self.rep_mx_choices, self.rep_my_choices, self.rep_mz_choices, self.rep_rx_choices, self.rep_ry_choices, self.rep_rz_choices)):
            if oc.GetSelection() > 0 and (rmxc.GetSelection() > 0 or rmyc.GetSelection() > 0 or rmzc.GetSelection() > 0 \
                                          or rrxc.GetSelection() > 0 or rryc.GetSelection() > 0 or rrzc.GetSelection() > 0):
                
                ov = oc.GetString(oc.GetSelection())
                rrxv = rrxc.GetString(rrxc.GetSelection())
                rryv = rryc.GetString(rryc.GetSelection())
                rrzv = rrzc.GetString(rrzc.GetSelection())
                rmxv = rmxc.GetString(rmxc.GetSelection())
                rmyv = rmyc.GetString(rmyc.GetSelection())
                rmzv = rmzc.GetString(rmzc.GetSelection())

                if (ov, rrxv, rryv, rrzv, rmxv, rmyv, rmzv) not in bone_list:
                    # ボーンペアがまだ登録されてないければ登録
                    bone_list.append((ov, rrxv, rryv, rrzv, rmxv, rmyv, rmzv))

        # どれも設定されていなければFalse
        return bone_list

    def add_line(self):
        # 置換前ボーン
        self.org_choices.append(wx.Choice(self.window, id=wx.ID_ANY, choices=self.org_bones))
        self.org_choices[-1].Bind(wx.EVT_CHOICE, lambda event: self.on_change_choice(event, len(self.org_choices) - 1))
        self.grid_sizer.Add(self.org_choices[-1], 0, wx.ALL, 5)

        # 矢印
        self.arrow_txt = wx.StaticText(self.window, wx.ID_ANY, u"　→　", wx.DefaultPosition, wx.DefaultSize, 0)
        self.arrow_txt.Wrap(-1)
        self.grid_sizer.Add(self.arrow_txt, 0, wx.CENTER | wx.ALL, 5)

        # 置換後ボーン(RX)
        self.rep_rx_choices.append(wx.Choice(self.window, id=wx.ID_ANY, choices=self.rep_bones))
        self.rep_rx_choices[-1].Bind(wx.EVT_CHOICE, lambda event: self.on_change_choice(event, len(self.rep_rx_choices) - 1))
        self.grid_sizer.Add(self.rep_rx_choices[-1], 0, wx.ALL, 5)

        # 置換後ボーン(RY)
        self.rep_ry_choices.append(wx.Choice(self.window, id=wx.ID_ANY, choices=self.rep_bones))
        self.rep_ry_choices[-1].Bind(wx.EVT_CHOICE, lambda event: self.on_change_choice(event, len(self.rep_ry_choices) - 1))
        self.grid_sizer.Add(self.rep_ry_choices[-1], 0, wx.ALL, 5)

        # 置換後ボーン(RZ)
        self.rep_rz_choices.append(wx.Choice(self.window, id=wx.ID_ANY, choices=self.rep_bones))
        self.rep_rz_choices[-1].Bind(wx.EVT_CHOICE, lambda event: self.on_change_choice(event, len(self.rep_rz_choices) - 1))
        self.grid_sizer.Add(self.rep_rz_choices[-1], 0, wx.ALL, 5)

        # 置換後ボーン(MX)
        self.rep_mx_choices.append(wx.Choice(self.window, id=wx.ID_ANY, choices=self.rep_bones))
        self.rep_mx_choices[-1].Bind(wx.EVT_CHOICE, lambda event: self.on_change_choice(event, len(self.rep_mx_choices) - 1))
        self.grid_sizer.Add(self.rep_mx_choices[-1], 0, wx.ALL, 5)

        # 置換後ボーン(MY)
        self.rep_my_choices.append(wx.Choice(self.window, id=wx.ID_ANY, choices=self.rep_bones))
        self.rep_my_choices[-1].Bind(wx.EVT_CHOICE, lambda event: self.on_change_choice(event, len(self.rep_my_choices) - 1))
        self.grid_sizer.Add(self.rep_my_choices[-1], 0, wx.ALL, 5)

        # 置換後ボーン(MZ)
        self.rep_mz_choices.append(wx.Choice(self.window, id=wx.ID_ANY, choices=self.rep_bones))
        self.rep_mz_choices[-1].Bind(wx.EVT_CHOICE, lambda event: self.on_change_choice(event, len(self.rep_mz_choices) - 1))
        self.grid_sizer.Add(self.rep_mz_choices[-1], 0, wx.ALL, 5)

        # スクロールバーの表示のためにサイズ調整
        self.set_list_sizer.Layout()
        self.set_list_sizer.FitInside(self.window)

    # ボーンが設定されているか
    def is_set_bone(self):
        for midx, (oc, rmxc, rmyc, rmzc, rrxc, rryc, rrzc) in \
                enumerate(zip(self.org_choices, self.rep_mx_choices, self.rep_my_choices, self.rep_mz_choices, self.rep_rx_choices, self.rep_ry_choices, self.rep_rz_choices)):
            if oc.GetSelection() > 0 and (rmxc.GetSelection() > 0 or rmyc.GetSelection() > 0 or rmzc.GetSelection() > 0 \
                                          or rrxc.GetSelection() > 0 or rryc.GetSelection() > 0 or rrzc.GetSelection() > 0):
                # なんか設定されていたらOK
                return True

        # どれも設定されていなければFalse
        return False

    def on_change_choice(self, event: wx.Event, midx: int):
        # 最後である場合、行追加
        if midx == len(self.org_choices) - 1 and self.org_choices[midx].GetSelection() > 0 and \
                (self.rep_mx_choices[midx].GetSelection() > 0 or self.rep_my_choices[midx].GetSelection() > 0 or self.rep_mz_choices[midx].GetSelection() > 0 \
                    or self.rep_rx_choices[midx].GetSelection() > 0 or self.rep_ry_choices[midx].GetSelection() > 0 or self.rep_rz_choices[midx].GetSelection() > 0):
            self.add_line()





