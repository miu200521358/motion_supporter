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
from form.worker.MultiSplitWorkerThread import MultiSplitWorkerThread
from utils import MFormUtils, MFileUtils
from utils.MLogger import MLogger # noqa

logger = MLogger(__name__)

# イベント定義
(MultiSplitThreadEvent, EVT_SMOOTH_THREAD) = wx.lib.newevent.NewEvent()


class MultiSplitPanel(BasePanel):
        
    def __init__(self, frame: wx.Frame, multi_split: wx.Notebook, tab_idx: int):
        super().__init__(frame, multi_split, tab_idx)
        self.convert_multi_split_worker = None

        # ボーンリスト
        self.bone_set_dict = {}
        # ボーン選択用ダイアログ
        self.bone_dialog = TargetBoneDialog(self.frame)

        self.header_sizer = wx.BoxSizer(wx.VERTICAL)

        self.description_txt = wx.StaticText(self, wx.ID_ANY, u"モーションの指定ボーンの移動量と回転量をXYZに分割します。" \
                                             + "\n既存ボーン名＋[移動:M or 回転:R]＋[X or Y or Z] で新しくキーフレを生成します。（例：センターMY、右腕RX）", wx.DefaultPosition, wx.DefaultSize, 0)
        self.header_sizer.Add(self.description_txt, 0, wx.ALL, 5)

        self.static_line01 = wx.StaticLine(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        self.header_sizer.Add(self.static_line01, 0, wx.EXPAND | wx.ALL, 5)

        # 対象VMDファイルコントロール
        self.multi_split_vmd_file_ctrl = HistoryFilePickerCtrl(self.frame, self, u"対象モーションVMD", u"対象モーションVMDファイルを開く", ("vmd"), wx.FLP_DEFAULT_STYLE, \
                                                               u"調整したい対象モーションのVMDパスを指定してください。\nD&Dでの指定、開くボタンからの指定、履歴からの選択ができます。", \
                                                               file_model_spacer=0, title_parts_ctrl=None, title_parts2_ctrl=None, file_histories_key="multi_split_vmd", is_change_output=True, \
                                                               is_aster=False, is_save=False, set_no=1)
        self.multi_split_vmd_file_ctrl.file_ctrl.Bind(wx.EVT_FILEPICKER_CHANGED, self.on_change_file)
        self.header_sizer.Add(self.multi_split_vmd_file_ctrl.sizer, 1, wx.EXPAND, 0)

        # 対象PMXファイルコントロール
        self.model_file_ctrl = HistoryFilePickerCtrl(self.frame, self, u"適用モデルPMX", u"適用モデルPMXファイルを開く", ("pmx"), wx.FLP_DEFAULT_STYLE, \
                                                     u"モーションを適用したいモデルのPMXパスを指定してください。\n人体モデル以外にも適用可能です。\nD&Dでの指定、開くボタンからの指定、履歴からの選択ができます。", \
                                                     file_model_spacer=0, title_parts_ctrl=None, title_parts2_ctrl=None, file_histories_key="multi_split_pmx", \
                                                     is_change_output=True, is_aster=False, is_save=False, set_no=1)
        self.model_file_ctrl.file_ctrl.Bind(wx.EVT_FILEPICKER_CHANGED, self.on_change_file)
        self.header_sizer.Add(self.model_file_ctrl.sizer, 1, wx.EXPAND, 0)

        # 出力先VMDファイルコントロール
        self.output_multi_split_vmd_file_ctrl = BaseFilePickerCtrl(frame, self, u"出力対象VMD", u"出力対象VMDファイルを開く", ("vmd"), wx.FLP_OVERWRITE_PROMPT | wx.FLP_SAVE | wx.FLP_USE_TEXTCTRL, \
                                                                   u"調整結果の対象VMD出力パスを指定してください。\n対象VMDファイル名に基づいて自動生成されますが、任意のパスに変更することも可能です。", \
                                                                   is_aster=False, is_save=True, set_no=1)
        self.header_sizer.Add(self.output_multi_split_vmd_file_ctrl.sizer, 1, wx.EXPAND, 0)

        self.sizer.Add(self.header_sizer, 0, wx.EXPAND | wx.ALL, 5)

        self.setting_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # ボーン名指定
        self.bone_target_txt_ctrl = wx.TextCtrl(self, wx.ID_ANY, "", wx.DefaultPosition, (450, 50), wx.HSCROLL | wx.VSCROLL | wx.TE_MULTILINE | wx.TE_READONLY)
        self.bone_target_txt_ctrl.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DLIGHT))
        self.setting_sizer.Add(self.bone_target_txt_ctrl, 1, wx.EXPAND | wx.ALL, 5)

        self.bone_target_btn_ctrl = wx.Button(self, wx.ID_ANY, u"ボーン選択", wx.DefaultPosition, wx.DefaultSize, 0)
        self.bone_target_btn_ctrl.SetToolTip(u"モーションに登録されているボーンから、分割したいボーンを選択できます")
        self.bone_target_btn_ctrl.Bind(wx.EVT_BUTTON, self.on_click_bone_target)
        self.setting_sizer.Add(self.bone_target_btn_ctrl, 0, wx.ALIGN_BOTTOM | wx.ALL, 5)

        self.static_line03 = wx.StaticLine(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        self.setting_sizer.Add(self.static_line03, 0, wx.EXPAND | wx.ALL, 5)

        self.sizer.Add(self.setting_sizer, 0, wx.EXPAND | wx.ALL, 5)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # 実行ボタン
        self.multi_split_btn_ctrl = wx.Button(self, wx.ID_ANY, u"多段分割", wx.DefaultPosition, wx.Size(200, 50), 0)
        self.multi_split_btn_ctrl.SetToolTip(u"キーフレを多段用に分割したモーションを生成します")
        self.multi_split_btn_ctrl.Bind(wx.EVT_BUTTON, self.on_convert_multi_split)
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

        # フレームに変換完了処理バインド
        self.frame.Bind(EVT_SMOOTH_THREAD, self.on_convert_multi_split_result)
    
    def on_click_bone_target(self, event: wx.Event):
        if self.bone_dialog.ShowModal() == wx.ID_CANCEL:
            return     # the user changed their mind

        # 一旦クリア
        self.bone_target_txt_ctrl.SetValue("")

        # 選択されたボーンリストを入力欄に設定
        selections = [self.bone_set_dict[0].rep_choices.GetString(n) for n in self.bone_set_dict[0].rep_choices.GetSelections()]
        self.bone_target_txt_ctrl.WriteText(', '.join(selections))

        self.bone_dialog.Hide()

    def on_wheel_spin_ctrl(self, event: wx.Event, inc=1):
        # self.frame.on_wheel_spin_ctrl(event, inc)
        self.set_output_vmd_path(event)

    # ファイル変更時の処理
    def on_change_file(self, event: wx.Event):
        self.set_output_vmd_path(event)
    
    def set_output_vmd_path(self, event, is_force=False):
        output_multi_split_vmd_path = MFileUtils.get_output_multi_split_vmd_path(
            self.multi_split_vmd_file_ctrl.file_ctrl.GetPath(),
            self.model_file_ctrl.file_ctrl.GetPath(),
            self.output_multi_split_vmd_file_ctrl.file_ctrl.GetPath(), is_force)

        self.output_multi_split_vmd_file_ctrl.file_ctrl.SetPath(output_multi_split_vmd_path)

        if len(output_multi_split_vmd_path) >= 255 and os.name == "nt":
            logger.error("生成予定のファイルパスがWindowsの制限を超えています。\n生成予定パス: {0}".format(output_multi_split_vmd_path), decoration=MLogger.DECORATION_BOX)

        if not self.multi_split_vmd_file_ctrl.data or (self.multi_split_vmd_file_ctrl.data and 0 in self.bone_set_dict and \
                                                       self.multi_split_vmd_file_ctrl.data.digest != self.bone_set_dict[0].rep_model_digest):
            # VMD読み込み
            sys.stdout = self.console_ctrl
            self.multi_split_vmd_file_ctrl.load()
            # ボーンセット登録
            new_bone_set = TargetBoneSet(self.frame, self, self.bone_dialog.scrolled_window)

            if 0 in self.bone_set_dict:
                # 置き換え
                self.bone_dialog.set_list_sizer.Hide(self.bone_set_dict[0].set_sizer, recursive=True)
                self.bone_dialog.set_list_sizer.Replace(self.bone_set_dict[0].set_sizer, new_bone_set.set_sizer, recursive=True)

                # 置き換えの場合、剛体リストクリア
                self.bone_target_txt_ctrl.SetValue("")
            else:
                # 新規追加
                self.bone_dialog.set_list_sizer.Add(new_bone_set.set_sizer, 0, wx.EXPAND | wx.ALL, 5)

            self.bone_set_dict[0] = new_bone_set

    # フォーム無効化
    def disable(self):
        self.multi_split_vmd_file_ctrl.disable()
        self.output_multi_split_vmd_file_ctrl.disable()
        self.multi_split_btn_ctrl.Disable()

    # フォーム無効化
    def enable(self):
        self.multi_split_vmd_file_ctrl.enable()
        self.output_multi_split_vmd_file_ctrl.enable()
        self.multi_split_btn_ctrl.Enable()

    # 多段分割変換
    def on_convert_multi_split(self, event: wx.Event):
        # フォーム無効化
        self.disable()
        # タブ固定
        self.fix_tab()
        # コンソールクリア
        self.console_ctrl.Clear()
        # 出力先を多段分割パネルのコンソールに変更
        sys.stdout = self.console_ctrl

        wx.GetApp().Yield()

        self.multi_split_vmd_file_ctrl.save()
        self.model_file_ctrl.save()

        # JSON出力
        MFileUtils.save_history(self.frame.mydir_path, self.frame.file_hitories)

        self.elapsed_time = 0
        result = True
        result = self.multi_split_vmd_file_ctrl.is_valid() and result

        if not result:
            # 終了音
            self.frame.sound_finish()
            # タブ移動可
            self.release_tab()
            # フォーム有効化
            self.enable()

            return result

        # 多段分割変換開始
        if self.convert_multi_split_worker:
            logger.error("まだ処理が実行中です。終了してから再度実行してください。", decoration=MLogger.DECORATION_BOX)
        else:
            # 別スレッドで実行
            self.convert_multi_split_worker = MultiSplitWorkerThread(self.frame, MultiSplitThreadEvent, self.frame.is_saving)
            self.convert_multi_split_worker.start()

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

    def show_worked_time(self):
        # 経過秒数を時分秒に変換
        td_m, td_s = divmod(self.elapsed_time, 60)

        if td_m == 0:
            worked_time = "{0:02d}秒".format(int(td_s))
        else:
            worked_time = "{0:02d}分{1:02d}秒".format(int(td_m), int(td_s))

        return worked_time

    def get_target_bones(self):
        target = []
        
        # 選択されたボーンリストを取得
        target = [self.bone_set_dict[0].rep_bone_names[n] for n in self.bone_set_dict[0].rep_choices.GetSelections()]
        
        return target
    

class TargetBoneSet():

    def __init__(self, frame: wx.Frame, panel: wx.Panel, window: wx.Window):
        self.frame = frame
        self.panel = panel
        self.window = window
        self.rep_model_digest = 0 if not panel.multi_split_vmd_file_ctrl.data else panel.multi_split_vmd_file_ctrl.data.digest
        self.rep_bones = []   # 選択肢文言
        self.rep_bone_names = []   # 選択肢文言に紐付くモーフ名
        self.rep_choices = None

        self.set_sizer = wx.BoxSizer(wx.VERTICAL)

        if panel.multi_split_vmd_file_ctrl.data:
            self.model_name_txt = wx.StaticText(self.window, wx.ID_ANY, panel.multi_split_vmd_file_ctrl.data.model_name[:15], wx.DefaultPosition, wx.DefaultSize, 0)
            self.model_name_txt.Wrap(-1)
            self.set_sizer.Add(self.model_name_txt, 0, wx.ALL, 5)

            for bone_name in panel.multi_split_vmd_file_ctrl.data.bones.keys():
                # 処理対象ボーン：有効なボーン
                self.rep_bones.append(bone_name)
                self.rep_bone_names.append(bone_name)

            # 選択コントロール
            self.rep_choices = wx.ListBox(self.window, id=wx.ID_ANY, choices=self.rep_bones, style=wx.LB_MULTIPLE | wx.LB_NEEDED_SB, size=(-1, 220))
            self.set_sizer.Add(self.rep_choices, 0, wx.ALL, 5)
        else:
            self.no_data_txt = wx.StaticText(self.window, wx.ID_ANY, u"データなし", wx.DefaultPosition, wx.DefaultSize, 0)
            self.no_data_txt.Wrap(-1)
            self.set_sizer.Add(self.no_data_txt, 0, wx.ALL, 5)


class TargetBoneDialog(wx.Dialog):

    def __init__(self, parent):
        super().__init__(parent, id=wx.ID_ANY, title="分割ボーン選択", pos=(-1, -1), size=(700, 450), style=wx.DEFAULT_DIALOG_STYLE, name="TargetBoneDialog")

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
        self.sizer.Add(self.btn_sizer, 0, wx.ALL, 5)

        self.static_line01 = wx.StaticLine(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        self.sizer.Add(self.static_line01, 0, wx.EXPAND | wx.ALL, 5)

        self.scrolled_window = wx.ScrolledWindow(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, \
                                                 wx.FULL_REPAINT_ON_RESIZE | wx.HSCROLL | wx.ALWAYS_SHOW_SB)
        self.scrolled_window.SetScrollRate(5, 5)

        # 接触回避用剛体セット用基本Sizer
        self.set_list_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # スクロールバーの表示のためにサイズ調整
        self.scrolled_window.SetSizer(self.set_list_sizer)
        self.scrolled_window.Layout()
        self.sizer.Add(self.scrolled_window, 1, wx.ALL | wx.EXPAND, 5)
        self.SetSizer(self.sizer)
        self.sizer.Layout()
        
        # 画面中央に表示
        self.CentreOnScreen()
        
        # 最初は隠しておく
        self.Hide()

