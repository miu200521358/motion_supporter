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
from form.worker.NoiseWorkerThread import NoiseWorkerThread
from utils import MFormUtils, MFileUtils
from utils.MLogger import MLogger # noqa

logger = MLogger(__name__)
TIMER_ID = wx.NewId()

# イベント定義
(NoiseThreadEvent, EVT_SMOOTH_THREAD) = wx.lib.newevent.NewEvent()


class NoisePanel(BasePanel):
        
    def __init__(self, frame: wx.Frame, noise: wx.Notebook, tab_idx: int):
        super().__init__(frame, noise, tab_idx)
        self.timer = wx.Timer(self, TIMER_ID)
        self.convert_noise_worker = None

        self.header_sizer = wx.BoxSizer(wx.VERTICAL)

        self.description_txt = wx.StaticText(self, wx.ID_ANY, u"モーションをゆらぎ（ノイズ）を付与して複製します。\n" \
                                             + "出力ファイル名のNxxは指定ゆらぎの大きさ、nxxxは複製連番、axxはやる気係数（身体の振りの大きさ）です。", wx.DefaultPosition, wx.DefaultSize, 0)
        self.header_sizer.Add(self.description_txt, 0, wx.ALL, 5)

        self.static_line01 = wx.StaticLine(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        self.header_sizer.Add(self.static_line01, 0, wx.EXPAND | wx.ALL, 5)

        # 対象VMDファイルコントロール
        self.noise_vmd_file_ctrl = HistoryFilePickerCtrl(self.frame, self, u"対象モーションVMD/VPD", u"対象モーションVMD/VPDファイルを開く", ("vmd", "vpd"), wx.FLP_DEFAULT_STYLE, \
                                                         u"調整したい対象モーションのVMDパスを指定してください。\nD&Dでの指定、開くボタンからの指定、履歴からの選択ができます。", \
                                                         file_model_spacer=46, title_parts_ctrl=None, title_parts2_ctrl=None, file_histories_key="noise_vmd", is_change_output=True, \
                                                         is_aster=False, is_save=False, set_no=1)
        self.header_sizer.Add(self.noise_vmd_file_ctrl.sizer, 1, wx.EXPAND, 0)

        # 出力先VMDファイルコントロール
        self.output_noise_vmd_file_ctrl = BaseFilePickerCtrl(frame, self, u"出力対象VMD", u"出力対象VMDファイルを開く", ("vmd"), wx.FLP_OVERWRITE_PROMPT | wx.FLP_SAVE | wx.FLP_USE_TEXTCTRL, \
                                                             u"調整結果の対象VMD出力パスを指定してください。\n対象VMDファイル名に基づいて自動生成されますが、任意のパスに変更することも可能です。", \
                                                             is_aster=False, is_save=True, set_no=1)
        self.header_sizer.Add(self.output_noise_vmd_file_ctrl.sizer, 1, wx.EXPAND, 0)

        self.sizer.Add(self.header_sizer, 0, wx.EXPAND | wx.ALL, 5)

        self.setting_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # ゆらぎの大きさ
        self.noise_size_txt = wx.StaticText(self, wx.ID_ANY, u"ゆらぎの大きさ", wx.DefaultPosition, wx.DefaultSize, 0)
        self.setting_sizer.Add(self.noise_size_txt, 0, wx.ALL, 5)

        self.noise_size_ctrl = wx.SpinCtrl(self, id=wx.ID_ANY, size=wx.Size(60, -1), value="8", min=0, max=99999999, initial=8)
        self.noise_size_ctrl.SetToolTip(u"ゆらぎの大きさを指定して下さい。値が大きいほど、ゆらぎが大きくなります。")
        self.noise_size_ctrl.Bind(wx.EVT_SPINCTRL, self.on_change_file)
        self.setting_sizer.Add(self.noise_size_ctrl, 0, wx.ALL, 5)

        # 複製数
        self.copy_cnt_txt = wx.StaticText(self, wx.ID_ANY, u"複製数", wx.DefaultPosition, wx.DefaultSize, 0)
        self.setting_sizer.Add(self.copy_cnt_txt, 0, wx.ALL, 5)

        self.copy_cnt_ctrl = wx.SpinCtrl(self, id=wx.ID_ANY, size=wx.Size(60, -1), value="2", min=1, max=99999999, initial=2)
        self.copy_cnt_ctrl.SetToolTip(u"複製する数を指定して下さい。")
        self.copy_cnt_ctrl.Bind(wx.EVT_SPINCTRL, self.on_change_file)
        self.setting_sizer.Add(self.copy_cnt_ctrl, 0, wx.ALL, 5)

        # やる気係数
        self.motivation_flg_ctrl = wx.CheckBox(self, wx.ID_ANY, u"やる気係数を適用する", wx.DefaultPosition, wx.DefaultSize, 0)
        self.motivation_flg_ctrl.SetToolTip(u"チェックを入れると、やる気係数もランダムに発生します。\nやる気係数は値が大きいほどモーションの振り幅が大きくなります。\n値が小さいほどモーションの振り幅が小さくなります。")
        self.setting_sizer.Add(self.motivation_flg_ctrl, 0, wx.ALL, 5)

        # 指ゆらぎ
        self.finger_noise_flg_ctrl = wx.CheckBox(self, wx.ID_ANY, u"指にもゆらぎを適用する", wx.DefaultPosition, wx.DefaultSize, 0)
        self.finger_noise_flg_ctrl.SetToolTip(u"チェックを入れると、「指」をボーン名に含むボーンも揺らがせます。")
        self.setting_sizer.Add(self.finger_noise_flg_ctrl, 0, wx.ALL, 5)

        self.sizer.Add(self.setting_sizer, 0, wx.EXPAND | wx.ALL, 5)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # 実行ボタン
        self.noise_btn_ctrl = wx.Button(self, wx.ID_ANY, u"ゆらぎ複製", wx.DefaultPosition, wx.Size(200, 50), 0)
        self.noise_btn_ctrl.SetToolTip(u"ゆらぎを付与したモーションを複製します")
        self.noise_btn_ctrl.Bind(wx.EVT_LEFT_DOWN, self.on_convert_noise)
        self.noise_btn_ctrl.Bind(wx.EVT_LEFT_DCLICK, self.on_doubleclick)
        btn_sizer.Add(self.noise_btn_ctrl, 0, wx.ALL, 5)

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
        self.frame.Bind(EVT_SMOOTH_THREAD, self.on_convert_noise_result)

    def on_wheel_spin_ctrl(self, event: wx.Event, inc=1):
        # self.frame.on_wheel_spin_ctrl(event, inc)
        self.set_output_vmd_path(event)

    # ファイル変更時の処理
    def on_change_file(self, event: wx.Event):
        self.set_output_vmd_path(event, is_force=True)
    
    def set_output_vmd_path(self, event, is_force=False):
        output_noise_vmd_path = MFileUtils.get_output_noise_vmd_path(
            self.noise_vmd_file_ctrl.file_ctrl.GetPath(),
            self.output_noise_vmd_file_ctrl.file_ctrl.GetPath(),
            self.noise_size_ctrl.GetValue(), is_force)

        self.output_noise_vmd_file_ctrl.file_ctrl.SetPath(output_noise_vmd_path)

        if len(output_noise_vmd_path) >= 255 and os.name == "nt":
            logger.error("生成予定のファイルパスがWindowsの制限を超えています。\n生成予定パス: {0}".format(output_noise_vmd_path), decoration=MLogger.DECORATION_BOX)
        
    # フォーム無効化
    def disable(self):
        self.noise_vmd_file_ctrl.disable()
        self.output_noise_vmd_file_ctrl.disable()
        self.noise_btn_ctrl.Disable()

    # フォーム無効化
    def enable(self):
        self.noise_vmd_file_ctrl.enable()
        self.output_noise_vmd_file_ctrl.enable()
        self.noise_btn_ctrl.Enable()

    def on_doubleclick(self, event: wx.Event):
        self.timer.Stop()
        logger.warning("ダブルクリックされました。", decoration=MLogger.DECORATION_BOX)
        event.Skip(False)
        return False
    
    # 多段分割変換
    def on_convert_noise(self, event: wx.Event):
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

        self.noise_vmd_file_ctrl.save()

        # JSON出力
        MFileUtils.save_history(self.frame.mydir_path, self.frame.file_hitories)

        self.elapsed_time = 0
        result = True
        result = self.noise_vmd_file_ctrl.is_valid() and result

        if not result:
            # 終了音
            self.frame.sound_finish()
            # タブ移動可
            self.release_tab()
            # フォーム有効化
            self.enable()

            return result

        # ゆらぎ複製変換開始
        if self.noise_btn_ctrl.GetLabel() == "ゆらぎ複製停止" and self.convert_noise_worker:
            # フォーム無効化
            self.disable()
            # 停止状態でボタン押下時、停止
            self.convert_noise_worker.stop()

            # タブ移動可
            self.frame.release_tab()
            # フォーム有効化
            self.frame.enable()
            # ワーカー終了
            self.convert_noise_worker = None
            # プログレス非表示
            self.gauge_ctrl.SetValue(0)

            logger.warning("ゆらぎ複製を中断します。", decoration=MLogger.DECORATION_BOX)
            self.noise_btn_ctrl.SetLabel("ゆらぎ複製")
            
            event.Skip(False)
        elif not self.convert_noise_worker:
            # フォーム無効化
            self.disable()
            # タブ固定
            self.fix_tab()
            # コンソールクリア
            self.console_ctrl.Clear()
            # ラベル変更
            self.noise_btn_ctrl.SetLabel("ゆらぎ複製停止")
            self.noise_btn_ctrl.Enable()

            self.convert_noise_worker = NoiseWorkerThread(self.frame, NoiseThreadEvent, self.frame.is_saving, self.frame.is_out_log)
            self.convert_noise_worker.start()
            
            event.Skip()
        else:
            logger.error("まだ処理が実行中です。終了してから再度実行してください。", decoration=MLogger.DECORATION_BOX)
            event.Skip(False)

        return result

    # 多段分割変換完了処理
    def on_convert_noise_result(self, event: wx.Event):
        self.elapsed_time = event.elapsed_time
        logger.info("\n処理時間: %s", self.show_worked_time())
        self.noise_btn_ctrl.SetLabel("ゆらぎ複製")

        # 終了音
        self.frame.sound_finish()

        # タブ移動可
        self.release_tab()
        # フォーム有効化
        self.enable()
        # ワーカー終了
        self.convert_noise_worker = None
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
