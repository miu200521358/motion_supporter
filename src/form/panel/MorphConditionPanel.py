# -*- coding: utf-8 -*-
#
import wx
import wx.lib.newevent
import sys
import os

from form.panel.BasePanel import BasePanel
from form.parts.BaseFilePickerCtrl import BaseFilePickerCtrl
from form.parts.HistoryFilePickerCtrl import HistoryFilePickerCtrl
from form.parts.ConsoleCtrl import ConsoleCtrl
from form.worker.MorphConditionWorkerThread import MorphConditionWorkerThread
from form.parts.TargetMorphConditionDialog import TargetMorphConditionDialog
from utils import MFormUtils, MFileUtils  # noqa
from utils.MLogger import MLogger  # noqa

logger = MLogger(__name__)
TIMER_ID = wx.NewId()

# イベント定義
(MorphConditionThreadEvent, EVT_CSV_THREAD) = wx.lib.newevent.NewEvent()


class MorphConditionPanel(BasePanel):
    def __init__(self, frame: wx.Frame, morph_condition: wx.Notebook, tab_idx: int):
        super().__init__(frame, morph_condition, tab_idx)
        self.convert_morph_condition_worker = None

        self.header_sizer = wx.BoxSizer(wx.VERTICAL)

        self.description_txt = wx.StaticText(
            self, wx.ID_ANY, "対象モーションVMD/VPDの指定モーフを任意の条件に合わせて調整します。\n", wx.DefaultPosition, wx.DefaultSize, 0
        )
        self.header_sizer.Add(self.description_txt, 0, wx.ALL, 5)

        self.static_line01 = wx.StaticLine(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        self.header_sizer.Add(self.static_line01, 0, wx.EXPAND | wx.ALL, 5)

        # 対象VMDファイルコントロール
        self.morph_condition_vmd_file_ctrl = HistoryFilePickerCtrl(
            self.frame,
            self,
            "対象モーションVMD/VPD",
            "対象モーションVMDファイルを開く",
            ("vmd", "vpd"),
            wx.FLP_DEFAULT_STYLE,
            "調整したい対象モーションのVMDパスを指定してください。\nD&Dでの指定、開くボタンからの指定、履歴からの選択ができます。",
            file_model_spacer=46,
            title_parts_ctrl=None,
            title_parts2_ctrl=None,
            file_histories_key="morph_condition_vmd",
            is_change_output=True,
            is_aster=False,
            is_save=False,
            set_no=1,
        )
        self.header_sizer.Add(self.morph_condition_vmd_file_ctrl.sizer, 1, wx.EXPAND, 0)

        # 出力先VMDファイルコントロール
        self.output_morph_condition_vmd_file_ctrl = BaseFilePickerCtrl(
            frame,
            self,
            "出力対象VMD",
            "出力対象VMDファイルを開く",
            ("vmd"),
            wx.FLP_OVERWRITE_PROMPT | wx.FLP_SAVE | wx.FLP_USE_TEXTCTRL,
            "調整結果の対象VMD出力パスを指定してください。\n対象VMDファイル名に基づいて自動生成されますが、任意のパスに変更することも可能です。",
            is_aster=False,
            is_save=True,
            set_no=1,
        )
        self.header_sizer.Add(self.output_morph_condition_vmd_file_ctrl.sizer, 1, wx.EXPAND, 0)

        self.sizer.Add(self.header_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # 条件sizer
        self.condition_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # モーフ名指定
        self.morph_condition_target_txt_ctrl = wx.TextCtrl(
            self,
            wx.ID_ANY,
            "",
            wx.DefaultPosition,
            (450, 100),
            wx.HSCROLL | wx.VSCROLL | wx.TE_MULTILINE | wx.TE_READONLY,
        )
        self.morph_condition_target_txt_ctrl.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DLIGHT))
        self.condition_sizer.Add(self.morph_condition_target_txt_ctrl, 1, wx.EXPAND | wx.ALL, 5)

        self.morph_condition_target_btn_ctrl = wx.Button(
            self, wx.ID_ANY, "モーフ指定", wx.DefaultPosition, wx.DefaultSize, 0
        )
        self.morph_condition_target_btn_ctrl.SetToolTip("モーションに登録されているモーフから、調整したいモーフを指定できます")
        self.morph_condition_target_btn_ctrl.Bind(wx.EVT_BUTTON, self.on_click_morph_target)
        self.condition_sizer.Add(self.morph_condition_target_btn_ctrl, 0, wx.ALIGN_BOTTOM | wx.ALL, 5)

        self.sizer.Add(self.condition_sizer, 0, wx.EXPAND | wx.ALL, 5)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # モーフ調整実行ボタン
        self.morph_condition_btn_ctrl = wx.Button(
            self, wx.ID_ANY, "モーフ条件調整実行", wx.DefaultPosition, wx.Size(200, 50), 0
        )
        self.morph_condition_btn_ctrl.SetToolTip("モーフを調整したVMDを生成します。")
        self.morph_condition_btn_ctrl.Bind(wx.EVT_BUTTON, self.on_convert_morph_condition)
        btn_sizer.Add(self.morph_condition_btn_ctrl, 0, wx.ALL, 5)

        self.sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.SHAPED, 5)

        # コンソール
        self.console_ctrl = ConsoleCtrl(
            self,
            self.frame.logging_level,
            wx.ID_ANY,
            wx.EmptyString,
            wx.DefaultPosition,
            wx.Size(-1, 320),
            wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_NONE | wx.HSCROLL | wx.VSCROLL | wx.WANTS_CHARS,
        )
        self.console_ctrl.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DLIGHT))
        self.console_ctrl.Bind(wx.EVT_CHAR, lambda event: MFormUtils.on_select_all(event, self.console_ctrl))
        self.sizer.Add(self.console_ctrl, 1, wx.ALL | wx.EXPAND, 5)

        # ゲージ
        self.gauge_ctrl = wx.Gauge(self, wx.ID_ANY, 100, wx.DefaultPosition, wx.DefaultSize, wx.GA_HORIZONTAL)
        self.gauge_ctrl.SetValue(0)
        self.sizer.Add(self.gauge_ctrl, 0, wx.ALL | wx.EXPAND, 5)

        self.fit()

        # フレームに変換完了処理バインド
        self.frame.Bind(EVT_CSV_THREAD, self.on_convert_morph_condition_result)

        # ボーン選択用ダイアログ
        self.morph_dialog = TargetMorphConditionDialog(self.frame, self)

    def on_wheel_spin_ctrl(self, event: wx.Event, inc=1):
        self.frame.on_wheel_spin_ctrl(event, inc)
        self.set_output_vmd_path(event)

    def on_click_morph_target(self, event: wx.Event):
        self.disable()

        sys.stdout = self.console_ctrl
        # VMD読み込み
        self.morph_condition_vmd_file_ctrl.load()

        if (
            self.morph_condition_vmd_file_ctrl.data
            and self.morph_condition_vmd_file_ctrl.data.digest != self.morph_dialog.vmd_digest
        ):

            # データが揃ってたら押下可能
            self.morph_condition_btn_ctrl.Enable()
            # リストクリア
            self.morph_condition_target_txt_ctrl.SetValue("")
            # モーフ選択用ダイアログ
            self.morph_dialog.Destroy()
            self.morph_dialog = TargetMorphConditionDialog(self.frame, self)
            self.morph_dialog.initialize()
        else:
            if not self.morph_condition_vmd_file_ctrl.data:
                logger.error("対象モーションVMD/VPDが未指定です。", decoration=MLogger.DECORATION_BOX)
                self.enable()
                return

        self.enable()

        if self.morph_dialog.ShowModal() == wx.ID_CANCEL:
            return  # the user changed their mind

        # 選択されたモーフリストを入力欄に設定
        morph_list = self.morph_dialog.get_morph_list()
        selections = [
            "【{0}】が【{1}{2}】だったら【{3}】倍にする".format(morph_set[0], morph_set[1], morph_set[2], morph_set[3])
            for morph_set in morph_list
        ]
        self.morph_condition_target_txt_ctrl.SetValue("\n".join(selections))

        self.morph_dialog.Hide()

    # ファイル変更時の処理
    def on_change_file(self, event: wx.Event):
        self.set_output_vmd_path(event, is_force=True)

    def set_output_vmd_path(self, event, is_force=False):
        output_morph_condition_vmd_path = MFileUtils.get_output_morph_condition_vmd_path(
            self.morph_condition_vmd_file_ctrl.file_ctrl.GetPath(),
            self.output_morph_condition_vmd_file_ctrl.file_ctrl.GetPath(),
            is_force,
        )

        self.output_morph_condition_vmd_file_ctrl.file_ctrl.SetPath(output_morph_condition_vmd_path)

        if len(output_morph_condition_vmd_path) >= 255 and os.name == "nt":
            logger.error(
                "生成予定のファイルパスがWindowsの制限を超えています。\n生成予定パス: {0}".format(output_morph_condition_vmd_path),
                decoration=MLogger.DECORATION_BOX,
            )

    # フォーム無効化
    def disable(self):
        self.morph_condition_vmd_file_ctrl.disable()
        self.output_morph_condition_vmd_file_ctrl.disable()
        self.morph_condition_btn_ctrl.Disable()
        self.morph_condition_target_btn_ctrl.Disable()

    # フォーム無効化
    def enable(self):
        self.morph_condition_vmd_file_ctrl.enable()
        self.output_morph_condition_vmd_file_ctrl.enable()
        self.morph_condition_btn_ctrl.Enable()
        self.morph_condition_target_btn_ctrl.Enable()

    def on_doubleclick(self, event: wx.Event):
        self.timer.Stop()
        logger.warning("ダブルクリックされました。", decoration=MLogger.DECORATION_BOX)
        event.Skip(False)
        return False

    # モーフ条件調整変換
    def on_convert_morph_condition(self, event: wx.Event):
        self.timer = wx.Timer(self, TIMER_ID)
        self.timer.Start(200)
        self.Bind(wx.EVT_TIMER, self.on_convert, id=TIMER_ID)

    # モーフ条件調整変換
    def on_convert(self, event: wx.Event):
        self.timer.Stop()
        self.Unbind(wx.EVT_TIMER, id=TIMER_ID)
        # フォーム無効化
        self.disable()
        # タブ固定
        self.fix_tab()
        # コンソールクリア
        self.console_ctrl.Clear()
        # 出力先をモーフ条件調整パネルのコンソールに変更
        sys.stdout = self.console_ctrl

        self.morph_condition_vmd_file_ctrl.save()

        # JSON出力
        MFileUtils.save_history(self.frame.mydir_path, self.frame.file_hitories)

        self.elapsed_time = 0
        result = True
        result = self.morph_condition_vmd_file_ctrl.is_valid() and result

        if not result:
            # 終了音
            self.frame.sound_finish()
            # タブ移動可
            self.release_tab()
            # フォーム有効化
            self.enable()

            return result

        # モーフ条件調整変換開始
        if self.morph_condition_btn_ctrl.GetLabel() == "モーフ条件調整停止" and self.convert_morph_condition_worker:
            # フォーム無効化
            self.disable()
            # 停止状態でボタン押下時、停止
            self.convert_morph_condition_worker.stop()

            # タブ移動可
            self.frame.release_tab()
            # フォーム有効化
            self.frame.enable()
            # ワーカー終了
            self.convert_morph_condition_worker = None
            # プログレス非表示
            self.gauge_ctrl.SetValue(0)

            logger.warning("モーフ条件調整を中断します。", decoration=MLogger.DECORATION_BOX)
            self.morph_condition_btn_ctrl.SetLabel("モーフ条件調整")

            event.Skip(False)
        elif not self.convert_morph_condition_worker:
            # フォーム無効化
            self.disable()
            # タブ固定
            self.fix_tab()
            # コンソールクリア
            self.console_ctrl.Clear()
            # ラベル変更
            self.morph_condition_btn_ctrl.SetLabel("モーフ条件調整停止")
            self.morph_condition_btn_ctrl.Enable()

            self.convert_morph_condition_worker = MorphConditionWorkerThread(
                self.frame, MorphConditionThreadEvent, self.frame.is_saving, self.frame.is_out_log
            )
            self.convert_morph_condition_worker.start()

            event.Skip()
        else:
            logger.error("まだ処理が実行中です。終了してから再度実行してください。", decoration=MLogger.DECORATION_BOX)
            event.Skip(False)

        return result

    # モーフ条件調整変換完了処理
    def on_convert_morph_condition_result(self, event: wx.Event):
        self.elapsed_time = event.elapsed_time
        logger.info("\n処理時間: %s", self.show_worked_time())
        self.morph_condition_btn_ctrl.SetLabel("モーフ条件調整")

        # 終了音
        self.frame.sound_finish()

        # タブ移動可
        self.release_tab()
        # フォーム有効化
        self.enable()
        # ワーカー終了
        self.convert_morph_condition_worker = None
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
