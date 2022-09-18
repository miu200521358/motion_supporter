# -*- coding: utf-8 -*-
#
import os
import wx
import wx.lib.newevent
import csv
import traceback
from datetime import datetime

from utils import MFileUtils
from utils.MLogger import MLogger  # noqa

logger = MLogger(__name__)


class TargetMorphConditionDialog(wx.Dialog):
    def __init__(self, frame: wx.Frame, panel: wx.Panel):
        super().__init__(
            frame,
            id=wx.ID_ANY,
            title="モーフ条件調整指定",
            pos=(-1, -1),
            size=(700, 450),
            style=wx.DEFAULT_DIALOG_STYLE,
            name="TargetMorphConditionDialog",
        )

        self.frame = frame
        self.panel = panel
        self.vmd_digest = (
            0
            if not self.panel.morph_condition_vmd_file_ctrl.data
            else self.panel.morph_condition_vmd_file_ctrl.data.digest
        )
        self.org_morph_ctrls = []  # 条件調整元データ（条件を割り当てる側）
        self.org_morph_name_suffix_ctrls = []  # が
        self.condition_ctrls = []  # 条件
        self.condition_value_ctrls = []  # 条件値
        self.condition_suffix_ctrls = []  # だったら
        self.ratio_ctrls = []  # 適用割合
        self.ratio_suffix_ctrls = []  # 倍にする
        self.org_morph_names = [""]  # 選択肢文言
        self.condition_choices = ["", "より大きい(＞)", "以上(≧)", "等しい(＝)", "以下(≦)", "より小さい(＜)"]  # 選択コントロール

        self.sizer = wx.BoxSizer(wx.VERTICAL)

        # 説明文
        self.description_txt = wx.StaticText(
            self,
            wx.ID_ANY,
            "条件調整したいモーフ名を選択・入力してください。プルダウン欄にモーフ名の一部を入力して絞り込みをかける事ができます。",
            wx.DefaultPosition,
            wx.DefaultSize,
            0,
        )
        self.sizer.Add(self.description_txt, 0, wx.ALL, 5)

        # ボタン
        self.btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.ok_btn = wx.Button(self, wx.ID_OK, "OK")
        self.btn_sizer.Add(self.ok_btn, 0, wx.ALL, 5)

        self.calcel_btn = wx.Button(self, wx.ID_CANCEL, "キャンセル")
        self.btn_sizer.Add(self.calcel_btn, 0, wx.ALL, 5)

        # インポートボタン
        self.import_btn_ctrl = wx.Button(self, wx.ID_ANY, "インポート ...", wx.DefaultPosition, wx.DefaultSize, 0)
        self.import_btn_ctrl.SetToolTip("調整モーフデータをCSVファイルから読み込みます。\nファイル選択ダイアログが開きます。")
        self.import_btn_ctrl.Bind(wx.EVT_BUTTON, self.on_import)
        self.btn_sizer.Add(self.import_btn_ctrl, 0, wx.ALL, 5)

        # エクスポートボタン
        self.export_btn_ctrl = wx.Button(self, wx.ID_ANY, "エクスポート ...", wx.DefaultPosition, wx.DefaultSize, 0)
        self.export_btn_ctrl.SetToolTip("調整モーフデータをCSVファイルに出力します。\n調整対象VMDと同じフォルダに出力します。")
        self.export_btn_ctrl.Bind(wx.EVT_BUTTON, self.on_export)
        self.btn_sizer.Add(self.export_btn_ctrl, 0, wx.ALL, 5)

        # 行追加ボタン
        self.add_line_btn_ctrl = wx.Button(self, wx.ID_ANY, "行追加", wx.DefaultPosition, wx.DefaultSize, 0)
        self.add_line_btn_ctrl.SetToolTip("調整モーフ{0}の組み合わせ行を追加します。\n上限はありません。".format(type))
        self.add_line_btn_ctrl.Bind(wx.EVT_BUTTON, self.on_add_line)
        self.btn_sizer.Add(self.add_line_btn_ctrl, 0, wx.ALL, 5)

        self.sizer.Add(self.btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 5)

        self.static_line01 = wx.StaticLine(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        self.sizer.Add(self.static_line01, 0, wx.EXPAND | wx.ALL, 5)

        self.window = wx.ScrolledWindow(
            self,
            wx.ID_ANY,
            wx.DefaultPosition,
            wx.DefaultSize,
            wx.FULL_REPAINT_ON_RESIZE | wx.HSCROLL | wx.ALWAYS_SHOW_SB,
        )
        self.window.SetScrollRate(5, 5)

        # セット用基本Sizer
        self.set_list_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # タイトル部分
        self.grid_sizer = wx.FlexGridSizer(0, 7, 0, 0)
        self.grid_sizer.SetFlexibleDirection(wx.BOTH)
        self.grid_sizer.SetNonFlexibleGrowMode(wx.FLEX_GROWMODE_SPECIFIED)

        self.org_morph_name_txt = wx.StaticText(self.window, wx.ID_ANY, "モーフ名", wx.DefaultPosition, wx.DefaultSize, 0)
        self.org_morph_name_txt.Wrap(-1)
        self.grid_sizer.Add(self.org_morph_name_txt, 0, wx.ALL, 5)

        self.org_morph_name_suffix_txt = wx.StaticText(
            self.window, wx.ID_ANY, " が ", wx.DefaultPosition, wx.DefaultSize, 0
        )
        self.org_morph_name_suffix_txt.Wrap(-1)
        self.grid_sizer.Add(self.org_morph_name_suffix_txt, 0, wx.ALL, 5)

        self.condition_txt = wx.StaticText(self.window, wx.ID_ANY, "条件値", wx.DefaultPosition, wx.DefaultSize, 0)
        self.condition_txt.Wrap(-1)
        self.grid_sizer.Add(self.condition_txt, 0, wx.ALL, 5)

        self.condition_txt = wx.StaticText(self.window, wx.ID_ANY, "条件", wx.DefaultPosition, wx.DefaultSize, 0)
        self.condition_txt.Wrap(-1)
        self.grid_sizer.Add(self.condition_txt, 0, wx.ALL, 5)

        self.condition_suffix_txt = wx.StaticText(
            self.window, wx.ID_ANY, " だったら ", wx.DefaultPosition, wx.DefaultSize, 0
        )
        self.condition_suffix_txt.Wrap(-1)
        self.grid_sizer.Add(self.condition_suffix_txt, 0, wx.ALL, 5)

        self.condition_value_txt = wx.StaticText(
            self.window, wx.ID_ANY, "補正値（割合）", wx.DefaultPosition, wx.DefaultSize, 0
        )
        self.condition_value_txt.Wrap(-1)
        self.grid_sizer.Add(self.condition_value_txt, 0, wx.ALL, 5)

        self.ratio_suffix_txt = wx.StaticText(self.window, wx.ID_ANY, " 倍にする", wx.DefaultPosition, wx.DefaultSize, 0)
        self.ratio_suffix_txt.Wrap(-1)
        self.grid_sizer.Add(self.ratio_suffix_txt, 0, wx.ALL, 5)

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
        if self.panel.morph_condition_vmd_file_ctrl.data:
            self.org_morph_names = [""]

            for morph_name in self.panel.morph_condition_vmd_file_ctrl.data.morphs.keys():
                # 処理対象調整モーフ：有効な調整モーフ
                self.org_morph_names.append(morph_name)

            # 一行追加
            self.add_line()

    def on_import(self, event: wx.Event):
        with wx.FileDialog(
            self.frame,
            "調整モーフ組み合わせCSVを読み込む",
            wildcard="CSVファイル (*.csv)|*.csv|すべてのファイル (*.*)|*.*",
            defaultDir=os.path.dirname(self.panel.morph_condition_vmd_file_ctrl.path()),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as fileDialog:

            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return  # the user changed their mind

            # Proceed loading the file chosen by the user
            target_morph_path = fileDialog.GetPath()
            try:
                with open(target_morph_path, "r") as f:
                    cr = csv.reader(f, delimiter=",", quotechar='"')
                    morph_lines = [row for row in cr]

                    if not morph_lines:
                        return

                    for midx, morph_set in enumerate(morph_lines):
                        org_morph_name, condition_value, condition_name, ratio = morph_set
                        self.org_morph_ctrls[-1].SetValue(org_morph_name)
                        self.condition_value_ctrls[-1].SetValue(condition_value)
                        self.condition_ctrls[-1].SetValue(condition_name)
                        self.ratio_ctrls[-1].SetValue(ratio)

                        self.add_line(midx + 1)

                    if not morph_lines[0]:
                        raise Exception("処理対象調整モーフ名指定なし")

            except Exception:
                dialog = wx.MessageDialog(
                    self.frame,
                    "CSVファイルが読み込めませんでした '%s'\n\n%s." % (target_morph_path, traceback.format_exc()),
                    style=wx.OK,
                )
                dialog.ShowModal()
                dialog.Destroy()

    def on_export(self, event: wx.Event):
        export_morphs = []

        for m in self.get_morph_list():
            export_morphs.append([m[0], m[1], m[2], m[3]])

        output_morph_path = os.path.join(
            os.path.dirname(self.panel.morph_condition_vmd_file_ctrl.path()),
            f"{os.path.basename(self.panel.morph_condition_vmd_file_ctrl.path()).split('.')[-1]}_morph_condition_{datetime.now():%Y%m%d_%H%M%S}.csv",
        )

        try:
            with open(output_morph_path, encoding="cp932", mode="w", newline="") as f:
                cw = csv.writer(f, delimiter=",", quotechar='"', quoting=csv.QUOTE_ALL)
                cw.writerows(export_morphs)

            logger.info("出力成功: %s" % output_morph_path)

            dialog = wx.MessageDialog(self.frame, "モーフ条件調整データのエクスポートに成功しました \n'%s'" % (output_morph_path), style=wx.OK)
            dialog.ShowModal()
            dialog.Destroy()

        except Exception:
            dialog = wx.MessageDialog(
                self.frame,
                "モーフ条件調整データのエクスポートに失敗しました \n'%s'\n\n%s." % (output_morph_path, traceback.format_exc()),
                style=wx.OK,
            )
            dialog.ShowModal()
            dialog.Destroy()

    def on_add_line(self, event: wx.Event):
        # 行追加
        self.add_line(len(self.org_morph_ctrls) - 1)

    def get_morph_list(self):
        morph_list = []

        for midx, (org_morph_ctrl, condition_ctrl, condition_value_ctrl, ratio_ctrl) in enumerate(
            zip(
                self.org_morph_ctrls,
                self.condition_ctrls,
                self.condition_value_ctrls,
                self.ratio_ctrls,
            )
        ):
            if org_morph_ctrl.GetValue() and condition_ctrl.GetValue():

                org_morph_name = org_morph_ctrl.GetValue()
                condition_name = condition_ctrl.GetValue()
                condition_value = condition_value_ctrl.GetValue()
                ratio = ratio_ctrl.GetValue()

                if (org_morph_name, condition_value, condition_name, ratio) not in morph_list:
                    # 調整モーフペアがまだ登録されてないければ登録
                    morph_list.append((org_morph_name, condition_value, condition_name, ratio))

        return morph_list

    def add_line(self, midx=0):
        # 置換前調整モーフ
        self.org_morph_ctrls.append(
            wx.ComboBox(
                self.window, id=wx.ID_ANY, choices=self.org_morph_names, style=wx.CB_DROPDOWN | wx.TE_PROCESS_ENTER
            )
        )
        self.org_morph_ctrls[-1].Bind(wx.EVT_COMBOBOX, lambda event: self.on_change_choice(event, midx))
        self.org_morph_ctrls[-1].Bind(wx.EVT_TEXT_ENTER, lambda event: self.on_enter_choice(event, midx))
        self.grid_sizer.Add(self.org_morph_ctrls[-1], 0, wx.ALL, 5)

        self.org_morph_name_suffix_ctrls.append(
            wx.StaticText(self.window, wx.ID_ANY, " が ", wx.DefaultPosition, wx.DefaultSize, 0)
        )
        self.org_morph_name_suffix_ctrls[-1].Wrap(-1)
        self.grid_sizer.Add(self.org_morph_name_suffix_ctrls[-1], 0, wx.CENTER | wx.ALL, 5)

        # 条件値（実値）
        self.condition_value_ctrls.append(
            wx.SpinCtrlDouble(self.window, id=wx.ID_ANY, size=wx.Size(80, -1), min=-10, max=10, initial=1.0, inc=0.05)
        )
        self.condition_value_ctrls[-1].Bind(
            wx.EVT_MOUSEWHEEL, lambda event: self.frame.on_wheel_spin_ctrl(event, 0.05)
        )
        self.grid_sizer.Add(self.condition_value_ctrls[-1], 0, wx.ALL, 5)

        # 条件
        self.condition_ctrls.append(
            wx.ComboBox(
                self.window, id=wx.ID_ANY, choices=self.condition_choices, style=wx.CB_DROPDOWN | wx.TE_PROCESS_ENTER
            )
        )
        self.condition_ctrls[-1].Bind(wx.EVT_TEXT_ENTER, lambda event: self.on_enter_choice(event, midx))
        self.grid_sizer.Add(self.condition_ctrls[-1], 0, wx.ALL, 5)

        self.condition_suffix_ctrls.append(
            wx.StaticText(self.window, wx.ID_ANY, " だったら ", wx.DefaultPosition, wx.DefaultSize, 0)
        )
        self.condition_suffix_ctrls[-1].Wrap(-1)
        self.grid_sizer.Add(self.condition_suffix_ctrls[-1], 0, wx.CENTER | wx.ALL, 5)

        # 補正値（割合）
        self.ratio_ctrls.append(
            wx.SpinCtrlDouble(self.window, id=wx.ID_ANY, size=wx.Size(80, -1), min=-10, max=10, initial=1.0, inc=0.05)
        )
        self.ratio_ctrls[-1].Bind(wx.EVT_MOUSEWHEEL, lambda event: self.frame.on_wheel_spin_ctrl(event, 0.05))
        self.grid_sizer.Add(self.ratio_ctrls[-1], 0, wx.ALL, 5)

        self.ratio_suffix_ctrls.append(
            wx.StaticText(self.window, wx.ID_ANY, " 倍にする", wx.DefaultPosition, wx.DefaultSize, 0)
        )
        self.ratio_suffix_ctrls[-1].Wrap(-1)
        self.grid_sizer.Add(self.ratio_suffix_ctrls[-1], 0, wx.CENTER | wx.ALL, 5)

        # スクロールバーの表示のためにサイズ調整
        self.set_list_sizer.Layout()
        self.set_list_sizer.FitInside(self.window)

    # 調整モーフが設定されているか
    def is_set_morph(self):

        for (org_morph_ctrl, condition_ctrl) in zip(
            self.org_morph_ctrls,
            self.condition_ctrls,
        ):
            if org_morph_ctrl.GetSelection() > 0 and condition_ctrl.GetSelection() > 0:
                # なんか設定されていたらOK
                return True

        # どれも設定されていなければFalse
        return False

    # 文字列が入力された際、一致しているのがあれば適用
    def on_enter_choice(self, event: wx.Event, midx: int):
        idx = event.GetEventObject().FindString(event.GetEventObject().GetValue())
        if idx >= 0:
            event.GetEventObject().SetSelection(idx)
            self.on_change_choice(event, midx)

    # 選択肢が変更された場合
    def on_change_choice(self, event: wx.Event, midx: int):
        text = event.GetEventObject().GetStringSelection()

        # 同じ選択肢を初期設定
        if text:
            self.org_morph_ctrls[midx].ChangeValue(text)
            cidx = self.org_morph_ctrls[midx].FindString(text)
            if cidx >= 0:
                self.org_morph_ctrls[midx].SetSelection(cidx)

        else:
            # 空にした場合は空に
            self.org_morph_ctrls[midx].ChangeValue("")
            self.org_morph_ctrls[midx].SetSelection(-1)
            self.condition_value_ctrls[midx].ChangeValue(1.0)
            self.condition_ctrls[midx].ChangeValue("")
            self.condition_ctrls[midx].SetSelection(-1)
            self.ratio_ctrls[midx].ChangeValue(1.0)

        # 最後である場合、行追加
        if midx == len(self.org_morph_ctrls) - 1 and self.org_morph_ctrls[midx].GetSelection() > 0:
            self.add_line(midx + 1)
